"""
Feature: Create a file.

LIMA 2.x added ``write_file``: it creates a text file (or overwrites one) with the content
the model gives it, and "Write a file" is a gated action, so the suite's background
approver answers Yes before it runs (``llm_tts_worker._AUTO_RUN_TOOLS``). This test asks
LIMA to create a file that does not exist yet, holding a code word it cannot guess, then
reads the file from disk.

The outcome is the file itself, not LIMA's claim that it wrote one: the file must exist and
its text must contain the code word. The file is written after the approval, so the check
polls briefly instead of looking once when the turn ends.
"""

import os

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: Create a file"

# The turn check already waits for LIMA's saved conversation; the write happens before the
# tool result is saved, so this is slack for a slow disk or a late approval, not the
# expected wait.
FILE_TIMEOUT = 30.0


def _quoted(path):
    """The path as written in an instruction: quoted only when it contains spaces."""
    return f'"{path}"' if " " in path else path


def _instruction(path, code_word):
    return (f"Create a new text file at {_quoted(path)} containing exactly this text: "
            f"{code_word}")


def _file_text(path):
    """The file's text, or None when it is missing or unreadable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _has_code_word(path, code_word):
    text = _file_text(path)
    return text is not None and _common.contains_code_word(text, code_word)


def _run_case(executor, created):
    """Do the scenario; return (passed, message). Paths made go into created for cleanup."""
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA was not running with its window ready, so the test could not run"

    # new_test_file_path only returns a path nothing exists at, so the file appearing is
    # LIMA's doing and not a leftover.
    path = _common.new_test_file_path()
    created.append(path)
    code_word = _common.make_code_word()
    print(f"  Asking LIMA to create {path} holding {code_word!r}")

    instruction = _instruction(path, code_word)
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be focused before sending the instruction"

    _common.send_instruction(instruction)
    _conversation, after = _common.wait_for_turn_end(executor, instruction)

    if _common.wait_until(lambda: _has_code_word(path, code_word), FILE_TIMEOUT):
        return True, (
            f"LIMA created {os.path.basename(path)!r} holding the code word "
            f"{code_word!r}; the file now reads {_file_text(path)!r}. "
            f"{_common.describe_turn(after)}")

    if not os.path.exists(path):
        seen = "no file exists at that path"
    else:
        seen = f"the file exists but reads {_file_text(path)!r}"
    return False, (
        f"Expected LIMA to create {path!r} containing the code word {code_word!r}; after "
        f"{FILE_TIMEOUT:.0f}s {seen}. {_common.describe_turn(after)}")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    created = []
    try:
        passed, message = _run_case(executor, created)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        for path in created:
            _common.remove_quietly(path)

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
