import queue
import threading
import uuid
import json
import time
from pathlib import Path
from datetime import datetime

from config import Config

# Import your processing function
from process import process_audio_file  # see note below


class JobStore:
    """In-memory job state. Persisted to a JSON file per-job for durability."""

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def create(self, job_id, filename, params):
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "filename": filename,
                "params": params,
                "status": "queued",       # queued | processing | done | error
                "progress": 0,
                "message": "Queued",
                "created_at": time.time(),
                "finished_at": None,
                "output_txt": None,
                "output_edl": None,
                "marker_count": 0,
                "error": None,
            }
        return self._jobs[job_id]

    def update(self, job_id, **kwargs):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def all(self):
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    def delete(self, job_id):
        with self._lock:
            return self._jobs.pop(job_id, None)

    def prune_old(self, ttl_seconds):
        """Remove jobs older than TTL."""
        now = time.time()
        with self._lock:
            old_ids = [
                jid for jid, j in self._jobs.items()
                if j.get("finished_at") and (now - j["finished_at"]) > ttl_seconds
            ]
            for jid in old_ids:
                self._jobs.pop(jid, None)
        return old_ids


jobs = JobStore()
job_queue = queue.Queue(maxsize=Config.MAX_QUEUE_SIZE)


def _run_job(job):
    job_id = job["id"]
    jobs.update(job_id, status="processing", progress=5,
                message="Loading audio…")

    upload_path = Path(Config.UPLOAD_FOLDER) / job["filename"]
    out_txt = Path(Config.OUTPUT_FOLDER) / f"{job_id}.txt"
    out_edl = Path(Config.OUTPUT_FOLDER) / f"{job_id}.edl"

    try:
        def on_progress(pct, msg):
            jobs.update(job_id, progress=int(pct), message=msg)

        result = process_audio_file(
            audio_path=str(upload_path),
            out_txt=str(out_txt),
            out_edl=str(out_edl),
            fps=job["params"]["fps"],
            sensitivity=job["params"]["sensitivity"],
            loudness=job["params"]["loudness"],
            min_gap=job["params"]["min_gap"],
            beats_only=job["params"]["beats_only"],
            progress_callback=on_progress,
        )

        jobs.update(
            job_id,
            status="done",
            progress=100,
            message=f"{result['marker_count']} markers",
            output_txt=f"{job_id}.txt",
            output_edl=f"{job_id}.edl",
            marker_count=result["marker_count"],
            finished_at=time.time(),
        )
    except Exception as e:
        jobs.update(
            job_id,
            status="error",
            message="Processing failed",
            error=str(e),
            finished_at=time.time(),
        )
    finally:
        # Delete the original upload once processing is done
        try:
            upload_path.unlink(missing_ok=True)
        except Exception:
            pass


def _worker_loop():
    while True:
        job = job_queue.get()
        if job is None:
            break
        try:
            _run_job(job)
        finally:
            job_queue.task_done()


def _cleanup_loop():
    while True:
        time.sleep(Config.CLEANUP_INTERVAL)
        # Prune job records
        old_ids = jobs.prune_old(Config.FILE_TTL_SECONDS)
        # Delete files older than TTL
        now = time.time()
        for folder in (Config.UPLOAD_FOLDER, Config.OUTPUT_FOLDER):
            for f in Path(folder).iterdir():
                try:
                    if f.is_file() and (now - f.stat().st_mtime) > Config.FILE_TTL_SECONDS:
                        f.unlink()
                except Exception:
                    pass


def start_workers(num_workers=2):
    threads = []
    for _ in range(num_workers):
        t = threading.Thread(target=_worker_loop, daemon=True)
        t.start()
        threads.append(t)
    cleanup = threading.Thread(target=_cleanup_loop, daemon=True)
    cleanup.start()
    return threads


def enqueue(filename, params):
    job_id = uuid.uuid4().hex[:12]
    job = jobs.create(job_id, filename, params)
    try:
        job_queue.put_nowait(job)
    except queue.Full:
        jobs.update(job_id, status="error",
                    message="Queue full — try again later",
                    finished_at=time.time())
        raise RuntimeError("queue_full")
    return job