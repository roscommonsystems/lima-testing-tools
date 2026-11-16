"""
AI tools: type text, with and without submitting it.

``type_text`` has a ``press_enter`` flag: off when the user is filling in a field, on when the
text should be sent. Getting it wrong either leaves a search unsent or submits a half-filled
form. The practice page opens with the form's First name field focused, and reports what the
field holds and whether the form was submitted, so both halves are checked: the text arrived,
and Enter was or was not pressed.

The text is a code word made up for the run, so it can only be in the field because LIMA
typed it.
"""

from ai_tool_tests import _common
from feature_tests._common import contains_code_word, make_code_word
from lima_practice_page import FORM_FIELDS, SUBMIT_NAME

FIELD_NAME = FORM_FIELDS[0]
FIELD_ID = "first-name"

# (result name, the instruction with a place for the code word, whether the form must be sent)
CASES = (
    ("AI tools: type without submitting", "Type {code_word} here, but don't submit it yet.", False),
    ("AI tools: type and press Enter", "Type {code_word} here and press Enter.", True),
)


def case_name(case):
    result_name = case[0]
    return result_name


def _check_for(code_word, must_submit):
    def check(page, since):
        submit = page.wait_for_event("submit", target=SUBMIT_NAME, since=since,
                                     timeout=_common.EVENT_TIMEOUT)
        typed = page.field_value(FIELD_NAME)
        if not contains_code_word(typed, code_word):
            outcome = f"The {FIELD_NAME} field holds {typed!r}, not the code word {code_word!r}."
            return False, outcome
        if must_submit and submit is None:
            outcome = f"{code_word!r} was typed into {FIELD_NAME}, but the form was never submitted."
            return False, outcome
        if not must_submit and submit is not None:
            outcome = (f"{code_word!r} was typed into {FIELD_NAME}, but the form was submitted "
                       f"although LIMA was asked not to.")
            return False, outcome
        sent = "and the form was submitted" if must_submit else "and the form was not submitted"
        outcome = f"{code_word!r} was typed into {FIELD_NAME} {sent}."
        return True, outcome
    return check


def run_case(executor, case):
    result_name, instruction_template, must_submit = case
    code_word = make_code_word()
    instruction = instruction_template.format(code_word=code_word)
    check = _check_for(code_word, must_submit)
    _common.run_page_test(executor, result_name, instruction, check, focus=FIELD_ID)
