"""
Feature: Open a file.

LIMA 2.x added ``open_file``: it opens a file or folder with its default program, the same
as double-clicking it (``tools.py`` ``open_file`` -> ``os.startfile``). This test writes a
text file, asks LIMA to open it by its full path, and watches for a Notepad window whose
title names that file.

The outcome is judged over Win32 (``feature_tests._common.notepad_windows``), not by
screenshot: a screenshot would need a vision model and would still only show that some
window exists, not that it is the file we asked for.
"""

import os

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: Open a file"

# The turn check already waits for LIMA's saved conversation, so this only has to cover
# Notepad finishing its start-up and painting its window after the action was approved.
WINDOW_TIMEOUT = 30.0

# Short, plain text: the test checks the window, not the content, but an empty file would
# look the same as a failed write.
FILE_TEXT = "This file exists so LIMA has something to open."


def _quoted(path):
    """The path as written in an instruction: quoted only when it contains spaces."""
    return f'"{path}"' if " " in path else path


def _instruction(path):
    return f"Open the file {_quoted(path)}."


def _notepad_window_for(base_name):
    """(hwnd, title) of a visible Notepad window whose title names base_name, or None."""
    needle = base_name.casefold()
    for hwnd, title in _common.notepad_windows():
        if needle in (title or "").casefold():
            return hwnd, title
    return None


def _notepad_titles():
    return [title for _hwnd, title in _common.notepad_windows()]


def _run_case(executor, created):
    """Do the scenario; return (passed, message). Paths made go into created for cleanup."""
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA was not running with its window ready, so the test could not run"

    path = _common.new_test_file_path()
    created.append(path)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(FILE_TEXT + "\n")
    except OSError as error:
        return False, f"Could not create the test file {path!r}: {error}"
    print(f"  Created {path}")

    # Any Notepad already open would make it impossible to tell whether LIMA opened ours.
    _common.close_apps(_common.NOTEPAD_PROCESSES, _common.NOTEPAD_WINDOW_KEYWORDS)
    if not _common.wait_until(lambda: not _common.notepad_windows(), 10.0):
        return False, ("Notepad was still open after closing it, so a Notepad window would "
                       "not prove that LIMA opened the file")

    instruction = _instruction(path)
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be focused before sending the instruction"

    _common.send_instruction(instruction)
    _conversation, after = _common.wait_for_turn_end(executor, instruction)

    # Windows 11 Notepad shows "name.txt - Notepad" for an opened file and classic Notepad
    # shows "name.txt - Notepad" too, but the extension is not guaranteed in the title, so
    # match the base name only.
    base_name = os.path.splitext(os.path.basename(path))[0]
    found = _common.wait_until(lambda: _notepad_window_for(base_name), WINDOW_TIMEOUT)
    if not found:
        return False, (
            f"Expected a Notepad window titled with {base_name!r} within "
            f"{WINDOW_TIMEOUT:.0f}s of LIMA's turn ending, as proof that LIMA opened "
            f"{path!r}. Notepad windows open: {_notepad_titles() or 'none'}. "
            f"{_common.describe_turn(after)}")

    hwnd, title = found
    return True, (
        f"LIMA opened {os.path.basename(path)!r}: a Notepad window {title!r} appeared "
        f"(handle {hwnd}). {_common.describe_turn(after)}")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    created = []
    try:
        passed, message = _run_case(executor, created)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # Close Notepad before deleting the file: a window on a deleted file would linger in
        # the next test's way.
        try:
            _common.close_apps(_common.NOTEPAD_PROCESSES, _common.NOTEPAD_WINDOW_KEYWORDS)
        except Exception as error:
            print(f"  ! Could not close Notepad during cleanup: {error}")
        for path in created:
            _common.remove_quietly(path)

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
