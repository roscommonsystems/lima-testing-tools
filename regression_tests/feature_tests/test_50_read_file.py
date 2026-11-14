"""
Feature: Read a file.

LIMA 2.x added ``read_file``, which is one of the informational tools that run without an
approval (``llm_tts_worker._AUTO_RUN_TOOLS`` in v2.1.0.5). This test writes a file holding
a code word LIMA cannot guess (``make_code_word``) and asks LIMA to read that file and say
the code word. The only way to answer is to read the file, so the code word appearing in
LIMA's reply proves the tool worked.

The reply is judged from LIMA's saved conversation, not from a screenshot. If the code word
arrives through some other route (the model may answer from an earlier tool, or a different
tool may have supplied it), the test still passes but names the tools that were called, so a
reader can tell what happened.
"""

import os

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: Read a file"


def _quoted(path):
    """The path as written in an instruction: quoted only when it contains spaces."""
    return f'"{path}"' if " " in path else path


def _instruction(path):
    return f"Read the file {_quoted(path)} and tell me the code word written in it."


def _tool_names(after):
    return [name for name, _arguments in _common.tool_calls(after)]


def _run_case(executor, created):
    """Do the scenario; return (passed, message). Paths made go into created for cleanup."""
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA was not running with its window ready, so the test could not run"

    path = _common.new_test_file_path()
    created.append(path)
    code_word = _common.make_code_word()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"The code word is {code_word}.\n")
    except OSError as error:
        return False, f"Could not create the test file {path!r}: {error}"
    print(f"  Created {path} holding the code word {code_word!r}")

    instruction = _instruction(path)
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be focused before sending the instruction"

    _common.send_instruction(instruction)
    _conversation, after = _common.wait_for_turn_end(executor, instruction)

    reply = _common.assistant_text(after)
    names = _tool_names(after)
    read_file_called = "read_file" in names
    tool_report = (f"read_file was among the tools called: {'yes' if read_file_called else 'no'}; "
                   f"tools called: {names or 'none'}")

    if _common.contains_code_word(reply, code_word):
        return True, (
            f"LIMA's reply contained the code word {code_word!r} from "
            f"{os.path.basename(path)!r}. {tool_report}.")

    return False, (
        f"Expected LIMA's reply to contain the code word {code_word!r} written in "
        f"{path!r}, which it could only know by reading the file. {tool_report}. "
        f"{_common.describe_turn(after)}")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    created = []
    try:
        passed, message = _run_case(executor, created)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # The model may have opened the file in Notepad to read it by eye; close that before
        # deleting the file.
        try:
            _common.close_apps(_common.NOTEPAD_PROCESSES, _common.NOTEPAD_WINDOW_KEYWORDS)
        except Exception as error:
            print(f"  ! Could not close Notepad during cleanup: {error}")
        for path in created:
            _common.remove_quietly(path)

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
