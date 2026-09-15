import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    OUTPUT_FOLDER = BASE_DIR / "outputs"
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB
    ALLOWED_EXTENSIONS = {"wav", "mp3", "flac", "ogg", "m4a", "aiff", "aif"}
    FILE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
    CLEANUP_INTERVAL = 15 * 60      # run cleanup every 15 min
    MAX_QUEUE_SIZE = 50             # refuse new jobs past this

Config.UPLOAD_FOLDER.mkdir(exist_ok=True)
Config.OUTPUT_FOLDER.mkdir(exist_ok=True)