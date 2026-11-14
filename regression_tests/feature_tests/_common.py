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

import pyautogui
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


def open_notepad(file_path=None, timeout=45.0, attempts=2):
    """
    Start Notepad (optionally on a file) and wait for its window.

    Closes any running Notepad first (close_notepads), so the window found is the one this
    call started and a test never acts on a window left over from an earlier test. The first
    start after Windows boots can be slow, so a launch that shows no window in time is retried
    once before giving up.

    Returns:
        int: the Notepad window handle, or 0 when no window appeared.
    """
    for attempt in range(1, attempts + 1):
        close_notepads()
        args = ["notepad.exe"] + ([file_path] if file_path else [])
        subprocess.Popen(args)
        windows = wait_until(notepad_windows, timeout)
        if windows:
            hwnd, title = windows[0]
            print(f"  Opened Notepad: {title!r}")
            return hwnd
        print(f"  ! Notepad's window did not appear within {timeout:.0f}s (attempt {attempt})")
    return 0


def _notepad_text_control(hwnd):
    """Notepad's text area: a Document control (Windows 11, RichEditD2DPT) or an Edit control
    (classic Notepad). The typed finders matter: a plain window.Control(...) match is a generic
    Control without GetTextPattern/GetValuePattern."""
    window = auto.ControlFromHandle(hwnd)
    if window is None:
        return None
    for find in (window.DocumentControl, window.EditControl):
        control = find(searchDepth=12)
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
    Empty the current Notepad document, e.g. text a test had LIMA type into an untitled tab.

    Only use it on a document the test itself created: emptying a file's tab would change it.
    """
    control = _notepad_text_control(hwnd)
    if control is None:
        return
    try:
        control.GetValuePattern().SetValue("")
    except Exception as error:
        print(f"  ! Could not empty Notepad's document: {error}")


def _cancel_save_prompt(hwnd, timeout=1.5):
    """
    If closing a tab made Notepad ask to save, answer Cancel and return True.

    Never "Don't save": the tab may hold someone's unsaved notes. A tab that asks is left
    open, and close_notepads ends the process instead, which Windows 11 Notepad restores
    without loss.
    """
    # The usual case is that the tab closed and took the window with it while this searched;
    # UIA then raises from the vanished tree, which just means "no prompt".
    try:
        window = auto.ControlFromHandle(hwnd)
        if window is None:
            return False
        cancel = window.ButtonControl(searchDepth=15, Name="Cancel")
        if not cancel.Exists(maxSearchSeconds=timeout):
            return False
    except Exception:
        return False
    try:
        cancel.GetInvokePattern().Invoke()
    except Exception:
        pyautogui.press("escape")
    time.sleep(SLEEP_A)
    return True


def close_notepad_window(hwnd, max_tabs=20):
    """
    Close a Notepad window one tab at a time (Ctrl+W), so it has nothing left to restore.

    Windows 11 Notepad reopens the tabs of its last session, also after its process is ended.
    A test that ends Notepad with its file still open leaves a tab for a file the test then
    deletes, and the next Notepad opens with a "can't find the file" error that the next test
    (and the model) trips over. Closing the tab itself is the only way to drop it from the
    session. Stops at the first tab that asks to save (see _cancel_save_prompt).

    Returns:
        bool: True when the window is gone.
    """
    for _ in range(max_tabs):
        if not is_open(hwnd):
            return True
        if not activate_window(hwnd):
            break
        pyautogui.hotkey("ctrl", "w")
        if _cancel_save_prompt(hwnd):
            print("  ! A Notepad tab has unsaved changes; leaving it for Notepad to restore")
            break
        wait_until(lambda: not is_open(hwnd), 2.0)
    return not is_open(hwnd)


def close_notepads():
    """
    Close every Notepad window tab by tab, then end whatever is still running.

    Use this instead of close_apps for Notepad: see close_notepad_window for why.
    """
    for hwnd, _title in notepad_windows():
        try:
            close_notepad_window(hwnd)
        except Exception as error:
            print(f"  ! Could not close Notepad's tabs: {error}")
    close_apps(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)


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


def find_user_message(executor, user_text, since=0.0):
    """
    The newest saved conversation with a user message equal to user_text.

    Args:
        since: ignore conversation files last written before this time (time.time()). LIMA's
            data folder keeps every earlier run's conversations, and most instructions are the
            same every run, so without it an old run's file answers for this one.

    Returns:
        (path, conversation, index of that message) or (None, None, None).
    """
    wanted = user_text.strip().casefold()
    files = sorted(((path, mtime) for path, mtime in list_conversation_files(executor).items()
                    if mtime >= since), key=lambda item: item[1], reverse=True)
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


# How far before wait_for_turn_end's call a conversation file may have been written and still
# count as this turn's. LIMA saves at the end of a turn, which takes a model call, so the save
# for an instruction sent just before the call is always later than this.
SINCE_SLACK_SECONDS = 2.0


def wait_for_turn_end(executor, user_text, timeout=TURN_TIMEOUT, quiet_seconds=20.0, since=None):
    """
    Wait until LIMA has finished answering user_text, judged from its saved conversation.

    Call it straight after send_instruction(user_text). Only conversation files written after
    that (since, default: the time of this call minus SINCE_SLACK_SECONDS) count, so a file an
    earlier run saved for the same words can't end the wait before this turn has run.

    The turn has ended when the messages after user_text end in an assistant reply with no
    pending tool call and no approval popup is open. A turn that ends on an action with no
    closing words is also accepted once the file has been unchanged for quiet_seconds.

    Returns:
        (path, messages after user_text) once the turn has ended, or (path or None, messages
        so far) on timeout. The caller decides what a timeout means for its test.
    """
    if since is None:
        since = time.time() - SINCE_SLACK_SECONDS
    deadline = time.time() + timeout
    path, after, last_change, last_count = None, [], time.time(), -1
    while time.time() < deadline:
        path, conversation, index = find_user_message(executor, user_text, since)
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
