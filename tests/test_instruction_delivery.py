"""Instruction delivery regressions; all desktop input and timing are mocked."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'regression_tests'))
import lima_test_utils as utils


class InstructionDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.value = ''
        self.foreground = 123
        self.clock = 0
        self.drop_key = False
        self.fail_clear = False
        self.steal_focus = False
        self.input = Mock()
        self.input.GetValuePattern.side_effect = lambda: SimpleNamespace(Value=self.value)
        self.input.SendKeys.side_effect = self.send_keys
        self.user32 = Mock()
        self.user32.GetForegroundWindow.side_effect = lambda: self.foreground
        patches = [
            patch.object(utils, 'find_lima_uia_window', return_value=SimpleNamespace(NativeWindowHandle=123)),
            patch.object(utils, 'find_lima_message_input', return_value=self.input),
            patch.object(utils, 'activate_window', side_effect=self.activate),
            patch.object(utils.ctypes, 'windll', SimpleNamespace(user32=self.user32)),
            patch.object(utils, 'pyautogui'),
            patch.object(utils, 'time'),
            patch.object(utils, 'get_window_pid', return_value=42),
            patch.object(utils.psutil, 'Process'),
            patch('lima_action_approver.approve_action_prompts'),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.mocks[5].monotonic.side_effect = self.tick
        self.mocks[7].return_value.name.return_value = 'notepad.exe'

    def tick(self):
        self.clock += 0.5
        return self.clock

    def activate(self, hwnd):
        self.foreground = hwnd
        return True

    def send_keys(self, text):
        if text == '{Ctrl}a{Delete}':
            if not self.fail_clear:
                self.value = ''
        else:
            self.value += text[:-1] if self.drop_key else text
            if self.steal_focus:
                self.foreground = 456

    def test_replaces_leftover_input(self):
        self.value = 'old partial command'
        utils.type_into_lima('count to 5')
        self.assertEqual(self.value, 'count to 5')

    def test_partial_failure_is_cleared_and_next_call_recovers(self):
        self.drop_key = True
        with self.assertRaisesRegex(RuntimeError, 'instruction did not reach'):
            utils.type_into_lima('change your voice to Test')
        self.assertEqual(self.value, '')
        self.drop_key = False
        utils.type_into_lima('count to 5')
        self.assertEqual(self.value, 'count to 5')

    def test_failed_clear_prevents_command_typing(self):
        self.value = 'leftover'
        self.fail_clear = True
        with self.assertRaisesRegex(RuntimeError, 'could not be cleared'):
            utils.type_into_lima('count to 5')
        self.assertTrue(all(c.args == ('{Ctrl}a{Delete}',) for c in self.input.SendKeys.call_args_list))

    def test_cleanup_skipped_when_foreground_is_lost(self):
        self.drop_key = self.steal_focus = True
        with self.assertRaisesRegex(RuntimeError, 'instruction did not reach'):
            utils.type_into_lima('count to 5')
        self.assertEqual(self.input.SendKeys.call_count, 2)

    def test_foreign_app_receives_no_escape(self):
        self.foreground = 456
        utils.type_into_lima('count to 5')
        self.mocks[4].press.assert_not_called()

    def test_start_menu_is_dismissed(self):
        self.foreground = 456
        self.mocks[7].return_value.name.return_value = 'StartMenuExperienceHost.exe'
        utils.type_into_lima('count to 5')
        self.mocks[4].press.assert_called_once_with('escape')
        self.mocks[6].assert_called_once_with(456)

    def test_unknown_owner_receives_no_escape(self):
        self.foreground = 456
        self.mocks[7].side_effect = utils.psutil.AccessDenied(42)
        utils.type_into_lima('count to 5')
        self.mocks[4].press.assert_not_called()

    def test_failed_activation_prevents_typing(self):
        self.mocks[2].side_effect = None
        self.mocks[2].return_value = False
        with self.assertRaisesRegex(RuntimeError, 'brought to the foreground'):
            utils.type_into_lima('count to 5')
        self.input.SendKeys.assert_not_called()

    def test_intercepted_click_prevents_clear_and_typing(self):
        self.input.Click.side_effect = lambda: setattr(self, 'foreground', 456)
        with self.assertRaisesRegex(RuntimeError, 'intercepted'):
            utils.type_into_lima('count to 5')
        self.input.SendKeys.assert_not_called()

    def test_text_pattern_fallback(self):
        self.input.GetValuePattern.side_effect = RuntimeError('unsupported')
        self.input.GetTextPattern.return_value.DocumentRange.GetText.side_effect = lambda n: self.value
        utils.type_into_lima('count to 5')
        self.assertEqual(self.value, 'count to 5')

    def test_accessible_name_cannot_pass_verification(self):
        self.input.GetValuePattern.side_effect = RuntimeError('unsupported')
        self.input.GetTextPattern.side_effect = RuntimeError('unsupported')
        self.input.Name = 'count to 5'
        self.assertFalse(utils.verify_text_in_lima_input('count to 5'))

    def test_shared_reader_keeps_substring_verification(self):
        self.value = 'prefix count to 5 suffix'
        self.assertTrue(utils.verify_text_in_lima_input('count to 5'))


if __name__ == '__main__':
    unittest.main()
