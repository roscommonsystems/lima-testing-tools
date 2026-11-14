"""
Feature: Newer Settings options present.

Three controls were added to LIMA's Settings dialog after 2.0 and are easy to lose in a layout
refactor, because nothing else in the suite opens them by name:

  * "Say when LIMA summarizes the conversation" — accessible name
    "Speak When Summarizing Checkbox" (settings_dialog.py ~L162, added in commit ee0206a,
    "feat: let the user silence the compaction notice (#178)");
  * the compaction threshold — accessible name "Conversation Compaction Threshold Dropdown"
    (~L721, commit bfaa1b5, "feat: expose the conversation compaction threshold in Settings
    (#177)");
  * the maximum agent steps — accessible name "Maximum Agent Steps Dropdown" (~L700, commit
    3f49162, "feat: add configurable max agent loops with context compression").

The test opens Settings the way the suite already does (lima_tool_tests.py "SETTINGS DIALOG":
File menu item by accessible name, Enter as the key fallback) and looks each accessible name up
in the dialog's UI Automation subtree. Accessible names are used rather than visible text
because they are what a screen reader announces and what the app deliberately sets; the visible
text of the checkbox is a sentence that may be reworded, the accessible name is stable.

Assumption about tabs: in v2.1.0.5 the dialog is two columns with no tab widget, so every
control is in one tree and no tab has to be selected. If a TabControl is found, each tab is
selected in turn anyway, so adding tabs later does not quietly turn this into a false failure.
The dialog is closed with Cancel or Escape and never Save: this test only observes.
"""

import time

import pyautogui
import uiautomation as auto

from lima_test_utils import (
    TEST_PASSED, TEST_FAILED, open_file_menu_item, SLEEP_A, SLEEP_B,
)
from feature_tests import _common

RESULT_NAME = "Feature: Newer Settings options present"

# File > Settings, as the tool sweep opens it (menu item by accessible name, Enter as fallback).
MENU_ITEM_NAME = "Settings"
MENU_NAV_KEYS = ["enter"]
DIALOG_TITLE = "LIMA Settings"

# (what it is, the accessible name settings_dialog.py sets, the commit that added it)
REQUIRED_CONTROLS = (
    ("announce-compaction checkbox (#178)", "Speak When Summarizing Checkbox", "ee0206a"),
    ("compaction threshold (#177)", "Conversation Compaction Threshold Dropdown", "bfaa1b5"),
    ("maximum agent steps", "Maximum Agent Steps Dropdown", "3f49162"),
)

DIALOG_TIMEOUT = 20.0
MAX_TREE_NODES = 4000


def _find_dialog(title_keyword, timeout=DIALOG_TIMEOUT):
    """The open Settings window, or None on timeout (any depth, matched by window type)."""
    deadline = time.time() + timeout
    while True:
        root = auto.GetRootControl()
        stack = [(child, 0) for child in root.GetChildren()]
        seen = 0
        while stack and seen < MAX_TREE_NODES:
            control, depth = stack.pop()
            seen += 1
            try:
                if (control.ControlTypeName in ("WindowControl", "PaneControl")
                        and title_keyword.lower() in (control.Name or "").lower()):
                    return control
                if depth < 6:
                    stack.extend((child, depth + 1) for child in control.GetChildren())
            except Exception:
                continue
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def _control_texts(control):
    """Every non-empty accessible name in the dialog's subtree, in tree order, deduplicated."""
    names = []
    stack = [(control, 0)]
    seen = 0
    while stack and seen < MAX_TREE_NODES:
        current, depth = stack.pop()
        seen += 1
        try:
            name = (current.Name or "").strip()
            if name and name not in names:
                names.append(name)
            if depth < 20:
                stack.extend((child, depth + 1) for child in current.GetChildren())
        except Exception:
            continue
    return names


def _find_tab_control(control):
    """The dialog's TabControl, if it has one."""
    stack = [(control, 0)]
    seen = 0
    while stack and seen < MAX_TREE_NODES:
        current, depth = stack.pop()
        seen += 1
        try:
            if current.ControlTypeName == "TabControl":
                return current
            if depth < 20:
                stack.extend((child, depth + 1) for child in current.GetChildren())
        except Exception:
            continue
    return None


def _select_tab(tab_item):
    """Bring a tab to the front, by UIA selection if possible and a click otherwise."""
    try:
        tab_item.GetSelectionItemPattern().Select()
        return
    except Exception:
        pass
    try:
        tab_item.Click()
    except Exception as error:
        print(f"  ! Could not select tab {tab_item.Name!r}: {error}")


def _collect_all_tabs(dialog, tab_control, first_names):
    """
    Names from the dialog plus every tab's names, selecting each tab in turn.

    UIA does build the tree of a non-active Qt tab (the widgets exist), but not every toolkit
    does, and a control inside an unselected tab can be reported as off-screen. Selecting each
    tab costs a few seconds and makes the check independent of that difference.
    """
    names = list(first_names)
    try:
        items = [child for child in tab_control.GetChildren()
                 if child.ControlTypeName == "TabItemControl"]
    except Exception:
        return names
    for item in items:
        print(f"  Selecting Settings tab {item.Name!r}")
        _select_tab(item)
        time.sleep(SLEEP_B)
        for name in _control_texts(dialog):
            if name not in names:
                names.append(name)
    return names


def _dialog_still_open(control):
    """True while the Settings window still exists."""
    try:
        hwnd = control.NativeWindowHandle
        if hwnd:
            return _common.is_open(hwnd)
    except Exception:
        pass
    try:
        return bool(control.Exists(maxSearchSeconds=0.2))
    except Exception:
        return False


def _find_button(control, names):
    """A button in the dialog whose accessible name or text is one of names."""
    wanted = {name.lower() for name in names}
    stack = [(control, 0)]
    seen = 0
    while stack and seen < MAX_TREE_NODES:
        current, depth = stack.pop()
        seen += 1
        try:
            if (current.ControlTypeName == "ButtonControl"
                    and (current.Name or "").strip().lower() in wanted):
                return current
            if depth < 20:
                stack.extend((child, depth + 1) for child in current.GetChildren())
        except Exception:
            continue
    return None


def _close_without_saving(control):
    """
    Close the dialog with Cancel, or Escape. Never Save.

    Only a button whose accessible name is exactly the Cancel button's is clicked, so a
    mis-aimed keyboard sequence can never commit a changed setting.
    """
    if not _dialog_still_open(control):
        return True
    button = _find_button(control, ("Cancel Settings Button", "Cancel"))
    if button is not None:
        try:
            print("  Closing Settings with Cancel")
            button.Click()
        except Exception as error:
            print(f"  ! Cancel click failed: {error}")
    if not _common.wait_until(lambda: not _dialog_still_open(control), 5.0):
        print("  ! Cancel did not close the dialog; pressing Escape")
        try:
            control.SetFocus()
        except Exception:
            pass
        pyautogui.press("escape")
        time.sleep(SLEEP_A)
    return not _dialog_still_open(control)


def _open_settings(executor):
    """Open File > Settings and return its UIA control, or None."""
    for attempt in range(1, 3):
        if not _common.ensure_lima_ready(executor):
            continue
        print(f"  Opening File > {MENU_ITEM_NAME} (attempt {attempt})")
        open_file_menu_item(MENU_ITEM_NAME, MENU_NAV_KEYS)
        time.sleep(SLEEP_B)
        dialog = _find_dialog(DIALOG_TITLE)
        if dialog is not None:
            return dialog
    return None


def _run_case(executor, opened):
    """Do the scenario; return (passed, message). opened receives the dialog for cleanup."""
    dialog = _open_settings(executor)
    if dialog is None:
        return False, (f"File > {MENU_ITEM_NAME} did not open a {DIALOG_TITLE!r} dialog within "
                       f"{DIALOG_TIMEOUT:.0f}s of clicking the menu item")
    opened.append(dialog)

    names = _control_texts(dialog)
    missing = [(label, accessible_name, commit)
               for label, accessible_name, commit in REQUIRED_CONTROLS
               if accessible_name not in names]

    if missing:
        # A tab may be holding a control that UIA does not expose while the tab is in the
        # background (see the module docstring); look again with each tab selected.
        tab_control = _find_tab_control(dialog)
        if tab_control is not None:
            print("  Some controls were not in the tree; selecting each tab and looking again")
            names = _collect_all_tabs(dialog, tab_control, names)
            missing = [(label, accessible_name, commit)
                       for label, accessible_name, commit in REQUIRED_CONTROLS
                       if accessible_name not in names]

    if missing:
        described = "; ".join(f"{label} (expected accessible name {accessible_name!r}, added in "
                              f"{commit})" for label, accessible_name, commit in missing)
        seen = [name for name in names if len(name) > 3][:25]
        return False, (f"{len(missing)} of {len(REQUIRED_CONTROLS)} newer Settings controls are "
                       f"missing from the dialog's UI Automation tree: {described}. Names the "
                       f"dialog did expose (first 25): {seen!r}. If the UI language is not "
                       f"English the accessible names are translated, and this test assumes the "
                       f"suite's English UI.")

    found = ", ".join(f"{label} = {accessible_name!r}"
                      for label, accessible_name, _commit in REQUIRED_CONTROLS)
    return True, f"All three newer Settings controls are present: {found}."


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    opened = []
    try:
        passed, message = _run_case(executor, opened)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # Close without saving, whatever happened: Cancel/Escape only, so no setting changes.
        for dialog in opened:
            if not _close_without_saving(dialog):
                message += (" CLEANUP FAILED: the Settings dialog is still open; it was not saved, "
                            "but the next test's keystrokes may go to it.")
                print("  ! The Settings dialog is still open")
        time.sleep(SLEEP_A)

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
