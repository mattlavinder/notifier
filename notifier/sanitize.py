"""Normalize agent-written HTML into a body fragment.

This keeps stored markup tidy (no document wrappers, no agent styles or scripts).
The viewer's Content-Security-Policy is what actually stops scripts from running.
"""

import json
import re
from html import escape
from html.parser import HTMLParser

# Removed along with everything inside them.
DROP_WITH_CONTENT = {"head", "style", "script", "iframe", "object", "embed", "template", "noscript", "title"}
# Removed, but their children are kept.
UNWRAP = {"html", "body"}
# Void elements that are simply removed.
DROP_VOID = {"meta", "link", "base"}

URL_ATTRS = {"href", "src", "xlink:href", "action", "formaction", "poster", "background"}
BAD_SCHEME = re.compile(r"^(javascript|vbscript):", re.I)
CONTROL_CHARS = re.compile(r"[\x00-\x20]+")


class ChartError(ValueError):
    pass


def _is_chart(tag, attrs) -> bool:
    names = {k: (v or "").strip().lower() for k, v in attrs}
    return tag == "script" and names.get("type") == "application/json" and "data-chart" in names


def _safe_attrs(attrs):
    kept = []
    for name, value in attrs:
        if name.startswith("on"):
            continue
        if name in URL_ATTRS and value and BAD_SCHEME.match(CONTROL_CHARS.sub("", value)):
            continue
        if name == "src" and value is None:
            continue
        kept.append((name, value))
    return kept


def _render_tag(tag, attrs, self_closing=False) -> str:
    parts = [tag]
    for name, value in attrs:
        parts.append(name if value is None else f'{name}="{escape(value, quote=True)}"')
    return "<" + " ".join(parts) + (" />" if self_closing else ">")


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.skip_tag: str | None = None
        self.skip_depth = 0
        self.in_chart = False
        self.chart_count = 0

    # --- tags -----------------------------------------------------------
    def _start(self, tag, attrs, self_closing):
        if self.skip_tag:
            if self.skip_tag == "head" and tag == "body":
                # An unclosed <head> ends where <body> begins, as in a browser.
                self.skip_tag = None
            elif tag == self.skip_tag and not self_closing:
                self.skip_depth += 1
            return
        if _is_chart(tag, attrs):
            kept = [(k, v) for k, v in _safe_attrs(attrs) if k != "src"]
            self.out.append(_render_tag(tag, kept))
            self.in_chart = True
            self.chart_text: list[str] = []
            return
        if tag in DROP_WITH_CONTENT:
            if not self_closing:
                self.skip_tag, self.skip_depth = tag, 1
            return
        if tag in UNWRAP or tag in DROP_VOID:
            return
        kept = _safe_attrs(attrs)
        if kept == attrs:
            # Untouched: keep the original text so SVG attribute case (viewBox etc.) survives.
            self.out.append(self.get_starttag_text())
        else:
            self.out.append(_render_tag(tag, kept, self_closing))

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, self_closing=True)

    def handle_endtag(self, tag):
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skip_tag = None
            return
        if self.in_chart and tag == "script":
            text = "".join(self.chart_text)
            self.chart_count += 1
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise ChartError(f"chart #{self.chart_count} is not valid JSON: {exc}") from None
            self.out.append(text + "</script>")
            self.in_chart = False
            return
        if tag in UNWRAP or tag in DROP_VOID or tag in DROP_WITH_CONTENT:
            return
        self.out.append(f"</{tag}>")

    # --- content --------------------------------------------------------
    def handle_data(self, data):
        if self.skip_tag:
            return
        if self.in_chart:
            self.chart_text.append(data)
        else:
            self.out.append(data)

    def handle_entityref(self, name):
        if not self.skip_tag:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip_tag:
            self.out.append(f"&#{name};")

    # Comments, doctypes and processing instructions are dropped.
    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass


def clean(html: str) -> str:
    """Return a cleaned body fragment. Raises ChartError on malformed chart JSON."""
    parser = _Cleaner()
    parser.feed(html)
    parser.close()
    if parser.in_chart:
        raise ChartError("chart <script> block is missing its closing </script>")
    return "".join(parser.out).strip()
