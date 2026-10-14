# Agent Notifier

Agents write a notification (subject + HTML fragment) to a local SQLite DB. A watcher
pops a macOS notification, and clicking it opens a local viewer that renders the
fragment inside an app-controlled template. The viewer also has an inbox with read and
unread state. Agents learn the format from a Claude Code skill.

**Status (2026-10-14):** installed and working. LaunchAgents are loaded, the skill is linked, and test
popup #1 was delivered.

Gotcha: brew's terminal-notifier is ad-hoc signed. It didn't show up in System Settings >
Notifications, and every popup failed ("Notifications are not allowed for this application"),
until the app was registered with `lsregister -f <terminal-notifier.app>` and launched once
via `open`. `install.sh` now does both. It finds the bundle from the wrapper script, then
runs a test notification and warns (and opens Settings) if macOS still refuses. Re-run
`install.sh` after `brew upgrade terminal-notifier`, because the bundle path changes.

## Layout
- `notifier/config.py`: paths and constants. DB is `~/.notifier/notifications.db`. Env overrides: `NOTIFIER_HOME`, `NOTIFIER_DB`, `NOTIFIER_PORT` (default 8765), `NOTIFIER_TN` (terminal-notifier path), `NOTIFIER_POLL_SECONDS`.
- `notifier/db.py`: schema plus all queries. Uses WAL and busy_timeout, and the schema is created on every connect.
  - Table `notifications`: `id, created_at, subject, body_html, source, notified_at, read_at`.
- `notifier/sanitize.py`: turns agent HTML into a body fragment.
  - Strips doctype/html/head/body/style/link/meta/iframe/script, `on*` attributes, and `javascript:` URLs.
  - Keeps `<script type="application/json" data-chart>` and validates its JSON. Invalid JSON raises `ChartError`, so `send` exits non-zero.
- `notifier/watcher.py`: polls every 2 s and shells out to `terminal-notifier -open <url>`. It sets `notified_at` per row.
  - More than 5 pending rows in one poll produce a single summary popup that links to the unread inbox.
- `notifier/web.py`: Flask app on 127.0.0.1 only.
  - Routes: `/` inbox (All/Unread tabs, paging), `/n/<id>` (auto-marks read), POST `/n/<id>/read`, `/n/<id>/unread`, `/read-all`, and GET `/api/recent`.
  - A strict CSP means only the app's own JS runs: `static/charts.js` plus the vendored Chart.js 4.4.1 in `static/vendor/`.
- `notifier/cli.py`: `notifier init|send|list|serve|watch`.
- `notifier/templates/`, `notifier/static/app.css`: look and feel. Light and dark come from CSS tokens, and the CSS defines the agent component classes (`callout`, `metrics`/`metric`, `badge`, `grid-2`, `figure`).
- `launchd/*.plist`: templates with `__VENV__` and `__LOGDIR__` placeholders that `scripts/install.sh` fills in.
- `scripts/install.sh` / `uninstall.sh`: install creates the venv, runs `brew install terminal-notifier`, inits the DB, bootstraps the LaunchAgents, and symlinks `skill/notify` to `~/.claude/skills/notify`.
- `skill/notify/SKILL.md`: the agent-facing format guide. If you change the CSS classes or chart conventions, update this file to match.

## Dev
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q                      # 12 tests: sanitizer, db, watcher, web
NOTIFIER_HOME=/tmp/nh NOTIFIER_PORT=8799 .venv/bin/notifier serve   # throwaway DB
```
`.venv` exists locally and is gitignored.

## Where it stopped
Done and verified:
- All unit tests pass.
- Sample notifications sent to a throwaway DB render correctly: chart, metrics, table, and callout, checked in dark mode with a headless Chrome screenshot.
- `<script>` and `onclick` are stripped.

Not done yet:
1. ~~Visual check of the inbox and SVG/doughnut pages~~ (done, looks good).
2. ~~Run `scripts/install.sh`~~ (done 2026-10-14). If a popup fails (terminal-notifier exits non-zero), the watcher leaves the row pending and retries every `RETRY_SECONDS`. Check `~/.notifier/logs/watcher.log`.
3. ~~End-to-end check~~ (done 2026-10-14: popup → click → page opens; reinstall/restart caused no duplicate popups).
4. Have an agent in another project use the `notify` skill.
5. ~~`git init`~~ (done).

## Relation to Claude scheduled tasks
Scheduled tasks decide **when** an agent runs. This project is about **how results reach the user**: a desktop popup plus a styled, persistent report inbox. The two can work together, with a scheduled task's prompt ending in "send the result with the notify skill". That only works when the task runs on this Mac (local/desktop scheduled tasks). Cloud routines can't reach `~/.notifier` or 127.0.0.1. If a scheduled task's built-in output and notifications are enough, this project can be shelved.
