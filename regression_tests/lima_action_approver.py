"""
LIMA Action Approver
Automatically approves LIMA's "Approve this action?" popup so the suite runs unattended.

LIMA 2.0 asks for approval before every action that changes the screen (clicking, typing,
scrolling, opening a program or website, pressing keys, controlling a window), and it can
ask several times in one turn. When the popup appears is unpredictable, so a background
thread watches for it for the whole run and always presses Yes.
"""

import ctypes
import threading

import pyautogui
import uiautomation as uia

from lima_test_utils import enum_top_level_windows, get_window_title, get_window_class_name

# Title of LIMA's ActionApprovalDialog in each language LIMA ships (English, Vietnamese,
# Tagalog). The Yes button ends in "(Y)" in every language.
APPROVAL_TITLES = ("Approve this action?", "Chấp nhận hành động này?", "Aprubahan ang aksyong ito?")


def find_action_prompts():
    """Return the window handles of every visible LIMA approval popup."""
    return [
        hwnd for hwnd in enum_top_level_windows()
        if get_window_title(hwnd) in APPROVAL_TITLES
        and get_window_class_name(hwnd).startswith("Qt")
        and ctypes.windll.user32.IsWindowVisible(hwnd)
    ]


def approve_action_prompts():
    """
    Press Yes on every open LIMA approval popup.

    Uses the Yes button's UIA Invoke, which neither moves the mouse nor changes focus (the
    popup never takes focus, and tests such as Move Mouse To check the cursor position).
    Falls back to pressing Y, which LIMA listens for system-wide while the popup is open.

    Returns:
        list: The description of each action approved.
    """
    approved = []
    for hwnd in find_action_prompts():
        description = ""
        try:
            prompt = uia.ControlFromHandle(hwnd)
            labels = [c.Name for c in prompt.GetChildren() if c.ControlTypeName == "TextControl" and c.Name]
            description = labels[-1] if labels else ""
            yes_button = prompt.ButtonControl(searchDepth=3, SubName="(Y)")
            yes_button.GetInvokePattern().Invoke()
        except Exception as error:
            print(f"  ! Could not press Yes on LIMA's approval popup ({error}), pressing Y instead")
            pyautogui.press('y')
        print(f"  OK Auto-approved LIMA action: {description!r}")
        approved.append(description)
    return approved


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
        print(f"  Auto-approved {self.approved_count} LIMA action(s) during the run")

    def _run(self):
        # UI Automation is COM-based and must be initialised on every thread that uses it.
        with uia.UIAutomationInitializerInThread():
            while not self._stop_event.is_set():
                try:
                    self.approved_count += len(approve_action_prompts())
                except Exception as error:
                    print(f"  ! Action approver error: {error}")
                self._stop_event.wait(self.poll_seconds)
