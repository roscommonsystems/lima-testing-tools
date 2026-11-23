"""Outcome checks for exact typing and submission, independent of model wording."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'regression_tests'))
from ai_tool_tests.test_30_type_text import _check_for, FIELD_NAME
from lima_practice_page import CHAT_FIELD_NAME, CHAT_SUBMIT_NAME


class TypingOutcomeTests(unittest.TestCase):
    def check_case(self, typed, submitted=None, must_submit=False, chat=False):
        page = Mock()
        page.field_value.return_value = typed
        page.wait_for_event.return_value = submitted
        kwargs = dict(field_name=CHAT_FIELD_NAME, submit_name=CHAT_SUBMIT_NAME) if chat else {}
        result = _check_for('draft123', must_submit, **kwargs)(page, 100.0)
        self.assertEqual(page.wait_for_event.call_args.kwargs['since'], 100.0)
        return result[0]

    def test_exact_unsubmitted_text_passes(self):
        self.assertTrue(self.check_case('draft123'))

    def test_extra_text_cannot_pass_by_containing_the_code_word(self):
        self.assertFalse(self.check_case('draft123 has been typed'))

    def test_missing_text_fails(self):
        self.assertFalse(self.check_case(''))

    def test_plain_chat_typing_must_not_send_even_if_composer_clears(self):
        event = {'detail': {'values': {CHAT_FIELD_NAME: 'draft123'}}}
        self.assertFalse(self.check_case('', event, chat=True))

    def test_chat_text_left_in_composer_passes(self):
        self.assertTrue(self.check_case('draft123', chat=True))

    def test_explicit_chat_send_checks_payload_after_composer_clears(self):
        event = {'detail': {'values': {CHAT_FIELD_NAME: 'draft123'}}}
        self.assertTrue(self.check_case('', event, must_submit=True, chat=True))

    def test_wrong_sent_text_fails_even_when_composer_contains_correct_text(self):
        event = {'detail': {'values': {CHAT_FIELD_NAME: 'wrong'}}}
        self.assertFalse(self.check_case('draft123', event, must_submit=True, chat=True))

    def test_send_requires_an_actual_submit_event(self):
        self.assertFalse(self.check_case('draft123', must_submit=True))

    def test_form_submission_checks_exact_payload(self):
        event = {'detail': {'values': {FIELD_NAME: 'draft123'}}}
        self.assertTrue(self.check_case('draft123', event, must_submit=True))


if __name__ == '__main__':
    unittest.main()
