---
name: notify
description: Send the user a macOS desktop notification that links to a rich HTML report page (text, tables, charts, SVG, images). Use when finishing a long-running or background task, when results are ready for the user to review, when the user asks to be notified/pinged/alerted, or when a summary would read better as a formatted page than terminal output.
---

# Sending a notification

Notifications go into a local SQLite inbox. A background service pops up a macOS
notification with the **subject**. Clicking it opens a styled page at
`http://127.0.0.1:8765/n/<id>` that renders your **HTML fragment**. The user can also
browse recent notifications and mark them read or unread at `http://127.0.0.1:8765/`.

## Command

Always use this absolute path, since it may not be on PATH:

```bash
cat > /tmp/notify-$$.html <<'HTML'
<p>Your fragment here.</p>
HTML
~/Work/source/notifier/.venv/bin/notifier send \
  --subject "Nightly import finished: 3 warnings" \
  --source "my-project" \
  --file /tmp/notify-$$.html
```

- `--subject` (required): the popup text and page title. Keep it under about 80 characters and lead with the outcome ("Build failed on main", "Report ready: Q3 churn").
- `--source` (optional): a short name for the project or agent, shown as a badge.
- `--file PATH`, `--body "<p>…</p>"`, or HTML on stdin. Prefer `--file` with a quoted heredoc (`<<'HTML'`) so the shell doesn't touch quotes or `$`.
- On success it prints `sent #<id>: <url>`. A non-zero exit means the notification was **not** saved. Read the error, fix it, and resend.

## HTML rules

Write a **body fragment only**. The viewer provides the page shell, fonts, colors,
light/dark mode, and the title header.

- Do **not** include `<!doctype>`, `<html>`, `<head>`, `<body>`, `<style>`, `<link>`, or `<script>` (the one exception is chart blocks, below). These are stripped.
- Do **not** repeat the subject as an `<h1>`, because the page already shows it. Start with a summary paragraph or callout, and use `<h2>`/`<h3>` for sections.
- No inline JavaScript or `on*=` handlers. They are stripped, and the page's CSP blocks them anyway.
- External URLs for images, scripts, or fonts are blocked. Embed images as `data:` URIs.
- Avoid inline `style=""` except for small one-off tweaks. Use the classes below so every page looks consistent.
- Standard elements are already styled: `p`, `ul/ol`, `table` (`th`/`td`, add `class="num"` to right-align numbers), `pre><code`, `code`, `blockquote`, `details/summary`, `hr`, and `a`.
- The size limit is 10 MB, but keep embedded images reasonable (under about 1 MB each).

### Component classes

| Class | Use |
|---|---|
| `<div class="callout">` plus `info` / `success` / `warn` / `error` | A highlighted box for the headline result, a warning, or an error |
| `<div class="metrics">` containing `<div class="metric"><div class="label">…</div><div class="value">…</div><div class="delta up">…</div></div>` | KPI tiles. `delta` takes `up` (green) or `down` (red) |
| `<span class="badge">` plus `success` / `warn` / `error` | A small status pill |
| `<div class="grid-2">` | A two-column layout that collapses to one column on narrow windows |
| `<figure class="figure">…<figcaption>…</figcaption></figure>` | An image or SVG with a caption |

## Graphics

1. **Charts (preferred for data).** Write a Chart.js v4 config as JSON in a chart block. The viewer draws it and applies theme colors automatically, so leave colors out unless they carry meaning.
   ```html
   <script type="application/json" data-chart data-height="300" data-caption="Daily signups">
   {"type":"line",
    "data":{"labels":["Mon","Tue","Wed","Thu","Fri"],
            "datasets":[{"label":"Signups","data":[12,19,15,25,22],"fill":true}]},
    "options":{"plugins":{"legend":{"display":false}}}}
   </script>
   ```
   - Supported types: `bar`, `line`, `pie`, `doughnut`, `radar`, `polarArea`, `scatter`, `bubble`. Use `"options":{"indexAxis":"y"}` for horizontal bars.
   - The content must be **strict JSON**: double quotes, no comments, no trailing commas, no functions. Invalid JSON makes `send` fail.
   - `data-height` (px, default 320) and `data-caption` are optional.
2. **Inline `<svg>`** for diagrams, simple shapes, and sparklines. Use a `viewBox` with no fixed width so it scales. Use `currentColor` so it works in both light and dark mode.
3. **Images** as base64 data URIs: `<img src="data:image/png;base64,…" alt="…">`. For example, a matplotlib PNG encoded with `base64 -i plot.png`.

## Example

```html
<div class="callout success"><p><strong>All 4 services deployed.</strong> No errors in the 10-minute bake.</p></div>

<div class="metrics">
  <div class="metric"><div class="label">p95 latency</div><div class="value">182 ms</div><div class="delta up">−12% vs last</div></div>
  <div class="metric"><div class="label">Error rate</div><div class="value">0.04%</div><div class="delta">flat</div></div>
  <div class="metric"><div class="label">Duration</div><div class="value">6m 41s</div></div>
</div>

<h2>Requests per minute</h2>
<script type="application/json" data-chart data-height="260">
{"type":"bar","data":{"labels":["api","web","worker","cron"],"datasets":[{"label":"rpm","data":[4200,3100,900,40]}]},"options":{"plugins":{"legend":{"display":false}}}}
</script>

<h2>Details</h2>
<table>
  <thead><tr><th>Service</th><th>Version</th><th class="num">Pods</th><th>Status</th></tr></thead>
  <tbody>
    <tr><td>api</td><td><code>v2.14.0</code></td><td class="num">6</td><td><span class="badge success">healthy</span></td></tr>
    <tr><td>worker</td><td><code>v2.14.0</code></td><td class="num">3</td><td><span class="badge warn">1 restart</span></td></tr>
  </tbody>
</table>

<details><summary>Full log</summary><pre><code>…</code></pre></details>
```

## Other commands

- `~/Work/source/notifier/.venv/bin/notifier list [--unread] [-n 20]` shows recent notifications (`*` marks unread).
- If `send` fails because the database can't be opened, or the command doesn't exist, tell the user the notifier isn't installed (`~/Work/source/notifier/scripts/install.sh`). Don't try to write to the database by hand.
