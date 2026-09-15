import os
import uuid
from pathlib import Path
from flask import (
    Flask, render_template, request, jsonify,
    send_file, abort, url_for
)
from werkzeug.utils import secure_filename

from config import Config
from worker import enqueue, jobs, start_workers

app = Flask(__name__)
app.config.from_object(Config)

# Start background workers once
start_workers(num_workers=2)


def allowed_file(name):
    return (
        "." in name
        and name.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify(error="No file provided"), 400

    f = request.files["file"]
    if not f.filename or not allowed_file(f.filename):
        return jsonify(error="Unsupported file type"), 400

    # Build params from form
    try:
        params = {
            "fps": int(request.form.get("fps", 30)),
            "sensitivity": request.form.get("sensitivity", "low"),
            "loudness": int(request.form.get("loudness", 70)),
            "min_gap": float(request.form.get("min_gap", 0.5)),
            "beats_only": request.form.get("beats_only", "false").lower() == "true",
        }
    except (ValueError, TypeError) as e:
        return jsonify(error=f"Invalid parameters: {e}"), 400

    if params["sensitivity"] not in {"very_low", "low", "medium", "high"}:
        return jsonify(error="Invalid sensitivity"), 400
    if not (0 <= params["loudness"] <= 100):
        return jsonify(error="Loudness must be 0–100"), 400
    if params["min_gap"] < 0:
        return jsonify(error="min_gap must be >= 0"), 400

    # Save upload with a unique prefix
    safe_name = secure_filename(f.filename)
    uid = uuid.uuid4().hex[:8]
    stored_name = f"{uid}_{safe_name}"
    dest = Path(Config.UPLOAD_FOLDER) / stored_name
    f.save(dest)

    try:
        job = enqueue(stored_name, params)
    except RuntimeError:
        dest.unlink(missing_ok=True)
        return jsonify(error="Server busy, try again shortly"), 503

    return jsonify(job_id=job["id"])


@app.route("/api/jobs")
def list_jobs():
    return jsonify(jobs=jobs.all())


@app.route("/api/jobs/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify(error="not found"), 404
    return jsonify(job)


@app.route("/api/jobs/<job_id>/download/<kind>")
def download(job_id, kind):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        abort(404)
    if kind not in {"txt", "edl"}:
        abort(400)

    filename = job.get(f"output_{kind}")
    if not filename:
        abort(404)

    path = Path(Config.OUTPUT_FOLDER) / filename
    if not path.exists():
        abort(404)

    base = Path(job["filename"]).stem
    download_name = f"{base}_markers.{kind}"
    mimetype = "text/plain" if kind == "txt" else "text/plain"

    return send_file(path, as_attachment=True,
                     download_name=download_name,
                     mimetype=mimetype)


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    """Allow users to manually delete their files before TTL."""
    job = jobs.delete(job_id)
    if not job:
        return jsonify(error="not found"), 404
    for key in ("output_txt", "output_edl"):
        if job.get(key):
            (Path(Config.OUTPUT_FOLDER) / job[key]).unlink(missing_ok=True)
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)