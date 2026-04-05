"""
LIMA Test Executor Module
Handles test execution, LIMA process lifecycle management, and test coordination.
"""

import ctypes
import os
import sys
import time
import pyautogui
import pygetwindow as gw

from lima_test_utils import *
from lima_test_reporter import LimaTestReporter
from lima_process_manager import LimaProcessManager
from lima_tool_tests import run_all_tool_tests


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
        """Show a Windows message box. MB_ICONERROR=0x10, MB_ICONINFORMATION=0x40."""
        icon = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(0, message, title, icon)

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
            
            # Test 5: License validation on startup
            self._test_license_validation_on_startup()
            
            # Test 6: Monitor stability
            self._test_stability_monitoring()
            
            # Test 7: Test keyboard input detection
            self._test_keyboard_input_detection()
            
            # Test 8: Test Settings dialog
            self._test_settings_dialog()
            
            # Test 9: Test About dialog
            self._test_about_dialog()
            
            # Test 10: Test About dialog links
            self._test_about_dialog_links()
            
            # Test 11: Close LIMA and reopen for next test
            close_error = self.process_manager.close()
            if close_error:
                self.add_error(close_error)
            time.sleep(2)
            
            # Test 12: Re-launch LIMA for subscription test
            if not self._test_lima_launch():
                self.reporter.finalize_results()
                self._msgbox("LIMA Tests Aborted", "LIMA failed to re-launch for subscription test.", error=True)
                return False
            
            time.sleep(2)
            
            # Test 13: Test Subscription Information dialog
            self._test_subscription_dialog()
            
            # Test 14: Close for tool tests
            close_error = self.process_manager.close()
            if close_error:
                self.add_error(close_error)
            time.sleep(3)

            print("\n" + "="*60)
            print("LAUNCHING FRESH LIMA FOR TOOL TESTING")
            print("="*60)

            # Launch LIMA once for all tool tests
            if not self._test_lima_launch():
                print("X Could not launch LIMA for tool tests")
                self.reporter.finalize_results()
                self._msgbox("LIMA Tests Aborted", "LIMA failed to launch for tool tests.", error=True)
                return False
            time.sleep(5)

            # Run all tool tests in single session.
            # Note: test filtering/selection is not supported by design — this is a full
            # regression suite intended to run every test on every execution.
            self._test_all_tools()

            # Close LIMA after all tool tests
            close_error = self.process_manager.close()
            if close_error:
                self.add_error(close_error)
            time.sleep(3)

            # Test 15: Check for crash logs after run
            self._test_postrun_crash_logs()

            
        except Exception as error:
            error_msg = f"Unexpected error during test execution: {str(error)}"
            self.add_test_result("Test Execution", TEST_FAILED, error_msg)
            self.add_error(error_msg)
            self._msgbox("LIMA Tests Crashed", f"Unexpected error:\n\n{error}", error=True)

        self.reporter.finalize_results()
        passed = self.reporter.get_overall_status() == TEST_PASSED
        tests = self.reporter.test_results["tests"]
        total = len(tests)
        failures = sum(1 for t in tests if t.get("status") == TEST_FAILED)
        if passed:
            self._msgbox("LIMA Tests Complete", f"All {total} tests passed.")
        else:
            self._msgbox("LIMA Tests Complete", f"{failures} of {total} tests failed.\n\nCheck test_results.json for details.", error=True)
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
                time.sleep(4)
                
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
    
    def _test_license_validation_on_startup(self):
        """
        Test: Verify license validation occurs on startup without errors.
        """
        try:
            # If LIMA launched successfully, license validation passed
            if self.process_manager.process and self.process_manager.is_running():
                message = "License validation completed successfully on startup"
                self.add_test_result("License Validation on Startup", TEST_PASSED, message)
            else:
                message = "LIMA did not start - possible license validation failure"
                self.add_test_result("License Validation on Startup", TEST_FAILED, message)
                self.add_error("License validation may have failed")
        except Exception as error:
            message = f"Exception during license validation test: {str(error)}"
            self.add_test_result("License Validation on Startup", TEST_FAILED, message)
            self.add_error(f"License test exception: {str(error)}")
    
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
    
    def _test_keyboard_input_detection(self):
        """
        Test: Verify LIMA detects keyboard input (manual text entry).
        """
        print("\n" + "="*60)
        print("TEST: Keyboard Input Detection")
        print("="*60)
        
        try:
            # Find LIMA window
            lima_window = find_window_by_title("LIMA", timeout=5)
            if not lima_window:
                message = "Could not find LIMA window to test keyboard input"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            
            # Activate window and maximize for consistent positioning
            lima_window.activate()
            time.sleep(1.0)
            lima_window.maximize()
            time.sleep(1.0)
            
            # Use Windows UI Automation to click the actual text input (Edit control)
            try:
                from pywinauto import Desktop
                desktop = Desktop(backend="uia")
                lima_app = desktop.window(title_re=".*LIMA Screen Reader.*")
                edit = lima_app.child_window(control_type="Edit")
                edit.set_focus()
                edit.click_input()
                time.sleep(0.5)
            except Exception:
                # Fallback: click near window bottom if UIA fails
                try:
                    click_x = lima_window.left + (lima_window.width // 2)
                    click_y = lima_window.top + int(lima_window.height * 0.88)
                    pyautogui.click(click_x, click_y)
                    time.sleep(0.5)
                except Exception:
                    pass
            
            # ========================================
            # STEP 1: Take BEFORE screenshot
            # ========================================
            print("  Taking BEFORE screenshot...")
            before_screenshot = take_screenshot()
            if not before_screenshot:
                message = "Failed to capture before screenshot"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            print("  OK BEFORE screenshot captured")
            
            # ========================================
            # STEP 2: Execute the tool (type text)
            # ========================================
            print("  Executing keyboard input tool...")
            test_message = "Hello world"
            try:
                pyautogui.write(test_message, interval=0.2)
            except Exception:
                # Fallback to character by character if write fails
                for char in test_message:
                    pyautogui.press(char if len(char) == 1 else 'space')
                    time.sleep(0.05)
            
            time.sleep(1)  # Wait for text to appear
            print(f"  OK Typed: '{test_message}'")
            
            # ========================================
            # STEP 3: Take AFTER screenshot
            # ========================================
            print("  Taking AFTER screenshot...")
            after_screenshot = take_screenshot()
            if not after_screenshot:
                message = "Failed to capture after screenshot"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            print("  OK AFTER screenshot captured")
            
            # ========================================
            # STEP 4: Verify with OpenRouter Gemini
            # ========================================
            print("  Verifying with OpenRouter Gemini model...")
            verification_prompt = f"""Does the AFTER screenshot show the text '{test_message}' appearing in a text input field?
            This would indicate that keyboard input was successfully detected and displayed.
            Look for the text in the bottom portion of the LIMA Screen Reader window."""
            
            verification_result = verify_tool_with_screenshots(
                before_screenshot=before_screenshot,
                after_screenshot=after_screenshot,
                tool_name="keyboard_input_detection",
                verification_prompt=verification_prompt
            )
            
            # Clear the typed text after verification
            for _ in range(len(test_message)):
                pyautogui.press('backspace')
                time.sleep(0.02)
            
            time.sleep(1)
            
            # Verify LIMA is still running
            if not self.process_manager.is_running():
                message = "LIMA process crashed during keyboard input test"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            
            # ========================================
            # Process verification result
            # ========================================
            if verification_result is None:
                message = "Keyboard input test — API verification unavailable — cannot confirm result"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                print("  ! API verification unavailable")
                print("  X Test FAILED (API verification unavailable)")
            elif verification_result.get("answer") == "YES":
                # Tool verified as working
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"Keyboard input verified: {explanation}"
                self.add_test_result("Keyboard Input Detection Test", TEST_PASSED, message)
                print(f"\n  OK VERIFICATION PASSED")
                print(f"  Note: {explanation}")
                print("  OK Test PASSED")
            else:
                # Tool verified as NOT working
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"Keyboard input verification failed: {explanation}"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                print(f"\n  X VERIFICATION FAILED")
                print(f"  Note: {explanation}")
                print("  X Test FAILED")
            
            print("="*60 + "\n")
            
        except Exception as error:
            message = f"Exception during keyboard input test: {str(error)}"
            self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
    
    def _test_dialog(self, test_name, result_name, menu_nav_keys, dialog_title_keywords, verify_prompt):
        """
        Shared helper for testing dialogs opened from the LIMA File menu.

        Opens a dialog via menu navigation, verifies it appeared with AI screenshot
        comparison, then closes it.

        Args:
            test_name: Display name for print output (e.g. "Settings Dialog")
            result_name: Name used in test result recording (e.g. "Settings Dialog Test")
            menu_nav_keys: Keys to press after opening the menu to reach the item
                           (e.g. ['enter'] for Settings, ['down', 'enter'] for Subscription)
            dialog_title_keywords: Window title substrings to match when searching for the dialog
            verify_prompt: AI verification prompt describing what to look for
        """
        try:
            # Find LIMA window
            lima_window = None
            all_windows = gw.getAllWindows()
            for window in all_windows:
                if window.title == "LIMA Screen Reader":
                    lima_window = window
                    break
            if not lima_window:
                lima_window = find_window_by_title("LIMA Screen Reader", timeout=5)
            if not lima_window:
                message = f"Could not find LIMA Screen Reader window to open {test_name}"
                self.add_test_result(result_name, TEST_FAILED, message)
                self.add_error(f"LIMA window not found during {test_name}")
                return

            # Clear any stuck menus, then activate and focus
            try:
                pyautogui.press('escape')
                time.sleep(0.3)
                lima_window.activate()
                time.sleep(1.0)
                lima_window.maximize()
                time.sleep(1.0)
            except Exception:
                pass
            try:
                pyautogui.click(lima_window.left + 200, lima_window.top + 200)
                time.sleep(0.5)
            except Exception:
                pass

            # ========================================
            # STEP 1: Take BEFORE screenshot
            # ========================================
            print("  Taking BEFORE screenshot...")
            before_screenshot = take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")

            # Open File menu, then navigate to the target item
            print(f"  Opening {test_name}...")
            try:
                pyautogui.press('alt')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(1.5)
                for key in menu_nav_keys:
                    pyautogui.press(key)
                    time.sleep(0.5)
                time.sleep(2.5)
            except Exception:
                pass

            # ========================================
            # STEP 2: Take AFTER screenshot
            # ========================================
            print("  Taking AFTER screenshot...")
            after_screenshot = take_screenshot()
            if not after_screenshot:
                print("  ! Could not capture after screenshot")
            else:
                print("  OK AFTER screenshot captured")

            # Search for the dialog window
            print(f"  Searching for {test_name} window...")
            dialog_window = None
            for attempt in range(10):
                all_windows = gw.getAllWindows()
                if attempt == 0:
                    print("    Current windows:")
                    for w in all_windows:
                        if w.title.strip():
                            print(f"      - '{w.title}'")
                for window in all_windows:
                    if any(kw in window.title for kw in dialog_title_keywords):
                        dialog_window = window
                        print(f"  OK Found dialog: '{window.title}'")
                        break
                if dialog_window:
                    break
                if attempt % 2 == 0:
                    print(f"    Attempt {attempt + 1}/10 - {test_name} not found yet...")
                time.sleep(0.5)

            # ========================================
            # STEP 3: Verify with OpenRouter Gemini
            # ========================================
            print("  Verifying with OpenRouter Gemini model...")
            verification_result = verify_tool_with_screenshots(
                before_screenshot=before_screenshot,
                after_screenshot=after_screenshot,
                tool_name=test_name,
                verification_prompt=verify_prompt
            )

            if not dialog_window:
                message = f"{test_name} did not appear within timeout — menu navigation failed"
                self.add_test_result(result_name, TEST_FAILED, message)
                self.add_error(f"{test_name} window not found after menu click")
                print(f"  X {test_name} FAILED - dialog did not open")
                return

            # Close the dialog
            print(f"  Closing {test_name}...")
            try:
                pyautogui.press('escape')
            except Exception:
                pass
            time.sleep(0.7)

            if not self.process_manager.is_running():
                message = f"LIMA crashed after closing {test_name}"
                self.add_test_result(result_name, TEST_FAILED, message)
                self.add_error(f"LIMA crashed after {test_name}")
                return

            # Process verification result
            if verification_result and verification_result.get("answer") == "YES":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"{test_name} opened and verified: {explanation}"
                self.add_test_result(result_name, TEST_PASSED, message)
                print(f"  OK {test_name.upper()} test PASSED")
                print(f"    Note: {explanation}")
            elif verification_result and verification_result.get("answer") == "NO":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"{test_name} verification failed: {explanation}"
                self.add_test_result(result_name, TEST_FAILED, message)
                print(f"  X {test_name.upper()} test FAILED")
                print(f"    Note: {explanation}")
            else:
                message = f"{test_name} — API verification unavailable — cannot confirm result"
                self.add_test_result(result_name, TEST_FAILED, message)
                print(f"  X {test_name.upper()} test FAILED (API verification unavailable)")

        except Exception as error:
            message = f"Exception during {test_name}: {str(error)}"
            self.add_test_result(result_name, TEST_FAILED, message)
            self.add_error(f"{test_name} exception: {str(error)}")

    def _test_settings_dialog(self):
        """Test: Open Settings dialog from File menu and verify it displays correctly."""
        self._test_dialog(
            test_name="Settings Dialog",
            result_name="Settings Dialog Test",
            menu_nav_keys=['enter'],  # Settings is the first item in the File menu
            dialog_title_keywords=["LIMA Settings", "Settings"],
            verify_prompt=(
                "Does the AFTER screenshot show a Settings dialog window appearing on screen? "
                "Look for a dialog box with settings options (like preferences, options, configuration) "
                "that was not present in the BEFORE screenshot."
            )
        )

    def _test_subscription_dialog(self):
        """Test: Open Subscription Information dialog from File menu and verify it displays correctly."""
        self._test_dialog(
            test_name="Subscription Dialog",
            result_name="Subscription Dialog Test",
            menu_nav_keys=['down', 'enter'],  # Down past Settings, then enter
            dialog_title_keywords=["Subscription Information", "Subscription"],
            verify_prompt=(
                "Does the AFTER screenshot show a Subscription Information dialog window appearing on screen? "
                "Look for a dialog box with subscription-related information that was not present in the BEFORE screenshot."
            )
        )

    def _test_about_dialog(self):
        """Test: Open About dialog from File menu and verify it displays correctly."""
        self._test_dialog(
            test_name="About Dialog",
            result_name="About Dialog Test",
            menu_nav_keys=['down', 'down', 'enter'],  # Down past Settings, down past Subscription, then enter
            dialog_title_keywords=["About LIMA", "About"],
            verify_prompt=(
                "Does the AFTER screenshot show an About LIMA dialog window appearing on screen? "
                "Look for a dialog box with About information (version, copyright, etc.) "
                "that was not present in the BEFORE screenshot."
            )
        )
    
    def _test_about_dialog_links(self):
        """
        Test: Open About dialog and click the website and documentation links with mouse.
        """
        try:
            # Find LIMA window
            lima_window = None
            all_windows = gw.getAllWindows()
            for window in all_windows:
                if window.title == "LIMA Screen Reader":
                    lima_window = window
                    break
            
            if not lima_window:
                message = "Could not find LIMA Screen Reader window"
                self.add_test_result("About Dialog Links Test", TEST_FAILED, message)
                return
            
            # Clear menus and activate
            try:
                pyautogui.press('escape')
                time.sleep(0.3)
                lima_window.activate()
                time.sleep(1.0)
                pyautogui.click(lima_window.left + 200, lima_window.top + 200)
                time.sleep(0.5)
            except Exception:
                pass
            
            # Open About dialog
            print("  Opening About dialog to test links...")
            try:
                pyautogui.press('alt')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(1.5)
                pyautogui.press('down')
                time.sleep(0.5)
                pyautogui.press('down')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(2.0)
            except Exception:
                pass
            
            # Find About dialog window
            about_window = None
            for attempt in range(5):
                all_windows = gw.getAllWindows()
                for window in all_windows:
                    if "About LIMA" in window.title:
                        about_window = window
                        break
                if about_window:
                    break
                time.sleep(0.5)
            
            if not about_window:
                message = "Could not open About dialog for links test"
                self.add_test_result("About Dialog Links Test", TEST_FAILED, message)
                return
            
            print(f"  OK About dialog opened at position: ({about_window.left}, {about_window.top})")
            print(f"    Dialog size: {about_window.width} x {about_window.height}")
            
            # ========================================
            # STEP 1: Take BEFORE screenshot (About dialog open)
            # ========================================
            print("  Taking BEFORE screenshot (About dialog open)...")
            before_screenshot = take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")
            
            browser_opened_count = 0

            # ========================================
            # Test 1: Activate "Roscommon Systems" website link via Tab + Enter
            # ========================================
            print(f"  Activating Website link via Tab + Enter...")
            try:
                about_window.activate()
                time.sleep(0.5)
                pyautogui.press('tab')   # Move focus to first interactive control (website link)
                time.sleep(0.3)
                pyautogui.press('enter')  # Activate the link
                time.sleep(3.0)
                
                # ========================================
                # STEP 2: Take AFTER 1 screenshot (Website 1 open)
                # ========================================
                print("  Taking AFTER 1 screenshot (Website 1 opened)...")
                after_screenshot_website = take_screenshot()
                if not after_screenshot_website:
                    print("  ! Could not capture after screenshot for website 1")
                else:
                    print("  OK AFTER 1 screenshot captured")
                
                # Verify with Gemini: BEFORE vs AFTER 1
                if before_screenshot and after_screenshot_website:
                    print("      Verifying website link with Gemini...")
                    website_verification_prompt = """Did a web browser window open after clicking the website link?
                    Compare the BEFORE screenshot (About dialog) to the AFTER screenshot.
                    Look for a browser window appearing in the AFTER screenshot that was not in the BEFORE screenshot."""
                    
                    website_result = verify_tool_with_screenshots(
                        before_screenshot=before_screenshot,
                        after_screenshot=after_screenshot_website,
                        tool_name="Website Link Click",
                        verification_prompt=website_verification_prompt
                    )
                    
                    if website_result and website_result.get("answer") == "YES":
                        browser_opened_count += 1
                        print(f"      OK Website link verification PASSED")
                        print(f"        Note: {website_result.get('explanation', '')}")
                    elif website_result and website_result.get("answer") == "NO":
                        print(f"      X Website link verification FAILED")
                        print(f"        Note: {website_result.get('explanation', '')}")
                    else:
                        print(f"      ! Website link verification unavailable")
                
                # Close the browser window
                try:
                    for window in gw.getAllWindows():
                        if any(browser in window.title.lower() for browser in ['chrome', 'firefox', 'edge', 'safari']):
                            try:
                                window.activate()
                                time.sleep(0.5)
                                pyautogui.hotkey('ctrl', 'w')
                                time.sleep(1.0)
                                break
                            except Exception:
                                pass
                except Exception:
                    pass
                
            except Exception as e:
                print(f"  Error clicking Website link: {str(e)}")
            
            # ========================================
            # Test 2: Activate "LIMA Documentation" link via Tab + Enter
            # ========================================
            print(f"  Activating Documentation link via Tab + Enter...")
            try:
                about_window.activate()
                time.sleep(0.5)
                pyautogui.press('tab')   # Move focus to next interactive control (docs link)
                time.sleep(0.3)
                pyautogui.press('enter')  # Activate the link
                time.sleep(3.0)
                
                # ========================================
                # STEP 3: Take AFTER 2 screenshot (Website 2 open)
                # ========================================
                print("  Taking AFTER 2 screenshot (Website 2 opened)...")
                after_screenshot_docs = take_screenshot()
                if not after_screenshot_docs:
                    print("  ! Could not capture after screenshot for website 2")
                else:
                    print("  OK AFTER 2 screenshot captured")
                
                # Verify with Gemini: BEFORE vs AFTER 2
                if before_screenshot and after_screenshot_docs:
                    print("      Verifying documentation link with Gemini...")
                    docs_verification_prompt = """Did a web browser window open after clicking the documentation link?
                    Compare the BEFORE screenshot (About dialog) to the AFTER screenshot.
                    Look for a browser window appearing in the AFTER screenshot that was not in the BEFORE screenshot."""
                    
                    docs_result = verify_tool_with_screenshots(
                        before_screenshot=before_screenshot,
                        after_screenshot=after_screenshot_docs,
                        tool_name="Documentation Link Click",
                        verification_prompt=docs_verification_prompt
                    )
                    
                    if docs_result and docs_result.get("answer") == "YES":
                        browser_opened_count += 1
                        print(f"      OK Documentation link verification PASSED")
                        print(f"        Note: {docs_result.get('explanation', '')}")
                    elif docs_result and docs_result.get("answer") == "NO":
                        print(f"      X Documentation link verification FAILED")
                        print(f"        Note: {docs_result.get('explanation', '')}")
                    else:
                        print(f"      ! Documentation link verification unavailable")
                
                # Close the browser window
                try:
                    for window in gw.getAllWindows():
                        if any(browser in window.title.lower() for browser in ['chrome', 'firefox', 'edge', 'safari']):
                            try:
                                window.activate()
                                time.sleep(0.5)
                                pyautogui.hotkey('ctrl', 'w')
                                time.sleep(1.0)
                                break
                            except Exception:
                                pass
                except Exception:
                    pass
                
            except Exception as e:
                print(f"  Error clicking Documentation link: {str(e)}")
            
            # Close About dialog
            try:
                about_window.activate()
                time.sleep(0.3)
                pyautogui.press('escape')
                time.sleep(0.7)
            except Exception:
                pass
            
            # Verify LIMA is still running
            if not self.process_manager.is_running():
                message = "LIMA crashed during About dialog links test"
                self.add_test_result("About Dialog Links Test", TEST_FAILED, message)
                return
            
            if browser_opened_count >= 1:
                message = f"About dialog links working ({browser_opened_count}/2 links opened browser successfully)"
                self.add_test_result("About Dialog Links Test", TEST_PASSED, message)
                print(f"\n  OK ABOUT DIALOG LINKS test PASSED ({browser_opened_count}/2 links worked)")
            else:
                message = "About dialog links did not open browser - link positions may need adjustment"
                self.add_test_result("About Dialog Links Test", TEST_FAILED, message)
                print("\n  X ABOUT DIALOG LINKS test FAILED - no browser windows opened")
            
        except Exception as error:
            message = f"Exception during About links test: {str(error)}"
            self.add_test_result("About Dialog Links Test", TEST_FAILED, message)
    
    def _test_postrun_crash_logs(self):
        """Test: Check for crash logs created during test run."""
        # Give filesystem time to flush
        time.sleep(1)
        
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

    # ========================================
    # Delegate Methods to Reporter
    # ========================================
    
    def save_report(self, output_path="test_results.json"):
        """Save test results to JSON file."""
        self.reporter.save_report(output_path)
    
    def print_summary(self):
        """Print a summary of test results to console."""
        self.reporter.print_summary()
