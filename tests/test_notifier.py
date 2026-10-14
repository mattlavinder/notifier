import pytest

from notifier import config, db, sanitize, watcher


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = tmp_path / "n.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    c = db.connect(path)
    yield c
    c.close()


# --- sanitize -----------------------------------------------------------

def test_strips_document_wrappers():
    out = sanitize.clean(
        "<!doctype html><html><head><title>t</title><style>p{}</style></head>"
        "<body><p>hi</p></body></html>"
    )
    assert out == "<p>hi</p>"


def test_unclosed_head_ends_at_body():
    assert sanitize.clean("<head><meta charset=utf-8><body><p>x</p>") == "<p>x</p>"


def test_strips_scripts_and_handlers():
    out = sanitize.clean('<p onclick="x()">a</p><script>alert(1)</script><a href=" javascript:x">l</a>')
    assert "script" not in out and "onclick" not in out and "javascript" not in out
    assert "<p>a</p>" in out and "<a>l</a>" in out


def test_keeps_chart_block():
    src = '<script type="application/json" data-chart data-height="200">{"type":"bar","data":{}}</script>'
    assert sanitize.clean(src) == src


def test_bad_chart_json_raises():
    with pytest.raises(sanitize.ChartError):
        sanitize.clean('<script type="application/json" data-chart>{type: bar}</script>')


def test_svg_case_and_entities_preserved():
    src = '<svg viewBox="0 0 10 10"><linearGradient id="g"/><path d="M0 0"/></svg><p>a &amp; b &#169;</p>'
    assert sanitize.clean(src) == src


def test_data_image_kept():
    src = '<img src="data:image/png;base64,AAAA" alt="x">'
    assert sanitize.clean(src) == src


# --- db -----------------------------------------------------------------

def test_read_state(conn):
    a = db.insert(conn, "a", "<p>a</p>")
    b = db.insert(conn, "b", "<p>b</p>", "src")
    assert db.count(conn, unread_only=True) == 2
    db.set_read(conn, a, True)
    assert [r["id"] for r in db.recent(conn, 10, unread_only=True)] == [b]
    db.set_read(conn, a, False)
    db.mark_all_read(conn)
    assert db.count(conn, unread_only=True) == 0
    assert db.neighbors(conn, a) == (None, b)


# --- watcher ------------------------------------------------------------

def test_watcher_notifies_once(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(watcher, "popup", lambda tn, msg, url, *a, **k: calls.append((msg, url)) or True)
    nid = db.insert(conn, "hello", "<p>x</p>")
    watcher.deliver(conn, "tn", db.pending(conn))
    watcher.deliver(conn, "tn", db.pending(conn))
    assert calls == [("hello", config.notification_url(nid))]


def test_watcher_summarizes_burst(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(watcher, "popup", lambda tn, msg, url, *a, **k: calls.append((msg, url)) or True)
    for i in range(config.BURST_THRESHOLD + 2):
        db.insert(conn, f"n{i}", "<p>x</p>")
    watcher.deliver(conn, "tn", db.pending(conn))
    assert len(calls) == 1 and calls[0][0].startswith(f"{config.BURST_THRESHOLD + 2} new")
    assert db.pending(conn) == []


def test_watcher_keeps_rows_pending_on_failure(conn, monkeypatch):
    monkeypatch.setattr(watcher, "popup", lambda *a, **k: False)
    db.insert(conn, "hello", "<p>x</p>")
    assert watcher.deliver(conn, "tn", db.pending(conn)) is False
    assert len(db.pending(conn)) == 1


# --- web ----------------------------------------------------------------

@pytest.fixture
def client(conn):
    from notifier.web import app

    return app.test_client()


def test_web_read_flow(conn, client):
    nid = db.insert(conn, "Report", '<p>body</p><script type="application/json" data-chart>{}</script>', "agent")
    inbox = client.get("/")
    assert b"Report" in inbox.data and b"unread" in inbox.data
    assert "script-src 'self'" in inbox.headers["Content-Security-Policy"]

    page = client.get(f"/n/{nid}")
    assert page.status_code == 200 and b"<p>body</p>" in page.data
    assert db.get(conn, nid)["read_at"] is not None

    r = client.post(f"/n/{nid}/unread", data={"next": "/?filter=unread"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/?filter=unread")
    assert db.get(conn, nid)["read_at"] is None

    r = client.post("/read-all", data={"next": "//evil.example"})
    assert r.headers["Location"] == "/"
    assert db.count(conn, unread_only=True) == 0

    assert client.get("/n/9999").status_code == 404
    assert client.get("/api/recent").json["items"][0]["id"] == nid


def test_state_changes_with_inbox(conn, client):
    empty = client.get("/api/state").json
    assert empty["unread"] == 0 and empty["latest_id"] == 0
    nid = db.insert(conn, "x", "<p>x</p>")
    added = client.get("/api/state")
    assert added.headers["Cache-Control"] == "no-store"
    assert added.json["latest_id"] == nid and added.json["version"] != empty["version"]
    db.set_read(conn, nid, True)
    assert client.get("/api/state").json["version"] != added.json["version"]
    page = client.get("/").data.decode()
    assert 'data-page="inbox"' in page and "live.js" in page
