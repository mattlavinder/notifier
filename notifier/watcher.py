import logging
import os
import shutil
import subprocess
import time

from . import config, db

log = logging.getLogger("notifier.watcher")

TITLE = "Agent Notifier"
# launchd starts with a minimal PATH, so check the Homebrew locations too.
FALLBACK_PATHS = ["/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"]


def find_terminal_notifier() -> str | None:
    explicit = os.environ.get("NOTIFIER_TN")
    if explicit:
        return explicit
    found = shutil.which("terminal-notifier")
    if found:
        return found
    return next((p for p in FALLBACK_PATHS if os.access(p, os.X_OK)), None)


def popup(tn: str, message: str, url: str, subtitle: str | None = None, group: str | None = None) -> bool:
    """Show one notification. Returns False if macOS didn't accept it."""
    # terminal-notifier treats a leading "-" or "[" in the message as special; pad it.
    if message[:1] in "-[":
        message = " " + message
    cmd = [tn, "-title", TITLE, "-message", message, "-open", url, "-sound", "default"]
    if subtitle:
        cmd += ["-subtitle", subtitle]
    if group:
        cmd += ["-group", group]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("terminal-notifier failed: %s", exc)
        return False
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        log.warning("terminal-notifier exited %s: %s", result.returncode, detail)
        return False
    return True


def deliver(conn, tn: str, rows) -> bool:
    """Pop up pending rows. Returns False on failure; failed rows stay pending for a retry."""
    if len(rows) > config.BURST_THRESHOLD:
        latest = rows[-1]
        if not popup(
            tn,
            f"{len(rows)} new notifications. Latest: {latest['subject']}",
            f"{config.BASE_URL}/?filter=unread",
            group="notifier-summary",
        ):
            return False
        db.mark_notified(conn, [r["id"] for r in rows])
        log.info("summarized %d notifications", len(rows))
        return True
    for row in rows:
        if not popup(tn, row["subject"], config.notification_url(row["id"]), row["source"], f"notifier-{row['id']}"):
            return False
        # Mark each one right away so a crash mid-batch never repeats a popup.
        db.mark_notified(conn, [row["id"]])
        log.info("notified #%s %s", row["id"], row["subject"])
    return True


def run(once: bool = False):
    tn = find_terminal_notifier()
    if not tn:
        raise SystemExit("terminal-notifier not found. Install it with: brew install terminal-notifier")
    conn = db.connect()
    log.info("watching %s (terminal-notifier: %s)", config.DB_PATH, tn)
    while True:
        delay = config.POLL_SECONDS
        try:
            rows = db.pending(conn)
            if rows and not deliver(conn, tn, rows):
                # Usually notifications are switched off for terminal-notifier in
                # System Settings > Notifications. Keep the rows and retry slowly.
                delay = config.RETRY_SECONDS
                log.warning("%d notification(s) still pending; retrying in %ss", len(rows), delay)
        except Exception:
            log.exception("poll failed")
        if once:
            return
        time.sleep(delay)
