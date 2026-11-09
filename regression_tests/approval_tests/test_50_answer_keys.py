"""
Approval: answer keys.

LIMA's approval dialog never takes keyboard focus — it must not close a Start menu or a
dropdown the action is about to use — so the answer comes from keys instead of the focused
control. There are two ways to answer that way:

  * plain Y / N, which the dialog listens for system-wide while it is on screen
    (action_approval_dialog.py: a KeyboardHook plus a no-modifier hotkey);
  * Ctrl+Alt+Y / Ctrl+Alt+N, registered from LIMA's config for the whole session
    (lima.py request_action_decision and the hotkey callbacks above it, startup.py defaults).

Both must resolve the same pending decision as the buttons, and a No from either must still
open the replacement popup. A user who has changed the hotkeys in Settings must not turn this
test red, so the real bindings are read from LIMA's config and the results are named after
them.

Each of the four inputs gets its own result line, so a failure says exactly which input
stopped working instead of leaving one vague "answer keys" failure.

Each input also gets its own LIMA launch, and so its own conversation (see _relaunch_lima).
Sharing one conversation made this test depend on what the model remembered: on the first VM
run the second "open Notepad" was answered with "Notepad is now open." and no action at all,
because the earlier cases' requests were still in the history and the model had no way to know
the test had closed Notepad. Nothing to answer meant nothing to test.
"""

import os
import time

from lima_test_utils import TEST_PASSED, TEST_FAILED, SLEEP_B
from lima_action_approver import (
    manual_approvals, wait_for_action_prompt, find_action_prompts, find_replacement_prompt,
    answer_action_prompt, wait_for_replacement_prompt, close_replacement_prompt,
    get_answer_hotkeys, VIA_KEY, VIA_HOTKEY,
)
from approval_tests import _common

# The banner line the runner prints before the test. Each case reports its own name below.
RESULT_NAME = "Approval: answer keys"

INSTRUCTION = "open Notepad"
NOTEPAD_PROCESSES = ("notepad.exe",)
NOTEPAD_WINDOW_KEYWORDS = ("Notepad",)

# Same reasoning as the other approval tests: the popup appears after a model turn plus TTS,
# so a minute is generous. Failing here means LIMA ran or dropped a gated action unasked.
ACTION_PROMPT_TIMEOUT = 60.0

# After a Yes the action runs and Notepad has to show up. Windows 11's Notepad is a Store
# app, so give it longer than a window-title check alone would need.
NOTEPAD_START_TIMEOUT = 20.0

# The replacement popup opens on the same GUI turn as the denial.
REPLACEMENT_PROMPT_TIMEOUT = 15.0

# Dead time on the deny path: nothing should happen at all, but a broken answer must be
# caught, so this has to cover a launched Notepad showing a process or a window.
NO_START_WINDOW = 15.0

# How long LIMA gets to finish the turn after the first prompt is answered. An approved action
# does not end the turn: the result goes back to the model, which re-plans, and that can be a
# whole further model round trip plus speech before the turn is over.
TURN_END_TIMEOUT = 60.0

# Polling interval while waiting for the turn to end. The popup check polls faster on its own.
TURN_END_POLL = 0.5

# Wait used when LIMA's install folder is unknown, so there is no conversation save to watch.
# Short and best effort: the next case relaunches LIMA, so this only avoids cutting a sentence
# off mid-word.
TURN_SETTLE = 2.0


def _hotkey_label(keys):
    """Format pyautogui key names as LIMA shows a hotkey: [ctrl, alt, y] -> 'Ctrl+Alt+Y'."""
    return "+".join(part.upper() if len(part) == 1 else part.capitalize() for part in keys)


def _result_names(hotkeys):
    """The four result names, built from the real configured hotkeys."""
    approve = _hotkey_label(hotkeys["approve"])
    deny = _hotkey_label(hotkeys["deny"])
    return {
        "y": "Approval: Y key approves",
        "n": "Approval: N key denies",
        "approve_hotkey": f"Approval: {approve} approves",
        "deny_hotkey": f"Approval: {deny} denies",
    }


def _wait_for_action_prompt(timeout):
    """
    Wait for the approval popup.

    Returns:
        (prompt, question): the action prompt, or the question prompt that appeared
        instead (None, None on timeout).
    """
    deadline = time.time() + timeout
    while True:
        prompt = wait_for_action_prompt(timeout=0.25)
        if prompt is not None:
            if prompt.kind == "question":
                return None, prompt
            return prompt, None
        if time.time() >= deadline:
            return None, None


def _answer_question(question):
    """Answer an unexpected question No and end its turn, so no popup is left waiting."""
    answer_action_prompt(question, approve=False)
    replacement = wait_for_replacement_prompt(timeout=5.0)
    if replacement:
        close_replacement_prompt(replacement)


def _check_notepad_is_not_running():
    """Make sure Notepad starts closed, so "it opened" really means LIMA opened it."""
    _common.close_apps(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)
    if _common.app_running(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS):
        return ("Notepad was already running and could not be closed, so it would be "
                "impossible to tell whether LIMA started it")
    return None


def _relaunch_lima(executor):
    """
    Close LIMA and start it again, so this case begins in a new, empty conversation.

    Every launch starts a fresh conversation: lima.py _init_state_variables builds one with
    conversation_store.new_conversation() and nothing is reloaded on startup (past
    conversations are reopened from the Conversations menu). Relaunching is therefore the
    same as Conversations > New Conversation (&New Conversation, or typing /new) for the
    conversation history, and better than either for this test: it also drops a pending
    action, a replacement popup, or a half-finished turn left by the previous case, so each
    case starts from the same state instead of from whatever the last one left behind.

    Closing rather than reusing also matches how lima_tool_tests.py isolates its tests.

    Returns:
        str: a failure message when a fresh LIMA did not come up, otherwise None.
    """
    process_manager = executor.process_manager
    if not process_manager.exe_full_path:
        return "LIMA's executable path is unknown, so a fresh LIMA could not be launched"

    print("  Closing LIMA to start this case in a new conversation...")
    process_manager.close()
    # Let the old instance go before the next one starts: LIMA enforces a single instance with
    # a QSharedMemory guard (lima.py), and a leftover would make the new launch report
    # "LIMA Is Already Running" and exit without a window.
    time.sleep(SLEEP_B)
    if not _common.ensure_lima_ready(executor):
        return ("A fresh LIMA did not start with its window ready, so this case could not run "
                "in a new conversation")
    return None


def _conversations_directory(executor):
    """
    LIMA's saved-conversations folder, or None when it cannot be worked out.

    conversation_store.py keeps each conversation in `data/conversations` relative to the
    process's working directory, and lima_process_manager.launch() starts LIMA with its
    install folder as that directory (it chdirs there before os.startfile), so the folder is
    <install>/data/conversations. The same folder holds data/config.json, which
    lima_action_approver already reads from the install path.
    """
    install_path = getattr(executor.process_manager, "install_path", None)
    if not install_path:
        return None
    return os.path.join(install_path, "data", "conversations")


def _conversation_snapshot(executor):
    """
    Map each saved conversation file to its size and modification time.

    None means there is nothing to watch (LIMA's install folder is unknown). A missing folder
    is an empty snapshot: the folder is created by the first save, so a file appearing later
    still shows up as a change.
    """
    directory = _conversations_directory(executor)
    if not directory:
        return None
    snapshot = {}
    try:
        names = os.listdir(directory)
    except OSError:
        return snapshot
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            status = os.stat(os.path.join(directory, name))
        except OSError:
            continue
        snapshot[name] = (status.st_size, status.st_mtime)
    return snapshot


def _wait_for_turn_end(executor, snapshot):
    """
    Wait until LIMA has finished the turn, denying any follow-up action it proposes.

    Why this is needed: approving an action does not end LIMA's turn. The worker feeds the
    tool result back to the model and re-plans (llm_tts_worker._run_step_through_actions), so
    it can announce a second gated action and sit waiting for an answer — on the first VM run
    a window_control followed the approved open_program. The test used to move on and clean up
    at that point, so the next instruction landed mid-turn and LIMA's saved order of turns was
    skewed by the overlap.

    A follow-up prompt is denied with the No button, not with the input this test is about: the
    result must say what that input did to the first prompt, and re-pressing Y/N or a hotkey
    here would blur which prompt an answer belonged to. Its replacement popup is closed empty,
    which is what ends the turn with the follow-up not run
    (llm_tts_worker._run_step_through_actions: a denial with no replacement breaks the loop).
    The follow-up never counts towards the case's result.

    The end of the turn is read from LIMA's own save: the turn's messages go to
    <install>/data/conversations when the turn ends (lima.py _handle_assistant_response ->
    _save_active_conversation), so a conversation file that is new or changed since `snapshot`
    means LIMA is done. Watching the transcript instead would be guessing, because the model
    is silent for a while between the tool result and its next proposal.

    Returns:
        list: the descriptions of the follow-up prompts that were denied (empty is normal).
    """
    if snapshot is None:
        print("  ! LIMA's install folder is unknown, so the end of its turn cannot be watched; "
              "waiting briefly instead")
        time.sleep(TURN_SETTLE)
        return []

    denied = []
    deadline = time.time() + TURN_END_TIMEOUT
    while time.time() < deadline:
        prompt = wait_for_action_prompt(timeout=0.25)
        if prompt is not None:
            print(f"  LIMA proposed a follow-up {prompt.kind}: {prompt.description!r} — "
                  f"denying it so the turn can end")
            answer_action_prompt(prompt, approve=False)
            replacement = wait_for_replacement_prompt(timeout=REPLACEMENT_PROMPT_TIMEOUT)
            if replacement:
                close_replacement_prompt(replacement)
            denied.append(prompt.description)
            continue
        # A replacement popup with no prompt beside it (left from an earlier answer) also keeps
        # the worker waiting, so close it empty too.
        if find_replacement_prompt():
            close_replacement_prompt()
            continue
        if _conversation_snapshot(executor) != snapshot:
            print("  LIMA finished its turn")
            return denied
        time.sleep(TURN_END_POLL)

    # Not a failure: the case's own checks have already passed or failed on their own evidence,
    # and the next case relaunches LIMA, which cannot inherit this turn.
    print(f"  ! LIMA did not finish its turn within {TURN_END_TIMEOUT:.0f}s; moving on")
    return denied


def _press_answer(prompt, approve, via, label):
    """
    Answer the popup with the key or hotkey under test.

    The key is only pressed while the popup is still on screen: once LIMA has resolved the
    decision the dialog stops listening, and a Y or N pressed then would be typed into
    whatever has focus. LIMA also ignores an approve/deny hotkey with no decision pending, so
    pressing late would silently do nothing and hide a real failure.

    Returns:
        (answered, message): answered is False with the reason when the popup had gone.
    """
    if prompt.hwnd not in find_action_prompts():
        return False, (f"LIMA's approval popup closed before the {label} could be pressed, "
                       f"so the answer was never tested")
    print(f"  Answering with {label}: {'Yes' if approve else 'No'}")
    if not answer_action_prompt(prompt, approve=approve, via=via):
        return False, (f"LIMA's approval popup did not close after the {label}, so the answer "
                       f"was not accepted")
    return True, ""


def _run_case(executor, approve, via, label):
    """Run one input's scenario; return (passed, message)."""
    failure = _check_notepad_is_not_running()
    if failure:
        return False, failure

    failure = _relaunch_lima(executor)
    if failure:
        return False, failure

    # Taken before the instruction is sent, so any later change to a saved conversation is this
    # case's turn ending (the previous case's LIMA is gone, and its save happened before this
    # launch).
    snapshot = _conversation_snapshot(executor)
    _common.send_instruction(INSTRUCTION)

    prompt, question = _wait_for_action_prompt(ACTION_PROMPT_TIMEOUT)
    if question is not None:
        _answer_question(question)
        return False, (
            f"LIMA asked a question ({question.description!r}) instead of proposing the "
            f"'{INSTRUCTION}' action. This test needs the action prompt; a Yes to a question "
            f"pre-approves the next action and would skip it.")
    if prompt is None:
        return False, (
            f"LIMA did not ask for approval of '{INSTRUCTION}' within "
            f"{ACTION_PROMPT_TIMEOUT:.0f}s, so the {label} had nothing to answer.")

    print(f"  LIMA asked to: {prompt.description!r}")

    answered, message = _press_answer(prompt, approve, via, label)
    if not answered:
        return False, message

    if approve:
        if not _common.wait_for_app(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS,
                                    timeout=NOTEPAD_START_TIMEOUT):
            return False, (
                f"LIMA accepted the {label} (the popup closed) but Notepad did not start "
                f"within {NOTEPAD_START_TIMEOUT:.0f}s, so the approval did not run the action.")
        # Notepad is closed only after the turn is over: while it is still running LIMA may
        # propose to control its window, and closing the app underneath a pending action would
        # turn a working approval into an unrelated failure.
        denied = _wait_for_turn_end(executor, snapshot)
        _common.close_apps(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)
        message = (f"{label} approved the action: LIMA asked to {prompt.description!r}, the "
                   f"popup closed, and Notepad started.")
        if denied:
            message += (f" LIMA then proposed a follow-up action ({denied[0]!r}); it was denied "
                        f"so the turn could end, and it is not counted in this result.")
        return True, message

    replacement = wait_for_replacement_prompt(REPLACEMENT_PROMPT_TIMEOUT)
    if replacement is None:
        return False, (
            f"No replacement popup appeared within {REPLACEMENT_PROMPT_TIMEOUT:.0f}s of "
            f"answering No with the {label}. A denial must ask what to do instead.")
    if not close_replacement_prompt(replacement):
        return False, "The replacement popup did not close when asked to close it empty"

    if _common.wait_for_app(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS,
                            timeout=NO_START_WINDOW):
        return False, (
            f"Notepad started even though the action was denied with the {label}. LIMA ran "
            f"the action after a No (asked: {prompt.description!r}).")

    leftover = find_action_prompts()
    if leftover:
        return False, (f"{len(leftover)} approval popup(s) are still open after the denial; "
                       f"the turn did not end")

    # A denial with the replacement closed empty ends the turn, so this returns at once; it is
    # here so both paths leave the same "turn is over" state behind.
    _wait_for_turn_end(executor, snapshot)

    return True, (f"{label} denied the action: LIMA asked to {prompt.description!r}, the "
                  f"replacement popup opened and was closed empty, and Notepad did not start "
                  f"within {NO_START_WINDOW:.0f}s.")


def _safe_run_case(executor, approve, via, label):
    """Run one case, turning any exception into that case's own failure."""
    try:
        return _run_case(executor, approve, via, label)
    except Exception as error:
        return False, f"Exception while answering with the {label}: {error}"
    finally:
        # Leave nothing behind for the next case: Notepad closed, no popup waiting.
        _common.cleanup(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)


def run(executor):
    """
    Answer the approval popup four ways — Y, Ctrl+Alt+Y, N, Ctrl+Alt+N — one result each.

    Each case runs in a LIMA launched for it alone, so it starts in a new conversation with no
    earlier instruction in the model's history, and its turn is over before the next case
    begins. Keyboard focus is left in LIMA's fresh message box, so a stray Y or N from the
    previous case cannot prefix the next instruction.
    """
    results = []
    with manual_approvals():
        try:
            # Same call (and so the same config file) answer_action_prompt(via='hotkey') uses,
            # so a result name can never disagree with the keys actually pressed. Read before
            # the first launch, which is also when LIMA is definitely installed.
            hotkeys = get_answer_hotkeys()
            names = _result_names(hotkeys)
            if not executor.process_manager.exe_full_path:
                # Every case launches its own LIMA, so without the path there is nothing to test.
                results.append((RESULT_NAME, False,
                                "LIMA's executable path is unknown, so it could not be "
                                "launched for a fresh conversation per case"))
            else:
                cases = [
                    (names["y"], True, VIA_KEY, "Y key"),
                    (names["approve_hotkey"], True, VIA_HOTKEY,
                     _hotkey_label(hotkeys["approve"])),
                    (names["n"], False, VIA_KEY, "N key"),
                    (names["deny_hotkey"], False, VIA_HOTKEY,
                     _hotkey_label(hotkeys["deny"])),
                ]
                for name, approve, via, label in cases:
                    print(f"\n  -- {name}")
                    passed, message = _safe_run_case(executor, approve, via, label)
                    print(("  OK " if passed else "  X ") + message)
                    results.append((name, passed, message))
        except Exception as error:
            results.append((RESULT_NAME, False, f"Exception during the test: {error}"))
        finally:
            _common.cleanup(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)

    if not results:
        results.append((RESULT_NAME, False, "The test did not run"))
    for name, passed, message in results:
        executor.add_test_result(name, TEST_PASSED if passed else TEST_FAILED, message)
