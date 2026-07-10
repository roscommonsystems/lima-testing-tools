"""
LIMA Test Executor Module
Handles test execution, LIMA process lifecycle management, and test coordination.
"""

import ctypes
import os
import sys
import time
import pyautogui

from lima_test_utils import *
from lima_test_reporter import LimaTestReporter
from lima_process_manager import LimaProcessManager
from lima_tool_tests import run_all_tool_tests
from lima_voice_tests import run_all_voice_tests


class LimaTestExecutor:
    """Handles execution of LIMA regression tests."""
    
    def __init__(self):
        """Initialize the test executor with reporter and process manager."""
        self.reporter = LimaTestReporter()
        self.process_manager = LimaProcessManager()
    
    # ========================================
    # Property Delegates to Reporter
    # ========================================
    
    @property
    def test_results(self):
        """Get test results from reporter."""
        return self.reporter.test_results
    
    def add_test_result(self, test_name, status, message):
        """Add a test result via reporter."""
        self.reporter.add_test_result(test_name, status, message)
    
    def add_error(self, error_message):
        """Add an error via reporter."""
        self.reporter.add_error(error_message)
    
    # ========================================
    # Helpers
    # ========================================

    def _msgbox(self, title, message, error=False):
        """Show a Windows message box. MB_ICONERROR=0x10, MB_ICONINFORMATION=0x40.
        MB_SYSTEMMODAL|MB_TOPMOST|MB_SETFOREGROUND force the dialog to the front
        so it doesn't hide behind the test console."""
        icon = 0x10 if error else 0x40
        flags = icon | 0x1000 | 0x40000 | 0x10000
        sys.stdout.flush()
        ctypes.windll.user32.MessageBoxW(0, message, title, flags)

    # ========================================
    # Main Test Runner
    # ========================================

    def run_tests(self):
        """
        Run the complete regression test suite.
        
        Returns:
            bool: True if all tests passed, False otherwise
        """
        try:
            # Minimize all other windows first for clean environment
            minimize_all_other_windows()

            # Center the mouse on startup for consistent test positioning
            screen_width, screen_height = pyautogui.size()
            pyautogui.moveTo(screen_width // 2, screen_height // 2)

            # Note: print() is used intentionally throughout this module instead of the logging
            # module. These tests are run via .bat scripts where stdout is the primary output channel.

            # Require API key before running any tests
            print("Checking API key availability...")
            if not initialize_openrouter_api_key():
                print("ERROR: OPEN_ROUTER_API_KEY could not be retrieved. Aborting test run.")
                print("  Hint: Make sure lima_config.json is properly configured with a valid license key.")
                self.reporter.finalize_results()
                self._msgbox("LIMA Tests Aborted", "Could not retrieve API key.\n\nCheck lima_config.json has a valid license key.", error=True)
                return False
            print("  OK API key verified\n")

            # Test 1: Find LIMA executable first
            if not self._test_lima_discovery():
                self.reporter.finalize_results()
                self._msgbox("LIMA Tests Aborted", "LIMA executable not found.\n\nCheck that LIMA Screen Reader is installed.", error=True)
                return False

            # Test 1b: Verify production build is windowed (no console window)
            self._test_no_console_window()

            # Test 2: Check for pre-existing crash logs
            self._test_prerun_crash_logs()
            
            # Test 3: Check license and settings file persistence
            self._test_license_key_persistence()
            self._test_settings_file_persistence()
            
            # Test 4: Launch LIMA
            if not self._test_lima_launch():
                self.reporter.finalize_results()
                self._msgbox("LIMA Tests Aborted", "LIMA failed to launch.", error=True)
                return False
            
            # Test 5: Monitor stability
            self._test_stability_monitoring()

            # Test 6: Close before tool-test loop (which relaunches per test)
            close_error = self.process_manager.close()
            if close_error:
                self.add_error(close_error)
            time.sleep(SLEEP_C)

            # Run all tool tests — each test relaunches LIMA independently for isolation.
            # Note: test filtering/selection is not supported by design — this is a full
            # regression suite intended to run every test on every execution.
            self._test_all_tools()

            # Close LIMA after all tool tests
            close_error = self.process_manager.close()
            if close_error:
                self.add_error(close_error)
            time.sleep(SLEEP_C)

            # Run all voice-coverage tests (launches/closes its own LIMA session)
            self._test_all_voices()

            close_error = self.process_manager.close()
            if close_error:
                self.add_error(close_error)
            time.sleep(SLEEP_C)

            # Test 8: Check for crash logs after run
            self._test_postrun_crash_logs()

            
        except Exception as error:
            error_msg = f"Unexpected error during test execution: {str(error)}"
            self.add_test_result("Test Execution", TEST_FAILED, error_msg)
            self.add_error(error_msg)
            self._msgbox("LIMA Tests Crashed", f"Unexpected error:\n\n{error}", error=True)

        self.reporter.finalize_results()
        passed = self.reporter.get_overall_status() == TEST_PASSED
        tests = self.reporter.test_results["tests"]
        total_tests = len(tests)
        failures = sum(1 for t in tests if t.get("status") == TEST_FAILED)
        self.print_summary()
        if passed:
            self._msgbox("LIMA Tests Complete", f"All {total_tests} tests passed.")
        else:
            self._msgbox("LIMA Tests Complete", f"{failures} of {total_tests} tests failed.\n\nCheck test_results.json for details.", error=True)
        return passed
    
    # ========================================
    # Individual Test Methods
    # ========================================
    
    def _test_lima_discovery(self):
        """
        Test: Discover LIMA executable in Program Files.
        
        Returns:
            bool: True if executable found, False otherwise
        """
        self.process_manager.install_path = None
        self.process_manager.exe_full_path = find_lima_executable()
        
        if self.process_manager.exe_full_path:
            # Extract installation directory
            self.process_manager.install_path = os.path.dirname(self.process_manager.exe_full_path)
            message = f"Found LIMA executable at {self.process_manager.exe_full_path}"
            self.add_test_result("Lima Executable Discovery", TEST_PASSED, message)
            return True
        else:
            message = "LIMA executable not found in standard locations"
            self.add_test_result("Lima Executable Discovery", TEST_FAILED, message)
            self.add_error("Unable to locate LIMA installation")
            return False
    
    def _test_no_console_window(self):
        """
        Test: Verify the production LIMA build is windowed (no console window).

        LIMA is a GUI screen reader, so its executable should be packaged with
        the WINDOWS_GUI subsystem. A WINDOWS_CONSOLE build causes a terminal
        window to appear whenever LIMA launches — a visible defect for end
        users. This is a static check on the shipped .exe (its PE subsystem),
        so it requires no launch and cannot flake.
        """
        try:
            exe_path = self.process_manager.exe_full_path
            if not exe_path:
                message = "Cannot check console subsystem - LIMA executable path unknown"
                self.add_test_result("Console Window Absence Check", TEST_FAILED, message)
                return

            subsystem = get_pe_subsystem(exe_path)
            subsystem_name = PE_SUBSYSTEM_NAMES.get(subsystem, f"UNKNOWN({subsystem})")

            if subsystem == PE_SUBSYSTEM_WINDOWS_GUI:
                message = f"Production build is windowed ({subsystem_name} subsystem) - no console window will appear"
                self.add_test_result("Console Window Absence Check", TEST_PASSED, message)
            else:
                message = (
                    f"Production build uses {subsystem_name} subsystem - a console/terminal "
                    f"window will appear on launch. Rebuild LIMA in windowed mode (console disabled)."
                )
                self.add_test_result("Console Window Absence Check", TEST_FAILED, message)
                self.add_error("LIMA executable is not packaged as a windowed (GUI) application")

        except Exception as error:
            message = f"Exception during console subsystem check: {str(error)}"
            self.add_test_result("Console Window Absence Check", TEST_FAILED, message)

    def _test_prerun_crash_logs(self):
        """Test: Check for pre-existing crash logs before starting LIMA."""
        crash_info = check_crash_logs(self.process_manager.install_path)
        
        if crash_info.get("exists"):
            self.process_manager.crash_log_baseline = crash_info
            message = "Pre-existing crash log detected (will monitor for new ones)"
            self.add_test_result("Pre-Run Crash Log Check", TEST_PASSED, message)
        else:
            message = "No pre-existing crash logs detected"
            self.add_test_result("Pre-Run Crash Log Check", TEST_PASSED, message)
    
    def _test_lima_launch(self):
        """
        Test: Launch LIMA application using os.startfile().
        
        Returns:
            bool: True if launch successful, False otherwise
        """
        try:
            if not self.process_manager.exe_full_path:
                raise ValueError("LIMA executable path not found")
            
            # Change to LIMA's installation directory before launching
            # This ensures relative paths work correctly
            original_dir = os.getcwd()
            os.chdir(self.process_manager.install_path)
            
            try:
                # Launch LIMA using os.startfile (Windows-specific)
                os.startfile(self.process_manager.exe_full_path)
                
                # Wait for process to start
                time.sleep(SLEEP_D)
                
                # Find the LIMA process
                self.process_manager.process = find_process_by_name(self.process_manager.exe_full_path)
                
                if self.process_manager.process:
                    self.process_manager.pid = self.process_manager.process.pid
                    message = f"Lima launched successfully (PID: {self.process_manager.pid})"
                    self.add_test_result("Application Launch", TEST_PASSED, message)
                    return True
                else:
                    message = "Lima process not found after launch - may have crashed immediately"
                    self.add_test_result("Application Launch", TEST_FAILED, message)
                    self.add_error("LIMA process not detected after launch")
                    return False
                    
            finally:
                # Restore original directory
                os.chdir(original_dir)
                
        except Exception as error:
            message = f"Failed to launch Lima: {str(error)}"
            self.add_test_result("Application Launch", TEST_FAILED, message)
            self.add_error(f"Launch exception: {str(error)}")
            return False
    
    def _test_stability_monitoring(self):
        """Test: Monitor LIMA stability for 10 seconds while checking for crashes."""
        monitoring_duration = 10
        check_interval = 2
        monitoring_start = time.time()
        
        while time.time() - monitoring_start < monitoring_duration:
            # Check if process is still running
            if not self.process_manager.is_running():
                message = "Lima process crashed unexpectedly during stability check"
                self.add_test_result("Stability Check", TEST_FAILED, message)
                self.add_error("Application crashed during monitoring")
                return
            
            # Check for crash logs during monitoring
            crash_info = check_crash_logs(self.process_manager.install_path)
            if crash_info.get("exists"):
                # Compare with baseline - if different, new crash occurred
                if not self.process_manager.crash_log_baseline or crash_info.get("contents") != self.process_manager.crash_log_baseline.get("contents"):
                    message = "Crash log created during monitoring phase"
                    self.add_test_result("Stability Check", TEST_FAILED, message)
                    self.reporter.set_crash_log_info(
                        True, crash_info["path"], crash_info["contents"]
                    )
                    self.add_error("Crash detected during stability monitoring")
                    return
            
            time.sleep(check_interval)
        
        message = f"Application remained stable for {monitoring_duration} seconds"
        self.add_test_result("Stability Check", TEST_PASSED, message)
    
    def _test_license_key_persistence(self):
        """
        Test: Verify license key file exists and persists (simulating update scenario).
        """
        try:
            if not self.process_manager.install_path:
                message = "Cannot test license persistence - install path unknown"
                self.add_test_result("License Key Persistence Test", TEST_FAILED, message)
                return
            
            # Check for license file (common names)
            license_paths = [
                os.path.join(self.process_manager.install_path, "data", "activation_key.txt"),
                os.path.join(self.process_manager.install_path, "data", "license.key"),
                os.path.join(self.process_manager.install_path, "data", "license.txt")
            ]
            
            license_found = False
            license_location = None
            
            for license_path in license_paths:
                if os.path.exists(license_path):
                    license_found = True
                    license_location = license_path
                    break
            
            if license_found:
                message = f"License file found at {license_location} - will persist across updates"
                self.add_test_result("License Key Persistence Test", TEST_PASSED, message)
            else:
                message = "No license file found in data directory - may require re-entry after updates"
                self.add_test_result("License Key Persistence Test", TEST_FAILED, message)
                
        except Exception as error:
            message = f"Exception during license persistence test: {str(error)}"
            self.add_test_result("License Key Persistence Test", TEST_FAILED, message)

    def _test_settings_file_persistence(self):
        """
        Test: Verify settings file exists and will persist through updates.
        """
        try:
            if not self.process_manager.install_path:
                message = "Cannot test settings file persistence - install path unknown"
                self.add_test_result("Settings File Persistence Test", TEST_FAILED, message)
                return
            
            import json
            config_path = os.path.join(self.process_manager.install_path, "data", "config.json")
            
            if os.path.exists(config_path):
                # Verify it's readable
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    
                    message = f"Settings file exists and is valid - will persist across updates"
                    self.add_test_result("Settings File Persistence Test", TEST_PASSED, message)
                except Exception as error:
                    message = f"Settings file exists but is corrupted: {str(error)}"
                    self.add_test_result("Settings File Persistence Test", TEST_FAILED, message)
            else:
                message = "Settings file not found - application using defaults"
                self.add_test_result("Settings File Persistence Test", TEST_FAILED, message)
                
        except Exception as error:
            message = f"Exception during settings file persistence test: {str(error)}"
            self.add_test_result("Settings File Persistence Test", TEST_FAILED, message)
    
    def _test_postrun_crash_logs(self):
        """Test: Check for crash logs created during test run."""
        # Give filesystem time to flush
        time.sleep(SLEEP_A)
        
        crash_info = check_crash_logs(self.process_manager.install_path)
        
        if crash_info.get("exists"):
            # Check if this is a new crash log
            if not self.process_manager.crash_log_baseline or crash_info.get("contents") != self.process_manager.crash_log_baseline.get("contents"):
                message = "New crash log detected after test run"
                self.add_test_result("Post-Run Crash Log Check", TEST_FAILED, message)
                self.reporter.set_crash_log_info(True, crash_info["path"], crash_info["contents"])
                self.add_error("Crash logs found after LIMA execution")
                return
        
        message = "No new crash logs detected after test run"
        self.add_test_result("Post-Run Crash Log Check", TEST_PASSED, message)
    
    # ========================================
    # Tool Testing Methods
    # ========================================
    
    def _test_all_tools(self):
        """Test: Run all LIMA AI tool tests in a single session with screenshot verification."""
        run_all_tool_tests(self)

    def _test_all_voices(self):
        """Test: Verify each selectable TTS voice can be switched to and produces audio."""
        run_all_voice_tests(self)

    # ========================================
    # Delegate Methods to Reporter
    # ========================================
    
    def save_report(self, output_path="test_results.json"):
        """Save test results to JSON file."""
        self.reporter.save_report(output_path)
    
    def print_summary(self):
        """Print a summary of test results to console."""
        self.reporter.print_summary()
