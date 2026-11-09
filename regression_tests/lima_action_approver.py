"""
LIMA Action Approver
Answers LIMA's "Approve this action?" popup — automatically during ordinary tests, and
deliberately (Yes or No, by button / Y-N key / Ctrl+Alt+Y-N hotkey) in approval tests.

LIMA 2.x asks for approval before every action that changes the screen (clicking, typing,
scrolling, opening a program or website, pressing keys, controlling a window), and it can
ask several times in one turn. When the popup appears is unpredictable, so a background
thread watches for it for the whole run and always presses Yes. That is the default: the
suite stays unattended.

The approval tests need the opposite — to see the popup and answer it themselves — so
``manual_approvals()`` pauses both the background thread and the pre-typing approval in
``type_into_lima``, and always restores them afterwards.

Answering No opens a second popup (``quick_input_dialog.py``) asking for a replacement
instruction. Closing it empty ends the turn with the action not run; typing text makes that
text the user's new instruction and LIMA re-plans. Helpers for both are at the bottom.
"""

import contextlib
import ctypes
import json
import os
import threading
import time
from dataclasses import dataclass

import pyautogui
import uiautomation as uia

from lima_test_utils import enum_top_level_windows, get_window_title, get_window_class_name

# Title of LIMA's ActionApprovalDialog in each language LIMA ships (English, Vietnamese,
# Tagalog). The Yes button ends in "(Y)" in every language.
APPROVAL_TITLES = ("Approve this action?",
                   "Chấp nhận hành động này?",
                   "Aprubahan ang aksyong ito?")

# The dialog's first label. "LIMA wants to:" introduces a gated action; "LIMA asks:" is the
# model's own yes/no question (the ask_permission tool), which reads as a whole sentence.
# Translations read from lima_vi.ts / lima_tl.ts in LIMA's source.
ACTION_HEADINGS = ("LIMA wants to:", "LIMA muốn:", "Gustong gawin ng LIMA:")
QUESTION_HEADINGS = ("LIMA asks:", "LIMA hỏi:", "Tanong ng LIMA:")

# Title of the replacement-instruction popup opened after a No (lima.py
# _open_replacement_input). The "Ask Lima" quick-input popup shares the same class but has a
# different title, so it is never mistaken for this one.
REPLACEMENT_TITLES = ("What should I do instead?",
                      "Bạn muốn tôi làm gì thay thế?",
                      "Ano ang dapat kong gawin sa halip?")

# How to answer a prompt. 'button' is the default because it needs no focus and no global
# hotkey: UIA Invoke on Yes/No. 'key' is the plain Y / N LIMA listens for system-wide while
# the dialog is open. 'hotkey' is Ctrl+Alt+Y / Ctrl+Alt+N from LIMA's config, which also
# works when Windows has dropped the keyboard hook.
VIA_BUTTON = "button"
VIA_KEY = "key"
VIA_HOTKEY = "hotkey"
ANSWER_VIAS = (VIA_BUTTON, VIA_KEY, VIA_HOTKEY)

# LIMA's defaults (startup.py DEFAULT_CONFIG). Only used when data\config.json can't be read.
DEFAULT_APPROVE_HOTKEY = {"modifier": "ctrl+alt", "key": "y"}
DEFAULT_DENY_HOTKEY = {"modifier": "ctrl+alt", "key": "n"}

WM_CLOSE = 0x0010

# The background thread and type_into_lima (main thread) both approve popups. Taking turns
# stops both acting on the same popup, where the loser would find it already closed.
_approve_lock = threading.Lock()

# Set while a test answers popups itself. Checked by approve_action_prompts(), which is the
# single place both the background thread and type_into_lima go through, so pausing here
# pauses both. Depth-counted so nested manual_approvals() blocks unwind correctly.
_manual_lock = threading.RLock()
_manual_depth = 0

# The approver the executor started, so manual_approvals() can stop and restart it without
# every test having to pass it in.
_active_approver = None


@dataclass
class ActionPrompt:
    """An open approval popup: its window handle, what it is asking, and the text shown."""

    hwnd: int
    kind: str          # 'action' for "LIMA wants to:", 'question' for "LIMA asks:"
    heading: str       # the localized heading exactly as LIMA showed it
    description: str   # the action or question itself
    title: str         # the localized dialog title ("Approve this action?")

    def __str__(self):
        return f"{self.kind} prompt: {self.description!r}"


# --------------------------------------------------------------------------------------
# Finding and reading prompts
# --------------------------------------------------------------------------------------

def find_action_prompts():
    """Return the window handles of every visible LIMA approval popup."""
    return [
        hwnd for hwnd in enum_top_level_windows()
        if get_window_title(hwnd) in APPROVAL_TITLES
        and get_window_class_name(hwnd).startswith("Qt")
        and ctypes.windll.user32.IsWindowVisible(hwnd)
    ]


def _read_labels(prompt_control):
    """Return the dialog's text labels in layout order (heading first, then description)."""
    return [control.Name for control in prompt_control.GetChildren()
            if control.ControlTypeName == "TextControl" and control.Name]


def _classify(heading):
    """Map a dialog heading to 'question' or 'action' (unknown languages default to action)."""
    text = (heading or "").strip()
    if text in QUESTION_HEADINGS:
        return "question"
    return "action"


def read_action_prompt(hwnd):
    """Read one approval popup into an ActionPrompt, or return None if it has gone."""
    try:
        prompt_control = uia.ControlFromHandle(hwnd)
        labels = _read_labels(prompt_control)
    except Exception:
        return None
    heading = labels[0] if labels else ""
    description = labels[-1] if len(labels) > 1 else ""
    return ActionPrompt(
        hwnd=hwnd,
        kind=_classify(heading),
        heading=heading,
        description=description,
        title=get_window_title(hwnd),
    )


def wait_for_action_prompt(timeout=60.0, kind=None, poll_seconds=0.25):
    """
    Wait for one of LIMA's approval popups.

    Args:
        timeout: seconds to wait before giving up.
        kind: None for either kind, or 'action' / 'question' to wait for that one only.
        poll_seconds: how often to look.

    Returns:
        ActionPrompt, or None if no matching popup appeared in time.
    """
    deadline = time.time() + timeout
    while True:
        for hwnd in find_action_prompts():
            prompt = read_action_prompt(hwnd)
            if prompt is not None and (kind is None or prompt.kind == kind):
                return prompt
        if time.time() >= deadline:
            return None
        time.sleep(poll_seconds)


# --------------------------------------------------------------------------------------
# Answering a prompt
# --------------------------------------------------------------------------------------

def _lima_install_path(install_path=None):
    """LIMA's install directory, from the argument or the discovered executable."""
    if install_path:
        return install_path
    try:
        from lima_test_utils import find_lima_executable
        exe_path = find_lima_executable()
        return os.path.dirname(exe_path) if exe_path else None
    except Exception:
        return None


def read_lima_config(install_path=None):
    """Return LIMA's data\\config.json as a dict ({} when it can't be read)."""
    base = _lima_install_path(install_path)
    if not base:
        return {}
    try:
        with open(os.path.join(base, "data", "config.json"), encoding="utf-8") as config_file:
            return json.load(config_file)
    except (OSError, ValueError):
        return {}


def _hotkey_keys(entry, default):
    """Turn a {"modifier": "ctrl+alt", "key": "y"} config entry into pyautogui key names."""
    entry = entry if isinstance(entry, dict) else {}
    modifier = entry.get("modifier") or default["modifier"]
    key = entry.get("key") or default["key"]
    modifiers = [part for part in str(modifier).replace("+", " ").split() if part]
    return modifiers + [str(key)]


def get_answer_hotkeys(install_path=None):
    """
    Return LIMA's real approve/deny hotkeys as pyautogui key lists.

    The config is read rather than assumed, because a user who changed the hotkeys in
    Settings would otherwise leave the hotkey test pressing the wrong keys:

        {'approve': ['ctrl', 'alt', 'y'], 'deny': ['ctrl', 'alt', 'n']}
    """
    config = read_lima_config(install_path)
    return {
        "approve": _hotkey_keys(config.get("approve_action_hotkey"), DEFAULT_APPROVE_HOTKEY),
        "deny": _hotkey_keys(config.get("deny_action_hotkey"), DEFAULT_DENY_HOTKEY),
    }


def _prompt_hwnd(prompt):
    """Accept an ActionPrompt or a raw window handle."""
    return prompt.hwnd if isinstance(prompt, ActionPrompt) else prompt


def _wait_until_closed(hwnd, timeout):
    """Wait for the popup to disappear; True when it did."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        time.sleep(0.1)
    return not ctypes.windll.user32.IsWindowVisible(hwnd)


def _invoke_answer_button(hwnd, approve):
    """Press Yes/No through UIA. Neither moves the mouse nor takes focus."""
    prompt_control = uia.ControlFromHandle(hwnd)
    suffix = "(Y)" if approve else "(N)"
    button = prompt_control.ButtonControl(searchDepth=3, SubName=suffix)
    button.GetInvokePattern().Invoke()


def answer_action_prompt(prompt, approve, via=VIA_BUTTON, settle_timeout=10.0):
    """
    Answer an approval popup Yes or No.

    Args:
        prompt: an ActionPrompt from wait_for_action_prompt(), or a raw window handle.
        approve: True for Yes, False for No.
        via: VIA_BUTTON (default) invokes the button through UIA; VIA_KEY presses Y or N;
            VIA_HOTKEY presses LIMA's configured Ctrl+Alt+Y / Ctrl+Alt+N.
        settle_timeout: how long to wait for the popup to close. On No the popup closes and
            the replacement popup opens, so this returns before that popup is ready — call
            wait_for_replacement_prompt() next.

    Returns:
        bool: True when the popup closed, i.e. LIMA accepted the answer.
    """
    if via not in ANSWER_VIAS:
        raise ValueError(f"Unknown approve via {via!r}; expected one of {ANSWER_VIAS}")
    hwnd = _prompt_hwnd(prompt)
    if hwnd is None:
        return False

    if via == VIA_BUTTON:
        try:
            _invoke_answer_button(hwnd, approve)
        except Exception as error:
            # Invoke also fails when the popup closed in the meantime.
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True
            print(f"  ! Could not press {'Yes' if approve else 'No'} by UIA ({error}), "
                  f"falling back to the {'Y' if approve else 'N'} key")
            pyautogui.press("y" if approve else "n")
    elif via == VIA_KEY:
        pyautogui.press("y" if approve else "n")
    else:
        hotkeys = get_answer_hotkeys()
        pyautogui.hotkey(*hotkeys["approve" if approve else "deny"])

    closed = _wait_until_closed(hwnd, settle_timeout)
    if not closed:
        print(f"  ! LIMA's approval popup is still open after answering via {via}")
    return closed


# --------------------------------------------------------------------------------------
# The replacement-instruction popup (opened after a No)
# --------------------------------------------------------------------------------------

def find_replacement_prompt():
    """Return the window handle of LIMA's replacement-instruction popup, or None."""
    for hwnd in enum_top_level_windows():
        if (get_window_title(hwnd) in REPLACEMENT_TITLES
                and get_window_class_name(hwnd).startswith("Qt")
                and ctypes.windll.user32.IsWindowVisible(hwnd)):
            return hwnd
    return None


def wait_for_replacement_prompt(timeout=15.0, poll_seconds=0.25):
    """Wait for the replacement-instruction popup; None if it never appears."""
    deadline = time.time() + timeout
    while True:
        hwnd = find_replacement_prompt()
        if hwnd:
            return hwnd
        if time.time() >= deadline:
            return None
        time.sleep(poll_seconds)


def close_replacement_prompt(prompt=None, timeout=10.0):
    """
    Close the replacement popup without typing anything.

    Closing it empty is what makes LIMA end the turn with the action not run (lima.py
    _on_replacement_closed -> cancelled). WM_CLOSE is used rather than Escape so the popup
    does not need to be the foreground window — the test may have moved focus elsewhere.

    Returns:
        bool: True when the popup is gone.
    """
    hwnd = _prompt_hwnd(prompt) or find_replacement_prompt()
    if not hwnd:
        return True
    try:
        ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    except Exception as error:
        print(f"  ! Could not close the replacement popup ({error})")
        return False
    return _wait_until_closed(hwnd, timeout)


def submit_replacement_instruction(text, prompt=None, timeout=10.0, type_interval=0.02):
    """
    Type a replacement instruction into the popup and press Enter.

    That text becomes the user's new instruction and LIMA re-plans from it. The popup's
    line edit is focused through UIA first, so typing lands there even if focus moved.

    Returns:
        bool: True when the popup closed after Enter (i.e. the text was submitted).
    """
    hwnd = _prompt_hwnd(prompt) or find_replacement_prompt()
    if not hwnd or not (text or "").strip():
        return False
    try:
        edit = uia.ControlFromHandle(hwnd).EditControl(searchDepth=3)
        edit.SetFocus()
        time.sleep(0.2)
    except Exception as error:
        print(f"  ! Could not focus the replacement popup's input ({error})")
    pyautogui.write(text, interval=type_interval)
    time.sleep(0.2)
    pyautogui.press("enter")
    return _wait_until_closed(hwnd, timeout)


# --------------------------------------------------------------------------------------
# Auto-approving (the default) and pausing it
# --------------------------------------------------------------------------------------

def is_manual_approval_active():
    """True while a manual_approvals() block is in charge of answering popups."""
    return _manual_depth > 0


def approve_action_prompts():
    """
    Press Yes on every open LIMA approval popup.

    Uses the Yes button's UIA Invoke, which neither moves the mouse nor changes focus (the
    popup never takes focus, and tests such as Move Mouse To check the cursor position).
    Falls back to pressing Y, which LIMA listens for system-wide while the popup is open.

    Does nothing while manual_approvals() is active — this is the one path the background
    thread and type_into_lima share, so skipping here pauses both.

    Returns:
        list: The description of each prompt approved.
    """
    if is_manual_approval_active():
        return []
    approved = []
    with _approve_lock:
        for hwnd in find_action_prompts():
            prompt = read_action_prompt(hwnd)
            description = prompt.description if prompt else ""
            kind = prompt.kind if prompt else "action"
            try:
                _invoke_answer_button(hwnd, approve=True)
            except Exception as error:
                # Invoke also fails when the popup closed in the meantime. LIMA stops listening
                # for Y then, so a Y pressed now would be typed into whatever has focus.
                if not ctypes.windll.user32.IsWindowVisible(hwnd):
                    continue
                print(f"  ! Could not press Yes on LIMA's approval popup ({error}), pressing Y instead")
                pyautogui.press('y')
            print(f"  OK Auto-approved LIMA {kind}: {description!r}")
            approved.append(description)
    return approved


def dismiss_pending_approvals(attempts=4):
    """
    Leave no approval or replacement popup open.

    Denies anything LIMA is waiting on (a No resolves the pending decision) and closes the
    replacement popup empty, which ends the turn. Used for cleanup, including after a failed
    test, so the next test never starts with a popup blocking LIMA's worker thread.
    """
    for _ in range(attempts):
        prompts = find_action_prompts()
        if prompts:
            for hwnd in prompts:
                prompt = read_action_prompt(hwnd) or ActionPrompt(
                    hwnd=hwnd, kind="action", heading="", description="", title="")
                print(f"  Cleaning up open approval {prompt}")
                answer_action_prompt(prompt, approve=False)
            continue
        if find_replacement_prompt():
            print("  Cleaning up the replacement popup (closing it empty)")
            close_replacement_prompt()
            continue
        return


def set_action_approver(approver):
    """Record the running approver so manual_approvals() can pause and restart it."""
    global _active_approver
    _active_approver = approver


@contextlib.contextmanager
def manual_approvals(approver=None):
    """
    Take over LIMA's approval popups for the duration of the block.

    Pauses the background ActionApprover and stops type_into_lima from approving popups
    before typing, then restores both — including when the block raises, so one failing test
    can't leave the rest of the run unattended.

    While this is active, type_into_lima will NOT answer a popup for you. Typing an "n" (or
    any text containing one) into LIMA while a popup is open would deny it, so answer or close
    the popup before typing; type_into_lima is safe again once the popup is gone.

    Example:
        with manual_approvals():
            send_instruction("open notepad")
            prompt = wait_for_action_prompt(timeout=60, kind="action")
            answer_action_prompt(prompt, approve=False)
            close_replacement_prompt()
    """
    global _manual_depth
    approver = approver or _active_approver
    with _manual_lock:
        _manual_depth += 1
        if _manual_depth == 1:
            print("  Paused automatic approval — this test answers LIMA's popups itself")
            if approver is not None:
                approver.pause()
    try:
        yield approver
    finally:
        with _manual_lock:
            _manual_depth -= 1
            if _manual_depth == 0:
                if approver is not None:
                    approver.resume()
                print("  Resumed automatic approval")


class ActionApprover:
    """Background thread that approves LIMA's approval popups for as long as it runs."""

    def __init__(self, poll_seconds=0.5):
        self.poll_seconds = poll_seconds
        self.approved_count = 0
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Start watching for approval popups."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="LimaActionApprover", daemon=True)
        self._thread.start()
        print("  OK Watching for LIMA approval popups (will always approve)")

    def stop(self):
        """Stop watching and wait for the thread to finish."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        print(f"  Auto-approved {self.approved_count} LIMA prompt(s) during the run")

    def pause(self):
        """Stop watching so a test can answer popups itself (see manual_approvals)."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            # The thread is stuck inside a UIA call. It can't approve anything more now:
            # approve_action_prompts() returns immediately while manual mode is on.
            print("  ! Action approver thread is still finishing its current poll")
        self._thread = None

    def resume(self):
        """Start watching again after pause()."""
        if self._thread is not None:
            return
        self.start()

    def _run(self):
        # UI Automation is COM-based and must be initialised on every thread that uses it.
        with uia.UIAutomationInitializerInThread():
            while not self._stop_event.is_set():
                try:
                    self.approved_count += len(approve_action_prompts())
                except Exception as error:
                    print(f"  ! Action approver error: {error}")
                self._stop_event.wait(self.poll_seconds)
