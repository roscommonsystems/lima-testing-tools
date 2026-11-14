"""
Feature: /new starts a new conversation.

LIMA 2.1.0.5 treats typed ``/new`` as a command, not a message: ``MainWindow._send_text_input``
(lima.py ~L1921) matches it case-insensitively, never appends it to the chat history, and calls
``_new_conversation`` (~L2522), which saves the active conversation and starts a fresh one
(``_start_fresh_conversation``, ~L2534: chat history cleared in place, new conversation id, a
"New conversation started" line spoken).

The test proves the switch from LIMA's own saved conversations, which is the only record that
survives the turn:

  1. a first instruction with an unguessable code word -> conversation P1 is on disk with it;
  2. ``/new`` -> nothing is saved for it (a command must not become a user message anywhere);
  3. a second instruction with a different code word -> conversation P2.

Pass requires all of: P2 exists and is a different file from P1; P1 still holds the first user
message (the old conversation was saved, not lost); P2 contains no trace of the first code word
(the fresh conversation did not inherit the old history); and no saved conversation has a user
message of exactly ``/new``.

Both conversations are left in place, like every other test's: they are the evidence the VM
harness copies into the run's results.
"""

import os
import time

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: /new starts a new conversation"

# "Reply with only the word" makes the turn short and gives the conversation a line of text
# that could not come from anywhere else, so no extra tool call is needed to mark it.
INSTRUCTION_TEMPLATE = "Reply with only the word {word}."

# The command typed into LIMA's message box, exactly as a user would type it.
NEW_COMMAND = "/new"

# /new runs on the GUI thread and saves the conversation synchronously, but the transcript's
# "new conversation" line and TTS follow it; a few seconds keeps the next instruction out of the
# old conversation if the switch is still settling.
NEW_COMMAND_SETTLE = 5.0


def _conversation_messages(path):
    """The saved conversation dict's messages, or None when the file cannot be read."""
    conversation = _common.load_conversation(path)
    if not conversation:
        return None
    return conversation.get("messages") or []


def _all_message_text(messages):
    """Every message's text joined, for "does this conversation contain the code word" checks."""
    return "\n".join(_common.message_text(message) for message in (messages or []))


def _has_user_message(messages, text):
    """True when the conversation has a user message equal to text (as LIMA matches it)."""
    wanted = text.strip().casefold()
    return any(message.get("role") == "user"
               and _common.message_text(message).strip().casefold() == wanted
               for message in (messages or []))


def _conversations_with_user_text(executor, text):
    """Paths of every saved conversation that has a user message equal to text."""
    found = []
    for path in _common.list_conversation_files(executor):
        if _has_user_message(_conversation_messages(path), text):
            found.append(path)
    return found


def _run_case(executor, words, paths):
    """Do the scenario; return (passed, message). words/paths are filled for cleanup."""
    first_word, second_word = words
    first_instruction = INSTRUCTION_TEMPLATE.format(word=first_word)
    second_instruction = INSTRUCTION_TEMPLATE.format(word=second_word)

    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be brought to the front to take the first instruction"

    _common.send_instruction(first_instruction)
    first_path, first_turn = _common.wait_for_turn_end(executor, first_instruction)
    if first_path is None:
        return False, (f"LIMA never saved a conversation for {first_instruction!r}, so there was "
                       f"nothing to switch away from; {_common.describe_turn(first_turn)}")
    paths.append(first_path)
    print(f"  First conversation: {os.path.basename(first_path)}")

    # The command goes into the same chat box, so LIMA must be in front again.
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be brought to the front to take the /new command"
    _common.send_instruction(NEW_COMMAND)
    time.sleep(NEW_COMMAND_SETTLE)

    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be brought to the front to take the second instruction"
    _common.send_instruction(second_instruction)
    second_path, second_turn = _common.wait_for_turn_end(executor, second_instruction)
    if second_path is None:
        return False, (f"LIMA never saved a conversation for {second_instruction!r} after /new, so "
                       f"it did not accept the next message; "
                       f"{_common.describe_turn(second_turn)}")
    paths.append(second_path)
    print(f"  Second conversation: {os.path.basename(second_path)}")

    if os.path.normcase(first_path) == os.path.normcase(second_path):
        return False, (f"/new did not start a new conversation: both instructions were saved in "
                       f"{os.path.basename(first_path)}. The command was typed as a message, or "
                       f"the switch did not happen before the next instruction. "
                       f"{_common.describe_turn(second_turn)}")

    first_messages = _conversation_messages(first_path)
    if not _has_user_message(first_messages, first_instruction):
        return False, (f"The conversation before /new ({os.path.basename(first_path)}) no longer "
                       f"holds the first user message {first_instruction!r}. /new must save the "
                       f"current conversation before starting a new one; it was lost instead.")

    second_messages = _conversation_messages(second_path)
    if _common.contains_code_word(_all_message_text(second_messages), first_word):
        return False, (f"The conversation after /new ({os.path.basename(second_path)}) still "
                       f"contains the first code word {first_word!r}, so it carried the old "
                       f"history over instead of starting fresh. "
                       f"{_common.describe_turn(second_turn)}")

    leaked = _conversations_with_user_text(executor, NEW_COMMAND)
    if leaked:
        return False, (f"/new was saved as a user message in "
                       f"{[os.path.basename(path) for path in leaked]}. It is a command and must "
                       f"never reach the AI or the conversation.")

    return True, (f"/new saved {os.path.basename(first_path)} (with {first_word!r}) and started "
                  f"{os.path.basename(second_path)} for the next message, which holds no trace of "
                  f"the first conversation. No saved conversation has a '/new' user message.")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    first_word = _common.make_code_word()
    second_word = _common.make_code_word()
    while second_word == first_word:  # the two words must be distinguishable
        second_word = _common.make_code_word()
    paths = []
    try:
        passed, message = _run_case(executor, (first_word, second_word), paths)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
