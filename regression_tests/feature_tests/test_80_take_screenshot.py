"""
Feature: Take a screenshot.

LIMA 2.1.0.5 can take a screenshot of the whole screen with the ``take_screenshot`` tool
(available_tools.py ~L534). It is one of the informative tools that run without asking
(llm_tts_worker.py ``_AUTO_RUN_TOOLS``), and it has two independent outputs (tools.py
``take_screenshot``, ~L1968):

  * a PNG on the Desktop, saved by ``_save_screenshot_to_desktop`` (~L1910) through the Windows
    shell's Desktop folder (CSIDL_DESKTOPDIRECTORY, the same lookup ``_common.desktop_dir`` uses,
    so a OneDrive-redirected or localised Desktop resolves to the same place), named
    ``Screenshot_<YYYY-MM-DD_HH-MM-SS>.png`` with ``_1``, ``_2``... appended when a second capture
    lands in the same second;
  * a copy on the clipboard as CF_DIB (``_copy_image_to_clipboard``, ~L1933).

The test judges the file, not a picture of the screen: the Desktop is listed before the
instruction, and a screenshot passes when a *new* file with LIMA's own name pattern appears.
Nothing else on the Desktop is read as evidence or touched afterwards.

The clipboard half is checked but never fails the test on its own. Reading the clipboard from
another process is the least reliable part of this feature: any app can hold it open, and the
retry loop in LIMA exists because that happens in practice. A missing clipboard copy is
reported in the message so a real clipboard regression is visible without turning a flaky
read into a false failure.
"""

import os
import re
import time

from lima_test_utils import TEST_PASSED, TEST_FAILED, SLEEP_A
from feature_tests import _common

RESULT_NAME = "Feature: Take a screenshot"

# Name the tool's job explicitly: "take a screenshot" is exactly the wording its schema says
# to use it for, so the model picks take_screenshot rather than observation_tool (which reads
# the screen and saves nothing).
INSTRUCTION = "Take a screenshot."

# LIMA's own file name (tools.py _save_screenshot_to_desktop). Matching it means the file came
# from this tool and not from some other program that happened to write a PNG to the Desktop.
SCREENSHOT_NAME_RE = re.compile(r"^Screenshot_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d+)?\.png$")

# The file is written while the turn is still running, so after the turn ends it is normally
# already there. A few seconds covers the save finishing just after LIMA speaks.
FILE_TIMEOUT = 30.0

# The clipboard is rewritten on the GUI side after the save; read it a little after the turn.
CLIPBOARD_SETTLE = 2.0

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


def _desktop_images(folder):
    """The image files on the Desktop as {name: mtime}, or {} when the folder is unreadable."""
    images = {}
    try:
        entries = os.listdir(folder)
    except OSError as error:
        print(f"  ! Could not list the Desktop ({folder}): {error}")
        return images
    for name in entries:
        if not name.lower().endswith(IMAGE_EXTENSIONS):
            continue
        try:
            images[name] = os.path.getmtime(os.path.join(folder, name))
        except OSError:
            continue
    return images


def _new_images(folder, before, started):
    """
    Image files that appeared on the Desktop after the test started, newest last.

    A file counts only when it was not on the Desktop before the instruction and was written
    after the test started. LIMA never overwrites an existing screenshot (the ``_n`` suffix),
    so a pre-existing file can never reappear as a "new" one.
    """
    created = []
    for name, mtime in _desktop_images(folder).items():
        if name in before or mtime + 1.0 < started:
            continue
        created.append(name)
    return sorted(created)


def _clipboard_has_image():
    """
    (True|False|None, note): whether the clipboard holds a DIB image, and what was seen.

    None means it could not be read at all (pywin32 missing, or another app holding the
    clipboard open), which is reported but not treated as a LIMA failure.
    """
    try:
        import win32clipboard
    except Exception as error:  # pywin32 absent on this machine
        return None, f"clipboard not checked ({error})"
    try:
        win32clipboard.OpenClipboard()
    except Exception as error:
        return None, f"clipboard not checked, it could not be opened ({error})"
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
            return True, "the clipboard holds an image"
        return False, "the clipboard holds no image"
    except Exception as error:
        return None, f"clipboard not checked ({error})"
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass


def _run_case(executor, state):
    """Do the scenario; return (passed, message). state records the Desktop snapshot."""
    if not _common.ensure_lima_ready(executor):
        message = "LIMA was not running with its window ready, so the test could not run"
        return False, message

    folder = _common.desktop_dir()
    if not os.path.isdir(folder):
        return False, (f"The Desktop folder LIMA saves to could not be found ({folder!r}), so "
                       f"there is nowhere for the screenshot to appear")

    # Keep the snapshot where cleanup can see it: the file can appear even when the turn then
    # fails, and a leftover screenshot would spoil the next run's "before" list.
    state["folder"] = folder
    state["before"] = _desktop_images(folder)
    state["started"] = time.time()
    before, started = state["before"], state["started"]
    print(f"  Desktop has {len(before)} image file(s) before the instruction")

    # LIMA must be in front: send_instruction types into its chat box.
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be brought to the front to take the instruction"

    _common.send_instruction(INSTRUCTION)
    path, after = _common.wait_for_turn_end(executor, INSTRUCTION)
    if path is None:
        return False, (f"LIMA never saved a conversation for {INSTRUCTION!r}, so the turn did not "
                       f"reach the AI; {_common.describe_turn(after)}")

    new_files = _common.wait_until(lambda: _new_images(folder, before, started), FILE_TIMEOUT)
    new_files = new_files or []
    matched = [name for name in new_files if SCREENSHOT_NAME_RE.match(name)]

    if not new_files:
        return False, (f"No screenshot file appeared on the Desktop within {FILE_TIMEOUT:.0f}s of "
                       f"{INSTRUCTION!r}. LIMA saves it as "
                       f"'Screenshot_<YYYY-MM-DD_HH-MM-SS>.png' in {folder!r}. "
                       f"{_common.describe_turn(after)}")

    if not matched:
        return False, (f"New image file(s) appeared on the Desktop but none has LIMA's screenshot "
                       f"name ('Screenshot_<date>_<time>.png'): {new_files}. "
                       f"{_common.describe_turn(after)}")

    time.sleep(CLIPBOARD_SETTLE)
    clipboard, clipboard_note = _clipboard_has_image()

    message = (f"'{INSTRUCTION}' saved {matched[0]} to the Desktop"
               + (f" (plus {len(matched) - 1} more capture(s): {matched[1:]})"
                  if len(matched) > 1 else ""))
    if clipboard is True:
        message += "; the clipboard holds the image too."
    elif clipboard is False:
        # Not a failure: see the module docstring on why the file is the evidence.
        message += (f"; NOTE the clipboard did not hold an image after {CLIPBOARD_SETTLE:.0f}s, "
                    f"although LIMA reported success. Not counted as a failure here because "
                    f"another app can hold the clipboard open.")
    else:
        message += f"; {clipboard_note}."
    return True, message


def _delete_test_screenshots(state):
    """Delete every screenshot this test caused; nothing else on the Desktop is touched."""
    if not state.get("folder"):
        return
    for name in _new_images(state["folder"], state["before"], state["started"]):
        if not SCREENSHOT_NAME_RE.match(name):
            # Not LIMA's name, so not this test's file: leave it for whoever wrote it.
            continue
        _common.remove_quietly(os.path.join(state["folder"], name))
        print(f"  Deleted {name} from the Desktop")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    state = {}
    try:
        passed, message = _run_case(executor, state)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        _delete_test_screenshots(state)
        time.sleep(SLEEP_A)

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
