from datetime import datetime, timezone

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for

from . import config, db

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'none'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)

app = Flask(__name__)


def conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def close_conn(_exc):
    c = g.pop("conn", None)
    if c is not None:
        c.close()


@app.after_request
def security_headers(resp):
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.context_processor
def inject_counts():
    return {"unread_total": db.count(conn(), unread_only=True)}


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


@app.template_filter("ago")
def ago(ts: str) -> str:
    secs = int((datetime.now(timezone.utc) - _parse(ts)).total_seconds())
    if secs < 60:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            n = secs // size
            if unit == "d" and n > 6:
                return _parse(ts).astimezone().strftime("%b %-d")
            return f"{n}{unit} ago"
    return ""


@app.template_filter("localtime")
def localtime(ts: str) -> str:
    return _parse(ts).astimezone().strftime("%a %b %-d, %Y at %-I:%M %p")


def _back(default: str):
    """Redirect to the form's `next` field when it is a local path."""
    target = request.form.get("next", "")
    if not target.startswith("/") or target.startswith("//"):
        target = default
    return redirect(target)


@app.get("/")
def inbox():
    unread_only = request.args.get("filter") == "unread"
    page = max(request.args.get("page", 1, type=int), 1)
    total = db.count(conn(), unread_only=unread_only)
    pages = max((total + config.PAGE_SIZE - 1) // config.PAGE_SIZE, 1)
    rows = db.recent(conn(), config.PAGE_SIZE, (page - 1) * config.PAGE_SIZE, unread_only)
    return render_template(
        "inbox.html",
        rows=rows,
        unread_only=unread_only,
        page=page,
        pages=pages,
        total=total,
        here=request.full_path.rstrip("?"),
    )


@app.get("/n/<int:nid>")
def show(nid: int):
    row = db.get(conn(), nid)
    if row is None:
        abort(404)
    db.set_read(conn(), nid, True)
    older, newer = db.neighbors(conn(), nid)
    return render_template("notification.html", n=row, older=older, newer=newer)


@app.post("/n/<int:nid>/read")
def mark_read(nid: int):
    db.set_read(conn(), nid, True)
    return _back(url_for("inbox"))


@app.post("/n/<int:nid>/unread")
def mark_unread(nid: int):
    db.set_read(conn(), nid, False)
    # Not back to /n/<id>: viewing it would immediately mark it read again.
    return _back(url_for("inbox"))


@app.post("/read-all")
def read_all():
    db.mark_all_read(conn())
    return _back(url_for("inbox"))


@app.get("/api/recent")
def api_recent():
    limit = min(request.args.get("limit", 20, type=int), 200)
    rows = db.recent(conn(), limit, unread_only=request.args.get("filter") == "unread")
    return jsonify(
        unread=db.count(conn(), unread_only=True),
        items=[dict(r) | {"url": config.notification_url(r["id"])} for r in rows],
    )


@app.get("/favicon.ico")
def favicon():
    # Browsers request this path directly for non-HTML responses; point them at the SVG.
    return redirect(url_for("static", filename="favicon.svg"), code=301)


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


def run():
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
