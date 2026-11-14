"""
Feature: Close another app's window.

LIMA 2.1's window_control close asks the *active* window to close, like its X button, and
refuses when the active window is LIMA itself (tools.py, window_control: it compares the
window's process id with LIMA's own). This test opens an empty Notepad, hands the focus back
to LIMA and asks LIMA to switch to Notepad and close it. The pass condition is over Win32:
that Notepad window handle is gone, and LIMA is still running.

Because close acts on the active window and the user was just typing into LIMA, the model has
to switch_to Notepad first; the instruction says so. Judging the handle rather than the reply
also catches the failure the tool guards against, LIMA closing itself.

Windows 11 Notepad can restore the previous session's tabs, and an unsaved document makes
closing show a "Save changes?" prompt. LIMA's close only asks the window to close and then
reports that it is still open, so a prompt would look like a failure. The test starts Notepad
on a brand-new empty file (nothing to save, so no prompt), checks the document really is empty
before sending the instruction, and clears any document it finds in Notepad in `finally`, so
this test leaves nothing for a later run to restore.
"""

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: Close another app's window"

# Explicit target and order, so the model switches first and closes second. Restore and close
# act on the active window, which is LIMA while the user is typing.
INSTRUCTION = "Switch to the Notepad window, then close it."

# The close happens inside the turn, but the window (and LIMA's report of it) can settle just
# after the conversation is saved, so poll the outcome for a while afterwards.
OUTCOME_TIMEOUT = 20.0


def _document_is_empty(hwnd):
    """
    True when Notepad's document has no text.

    Returns:
        bool: True for empty text, False when there is text, and True when the text cannot be
        read at all: an unreadable UIA tree is not evidence of unsaved content, and the result
        this test judges is the window handle, not the document.
    """
    text = _common.notepad_text(hwnd)
    if text is None:
        print("  ! Could not read Notepad's text to confirm the document is empty; continuing")
        return True
    return not text.strip()


def _run_case(executor, file_path):
    """Do the scenario; return (passed, message)."""
    if not _common.ensure_lima_ready(executor):
        return False, ("Setup: LIMA was not running with its window ready, so the test could not "
                       "run. This is not a LIMA failure.")

    # An existing empty file gives Notepad a document with nothing to save, so closing it does
    # not raise a "Save changes?" prompt.
    try:
        open(file_path, "w", encoding="utf-8").close()
    except OSError as error:
        return False, (f"Setup: could not create the empty document {file_path!r}: {error}. "
                       f"This is not a LIMA failure.")

    hwnd = _common.open_notepad(file_path)
    if not hwnd:
        return False, ("Setup: Notepad's window did not appear within 20s, so there was no window "
                       "to close. This is not a LIMA failure.")

    # A restored tab from an earlier session would carry unsaved text and make the close prompt
    # to save, which LIMA would then report as "still open". Empty it before the instruction.
    if not _document_is_empty(hwnd):
        print("  ! Notepad restored a document with text; emptying it before the close")
        _common.clear_notepad(hwnd)
        if not _document_is_empty(hwnd):
            return False, (f"Setup: Notepad (hwnd {hwnd}) still has text in it and could not be "
                           f"emptied, so closing it may prompt to save and the outcome could not "
                           f"be judged. This is not a LIMA failure.")
    print("  OK Notepad is open with an empty document")

    # send_instruction types into LIMA's chat box, so LIMA must be in front again.
    if not _common.ensure_lima_ready(executor):
        return False, ("Setup: LIMA's window was not ready after Notepad was opened, so the "
                       "instruction was not sent. This is not a LIMA failure.")

    _common.send_instruction(INSTRUCTION)
    path, after = _common.wait_for_turn_end(executor, INSTRUCTION)

    _common.wait_until(lambda: not _common.is_open(hwnd), OUTCOME_TIMEOUT)
    still_open = _common.is_open(hwnd)
    lima_running = executor.process_manager.is_running()

    if still_open:
        observed = (f"Notepad hwnd {hwnd} is still open after {OUTCOME_TIMEOUT:.0f}s. "
                    f"If a 'Save changes?' prompt is on screen, LIMA's close only asks the "
                    f"window to close and then reports it as still open.")
        if path is None:
            return False, (f"Instruction: LIMA never saved a conversation containing "
                           f"{INSTRUCTION!r}, so the instruction may not have reached it. "
                           f"{observed}")
        return False, (f"Outcome: after {INSTRUCTION!r} Notepad should be closed; {observed} "
                       f"{_common.describe_turn(after)}")

    # Notepad is gone. LIMA closing itself (the tool's own guard exists for that) must fail the
    # test rather than pass as "a window closed".
    if not lima_running:
        return False, (f"Outcome: Notepad (hwnd {hwnd}) closed, but LIMA is no longer running: "
                       f"closing a window must never end LIMA. "
                       f"{_common.describe_turn(after)}")

    return True, (f"LIMA switched to Notepad and closed it: hwnd {hwnd} is gone and LIMA is "
                  f"still running.")


def run(executor):
    """Run the test and report exactly one result."""
    file_path = _common.new_test_file_path()
    passed, message = False, "The test did not run"
    try:
        passed, message = _run_case(executor, file_path)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # Leave no Notepad and no file behind for the next test, even when the scenario failed.
        for hwnd, _title in _common.notepad_windows():
            _common.clear_notepad(hwnd)
        _common.close_apps(_common.NOTEPAD_PROCESSES, _common.NOTEPAD_WINDOW_KEYWORDS)
        _common.remove_quietly(file_path)

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
