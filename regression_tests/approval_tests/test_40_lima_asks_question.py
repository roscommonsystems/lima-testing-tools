"""
Approval: LIMA asks a yes/no question.

LIMA's ask_permission tool lets the model ask its own yes or no question through the same
always-on-top dialog, headed "LIMA asks:" instead of "LIMA wants to:". The tool promises
that "A yes approves your next action, so take it without asking again"
(available_tools.py, ask_permission), and the system prompt repeats it: "A yes approves your
next action, so take it without asking again" (globals.py, SYSTEM_PROMPT_TEMPLATE_EN). So a
Yes to the question must let the next gated action run without a second "LIMA wants to:"
prompt. This test makes the model ask before opening Notepad and checks exactly that.

Model behaviour caveat: the same system prompt says "when the user asks you to do something,
call the action straight away", so a model may ignore the request to ask first and call
open_program directly. That is model behaviour, not an approval-loop defect. When the first
attempt produces a gated-action prompt instead of a question, this test denies it, retries
once with a stronger wording, and reports SKIPPED if the model still does not ask — the
question path was simply not exercised. Only asking nothing at all, or asking again after a
Yes, fails.
"""

import time

from lima_test_utils import TEST_PASSED, TEST_FAILED, TEST_SKIPPED
from lima_action_approver import (
    manual_approvals, wait_for_action_prompt, read_action_prompt, find_action_prompts,
    answer_action_prompt, wait_for_replacement_prompt, close_replacement_prompt,
)
from approval_tests import _common

RESULT_NAME = "Approval: LIMA asks a yes/no question"

# The tool description's own example is "Shall I open welcome.html in your browser?", and its
# rule is that a yes covers the next action. The instruction below uses both, and says "ask
# me ... before you open Notepad" so it can't be read as a request to just open it.
INSTRUCTION = ("Ask me for permission first, as a yes or no question, before you open Notepad. "
               "Then open it if I say yes.")

# Used once when the model skipped asking. It names the tool and puts the question in the
# model's mouth, which is the strongest phrasing that still sounds like a user instruction.
RETRY_INSTRUCTION = ("Before you open Notepad, call your ask_permission tool to ask me a yes or "
                     "no question: shall I open Notepad? Open it only after I say yes.")

NOTEPAD_PROCESSES = ("notepad.exe",)
NOTEPAD_WINDOW_KEYWORDS = ("Notepad",)

# A model turn plus TTS before the popup opens; failing here means LIMA asked nothing at all.
PROMPT_TIMEOUT = 60.0

# The replacement popup opens immediately after a No, on the same GUI turn.
REPLACEMENT_PROMPT_TIMEOUT = 15.0

# Part of the pre-approval watch: how long a second "LIMA wants to:" prompt is watched for.
# The model re-plans straight after the Yes, so a prompt that was going to appear does so
# well within this. Notepad itself gets longer, because a launched Store app can be slow to
# show a process or window.
REPEAT_PROMPT_WINDOW = 20.0
APP_START_WINDOW = 20.0


def _watch_past_the_question():
    """
    Watch what LIMA does after a Yes to its question.

    A Yes pre-approves the next gated action, so no approval prompt may appear before Notepad
    starts. Both are checked in one loop so the failure names whichever happened first.

    Returns:
        ("prompt", ActionPrompt) when LIMA asked again,
        ("app", None) when Notepad started,
        ("timeout", None) when neither happened in time.
    """
    prompt_deadline = time.time() + REPEAT_PROMPT_WINDOW
    app_deadline = prompt_deadline + APP_START_WINDOW
    while True:
        now = time.time()
        if now < prompt_deadline:
            for hwnd in find_action_prompts():
                prompt = read_action_prompt(hwnd)
                if prompt is not None:
                    return "prompt", prompt
        if _common.app_running(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS):
            return "app", None
        if now >= app_deadline:
            return "timeout", None
        time.sleep(0.25)


def _deny_and_end_turn(prompt):
    """Answer No and close the replacement popup empty, so LIMA ends the turn."""
    if not answer_action_prompt(prompt, approve=False):
        print("  ! LIMA's approval popup did not close after answering No")
        return
    replacement = wait_for_replacement_prompt(timeout=REPLACEMENT_PROMPT_TIMEOUT)
    if replacement is None:
        print("  ! No replacement popup appeared after answering No")
        return
    if not close_replacement_prompt(replacement):
        print("  ! The replacement popup did not close when asked to close it empty")


def _check_question_path(prompt):
    """
    Answer LIMA's own question Yes and check the pre-approval.

    Returns:
        (status, message) for one result line.
    """
    question = (prompt.description or "").strip()
    if not question:
        return TEST_FAILED, (f"LIMA's '{prompt.heading}' popup had no question text, so there "
                             f"was nothing to answer")
    if not question.endswith("?"):
        return TEST_FAILED, (f"LIMA's '{prompt.heading}' popup did not ask a question: "
                             f"{question!r}")

    print(f"  LIMA asked: {question!r}")

    if not answer_action_prompt(prompt, approve=True):
        return TEST_FAILED, "LIMA's question popup did not close after answering Yes"

    outcome, second = _watch_past_the_question()
    if outcome == "prompt":
        if second is not None:
            _deny_and_end_turn(second)
        asked_again = (f"a '{second.heading}' prompt ({second.description!r})"
                       if second is not None else "another approval prompt")
        return TEST_FAILED, (
            f"Yes to LIMA's question didn't pre-approve the next action: LIMA asked again "
            f"with {asked_again} instead of opening Notepad after answering Yes to "
            f"{question!r}")

    if outcome == "timeout":
        return TEST_FAILED, (
            f"Notepad did not start within {REPEAT_PROMPT_WINDOW + APP_START_WINDOW:.0f}s of "
            f"answering Yes to LIMA's question {question!r}, so the pre-approved action never "
            f"ran")

    return TEST_PASSED, (
        f"LIMA asked {question!r} under 'LIMA asks:', a Yes was accepted, and Notepad opened "
        f"with no second 'LIMA wants to:' prompt — the answer pre-approved the action.")


def _run_case(executor):
    """
    Do the scenario.

    Returns:
        (status, message) for one result line.
    """
    if not _common.ensure_lima_ready(executor):
        return TEST_FAILED, "LIMA was not running with its window ready, so the test could not run"

    _common.close_apps(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)
    if _common.app_running(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS):
        return TEST_FAILED, ("Notepad was already running and could not be closed, so it would "
                             "be impossible to tell whether LIMA started it")

    _common.send_instruction(INSTRUCTION)
    prompt = wait_for_action_prompt(timeout=PROMPT_TIMEOUT)
    if prompt is None:
        return TEST_FAILED, (
            f"LIMA did not ask anything within {PROMPT_TIMEOUT:.0f}s of {INSTRUCTION!r}. "
            f"Opening Notepad is gated, and a request to be asked first must produce a "
            f"'LIMA asks:' question, so silence means the turn was dropped or ran without "
            f"asking.")

    if prompt.kind == "question":
        return _check_question_path(prompt)

    # The model skipped asking and proposed the action itself. That is its behaviour, not an
    # approval-loop defect, so deny it, end the turn, and retry once more explicitly.
    print(f"  Model proposed the action without asking: {prompt.description!r}")
    _deny_and_end_turn(prompt)

    _common.send_instruction(RETRY_INSTRUCTION)
    prompt = wait_for_action_prompt(timeout=PROMPT_TIMEOUT)
    if prompt is None:
        return TEST_SKIPPED, (
            f"Model didn't use ask_permission; question path not exercised (the retry "
            f"{RETRY_INSTRUCTION!r} produced no prompt within {PROMPT_TIMEOUT:.0f}s)")

    if prompt.kind == "question":
        return _check_question_path(prompt)

    print(f"  Model still proposed the action without asking: {prompt.description!r}")
    _deny_and_end_turn(prompt)
    return TEST_SKIPPED, (
        "Model didn't use ask_permission; question path not exercised (both attempts produced "
        "a 'LIMA wants to:' action prompt instead of a 'LIMA asks:' question)")


def run(executor):
    """Run the test and report exactly one result."""
    status, message = TEST_FAILED, "The test did not run"
    with manual_approvals():
        try:
            status, message = _run_case(executor)
        except Exception as error:
            status, message = TEST_FAILED, f"Exception during the test: {error}"
        finally:
            # Leave no popup waiting and no Notepad open, even when the scenario failed.
            _common.cleanup(NOTEPAD_PROCESSES, NOTEPAD_WINDOW_KEYWORDS)

    executor.add_test_result(RESULT_NAME, status, message)
    marker = {TEST_PASSED: "  OK ", TEST_SKIPPED: "  SKIP "}.get(status, "  X ")
    print(marker + message)
