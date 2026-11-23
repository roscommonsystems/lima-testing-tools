"""
LIMA practice page: a web page that reports what was done to it.

The mouse and keyboard tools (click, right-click, double-click, move the mouse, scroll, type,
press a key) used to be judged from before/after screenshots. A screenshot can't tell which
button was clicked or whether Enter was pressed, and a real site changes under the test.

This module serves one page on this machine only (127.0.0.1), opens it in Microsoft Edge, and
records every event the page sees: which element was clicked, double-clicked, right-clicked or
hovered, how far the page or its side list scrolled, each key pressed in the key box, what
each form field holds and what was submitted. A test asks LIMA to do something to the page and
then reads the event that proves it happened.

What is on the page (the names a test tells LIMA to act on):

* Buttons **Apple**, **Banana** and **Cherry**.
* A link, **Open the orchard page**, to a second page.
* A form: **First name**, **City**, **Favourite fruit** and a **Send form** button.
* A **Key practice box** that records each key pressed while it has focus.
* A **Fruit list** that scrolls on its own, beside the article.
* An article long enough that the page itself scrolls, and a bar chart (see CHART_VALUES).

The page's title deliberately does not contain "LIMA": the suite finds LIMA's own window by
that word.

Usage:

    with PracticePage() as page:
        browser = page.open_in_browser()
        ... ask LIMA to click the Banana button ...
        event = page.wait_for_event("click", target="Banana")
"""

import ctypes
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import psutil
from PIL import Image, ImageDraw, ImageFont

from lima_test_utils import (
    SLEEP_A, SLEEP_B, PRACTICE_PAGE_PORT, activate_window, enum_top_level_windows,
    get_window_class_name, get_window_pid, get_window_rect, get_window_title,
)

PAGE_TITLE = "Orchard Practice Page"
ORCHARD_PAGE_TITLE = "Orchard Second Page"
HOST = "127.0.0.1"

BUTTON_NAMES = ("Apple", "Banana", "Cherry")
LINK_NAME = "Open the orchard page"
FORM_FIELDS = ("First name", "City", "Favourite fruit")
SUBMIT_NAME = "Send form"
CHAT_FIELD_NAME = "Chat message"
CHAT_SUBMIT_NAME = "Send message"
KEY_BOX_NAME = "Key practice box"
FRUIT_LIST_NAME = "Fruit list"

# The bar chart's bars, in order. A test that asks LIMA what the chart shows checks the reply
# against these.
CHART_TITLE = "Boxes of fruit sold this week"
CHART_VALUES = (("Apples", 12), ("Bananas", 30), ("Cherries", 7))

FRUIT_LIST_ROWS = 80
ARTICLE_PARAGRAPHS = 40

# Where Edge is installed. It ships with Windows 11, in one of these.
EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
EDGE_WINDOW_CLASS = "Chrome_WidgetWin_1"
BROWSER_START_TIMEOUT = 45.0
SW_MAXIMIZE = 3
# How far in from the window's right-hand edge empty_point() is: clear of the scrollbar and
# the window border, and right of everything on the page.
EMPTY_POINT_INSET = 90

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  body { font-family: Segoe UI, Arial, sans-serif; font-size: 18px; margin: 24px; }
  button, input, textarea, a { font-size: 20px; }
  button { padding: 14px 28px; margin: 0 16px 16px 0; }
  .columns { display: flex; gap: 32px; align-items: flex-start; }
  #fruit-list { height: 220px; width: 260px; overflow-y: scroll; border: 2px solid #444; padding: 8px; }
  #key-box { width: 420px; height: 60px; }
  label { display: block; margin-top: 12px; }
  article p { max-width: 720px; line-height: 1.5; }
</style>
</head>
<body>
<section id="chat-practice" hidden>
  <h1>Orchard chat</h1>
  <p>Write a message. Enter sends it; Shift+Enter adds a new line.</p>
  <div id="chat-history" role="log" aria-label="Sent messages"></div>
  <form id="chat-form">
    <label for="chat-message">__CHAT_FIELD_NAME__</label>
    <textarea id="chat-message" aria-label="__CHAT_FIELD_NAME__" style="width: 600px; height: 100px"></textarea>
    <p><button type="submit">__CHAT_SUBMIT_NAME__</button></p>
  </form>
</section>
<div id="practice-content">
<h1>__TITLE__</h1>

<h2>Fruit buttons</h2>
<p>
__BUTTONS__
</p>
<p><a id="orchard-link" href="/orchard">__LINK_NAME__</a></p>

<h2>Key practice</h2>
<label for="key-box">__KEY_BOX_NAME__</label>
<textarea id="key-box" aria-label="__KEY_BOX_NAME__"></textarea>

<h2>Fruit order form</h2>
<form id="order-form">
__FIELDS__
  <p><button type="submit" id="send-form">__SUBMIT_NAME__</button></p>
</form>

<div class="columns">
  <article>
    <h2>The orchard in autumn</h2>
__ARTICLE__
  </article>
  <div>
    <h2>__FRUIT_LIST_NAME__</h2>
    <div id="fruit-list" role="list" aria-label="__FRUIT_LIST_NAME__" tabindex="0">
__FRUIT_ROWS__
    </div>
    <h2>__CHART_TITLE__</h2>
    <img id="chart" src="/chart.png" alt="Bar chart" width="520" height="340">
  </div>
</div>

</div>
<script>
function report(kind, target, detail) {
  fetch("/event", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({kind: kind, target: target, detail: detail || {}})
  });
}
function nameOf(element) {
  return element.getAttribute("data-name") || element.getAttribute("aria-label") || element.id;
}
document.querySelectorAll("[data-name]").forEach(function (element) {
  var name = nameOf(element);
  element.addEventListener("click", function () { report("click", name); });
  element.addEventListener("dblclick", function () { report("double_click", name); });
  element.addEventListener("contextmenu", function (event) {
    event.preventDefault();
    report("right_click", name);
  });
  element.addEventListener("mouseenter", function () { report("hover", name); });
});
document.querySelectorAll("#order-form input").forEach(function (field) {
  field.addEventListener("input", function () { report("field", nameOf(field), {value: field.value}); });
});
document.getElementById("order-form").addEventListener("submit", function (event) {
  event.preventDefault();
  var values = {};
  document.querySelectorAll("#order-form input").forEach(function (field) {
    values[nameOf(field)] = field.value;
  });
  report("submit", "__SUBMIT_NAME__", {values: values});
});
var keyBox = document.getElementById("key-box");
keyBox.addEventListener("keydown", function (event) {
  report("key", "__KEY_BOX_NAME__", {key: event.key, shift: event.shiftKey, ctrl: event.ctrlKey, alt: event.altKey});
});
keyBox.addEventListener("input", function () {
  report("field", "__KEY_BOX_NAME__", {value: keyBox.value});
});
function watchScroll(source, name, position) {
  var pending = null;
  source.addEventListener("scroll", function () {
    if (pending) { return; }
    pending = setTimeout(function () { pending = null; report("scroll", name, {top: position()}); }, 150);
  });
}
watchScroll(window, "page", function () { return Math.round(window.scrollY); });
var fruitList = document.getElementById("fruit-list");
watchScroll(fruitList, "__FRUIT_LIST_NAME__", function () { return Math.round(fruitList.scrollTop); });
var focusTarget = new URLSearchParams(window.location.search).get("focus");
var chatMessage = document.getElementById("chat-message");
var chatForm = document.getElementById("chat-form");
chatMessage.addEventListener("input", function () {
  report("field", "__CHAT_FIELD_NAME__", {value: chatMessage.value});
});
chatMessage.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});
chatForm.addEventListener("submit", function (event) {
  event.preventDefault();
  var values = {};
  values["__CHAT_FIELD_NAME__"] = chatMessage.value;
  report("submit", "__CHAT_SUBMIT_NAME__", {values: values});
  var sent = document.createElement("p");
  sent.textContent = chatMessage.value;
  document.getElementById("chat-history").appendChild(sent);
  chatMessage.value = "";
  report("field", "__CHAT_FIELD_NAME__", {value: ""});
});
if (focusTarget === "chat-message") {
  document.getElementById("practice-content").hidden = true;
  document.getElementById("chat-practice").hidden = false;
}
if (focusTarget) {
  var element = document.getElementById(focusTarget);
  if (element) { element.focus(); }
}
report("loaded", "page", {path: window.location.pathname + window.location.search});
</script>
</body>
</html>
"""

SIMPLE_PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title></head>
<body style="font-family: Segoe UI, Arial, sans-serif; font-size: 22px; margin: 24px;">
<h1>__TITLE__</h1><p>__BODY__</p></body></html>
"""


class PracticePageError(Exception):
    """The practice page or its browser could not be started. str(error) says why."""


def _fill(template, **values):
    """Replace each __NAME__ marker in template with its value."""
    text = template
    for name, value in values.items():
        text = text.replace(f"__{name.upper()}__", str(value))
    return text


def _button_html():
    buttons = [f'  <button type="button" data-name="{name}">{name}</button>' for name in BUTTON_NAMES]
    html = "\n".join(buttons)
    return html


def _field_html():
    fields = []
    for name in FORM_FIELDS:
        field_id = name.lower().replace(" ", "-")
        fields.append(f'  <label for="{field_id}">{name}</label>\n'
                      f'  <input type="text" id="{field_id}" aria-label="{name}" autocomplete="off">')
    html = "\n".join(fields)
    return html


def _article_html(code_word):
    """The article: a first paragraph carrying the code word, then enough text to scroll."""
    first = "The orchard keeper walks the rows before sunrise, checking each tree in turn."
    if code_word:
        first += f" This season the keeper's password for the gate is {code_word}."
    paragraphs = [f"    <p>{first}</p>"]
    for number in range(2, ARTICLE_PARAGRAPHS + 1):
        paragraphs.append(
            f"    <p>Paragraph {number}. The pickers work along row {number}, filling crates and "
            f"stacking them by the path, while the cart makes its slow way back to the barn.</p>")
    html = "\n".join(paragraphs)
    return html


def _fruit_rows_html():
    rows = [f'      <div role="listitem">Fruit crate {number}</div>'
            for number in range(1, FRUIT_LIST_ROWS + 1)]
    html = "\n".join(rows)
    return html


def render_chart():
    """The bar chart as PNG bytes: one labelled bar per CHART_VALUES entry, value above it."""
    width, height = 520, 340
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=20)
    draw.text((20, 12), CHART_TITLE, fill="black", font=font)
    baseline, top = height - 50, 60
    highest = max(value for _label, value in CHART_VALUES)
    bar_width, gap = 100, 50
    colours = ("#c0392b", "#f1c40f", "#8e44ad")
    for index, (label, value) in enumerate(CHART_VALUES):
        left = 50 + index * (bar_width + gap)
        bar_top = baseline - int((baseline - top) * value / highest)
        draw.rectangle((left, bar_top, left + bar_width, baseline), fill=colours[index % len(colours)],
                       outline="black")
        draw.text((left + 30, bar_top - 28), str(value), fill="black", font=font)
        draw.text((left, baseline + 10), label, fill="black", font=font)
    draw.line((40, baseline, width - 20, baseline), fill="black", width=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    chart_bytes = buffer.getvalue()
    return chart_bytes


def find_edge():
    """The path of msedge.exe, or None when Edge is not installed in a standard place."""
    for path in EDGE_PATHS:
        if os.path.isfile(path):
            return path
    on_path = shutil.which("msedge")
    return on_path


class PracticePage:
    """The practice page's server, its event log, and the browser window showing it."""

    def __init__(self, code_word=None):
        """
        Args:
            code_word: a word written into the article's first paragraph, for tests that ask
                LIMA to read the page: the word can only come from reading it.
        """
        self.code_word = code_word
        self._events = []
        self._fields = {}
        self._lock = threading.Lock()
        self._server = None
        self._thread = None
        self._chart = None
        self._browser = None
        self._profile_dir = None
        self.browser_hwnd = 0

    # ---- server -------------------------------------------------------------------

    def start(self):
        """Start serving. Returns the page's address."""
        if self._server is not None:
            return self.url
        self._chart = render_chart()
        self._server = ThreadingHTTPServer((HOST, PRACTICE_PAGE_PORT), self._handler_class())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="LimaPracticePage", daemon=True)
        self._thread.start()
        print(f"  Practice page is at {self.url}")
        return self.url

    def stop(self):
        """Close the browser window and stop serving."""
        self.close_browser()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _exception_type, _exception, _traceback):
        self.stop()
        return False

    @property
    def port(self):
        port_number = self._server.server_address[1] if self._server is not None else None
        return port_number

    @property
    def url(self):
        address = self.url_for("/")
        return address

    def url_for(self, path, **query):
        """The address of a path on the page's server, e.g. url_for("/", focus="key-box")."""
        address = f"http://{HOST}:{self.port}{path}"
        if query:
            address += "?" + urlencode(query)
        return address

    def _handler_class(self):
        page = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_arguments):
                """Keep the server's request log out of the test output."""

            def _send(self, status, content_type, body):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/chart.png":
                    self._send(200, "image/png", page._chart)
                    return
                if path == "/favicon.ico":
                    self._send(204, "image/x-icon", b"")
                    return
                page._record("request", "page", {"path": self.path})
                body = page._render(path).encode("utf-8")
                self._send(200, "text/html; charset=utf-8", body)

            def do_POST(self):
                if urlparse(self.path).path != "/event":
                    self._send(404, "text/plain", b"not found")
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    event = json.loads(self.rfile.read(length).decode("utf-8"))
                    page._record(str(event.get("kind")), str(event.get("target")),
                                 event.get("detail") or {})
                except (ValueError, UnicodeDecodeError):
                    self._send(400, "text/plain", b"bad event")
                    return
                self._send(204, "text/plain", b"")

        return Handler

    def _render(self, path):
        """The HTML for a path: the practice page at "/", a plain page for anything else."""
        if path == "/":
            html = _fill(PAGE_TEMPLATE, title=PAGE_TITLE, buttons=_button_html(),
                         link_name=LINK_NAME, key_box_name=KEY_BOX_NAME, fields=_field_html(),
                         submit_name=SUBMIT_NAME, chat_field_name=CHAT_FIELD_NAME,
                         chat_submit_name=CHAT_SUBMIT_NAME, article=_article_html(self.code_word),
                         fruit_list_name=FRUIT_LIST_NAME, fruit_rows=_fruit_rows_html(),
                         chart_title=CHART_TITLE)
            return html
        if path == "/orchard":
            body = "You followed the link from the practice page."
            html = _fill(SIMPLE_PAGE_TEMPLATE, title=ORCHARD_PAGE_TITLE, body=body)
            return html
        # Any other path is served too, so a test can ask LIMA to open an address it made up
        # and see the request arrive.
        body = f"This is the practice server's page for {path}."
        html = _fill(SIMPLE_PAGE_TEMPLATE, title="Orchard Practice Server", body=body)
        return html

    # ---- events -------------------------------------------------------------------

    def _record(self, kind, target, detail):
        event = {"time": time.time(), "kind": kind, "target": target, "detail": detail}
        with self._lock:
            self._events.append(event)
            if kind == "field":
                self._fields[target] = str(detail.get("value", ""))

    def events(self, kind=None, target=None, since=0.0):
        """Recorded events, oldest first, optionally only one kind, one target, or after a time."""
        with self._lock:
            recorded = list(self._events)
        matching = [event for event in recorded
                    if (kind is None or event["kind"] == kind)
                    and (target is None or event["target"] == target)
                    and event["time"] >= since]
        return matching

    def wait_for_event(self, kind, target=None, timeout=10.0, since=0.0, poll_seconds=0.2):
        """The first matching event, waiting up to timeout for one; None when none arrives."""
        deadline = time.time() + timeout
        while True:
            matching = self.events(kind, target, since)
            if matching:
                first = matching[0]
                return first
            if time.time() >= deadline:
                return None
            time.sleep(poll_seconds)

    def clear_events(self):
        """Forget what has been recorded so far (field values are kept)."""
        with self._lock:
            self._events.clear()

    def field_value(self, name):
        """What a form field or the key box holds now ("" when nothing was ever typed in it)."""
        with self._lock:
            value = self._fields.get(name, "")
        return value

    def scroll_top(self, target="page", since=0.0):
        """The latest scroll position reported for the page or the fruit list, or None."""
        scrolls = self.events("scroll", target, since)
        if not scrolls:
            return None
        top = scrolls[-1]["detail"].get("top")
        return top

    def describe_events(self, since=0.0, limit=12):
        """The most recent events as one line, for a failure message."""
        recent = self.events(since=since)[-limit:]
        described = "; ".join(f"{event['kind']} on {event['target']} {event['detail'] or ''}".strip()
                              for event in recent)
        summary = described or "no events were recorded"
        return summary

    # ---- browser ------------------------------------------------------------------

    def open_in_browser(self, path="/", timeout=BROWSER_START_TIMEOUT, **query):
        """
        Open the page in its own Edge window, in front, and wait until it has loaded.

        Edge is started with a throwaway profile, so it is a separate process from any Edge
        already running: the test can close exactly what it opened, and no sign-in, extension
        or restored tab from the machine's own profile appears in LIMA's view of the screen.

        Args:
            path: the page to open, "/" for the practice page.
            **query: e.g. focus="key-box" to start with the key box focused.

        Returns:
            int: the browser window's handle.

        Raises:
            PracticePageError: Edge is not installed, or the page did not load in time.
        """
        self.close_browser()
        edge = find_edge()
        if not edge:
            reason = "Microsoft Edge was not found, so the practice page could not be opened"
            raise PracticePageError(reason)
        address = self.url_for(path, **query)
        self._profile_dir = tempfile.mkdtemp(prefix="lima-practice-edge-")
        started = time.time()
        self._browser = subprocess.Popen([
            edge, f"--app={address}", f"--user-data-dir={self._profile_dir}",
            "--no-first-run", "--no-default-browser-check",
        ])
        loaded = self.wait_for_event("loaded", timeout=timeout, since=started)
        hwnd = self._wait_for_window(timeout=10.0) if loaded else 0
        if not hwnd:
            self.close_browser()
            reason = f"The practice page did not open in Edge within {timeout:.0f}s"
            raise PracticePageError(reason)
        self.browser_hwnd = hwnd
        self.bring_to_front()
        time.sleep(SLEEP_A)
        print(f"  Opened the practice page in Edge: {get_window_title(hwnd)!r}")
        return hwnd

    def bring_to_front(self):
        """
        Make the practice page the active window, maximized; True when it is in front.

        Maximized, so the page covers LIMA's own window: nothing of LIMA is then under the
        pointer or in LIMA's view of the screen. activate_window restores a window to its
        normal size on the way, which is why the maximize comes after it.
        """
        if not self.browser_hwnd:
            return False
        activate_window(self.browser_hwnd)
        ctypes.windll.user32.ShowWindow(self.browser_hwnd, SW_MAXIMIZE)
        time.sleep(SLEEP_A)
        in_front = self.is_in_front()
        return in_front

    def empty_point(self):
        """
        A screen position inside the page with nothing under it: (x, y), or None.

        It is near the page's right-hand edge, left of the scrollbar and level with the
        middle of the window. A test parks the pointer here so it starts on nothing the page
        reports, yet still over the page, where a scroll without a target scrolls the page.
        """
        rect = get_window_rect(self.browser_hwnd) if self.browser_hwnd else None
        if not rect:
            return None
        left, top, right, bottom = rect
        point = (right - EMPTY_POINT_INSET, (top + bottom) // 2)
        return point

    def _browser_pids(self):
        """The process ids of the Edge this page started, children included."""
        if self._browser is None:
            return set()
        pids = {self._browser.pid}
        try:
            pids.update(child.pid for child in psutil.Process(self._browser.pid).children(recursive=True))
        except psutil.Error:
            pass
        return pids

    def _wait_for_window(self, timeout):
        """The handle of the visible window of the Edge this page started, or 0."""
        user32 = ctypes.windll.user32
        deadline = time.time() + timeout
        while True:
            pids = self._browser_pids()
            for hwnd in enum_top_level_windows():
                if (user32.IsWindowVisible(hwnd) and get_window_pid(hwnd) in pids
                        and get_window_class_name(hwnd) == EDGE_WINDOW_CLASS
                        and get_window_title(hwnd)):
                    return hwnd
            if time.time() >= deadline:
                return 0
            time.sleep(0.25)

    def is_in_front(self):
        """True when the practice page is the active window."""
        in_front = bool(self.browser_hwnd) and (
            ctypes.windll.user32.GetForegroundWindow() == self.browser_hwnd)
        return in_front

    def close_browser(self):
        """End the Edge this page started and delete its throwaway profile."""
        if self._browser is not None:
            processes = []
            for pid in self._browser_pids():
                try:
                    processes.append(psutil.Process(pid))
                except psutil.Error:
                    continue
            for process in processes:
                try:
                    process.terminate()
                except psutil.Error:
                    continue
            _gone, alive = psutil.wait_procs(processes, timeout=5)
            for process in alive:
                try:
                    process.kill()
                except psutil.Error:
                    continue
            self._browser = None
            self.browser_hwnd = 0
        if self._profile_dir:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = None
