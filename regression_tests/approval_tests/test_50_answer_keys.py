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
"""

import time

from lima_test_utils import TEST_PASSED, TEST_FAILED, find_lima_uia_window, find_lima_message_input
from lima_action_approver import (
    manual_approvals, wait_for_action_prompt, find_action_prompts, answer_action_prompt,
    wait_for_replacement_prompt, close_replacement_prompt, get_answer_hotkeys,
    VIA_KEY, VIA_HOTKEY,
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

# LIMA finishes a turn after the action runs or the replacement popup is closed (it speaks, then
# clears its state). Sending the next instruction immediately can be ignored, which would fail a
# later case for the previous case's reason, so each case pauses here first.
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


def _clear_lima_input():
    """
    Empty LIMA's message box before typing the next instruction.

    The dialog never takes focus, so a key pressed in the moment after the answer has been
    taken lands in whatever does have focus — normally LIMA's own message box, which still
    holds focus from the last instruction. Clearing it means such a stray letter can't prefix
    the next instruction and fail a later case for the wrong reason. Best effort: the value is
    only cleared when the input exposes a writable value pattern.
    """
    try:
        window = find_lima_uia_window()
        message_input = find_lima_message_input(window) if window else None
        if message_input is not None:
            message_input.GetValuePattern().SetValue("")
    except Exception as error:
        print(f"  ! Could not clear LIMA's message box ({error})")


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

    time.sleep(TURN_SETTLE)
    _clear_lima_input()
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
        _common.close_apps(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)
        return True, (f"{label} approved the action: LIMA asked to {prompt.description!r}, the "
                      f"popup closed, and Notepad started.")

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

    Keyboard focus is left in LIMA's message box and LIMA's input is cleared between cases,
    because the dialog never takes focus: a stray Y or N would otherwise be typed into it.
    """
    results = []
    with manual_approvals():
        try:
            if not _common.ensure_lima_ready(executor):
                results.append((RESULT_NAME, False,
                                "LIMA was not running with its window ready, so the test "
                                "could not run"))
            else:
                # Same call (and so the same config file) answer_action_prompt(via='hotkey')
                # uses, so a result name can never disagree with the keys actually pressed.
                hotkeys = get_answer_hotkeys()
                names = _result_names(hotkeys)
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
