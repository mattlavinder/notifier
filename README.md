# Agent Notifier

Desktop notifications for AI agents on macOS.

An agent (Claude Code or any script) sends a **subject** and an **HTML fragment**. You get
a macOS notification, and clicking it opens a clean, styled report page in your browser.
Pages can include tables, charts, SVG diagrams, and images. A local inbox keeps your
recent notifications with read/unread state.

```
agent ──notifier send──▶ SQLite (~/.notifier/notifications.db)
                              │
            watcher (launchd) ┤──▶ macOS notification ──click──▶ http://127.0.0.1:8765/n/<id>
                              │
        web viewer (launchd) ─┘──▶ inbox at http://127.0.0.1:8765/
```

## How it works

- **Database.** Each notification is one row in a local SQLite file: id, timestamp, subject, HTML body, an optional source name, and when it was popped up and read.
- **Watcher.** Checks for new rows every 2 seconds and shows a notification through [terminal-notifier](https://github.com/julienXX/terminal-notifier). If more than 5 arrive at once, you get a single summary popup instead of a burst. If macOS refuses a popup, the notification stays queued and is retried.
- **Web viewer.** A small Flask app that only listens on `127.0.0.1`.
  - It wraps each fragment in the app's own template, so every page looks the same no matter which agent wrote it. Light and dark mode follow your system setting.
  - A strict Content-Security-Policy means agent-written JavaScript never runs. Charts are drawn by the app's own bundled copy of Chart.js.
- **`notify` skill.** Tells Claude Code agents when to send a notification, how to format the HTML, and how to add graphics.

## Requirements

- macOS (Apple silicon or Intel)
- Python 3.11+
- [Homebrew](https://brew.sh), which the installer uses to get `terminal-notifier`

## Install

```bash
git clone git@github.com:mattlavinder/notifier.git ~/Work/source/notifier
cd ~/Work/source/notifier
scripts/install.sh
```

The installer is safe to re-run. It:

1. Creates `.venv/` and installs the package (providing the `notifier` command).
2. Installs `terminal-notifier` if it's missing, registers it with macOS, and sends a test notification to confirm popups work.
3. Creates the database at `~/.notifier/notifications.db`.
4. Installs two LaunchAgents, `com.notifier.watcher` and `com.notifier.web`. They start when you log in and restart if they crash.
5. Links the skill into `~/.claude/skills/notify` so Claude Code agents can use it.

> The skill and docs assume the repo lives at `~/Work/source/notifier`. If you clone it
> somewhere else, update the command path in `skill/notify/SKILL.md`.

Check it works:

```bash
echo '<p>Hello from the notifier.</p>' | .venv/bin/notifier send -s "Notifier installed" --source setup
```

A popup should appear within a couple of seconds. Click it to open the page.

**Tip:** in System Settings → Notifications → terminal-notifier, set the style to
**Alerts** so popups stay on screen until you dismiss them.

## Usage

### From Claude Code

Ask an agent to notify you, for example "when you're done, send me a notification with a
summary". The `notify` skill tells it the command and how to format the HTML. To have
scheduled or long-running tasks report back, end the prompt with "send the result with
the notify skill". This only works for tasks running on this Mac; cloud-hosted agents
can't reach the local database.

### From the command line

```bash
notifier send --subject "Nightly import finished" --source etl --file report.html
notifier send -s "Quick note" -b "<p>Inline HTML works too.</p>"
cat report.html | notifier send -s "From stdin"

notifier list            # recent notifications; * marks unread
notifier list --unread -n 50
```

(`notifier` is `.venv/bin/notifier`. Add the venv's `bin` to your PATH or use the full path.)

`send` prints the new notification's URL. A non-zero exit means nothing was saved, for
example when the subject is empty, the body is over 10 MB, or a chart block contains
invalid JSON.

### Writing the HTML

Send a **body fragment only**: no `<html>`, `<head>`, `<body>`, `<style>`, or `<script>`.
The app strips them and provides the page shell and styling. Plain HTML (headings,
lists, tables, code blocks, `<details>`) is already styled, and a few component classes
are available:

```html
<div class="callout success"><p><strong>Done.</strong> All checks passed.</p></div>

<div class="metrics">
  <div class="metric"><div class="label">Rows</div><div class="value">12,480</div><div class="delta up">+4%</div></div>
</div>

<script type="application/json" data-chart data-height="260" data-caption="Rows per day">
{"type":"bar","data":{"labels":["Mon","Tue","Wed"],"datasets":[{"label":"Rows","data":[4100,3900,4480]}]}}
</script>
```

For graphics, use chart blocks (Chart.js v4 config as strict JSON), inline `<svg>`, or
images as `data:` URIs. External URLs are blocked. The full formatting guide, including
every component class and a complete example, is in
[`skill/notify/SKILL.md`](skill/notify/SKILL.md).

### The inbox

Open **http://127.0.0.1:8765/** to see recent notifications:

- **All** and **Unread** tabs, with the unread count in the header.
- Opening a notification marks it read. You can mark any one read or unread from the inbox or the page.
- **Mark all read** clears everything.
- `GET /api/recent?limit=20&filter=unread` returns the same data as JSON.

## Managing the services

```bash
launchctl list | grep notifier                                     # are they running?
launchctl kickstart -k gui/$(id -u)/com.notifier.watcher           # restart the watcher
launchctl kickstart -k gui/$(id -u)/com.notifier.web               # restart the viewer
tail -f ~/.notifier/logs/watcher.log ~/.notifier/logs/web.log      # logs
```

Both services run only while you're logged in. Anything sent while you're logged out
pops up when you log back in. They also appear under System Settings → General →
Login Items & Extensions; turning them off there stops them from starting.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No popup, and `watcher.log` says `Notifications are not allowed for this application` | Re-run `scripts/install.sh`. It registers terminal-notifier with macOS, which makes it appear in System Settings → Notifications. If it's listed there, make sure **Allow Notifications** is on. Queued notifications are retried every 30 s. |
| Popups stopped after `brew upgrade` | The terminal-notifier app moved to a new versioned path. Re-run `scripts/install.sh`. |
| Clicking a popup shows "can't connect" | The web service isn't running. Check `launchctl list \| grep notifier` and `~/.notifier/logs/web.log`. |
| A chart shows "Chart could not be rendered" | The chart config is valid JSON but not a valid Chart.js config. Check the type and data shape. |
| Port 8765 is taken | Change the `PORT` default in `notifier/config.py` (the services don't read your shell environment), update the URL in `skill/notify/SKILL.md`, and re-run the installer. |

## Configuration

Environment variables, all optional:

| Variable | Default | Purpose |
|---|---|---|
| `NOTIFIER_HOME` | `~/.notifier` | Data and log directory |
| `NOTIFIER_DB` | `$NOTIFIER_HOME/notifications.db` | Database path |
| `NOTIFIER_PORT` | `8765` | Web viewer port for manual or dev runs (the viewer always binds to 127.0.0.1) |
| `NOTIFIER_POLL_SECONDS` | `2` | How often the watcher checks for new rows |
| `NOTIFIER_TN` | auto-detected | Path to `terminal-notifier` |

## Uninstall

```bash
scripts/uninstall.sh
```

This stops and removes both LaunchAgents and the skill link. Your notification history
in `~/.notifier` is kept; delete that folder to remove it too.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q

# Run against a throwaway database without touching the installed services
NOTIFIER_HOME=/tmp/nh NOTIFIER_PORT=8799 .venv/bin/notifier serve
```

| Path | What it is |
|---|---|
| `notifier/db.py` | Schema and queries |
| `notifier/sanitize.py` | Turns agent HTML into a safe body fragment |
| `notifier/watcher.py` | Poll loop and terminal-notifier calls |
| `notifier/web.py`, `templates/`, `static/` | Viewer, inbox, styles, chart rendering |
| `notifier/cli.py` | The `notifier` command |
| `launchd/`, `scripts/` | Service definitions, install and uninstall |
| `skill/notify/SKILL.md` | Agent-facing formatting guide; keep it in sync with the CSS classes |
