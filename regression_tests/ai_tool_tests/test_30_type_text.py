"""
AI tools: type text, with and without submitting it.

``type_text`` has a ``press_enter`` flag: off when the user is filling in a field, on when the
text should be sent. Getting it wrong either leaves a search unsent or submits a half-filled
form. Test both a form field and a chat composer where Enter sends and clears the draft.
Check exact text in the field or submission payload and whether a submission happened.

The text is a code word made up for the run, so it can only be in the field because LIMA
typed it.
"""

import time

from ai_tool_tests import _common
from feature_tests._common import make_code_word
from lima_practice_page import FORM_FIELDS, SUBMIT_NAME, CHAT_FIELD_NAME, CHAT_SUBMIT_NAME

FIELD_NAME = FORM_FIELDS[0]
FIELD_ID = "first-name"

# (result name, instruction, whether to submit, field to focus)
CASES = (
    ("AI tools: plain type leaves text unsubmitted", "Type {code_word}", False, FIELD_ID),
    ("AI tools: type without submitting", "Type {code_word} here, but don't submit it yet.", False, FIELD_ID),
    ("AI tools: type and press Enter", "Type {code_word} here and press Enter.", True, FIELD_ID),
    ("AI tools: plain type in chat does not send", "Type {code_word}", False, "chat-message"),
    ("AI tools: type and press Enter in chat", "Type {code_word} here and press Enter.", True, "chat-message"),
)


def case_name(case):
    result_name = case[0]
    return result_name


def _check_for(code_word, must_submit, field_name=FIELD_NAME, submit_name=SUBMIT_NAME):
    def check(page, since):
        # The turn has ended, but browser event posts may still be in flight. Wait
        # for the whole delivery window even when the first submission is present.
        time.sleep(_common.EVENT_TIMEOUT)
        submissions = page.events("submit", target=submit_name, since=since)
        typed = page.field_value(field_name)
        if not must_submit and submissions:
            outcome = f"{submit_name} was triggered although the instruction did not authorize submission."
            return False, outcome
        if must_submit:
            if not submissions:
                return False, f"{submit_name} was never triggered. The field holds {typed!r}."
            if len(submissions) != 1:
                return False, f"{submit_name} was triggered {len(submissions)} times, expected exactly once."
            submit = submissions[0]
            sent_text = submit.get("detail", {}).get("values", {}).get(field_name)
            if sent_text != code_word:
                return False, f"{submit_name} submitted {sent_text!r}, expected exactly {code_word!r}."
            outcome = f"{submit_name} submitted exactly {code_word!r}."
        else:
            if typed != code_word:
                return False, f"The {field_name} field holds {typed!r}, expected exactly {code_word!r}."
            outcome = f"{code_word!r} remains in {field_name}; {submit_name} was not triggered."
        return True, outcome
    return check


def run_case(executor, case):
    result_name, instruction_template, must_submit, field_id = case
    code_word = make_code_word()
    instruction = instruction_template.format(code_word=code_word)
    chat = field_id == "chat-message"
    check = _check_for(code_word, must_submit,
                       CHAT_FIELD_NAME if chat else FIELD_NAME,
                       CHAT_SUBMIT_NAME if chat else SUBMIT_NAME)
    _common.run_page_test(executor, result_name, instruction, check, focus=field_id)
