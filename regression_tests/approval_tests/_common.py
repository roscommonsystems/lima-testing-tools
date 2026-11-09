"""
Shared helpers for the approval tests.

Everything a test needs to get LIMA into a known state, send it an instruction, watch for an
app, and clean up afterwards — so each test module is just the scenario it is testing and the
follow-up tests (replacement instruction, an unanswered wait, LIMA's own question, the Y/N
keys and hotkeys) can be added as one new file each without touching this one.
"""

import time

import psutil
import pyautogui
import pygetwindow as gw

from lima_test_utils import (
    type_into_lima, SLEEP_A, SLEEP_B, SLEEP_C,
)
from lima_action_approver import (
    dismiss_pending_approvals, find_action_prompts, find_replacement_prompt,
)


# --------------------------------------------------------------------------------------
# LIMA
# --------------------------------------------------------------------------------------

def ensure_lima_ready(executor):
    """
    Make sure LIMA is running, focused, and ready to take an instruction.

    Launches LIMA when it isn't running (a failed or never-run launch leaves the process
    manager with nothing to refocus), otherwise just refocuses the running window. Also
    drops a stray Escape and releases modifier keys the previous test may have left down,
    which would otherwise turn the next keystrokes into Ctrl/Alt combinations.

    Returns:
        bool: True when LIMA's window is ready.
    """
    process_manager = executor.process_manager
    if not process_manager.is_running():
        if not process_manager.exe_full_path:
            print("  ! LIMA executable path is unknown — cannot launch it")
            return False
        print("  Launching LIMA...")
        process_manager.close()
        if not process_manager.launch(process_manager.exe_full_path,
                                      process_manager.install_path):
            print("  ! LIMA did not start")
            return False
        time.sleep(SLEEP_C)

    if not process_manager.refocus(timeout=15):
        print("  ! Could not focus LIMA's window")
        return False

    pyautogui.press("escape")
    time.sleep(SLEEP_A)
    for key in ("win", "ctrl", "alt", "shift", "winleft", "winright"):
        pyautogui.keyUp(key)
    time.sleep(SLEEP_A)
    return True


def send_instruction(text):
    """
    Type an instruction into LIMA's message box and press Enter to submit it.

    While manual_approvals() is active this does NOT answer an approval popup first (see that
    context manager): close or answer any open popup before calling this, or an "n" in the
    text will deny the pending action.
    """
    print(f"  Sending instruction to LIMA: {text!r}")
    type_into_lima(text)
    time.sleep(SLEEP_A)
    pyautogui.press("enter")


# --------------------------------------------------------------------------------------
# Apps (Notepad, Calculator, ...)
# --------------------------------------------------------------------------------------

def _matching_processes(process_names):
    """Return running processes whose executable name is in process_names (case-insensitive)."""
    wanted = {name.lower() for name in process_names}
    matches = []
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = (process.info["name"] or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name in wanted:
            matches.append(process)
    return matches


def _matching_windows(window_keywords):
    """Return windows whose title contains any of window_keywords (case-insensitive)."""
    keywords = [keyword.lower() for keyword in window_keywords]
    try:
        windows = gw.getAllWindows()
    except Exception:
        return []
    return [window for window in windows
            if window.title and any(keyword in window.title.lower() for keyword in keywords)]


def app_running(process_names=(), window_keywords=()):
    """True when one of the named processes or a window with one of the titles is present."""
    return bool(_matching_processes(process_names) or _matching_windows(window_keywords))


def wait_for_app(process_names=(), window_keywords=(), timeout=15.0, poll_seconds=0.25):
    """
    Wait for an app to start.

    Checks the process list as well as window titles: a launched app appears as a process a
    moment before its window settles, and Notepad on Windows 11 is a Store app whose window
    may take a while to show.

    Returns:
        bool: True when the app appeared within timeout.
    """
    deadline = time.time() + timeout
    while True:
        if app_running(process_names, window_keywords):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(poll_seconds)


def close_apps(process_names=(), window_keywords=(), timeout=10.0):
    """
    Close any running instance of the named apps, so a test starts from "not running".

    Terminates matching processes (gracefully first, then forcibly) and closes matching
    windows that belong to something else. Waits up to timeout for them to go.

    Returns:
        list: Names/titles of what was closed (empty when nothing was running).
    """
    closed = []
    for process in _matching_processes(process_names):
        try:
            name = process.info["name"]
            process.terminate()
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                process.kill()
            closed.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for window in _matching_windows(window_keywords):
        try:
            window.close()
            closed.append(window.title)
        except Exception:
            continue

    if closed:
        print(f"  Closed app(s) left over from an earlier test: {closed}")
        deadline = time.time() + timeout
        while time.time() < deadline and app_running(process_names, window_keywords):
            time.sleep(0.25)
    return closed


# --------------------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------------------

def cleanup(process_names=(), window_keywords=()):
    """
    Leave nothing behind: no approval popup, no replacement popup, no app.

    Safe to call after a failure — dismissing a popup LIMA is waiting on (with a No, then
    closing the replacement popup empty) is what lets LIMA's worker thread end the turn
    instead of waiting forever for the next test.
    """
    try:
        dismiss_pending_approvals()
    except Exception as error:
        print(f"  ! Could not dismiss LIMA's popups: {error}")
    close_apps(process_names, window_keywords)


def popups_open():
    """True when LIMA has an approval or replacement popup on screen."""
    return bool(find_action_prompts() or find_replacement_prompt())
