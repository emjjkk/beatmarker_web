(function () {
  const form = document.getElementById("upload-form");
  const submitBtn = document.getElementById("submit-btn");
  const jobsList = document.getElementById("jobs-list");
  const loudness = document.getElementById("loudness");
  const loudnessVal = document.getElementById("loudness-val");

  loudness.addEventListener("input", () => {
    loudnessVal.textContent = loudness.value;
  });

  function fmtTime(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleTimeString();
  }

  function jobCard(job) {
    const el = document.createElement("div");
    el.className = "job";
    el.dataset.id = job.id;

    const pct = job.progress || 0;
    const isDone = job.status === "done";
    const isError = job.status === "error";
    const isProcessing = job.status === "processing" || job.status === "queued";

    el.innerHTML = `
      <div class="job-head">
        <span class="job-name">${escapeHtml(job.filename)}</span>
        <span class="job-status ${job.status}">${job.status}</span>
      </div>
      <div class="job-meta">
        <span>${escapeHtml(job.message || "")}</span>
        ${job.marker_count ? `<span>◆ ${job.marker_count} markers</span>` : ""}
        <span>${fmtTime(job.created_at)}</span>
      </div>
      ${isProcessing ? `
        <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
      ` : ""}
      ${isDone ? `
        <div class="job-actions">
          <a class="btn btn-ghost" href="/api/jobs/${job.id}/download/txt">↓ beats.txt</a>
          <a class="btn btn-ghost" href="/api/jobs/${job.id}/download/edl">↓ markers.edl</a>
          <button class="btn btn-ghost" data-action="delete">✕ Delete</button>
        </div>
      ` : ""}
      ${isError ? `
        <div class="job-meta" style="color:var(--danger)">
          <span>${escapeHtml(job.error || "Unknown error")}</span>
        </div>
        <div class="job-actions">
          <button class="btn btn-ghost" data-action="delete">✕ Dismiss</button>
        </div>
      ` : ""}
    `;

    el.querySelectorAll("[data-action='delete']").forEach(b => {
      b.addEventListener("click", async () => {
        await fetch(`/api/jobs/${job.id}`, { method: "DELETE" });
        refresh();
      });
    });

    return el;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;",
      '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  async function refresh() {
    try {
      const res = await fetch("/api/jobs");
      const data = await res.json();
      const jobs = data.jobs || [];
      if (!jobs.length) {
        jobsList.innerHTML = '<p class="muted">No jobs yet.</p>';
        return;
      }
      jobsList.innerHTML = "";
      jobs.forEach(j => jobsList.appendChild(jobCard(j)));
    } catch (e) {
      console.error(e);
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = "Uploading…";

    const fd = new FormData();
    const fileInput = document.getElementById("file-input");
    if (!fileInput.files.length) {
      alert("Please choose a file.");
      submitBtn.disabled = false;
      submitBtn.textContent = "Process";
      return;
    }
    fd.append("file", fileInput.files[0]);
    fd.append("sensitivity", document.getElementById("sensitivity").value);
    fd.append("loudness", document.getElementById("loudness").value);
    fd.append("min_gap", document.getElementById("min_gap").value);
    fd.append("fps", document.getElementById("fps").value);
    fd.append("beats_only", document.getElementById("beats_only").checked);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      form.reset();
      loudnessVal.textContent = "70";
      await refresh();
    } catch (err) {
      alert(err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Process";
    }
  });

  // Initial load + poll while jobs are in progress
  refresh();
  setInterval(refresh, 2500);
})();