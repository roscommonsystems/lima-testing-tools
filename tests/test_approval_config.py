"""Approval setup uses real temporary config files; desktop actions are mocked."""
import importlib
import json
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'regression_tests'))
from approval_tests import _common
import lima_backup
import lima_action_approver


class ApprovalConfigTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.config = Path(temp.name, 'data', 'config.json')
        self.config.parent.mkdir()
        self.original = b'{ "ask_before_every_action": false, "other": "preserve" }\n'
        self.config.write_bytes(self.original)
        manager = Mock(install_path=temp.name, exe_full_path='LIMA.exe')
        manager.close.return_value = None
        manager.is_running.return_value = False
        manager.launch.return_value = True
        manager.refocus.return_value = True
        self.executor = Mock(process_manager=manager)
        self.user32 = Mock()
        self.user32.RegisterHotKey.return_value = True
        p = patch.object(_common.ctypes, 'WinDLL', return_value=self.user32)
        p.start()
        self.addCleanup(p.stop)
        for target in ('lima_backup.time.sleep', 'approval_tests._common.time.sleep',
                       'approval_tests._common.pyautogui'):
            p = patch(target)
            p.start()
            self.addCleanup(p.stop)

    def assert_enabled(self):
        self.assertIs(json.loads(self.config.read_text())['ask_before_every_action'], True)

    def test_enabled_before_launch_and_original_bytes_restored(self):
        self.executor.process_manager.launch.side_effect = lambda *args: self.assert_enabled() or True
        with _common.approval_config(self.executor):
            self.assertTrue(_common.ensure_lima_ready(self.executor))
            self.assertEqual(json.loads(self.config.read_text())['other'], 'preserve')
        self.executor.process_manager.launch.assert_called_once()
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_scenario_exception_still_restores_config(self):
        with self.assertRaisesRegex(ValueError, 'scenario failed'):
            with _common.approval_config(self.executor):
                raise ValueError('scenario failed')
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_originally_missing_config_is_removed(self):
        self.config.unlink()
        with _common.approval_config(self.executor):
            self.assert_enabled()
        self.assertFalse(self.config.exists())

    def test_partial_setup_failure_restores_config(self):
        def failed_seed(*args, **kwargs):
            self.config.write_text('{}')
            raise OSError('write failed')
        with patch.object(_common, 'seed_config', side_effect=failed_seed):
            with self.assertRaisesRegex(OSError, 'write failed'):
                with _common.approval_config(self.executor):
                    self.fail('Scenario must not start')
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_failed_setting_readback_stops_before_launch(self):
        with patch.object(_common, 'read_lima_config', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'SETUP FAILED'):
                with _common.approval_config(self.executor):
                    self.fail('Scenario must not start')
        self.executor.process_manager.launch.assert_not_called()
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_setting_changed_by_launch_is_a_setup_failure(self):
        def launch(*args):
            self.config.write_text('{"ask_before_every_action": false}')
            return True
        self.executor.process_manager.launch.side_effect = launch
        with self.assertRaisesRegex(RuntimeError, 'SETUP FAILED'):
            with _common.approval_config(self.executor):
                _common.ensure_lima_ready(self.executor)
        self.executor.process_manager.refocus.assert_not_called()
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_close_failure_prevents_config_changes(self):
        self.executor.process_manager.close.return_value = 'still running'
        with self.assertRaisesRegex(RuntimeError, 'SETUP FAILED'):
            with _common.approval_config(self.executor):
                self.fail('Scenario must not start')
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_restore_failure_is_not_a_pass(self):
        with patch.object(lima_backup.FileBackup, 'restore', return_value=(False, 'locked')):
            with self.assertRaisesRegex(RuntimeError, 'CLEANUP FAILED.*locked'):
                with _common.approval_config(self.executor):
                    self.assert_enabled()

    def test_test_bindings_are_temporary_and_probes_are_released(self):
        with _common.approval_config(self.executor, answer_hotkeys=True):
            config = json.loads(self.config.read_text())
            self.assertEqual(config['approve_action_hotkey'], {'modifier': 'ctrl+alt+shift', 'key': 'f11'})
            self.assertEqual(config['deny_action_hotkey'], {'modifier': 'ctrl+alt+shift', 'key': 'f12'})
        self.assertEqual(self.user32.UnregisterHotKey.call_count, 2)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_occupied_test_binding_uses_another_key(self):
        self.user32.RegisterHotKey.side_effect = [False, True, True]
        with patch.object(_common.ctypes, 'get_last_error', return_value=1409):
            bindings = _common._test_answer_hotkeys(self.executor)
        self.assertEqual(bindings['approve_action_hotkey']['key'], 'f12')
        self.assertEqual(bindings['deny_action_hotkey']['key'], 'f9')
        self.assertEqual(self.user32.UnregisterHotKey.call_count, 2)

    def test_all_bindings_occupied_fails_setup_and_restores_config(self):
        self.user32.RegisterHotKey.return_value = False
        with patch.object(_common.ctypes, 'get_last_error', return_value=1409):
            with self.assertRaisesRegex(RuntimeError, 'SETUP FAILED: no two available'):
                with _common.approval_config(self.executor, answer_hotkeys=True):
                    self.fail('Scenario must not start')
        self.assertEqual(self.config.read_bytes(), self.original)
        self.user32.UnregisterHotKey.assert_not_called()

    def test_other_lima_binding_is_not_reused(self):
        self.config.write_text(json.dumps({'quick_input_hotkey': {
            'modifier': 'shift+ctrl+alt', 'key': 'f11'}}))
        bindings = _common._test_answer_hotkeys(self.executor)
        self.assertEqual(bindings['approve_action_hotkey']['key'], 'f12')
        self.assertEqual(bindings['deny_action_hotkey']['key'], 'f9')

    def test_unexpected_probe_error_is_reported(self):
        self.user32.RegisterHotKey.return_value = False
        with patch.object(_common.ctypes, 'get_last_error', return_value=5):
            with self.assertRaisesRegex(RuntimeError, 'Windows error 5'):
                _common._test_answer_hotkeys(self.executor)

    def test_hotkey_answer_reads_the_tested_instance_config(self):
        self.config.write_text(json.dumps({'deny_action_hotkey': {
            'modifier': 'ctrl+alt+shift', 'key': 'f12'}}))
        with patch.object(lima_action_approver, 'pyautogui') as keyboard, \
             patch.object(lima_action_approver, '_wait_until_closed', return_value=True):
            self.assertTrue(lima_action_approver.answer_action_prompt(
                123, False, via=lima_action_approver.VIA_HOTKEY,
                install_path=self.executor.process_manager.install_path))
        keyboard.hotkey.assert_called_once_with('ctrl', 'alt', 'shift', 'f12')

    def test_every_approval_module_runs_with_config_and_restores_it(self):
        modules = ('test_10_deny_stops_action', 'test_20_deny_with_replacement',
                   'test_30_waits_for_answer', 'test_40_lima_asks_question',
                   'test_50_answer_keys')
        for name in modules:
            with self.subTest(module=name):
                module = importlib.import_module(f'approval_tests.{name}')
                scenario = '_safe_run_case' if name == 'test_50_answer_keys' else '_run_case'
                def outcome(*args):
                    self.assert_enabled()
                    if name == 'test_40_lima_asks_question':
                        return module.TEST_PASSED, 'checked'
                    return True, 'checked'
                with patch.object(module, 'manual_approvals', side_effect=nullcontext), \
                     patch.object(_common, 'cleanup'), \
                     patch.object(module, scenario, side_effect=outcome) as run:
                    if name == 'test_50_answer_keys':
                        with patch.object(module, 'get_answer_hotkeys', return_value={
                                'approve': ['ctrl', 'alt', 'y'], 'deny': ['ctrl', 'alt', 'n']}):
                            module.run(self.executor)
                        self.assertEqual(run.call_count, 4)
                    else:
                        module.run(self.executor)
                        run.assert_called_once()
                self.assertEqual(self.config.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
