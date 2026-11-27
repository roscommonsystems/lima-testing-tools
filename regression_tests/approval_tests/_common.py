"""
Shared helpers for the approval tests.

Everything a test needs to get LIMA into a known state, send it an instruction, watch for an
app, and clean up afterwards — so each test module is just the scenario it is testing and the
follow-up tests (replacement instruction, an unanswered wait, LIMA's own question, the Y/N
keys and hotkeys) can be added as one new file each without touching this one.
"""

import time
import ctypes
import os
import shutil
from pathlib import Path
from contextlib import contextmanager

import psutil
import pyautogui
import pygetwindow as gw

from lima_test_utils import (
    type_into_lima, SLEEP_A, SLEEP_B, SLEEP_C,
)
from lima_action_approver import (
    dismiss_pending_approvals, find_action_prompts, find_replacement_prompt,
    read_lima_config,
)
from lima_backup import backup_data, close_lima_and_restore, seed_config
from lima_test_errors import TestSetupError, TestCleanupError


# --------------------------------------------------------------------------------------
# LIMA
# --------------------------------------------------------------------------------------

def _require_approval_config(executor):
    config = read_lima_config(executor.process_manager.install_path)
    if config.get("ask_before_every_action") is not True:
        raise TestSetupError(
            "SETUP FAILED: approval tests require ask_before_every_action=true in "
            "LIMA's config.json; opening a program otherwise runs without approval.")


def _test_answer_hotkeys(executor):
    """Find two unoccupied test bindings without changing any desktop shortcuts.

    NVDA's desktop shortcut commonly reserves Ctrl+Alt+N even while NVDA is closed.
    Probe temporary function-key bindings with Windows, releasing each probe immediately.
    The surrounding approval_config backup restores the user's bindings after the test.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    config = read_lima_config(executor.process_manager.install_path)
    reserved = {
        str(value.get("key", "")).lower()
        for name, value in config.items()
        if name.endswith("_hotkey") and isinstance(value, dict)
        and set(str(value.get("modifier", "")).lower().split("+")) == {"ctrl", "alt", "shift"}
    }
    bindings = []
    for number in (11, 12, 9, 10, 13, 14):
        key = f"f{number}"
        if key in reserved:
            continue
        # MOD_ALT | MOD_CONTROL | MOD_SHIFT; F1 is virtual key 0x70.
        ctypes.set_last_error(0)
        if user32.RegisterHotKey(None, 0xB000, 0x0007, 0x70 + number - 1):
            try:
                bindings.append({"modifier": "ctrl+alt+shift", "key": key})
            finally:
                user32.UnregisterHotKey(None, 0xB000)
        elif ctypes.get_last_error() != 1409:
            raise TestSetupError(f"SETUP FAILED: could not probe {key}: Windows error {ctypes.get_last_error()}")
        if len(bindings) == 2:
            return dict(zip(("approve_action_hotkey", "deny_action_hotkey"), bindings))
    raise TestSetupError("SETUP FAILED: no two available approval test hotkeys")


@contextmanager
def approval_config(executor, answer_hotkeys=False):
    """Enable action approval before launching LIMA; restore config even after failure.

    Use inside manual_approvals(), so the background approver stays paused during setup
    and cleanup. The setting also makes the question test exercise pre-approval of an
    otherwise gated action. Keep it enabled through the keyboard module's fresh launches.
    With answer_hotkeys=True, also seed two available temporary answer bindings.
    """
    if not executor.process_manager.install_path:
        raise TestSetupError("SETUP FAILED: LIMA's install path is unknown")
    recovery = Path(executor.process_manager.install_path, "data", ".lima-approval-backup")
    if recovery.exists():
        raise TestCleanupError(
            f"CLEANUP FAILED: unresolved approval config backup at {recovery}. "
            "Close LIMA and restore config.json from this directory (or delete the live "
            "config if config-was-missing exists), then remove the backup directory.")
    try:
        close_error = executor.process_manager.close()
        if close_error:
            raise TestSetupError(f"SETUP FAILED: could not close LIMA before config backup: {close_error}")
        backup = backup_data(executor, "config.json")
        recovery.mkdir(parents=True)
        original = backup.backups[0]
        snapshot = recovery / ("config.json" if original.existed else "config-was-missing")
        with snapshot.open("wb") as handle:
            handle.write(original.original)
            handle.flush()
            os.fsync(handle.fileno())
    except TestSetupError:
        raise
    except Exception as error:
        raise TestSetupError(f"SETUP FAILED: could not back up approval config: {error}") from error
    try:
        try:
            settings = _test_answer_hotkeys(executor) if answer_hotkeys else {}
            seed_config(executor, ask_before_every_action=True, **settings)
            _require_approval_config(executor)
        except Exception as error:
            raise TestSetupError(f"SETUP FAILED: approval config: {error}") from error
        yield
    finally:
        try:
            cleanup_note = close_lima_and_restore(executor, backup)
            if cleanup_note:
                raise TestCleanupError(cleanup_note)
            shutil.rmtree(recovery)
        except Exception as error:
            raise TestCleanupError(
                f"CLEANUP FAILED: approval test config restore: {error}. "
                f"Original config backup retained at {recovery}; stop testing until restored.") from error


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
    _require_approval_config(executor)
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

    _require_approval_config(executor)
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
