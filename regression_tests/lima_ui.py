"""
LIMA's own windows, driven over UI Automation.

Shared steps for tests that open one of LIMA's windows (Settings, Conversation History,
Memories, Connections, About, ...) and read or press what is in it: open a menu item by name,
find the window, find a control by its accessible name, press a button, read a list.

Controls are found by accessible name, because that is what a screen reader announces and
what LIMA sets on purpose (``setAccessibleName``). Positions, tab counts and visible wording
change with a layout refactor; the accessible name is what a blind user depends on, so a test
that can't find it has found a real problem.

All names here are the English ones. The suite runs LIMA in English; a test that switches
language has to look controls up by something else (a control type, an order).
"""

import ctypes
import time

import pyautogui
import uiautomation as uia
from PIL import ImageGrab

from lima_test_utils import (
    SLEEP_A, SLEEP_B, CONSOLE_WINDOW_CLASSES,
    enum_top_level_windows, get_window_title, get_window_class_name, get_window_pid,
    get_window_rect, find_lima_uia_window, _open_dialog_item_via_uia,
)

user32 = ctypes.windll.user32

WM_CLOSE = 0x0010

# Most nodes one search will look at. LIMA's largest window (Settings) has a few hundred.
MAX_TREE_NODES = 4000
MAX_TREE_DEPTH = 25

# LIMA's update offer (update_dialog.py UpdateDialog), shown during startup when a newer
# release exists. It is modal, so LIMA does not finish starting until it is answered.
UPDATE_WINDOW_TITLE = "Update Available"
UPDATE_DECLINE_BUTTON_NAMES = ("Not Now Update Button", "Not Now")


# --------------------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------------------

def is_lima_window(hwnd):
    """True for a visible Qt window that is not a test build's console."""
    class_name = get_window_class_name(hwnd)
    is_qt_window = (bool(user32.IsWindowVisible(hwnd)) and class_name.startswith("Qt")
                    and class_name not in CONSOLE_WINDOW_CLASSES)
    return is_qt_window


def find_window(title_keyword, pid=None):
    """
    The handle of LIMA's visible window whose title contains title_keyword, or 0.

    Only Qt windows match, so an editor or browser tab whose title happens to contain the
    same words is never taken for one of LIMA's windows.
    """
    for hwnd in enum_top_level_windows():
        if title_keyword not in get_window_title(hwnd):
            continue
        if pid is not None and get_window_pid(hwnd) != pid:
            continue
        if is_lima_window(hwnd):
            return hwnd
    return 0


def wait_for_window(title_keyword, timeout=20.0, pid=None, poll_seconds=0.25):
    """Wait for one of LIMA's windows by title; its handle, or 0 on timeout."""
    deadline = time.time() + timeout
    while True:
        hwnd = find_window(title_keyword, pid)
        if hwnd or time.time() >= deadline:
            return hwnd
        time.sleep(poll_seconds)


def wait_until_closed(hwnd, timeout=10.0, poll_seconds=0.2):
    """Wait for a window to go away; True when it is gone or hidden."""
    deadline = time.time() + timeout
    while True:
        gone = not (user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd))
        if gone or time.time() >= deadline:
            return gone
        time.sleep(poll_seconds)


def close_window(hwnd, timeout=10.0):
    """
    Ask a window to close (WM_CLOSE), as its title-bar X does; True when it is gone.

    WM_CLOSE rather than Escape, so the window does not need to be in front.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return True
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    closed = wait_until_closed(hwnd, timeout)
    return closed


def screenshot_window(hwnd):
    """A picture of one window as it is on screen (PIL image), or None."""
    rect = get_window_rect(hwnd)
    if not rect:
        return None
    try:
        image = ImageGrab.grab(bbox=rect)
    except Exception as error:
        print(f"  ! Could not take a picture of the window: {error}")
        return None
    return image


# --------------------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------------------

def window_control(hwnd):
    """The UI Automation control of a window handle, or None."""
    try:
        control = uia.ControlFromHandle(hwnd)
    except Exception:
        control = None
    return control


def walk(root, max_nodes=MAX_TREE_NODES, max_depth=MAX_TREE_DEPTH):
    """Every control under root, depth first. A node that vanishes mid-walk is skipped."""
    stack = [(root, 0)]
    seen = 0
    while stack and seen < max_nodes:
        control, depth = stack.pop()
        seen += 1
        yield control
        if depth >= max_depth:
            continue
        try:
            children = control.GetChildren()
        except Exception:
            continue
        # Reversed so the stack pops children in their on-screen order.
        stack.extend((child, depth + 1) for child in reversed(children))


def _name_of(control):
    try:
        name = (control.Name or "").strip()
    except Exception:
        name = ""
    return name


def _type_of(control):
    try:
        control_type = control.ControlTypeName
    except Exception:
        control_type = ""
    return control_type


def find_control(root, names=(), control_type=None, name_contains=None):
    """
    The first control under root that matches, or None.

    Args:
        names: accessible names to accept, compared ignoring case. Several, because a button
            may be reachable by its accessible name or its visible text.
        control_type: e.g. "ButtonControl", "ListControl", "ComboBoxControl".
        name_contains: text the name must contain, ignoring case, instead of names.
    """
    wanted = {name.casefold() for name in names}
    fragment = name_contains.casefold() if name_contains else None
    for control in walk(root):
        if control_type and _type_of(control) != control_type:
            continue
        name = _name_of(control).casefold()
        if wanted and name not in wanted:
            continue
        if fragment and fragment not in name:
            continue
        return control
    return None


def control_names(root):
    """Every non-empty accessible name under root, in tree order, without repeats."""
    names = []
    for control in walk(root):
        name = _name_of(control)
        if name and name not in names:
            names.append(name)
    return names


def press_button(root, names):
    """
    Press the button with one of these accessible names; True when it was pressed.

    UIA Invoke is used first: it needs neither focus nor the mouse. A click is the fallback.
    """
    button = find_control(root, names=names, control_type="ButtonControl")
    if button is None:
        print(f"  ! No button named any of {list(names)}")
        return False
    try:
        button.GetInvokePattern().Invoke()
        return True
    except Exception:
        pass
    try:
        button.Click()
        return True
    except Exception as error:
        print(f"  ! Could not press {_name_of(button)!r}: {error}")
        return False


def list_items(root, list_names):
    """
    The text of each row of the list with one of these accessible names, top to bottom.

    Returns:
        list of str, or None when there is no such list.
    """
    list_control = find_control(root, names=list_names, control_type="ListControl")
    if list_control is None:
        return None
    try:
        children = list_control.GetChildren()
    except Exception:
        return None
    rows = [_name_of(child) for child in children if _type_of(child) == "ListItemControl"]
    return rows


def control_text(control):
    """What a text field or read-only view holds, or None when it can't be read."""
    try:
        text = control.GetValuePattern().Value
        return text
    except Exception:
        pass
    try:
        text = control.GetTextPattern().DocumentRange.GetText(-1)
        return text
    except Exception:
        return None


def combo_value(combo):
    """The option a dropdown is showing, or None."""
    try:
        value = combo.GetValuePattern().Value
    except Exception:
        value = None
    return value


# --------------------------------------------------------------------------------------
# LIMA's menus and main window
# --------------------------------------------------------------------------------------

def open_menu_item(menu_title, item_name):
    """
    Open one of LIMA's menus from the menu bar and choose an item, both by name.

    For example open_menu_item("Conversations", "Conversation History"). LIMA must be in
    front (ensure_lima_ready). Names are as a screen reader says them, without the "&" of the
    keyboard mnemonic.

    Returns:
        bool: True when the item was found and chosen.
    """
    lima_window = find_lima_uia_window()
    if lima_window is None:
        print("  ! LIMA's window was not found, so its menu could not be opened")
        return False
    menu = find_control(lima_window, names=(menu_title,), control_type="MenuItemControl")
    if menu is None:
        print(f"  ! LIMA's menu bar has no {menu_title!r} menu")
        return False
    try:
        menu.Click()
    except Exception as error:
        print(f"  ! Could not open the {menu_title!r} menu: {error}")
        return False
    time.sleep(SLEEP_A)
    chosen = _open_dialog_item_via_uia(item_name)
    if not chosen:
        print(f"  ! The {menu_title!r} menu has no {item_name!r} item")
        pyautogui.press("escape")
        time.sleep(SLEEP_A)
        return False
    time.sleep(SLEEP_B)
    return True


def menu_bar_titles():
    """The names of LIMA's menus, left to right ([] when the window is not found)."""
    lima_window = find_lima_uia_window()
    if lima_window is None:
        return []
    menu_bar = find_control(lima_window, control_type="MenuBarControl")
    if menu_bar is None:
        return []
    try:
        children = menu_bar.GetChildren()
    except Exception:
        return []
    titles = [_name_of(child) for child in children if _type_of(child) == "MenuItemControl"]
    return titles


def transcript_lines():
    """
    The lines of LIMA's conversation transcript, oldest first.

    The transcript is the list named "Conversation Transcript" in the main window; each part
    of a turn is one row. Returns None when it can't be found.
    """
    lima_window = find_lima_uia_window()
    if lima_window is None:
        return None
    lines = list_items(lima_window, ("Conversation Transcript",))
    return lines


def decline_update_offer():
    """
    Answer Not Now if LIMA is offering an update; True when an offer was declined.

    The offer is modal and appears during startup, so an install that is behind the released
    version would otherwise never reach its main window, and every test would fail to launch.
    """
    hwnd = find_window(UPDATE_WINDOW_TITLE)
    if not hwnd:
        return False
    control = window_control(hwnd)
    if control is None:
        return False
    print("  LIMA is offering an update; answering Not Now so the run tests this build")
    if not press_button(control, UPDATE_DECLINE_BUTTON_NAMES):
        close_window(hwnd, timeout=2.0)
    wait_until_closed(hwnd, timeout=5.0)
    return True
