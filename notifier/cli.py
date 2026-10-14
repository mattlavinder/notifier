import argparse
import logging
import sys

from . import config, db, sanitize


def cmd_init(_args):
    db.connect().close()
    print(f"database ready: {config.DB_PATH}")


def cmd_send(args):
    subject = " ".join(args.subject.split())
    if not subject:
        sys.exit("error: --subject must not be empty")
    if len(subject) > config.MAX_SUBJECT_CHARS:
        sys.exit(f"error: --subject is longer than {config.MAX_SUBJECT_CHARS} characters")

    if args.body is not None:
        raw = args.body
    elif args.file:
        with open(args.file, encoding="utf-8") as fh:
            raw = fh.read()
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        sys.exit("error: provide the HTML with --file, --body, or on stdin")

    if len(raw.encode("utf-8")) > config.MAX_BODY_BYTES:
        sys.exit(f"error: body is larger than {config.MAX_BODY_BYTES // (1024 * 1024)} MB")
    try:
        body = sanitize.clean(raw)
    except sanitize.ChartError as exc:
        sys.exit(f"error: {exc}")
    if not body:
        sys.exit("error: body is empty after cleaning")

    conn = db.connect()
    nid = db.insert(conn, subject, body, args.source)
    conn.close()
    print(f"sent #{nid}: {config.notification_url(nid)}")


def cmd_list(args):
    conn = db.connect()
    for r in db.recent(conn, args.limit, unread_only=args.unread):
        flag = "*" if r["read_at"] is None else " "
        src = f"[{r['source']}] " if r["source"] else ""
        print(f"{flag} #{r['id']:<5} {r['created_at'][:19].replace('T', ' ')}Z  {src}{r['subject']}")


def cmd_serve(_args):
    from . import web

    web.run()


def cmd_watch(args):
    from . import watcher

    watcher.run(once=args.once)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="notifier", description="Agent notifications for macOS")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)

    s = sub.add_parser("send", help="queue a notification")
    s.add_argument("--subject", "-s", required=True, help="popup text and page title")
    s.add_argument("--source", help="agent or project name shown as a badge")
    src = s.add_mutually_exclusive_group()
    src.add_argument("--file", "-f", help="path to an HTML fragment")
    src.add_argument("--body", "-b", help="HTML fragment as a string")
    s.set_defaults(func=cmd_send)

    ls = sub.add_parser("list", help="show recent notifications (* = unread)")
    ls.add_argument("--limit", "-n", type=int, default=20)
    ls.add_argument("--unread", action="store_true")
    ls.set_defaults(func=cmd_list)

    sub.add_parser("serve", help=f"run the web viewer on {config.BASE_URL}").set_defaults(func=cmd_serve)

    w = sub.add_parser("watch", help="poll the database and show popups")
    w.add_argument("--once", action="store_true", help="process pending rows once and exit")
    w.set_defaults(func=cmd_watch)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
