import os
from pathlib import Path

HOME_DIR = Path(os.environ.get("NOTIFIER_HOME", Path.home() / ".notifier"))
DB_PATH = Path(os.environ.get("NOTIFIER_DB", HOME_DIR / "notifications.db"))
LOG_DIR = HOME_DIR / "logs"

HOST = "127.0.0.1"
PORT = int(os.environ.get("NOTIFIER_PORT", "8765"))
BASE_URL = f"http://{HOST}:{PORT}"

MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_SUBJECT_CHARS = 200
POLL_SECONDS = float(os.environ.get("NOTIFIER_POLL_SECONDS", "2"))
# More than this many pending rows in one poll collapses into a single summary popup.
BURST_THRESHOLD = 5
# Wait between retries when a popup fails (e.g. notifications not allowed).
RETRY_SECONDS = 30
PAGE_SIZE = 50


def notification_url(notification_id: int) -> str:
    return f"{BASE_URL}/n/{notification_id}"
