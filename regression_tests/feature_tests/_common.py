"""
Shared helpers for the feature tests.

The feature tests judge outcomes directly instead of by screenshot: the state of another
app's window, a file on disk, the text in Notepad, or what LIMA saved in its conversation
file. These helpers give each test those checks, plus the LIMA steps shared with the approval
tests (ensure_lima_ready, send_instruction, close_apps, wait_for_app), so a test module is just
its scenario.

LIMA saves the active conversation to ``<install folder>\\data\\conversations\\<id>.json`` at
the end of every turn (``lima.py`` ``_save_active_conversation``), with each message's text,
any ``tool_calls`` and the tool results. That file is the most reliable record of what LIMA
did and said, so the "wait for the turn to end" and "what did LIMA reply" checks read it.
"""

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import random
import re
import subprocess
import time

import uiautomation as auto

from lima_test_utils import (
    enum_top_level_windows, get_window_class_name, get_window_title,
    activate_window, SLEEP_A,
)
# The LIMA steps are the approval tests' own; re-exported so a feature test imports one module.
from approval_tests._common import (  # noqa: F401  (re-exported)
    ensure_lima_ready, send_instruction, close_apps, wait_for_app, app_running, popups_open,
)

user32 = ctypes.windll.user32

# Win32 constants used below.
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
GA_ROOTOWNER = 3
WM_CLOSE = 0x0010
CSIDL_PERSONAL = 0x0005            # Documents
CSIDL_DESKTOPDIRECTORY = 0x0010    # the physical Desktop folder (what LIMA's screenshot uses)

# Every file a feature test creates starts with this, so a leftover is easy to spot and delete.
TEST_FILE_PREFIX = "lima-feature-test-"

# A model turn with one or two approved actions and TTS normally ends well inside a minute; a
# slow OpenRouter provider can take a few. Longer than this and the test reports a timeout.
TURN_TIMEOUT = 180.0


# --------------------------------------------------------------------------------------
# Windows: finding, moving and reading another app's window
# --------------------------------------------------------------------------------------

def foreground_root():
    """The top-level window that owns the current foreground window (0 when there is none).

    A window with a dialog open hands the focus to the dialog, so compare root owners rather
    than raw handles when asking "is this app in front".
    """
    hwnd = user32.GetForegroundWindow()
    return user32.GetAncestor(hwnd, GA_ROOTOWNER) if hwnd else 0


def is_minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


def is_maximized(hwnd):
    return bool(user32.IsZoomed(hwnd))


def is_open(hwnd):
    """True while hwnd is still a visible window (a closed window is gone or hidden)."""
    return bool(user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd))


def show_window(hwnd, command):
    """ShowWindow(hwnd, command) — SW_MINIMIZE / SW_MAXIMIZE / SW_RESTORE — then let it settle."""
    user32.ShowWindow(hwnd, command)
    time.sleep(SLEEP_A)


def windows_of_class(class_name):
    """Visible top-level windows of a window class, front-most first, as (hwnd, title)."""
    return [(hwnd, get_window_title(hwnd)) for hwnd in enum_top_level_windows()
            if user32.IsWindowVisible(hwnd) and get_window_class_name(hwnd) == class_name]


def wait_until(predicate, timeout, poll_seconds=0.25):
    """Poll predicate() until it is truthy or timeout passes; return its last value."""
    deadline = time.time() + timeout
    while True:
        value = predicate()
        if value or time.time() >= deadline:
            return value
        time.sleep(poll_seconds)


# --------------------------------------------------------------------------------------
# Notepad
# --------------------------------------------------------------------------------------

NOTEPAD_PROCESSES = ("notepad.exe",)
NOTEPAD_WINDOW_KEYWORDS = ("Notepad",)
# Both the Windows 11 Store Notepad and classic Notepad use this top-level window class.
NOTEPAD_WINDOW_CLASS = "Notepad"


def notepad_windows():
    """Visible Notepad windows, front-most first, as (hwnd, title)."""
    return windows_of_class(NOTEPAD_WINDOW_CLASS)


def open_notepad(file_path=None, timeout=20.0):
    """
    Start Notepad (optionally on a file) and wait for its window.

    Closes any running Notepad first, so the window found is the one this call started and
    a test never acts on a window left over from an earlier test.

    Returns:
        int: the Notepad window handle, or 0 when no window appeared within timeout.
    """
    close_apps(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)
    args = ["notepad.exe"] + ([file_path] if file_path else [])
    subprocess.Popen(args)
    windows = wait_until(notepad_windows, timeout)
    if not windows:
        print("  ! Notepad's window did not appear")
        return 0
    hwnd, title = windows[0]
    print(f"  Opened Notepad: {title!r}")
    return hwnd


def _notepad_text_control(hwnd):
    """Notepad's text area: a Document control (Windows 11) or an Edit control (classic)."""
    window = auto.ControlFromHandle(hwnd)
    if window is None:
        return None
    for control_type in (auto.ControlType.DocumentControl, auto.ControlType.EditControl):
        control = window.Control(searchDepth=12, ControlType=control_type)
        if control.Exists(maxSearchSeconds=2):
            return control
    return None


def notepad_text(hwnd):
    """
    The text in a Notepad window's current document, read over UI Automation.

    Reads Notepad's own text area, never LIMA's window, log or a screenshot: those echo what
    LIMA *meant* to type, not what landed (see the Type Text pitfall in the README).

    Returns:
        str: the document text, or None when it could not be read.
    """
    control = _notepad_text_control(hwnd)
    if control is None:
        return None
    try:
        return control.GetTextPattern().DocumentRange.GetText(-1)
    except Exception:
        pass
    try:
        return control.GetValuePattern().Value
    except Exception:
        return None


def clear_notepad(hwnd):
    """
    Empty a Notepad document so closing it leaves nothing to save or restore.

    Windows 11 Notepad restores unsaved tabs the next time it starts; clearing the text first
    stops a test's typing from reappearing in a later test's Notepad.
    """
    control = _notepad_text_control(hwnd)
    if control is None:
        return
    try:
        control.GetValuePattern().SetValue("")
        return
    except Exception:
        pass
    if activate_window(hwnd):
        auto.SendKeys("{Ctrl}a{Delete}", waitTime=0.2)


# --------------------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------------------

def _shell_folder(csidl, fallback_name):
    """A Windows shell folder (Documents, Desktop), falling back to ~/<name>."""
    buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) == 0 and buffer.value:
        return buffer.value
    return os.path.join(os.path.expanduser("~"), fallback_name)


def documents_dir():
    return _shell_folder(CSIDL_PERSONAL, "Documents")


def desktop_dir():
    return _shell_folder(CSIDL_DESKTOPDIRECTORY, "Desktop")


def new_test_file_path(suffix=".txt", folder=None):
    """A new, unused path in Documents (or folder) whose name starts with TEST_FILE_PREFIX."""
    folder = folder or documents_dir()
    while True:
        path = os.path.join(folder, f"{TEST_FILE_PREFIX}{random.randint(10000, 99999)}{suffix}")
        if not os.path.exists(path):
            return path


def remove_quietly(path):
    """Delete a file if it exists; never raises (cleanup must not hide the real result)."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError as error:
        print(f"  ! Could not delete {path}: {error}")


# Real words, so the model repeats them verbatim instead of "correcting" a random string.
_CODE_WORDS = ("copper", "lantern", "harbor", "violet", "falcon", "meadow", "pepper",
               "glacier", "orchid", "saddle", "tundra", "walnut")


def make_code_word():
    """A word + number LIMA can't guess, e.g. 'falcon472', to prove it read or saved something."""
    return f"{random.choice(_CODE_WORDS)}{random.randint(100, 999)}"


def contains_code_word(text, code_word):
    """True when text contains code_word, ignoring case, spaces and punctuation ('Falcon 472')."""
    def squash(value):
        return re.sub(r"[^0-9a-z]", "", (value or "").lower())
    return squash(code_word) in squash(text)


# --------------------------------------------------------------------------------------
# LIMA's data folder and saved conversations
# --------------------------------------------------------------------------------------

def lima_data_dir(executor):
    """LIMA's data folder. LIMA runs with its install folder as the working directory."""
    return os.path.join(executor.process_manager.install_path or "", "data")


def conversations_dir(executor):
    return os.path.join(lima_data_dir(executor), "conversations")


def list_conversation_files(executor):
    """Saved conversation files as {path: modified time}."""
    folder = conversations_dir(executor)
    if not os.path.isdir(folder):
        return {}
    files = {}
    for name in os.listdir(folder):
        if name.endswith(".json"):
            path = os.path.join(folder, name)
            try:
                files[path] = os.path.getmtime(path)
            except OSError:
                continue
    return files


def load_conversation(path):
    """A saved conversation dict, or None while it is missing or half-written."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def message_text(message):
    content = message.get("content")
    return content if isinstance(content, str) else ""


def find_user_message(executor, user_text):
    """
    The newest saved conversation with a user message equal to user_text.

    Returns:
        (path, conversation, index of that message) or (None, None, None).
    """
    wanted = user_text.strip().casefold()
    files = sorted(list_conversation_files(executor).items(), key=lambda item: item[1], reverse=True)
    for path, _mtime in files:
        conversation = load_conversation(path)
        if not conversation:
            continue
        messages = conversation.get("messages") or []
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if message.get("role") == "user" and message_text(message).strip().casefold() == wanted:
                return path, conversation, index
    return None, None, None


def _turn_finished(messages):
    """True when the last message is an assistant reply with text and no pending action."""
    if not messages:
        return False
    last = messages[-1]
    return (last.get("role") == "assistant" and not last.get("tool_calls")
            and bool(message_text(last).strip()))


def wait_for_turn_end(executor, user_text, timeout=TURN_TIMEOUT, quiet_seconds=20.0):
    """
    Wait until LIMA has finished answering user_text, judged from its saved conversation.

    The turn has ended when the messages after user_text end in an assistant reply with no
    pending tool call and no approval popup is open. A turn that ends on an action with no
    closing words is also accepted once the file has been unchanged for quiet_seconds.

    Returns:
        (path, messages after user_text) once the turn has ended, or (path or None, messages
        so far) on timeout. The caller decides what a timeout means for its test.
    """
    deadline = time.time() + timeout
    path, after, last_change, last_count = None, [], time.time(), -1
    while time.time() < deadline:
        path, conversation, index = find_user_message(executor, user_text)
        if conversation is not None:
            after = (conversation.get("messages") or [])[index + 1:]
            if len(after) != last_count:
                last_count, last_change = len(after), time.time()
            if not popups_open():
                if _turn_finished(after):
                    return path, after
                if after and time.time() - last_change >= quiet_seconds:
                    return path, after
        time.sleep(1.0)
    print(f"  ! LIMA's turn for {user_text!r} did not end within {timeout:.0f}s")
    return path, after


def assistant_text(messages):
    """Everything LIMA said in these messages, as one string."""
    return "\n".join(message_text(m) for m in messages if m.get("role") == "assistant")


def tool_calls(messages):
    """The (name, arguments dict) of every tool LIMA called in these messages, in order."""
    calls = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except ValueError:
                arguments = {"_raw": function.get("arguments")}
            calls.append((function.get("name"), arguments))
    return calls


def describe_turn(messages, limit=300):
    """A short, single-line summary of a turn for a failure message: tools called and reply."""
    names = [name for name, _args in tool_calls(messages)]
    reply = " ".join(assistant_text(messages).split())
    if len(reply) > limit:
        reply = reply[:limit] + "..."
    return f"tools called: {names or 'none'}; LIMA said: {reply!r}"
