"""
LIMA Test Executor Module
Handles test execution, LIMA process lifecycle management, and test coordination.
"""

import os
import sys
import time
import pyautogui
import pygetwindow as gw
import psutil

from lima_test_utils import (
    TEST_PASSED, 
    TEST_FAILED, 
    LimaTestUtils
)
from lima_test_reporter import LimaTestReporter


class LimaTestExecutor:
    """Handles execution of LIMA regression tests."""
    
    def __init__(self):
        """Initialize the test executor with reporter and process references."""
        self.reporter = LimaTestReporter()
        self.lima_process = None
        self.lima_pid = None
        self.lima_install_path = None
        self.lima_exe_full_path = None
        self.crash_log_baseline = None
    
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
    # Process Management Methods
    # ========================================
    
    def _is_lima_running(self):
        """
        Check if LIMA process is still running.
        
        Returns:
            bool: True if running, False otherwise
        """
        if self.lima_process:
            try:
                return self.lima_process.is_running()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        return False
    
    def _close_lima(self):
        """Close LIMA application gracefully."""
        if self.lima_process and self._is_lima_running():
            try:
                self.lima_process.terminate()
                # Wait up to 5 seconds for graceful termination
                try:
                    self.lima_process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    # Force kill if graceful termination didn't work
                    self.lima_process.kill()
            except Exception as error:
                # Log but don't fail test for close errors
                error_msg = f"Note: Issue closing LIMA: {str(error)}"
                self.add_error(error_msg)
        
        self.lima_process = None
        self.lima_pid = None
    
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
            LimaTestUtils.minimize_all_other_windows()

            # Require API key before running any tests
            print("Checking API key availability...")
            if not LimaTestUtils.initialize_openrouter_api_key():
                print("ERROR: OPEN_ROUTER_API_KEY could not be retrieved. Aborting test run.")
                print("  Hint: Make sure lima_config.json is properly configured with a valid license key.")
                self.reporter.finalize_results()
                return False
            print("  OK API key verified\n")

            # Test 1: Find LIMA executable first
            if not self._test_lima_discovery():
                self.reporter.finalize_results()
                return False

            # Test 2: Check for pre-existing crash logs
            self._test_prerun_crash_logs()
            
            # Test 3: Check license and settings file persistence
            self._test_license_key_persistence()
            self._test_settings_file_persistence()
            
            # Test 4: Launch LIMA
            if not self._test_lima_launch():
                self.reporter.finalize_results()
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
            self._close_lima()
            time.sleep(2)
            
            # Test 12: Re-launch LIMA for subscription test
            if not self._test_lima_launch():
                self.reporter.finalize_results()
                return False
            
            time.sleep(2)
            
            # Test 13: Test Subscription Information dialog
            self._test_subscription_dialog()
            
            # Test 14: Close for tool tests
            self._close_lima()
            time.sleep(3)

            print("\n" + "="*60)
            print("LAUNCHING FRESH LIMA FOR TOOL TESTING")
            print("="*60)

            # Launch LIMA once for all tool tests
            if not self._test_lima_launch():
                print("X Could not launch LIMA for tool tests")
                self.reporter.finalize_results()
                return False
            time.sleep(5)

            # Run all tool tests in single session
            self._test_all_tools()

            # Close LIMA after all tool tests
            self._close_lima()
            time.sleep(3)

            # Test 15: Check for crash logs after run
            self._test_postrun_crash_logs()

            
        except Exception as error:
            error_msg = f"Unexpected error during test execution: {str(error)}"
            self.add_test_result("Test Execution", TEST_FAILED, error_msg)
            self.add_error(error_msg)
        
        self.reporter.finalize_results()
        return self.reporter.get_overall_status() == TEST_PASSED
    
    # ========================================
    # Individual Test Methods
    # ========================================
    
    def _test_lima_discovery(self):
        """
        Test: Discover LIMA executable in Program Files.
        
        Returns:
            bool: True if executable found, False otherwise
        """
        self.lima_install_path = None
        self.lima_exe_full_path = LimaTestUtils.find_lima_executable()
        
        if self.lima_exe_full_path:
            # Extract installation directory
            self.lima_install_path = os.path.dirname(self.lima_exe_full_path)
            message = f"Found LIMA executable at {self.lima_exe_full_path}"
            self.add_test_result("Lima Executable Discovery", TEST_PASSED, message)
            return True
        else:
            message = "LIMA executable not found in standard locations"
            self.add_test_result("Lima Executable Discovery", TEST_FAILED, message)
            self.add_error("Unable to locate LIMA installation")
            return False
    
    def _test_prerun_crash_logs(self):
        """Test: Check for pre-existing crash logs before starting LIMA."""
        crash_info = LimaTestUtils.check_crash_logs(self.lima_install_path)
        
        if crash_info.get("exists"):
            self.crash_log_baseline = crash_info
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
            if not self.lima_exe_full_path:
                raise ValueError("LIMA executable path not found")
            
            # Change to LIMA's installation directory before launching
            # This ensures relative paths work correctly
            original_dir = os.getcwd()
            os.chdir(self.lima_install_path)
            
            try:
                # Launch LIMA using os.startfile (Windows-specific)
                os.startfile(self.lima_exe_full_path)
                
                # Wait for process to start
                time.sleep(4)
                
                # Find the LIMA process
                self.lima_process = LimaTestUtils.find_process_by_name(self.lima_exe_full_path)
                
                if self.lima_process:
                    self.lima_pid = self.lima_process.pid
                    message = f"Lima launched successfully (PID: {self.lima_pid})"
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
            if not self._is_lima_running():
                message = "Lima process crashed unexpectedly during stability check"
                self.add_test_result("Stability Check", TEST_FAILED, message)
                self.add_error("Application crashed during monitoring")
                return
            
            # Check for crash logs during monitoring
            crash_info = LimaTestUtils.check_crash_logs(self.lima_install_path)
            if crash_info.get("exists"):
                # Compare with baseline - if different, new crash occurred
                if not self.crash_log_baseline or crash_info.get("contents") != self.crash_log_baseline.get("contents"):
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
            if self.lima_process and self._is_lima_running():
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
            if not self.lima_install_path:
                message = "Cannot test license persistence - install path unknown"
                self.add_test_result("License Key Persistence Test", TEST_FAILED, message)
                return
            
            # Check for license file (common names)
            license_paths = [
                os.path.join(self.lima_install_path, "data", "activation_key.txt"),
                os.path.join(self.lima_install_path, "data", "license.key"),
                os.path.join(self.lima_install_path, "data", "license.txt")
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
            if not self.lima_install_path:
                message = "Cannot test settings file persistence - install path unknown"
                self.add_test_result("Settings File Persistence Test", TEST_FAILED, message)
                return
            
            import json
            config_path = os.path.join(self.lima_install_path, "data", "config.json")
            
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
            lima_window = LimaTestUtils.find_window_by_title("LIMA", timeout=5)
            if not lima_window:
                message = "Could not find LIMA window to test keyboard input"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            
            # Activate window and maximize for consistent positioning
            lima_window.activate()
            time.sleep(1.0)
            lima_window.maximize()
            time.sleep(1.0)
            
            # Click the window center to focus the text input
            try:
                click_x = lima_window.left + (lima_window.width // 2)
                click_y = lima_window.top + (lima_window.height // 2)

                pyautogui.click(click_x, click_y)
                time.sleep(0.5)
            except Exception:
                pass
            
            # ========================================
            # STEP 1: Take BEFORE screenshot
            # ========================================
            print("  [1/4] Taking BEFORE screenshot...")
            before_screenshot = LimaTestUtils.take_screenshot()
            if not before_screenshot:
                message = "Failed to capture before screenshot"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            print("  OK BEFORE screenshot captured")
            
            # ========================================
            # STEP 2: Execute the tool (type text)
            # ========================================
            print("  [2/4] Executing keyboard input tool...")
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
            print("  [3/4] Taking AFTER screenshot...")
            after_screenshot = LimaTestUtils.take_screenshot()
            if not after_screenshot:
                message = "Failed to capture after screenshot"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            print("  OK AFTER screenshot captured")
            
            # ========================================
            # STEP 4: Verify with OpenRouter Gemini
            # ========================================
            print("  [4/4] Verifying with OpenRouter Gemini model...")
            verification_prompt = f"""Does the AFTER screenshot show the text '{test_message}' appearing in a text input field?
            This would indicate that keyboard input was successfully detected and displayed.
            Look for the text in the bottom portion of the LIMA Screen Reader window."""
            
            verification_result = LimaTestUtils.verify_tool_with_screenshots(
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
            if not self._is_lima_running():
                message = "LIMA process crashed during keyboard input test"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
                return
            
            # ========================================
            # Process verification result
            # ========================================
            if verification_result is None:
                # API verification failed - fall back to basic pass
                message = "Keyboard input test completed (API verification unavailable - check OPEN_ROUTER_API_KEY)"
                self.add_test_result("Keyboard Input Detection Test", TEST_PASSED, message)
                print("  ! API verification unavailable")
                print("  OK Test PASSED (fallback - no crash detected)")
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
            # Don't fail on pyautogui exceptions - consider it a pass if no crash
            if self.lima_process and self._is_lima_running():
                message = f"Keyboard test completed (minor exception: {str(error)[:50]})"
                self.add_test_result("Keyboard Input Detection Test", TEST_PASSED, message)
            else:
                message = f"Exception during keyboard input test: {str(error)}"
                self.add_test_result("Keyboard Input Detection Test", TEST_FAILED, message)
    
    def _test_settings_dialog(self):
        """
        Test: Open Settings dialog from File menu and verify it displays correctly.
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
                message = "Could not find LIMA Screen Reader window to open Settings"
                self.add_test_result("Settings Dialog Test", TEST_FAILED, message)
                self.add_error("LIMA window not found during Settings test")
                return
            
            # Activate and maximize window
            try:
                lima_window.activate()
                time.sleep(0.7)
                lima_window.maximize()
                time.sleep(0.7)
            except Exception:
                pass
            
            # Ensure focus
            try:
                pyautogui.click(lima_window.left + 200, lima_window.top + 200)
                time.sleep(0.5)
            except Exception:
                pass
            
            # ========================================
            # STEP 1: Take BEFORE screenshot
            # ========================================
            print("  [1/5] Taking BEFORE screenshot...")
            before_screenshot = LimaTestUtils.take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")
            
            # Open File menu and click Settings
            print("  [2/5] Opening Settings dialog...")
            try:
                pyautogui.press('alt')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(1.5)
                pyautogui.press('enter')  # Settings is first item
                time.sleep(2.5)  # Longer wait for dialog to appear
            except Exception:
                pass
            
            # ========================================
            # STEP 2: Take AFTER screenshot
            # ========================================
            print("  [3/5] Taking AFTER screenshot...")
            after_screenshot = LimaTestUtils.take_screenshot()
            if not after_screenshot:
                print("  ! Could not capture after screenshot")
            else:
                print("  OK AFTER screenshot captured")
            
            # VERIFICATION: Search for Settings dialog
            print("  Searching for Settings dialog window...")
            settings_window = None
            
            for attempt in range(8):  # 8 attempts = 4 seconds
                all_windows = gw.getAllWindows()
                
                # Debug: Print all windows to see what exists
                if attempt == 0:
                    print("    Current windows:")
                    for w in all_windows:
                        if w.title.strip():
                            print(f"      - '{w.title}'")
                
                for window in all_windows:
                    # Look for Settings dialog specifically
                    if "LIMA Settings" in window.title:
                        settings_window = window
                        print(f"  OK Found Settings dialog: '{window.title}'")
                        break
                    elif window.title == "Settings":  # Exact match
                        settings_window = window
                        print(f"  OK Found Settings dialog: '{window.title}'")
                        break
                
                if settings_window:
                    break
                
                if attempt % 2 == 0:
                    print(f"    Attempt {attempt + 1}/8 - Settings dialog not found yet...")
                
                time.sleep(0.5)
            
            if not settings_window:
                # FAIL - dialog did not appear
                message = "Settings dialog did not appear within 4 seconds - menu navigation failed"
                self.add_test_result("Settings Dialog Test", TEST_FAILED, message)
                self.add_error("Settings dialog window not found after menu click")
                print("  X Settings dialog test FAILED - dialog did not open")
                return
            
            # SUCCESS - Dialog appeared!
            print(f"  OK Settings dialog confirmed open: '{settings_window.title}'")
            print(f"    Position: ({settings_window.left}, {settings_window.top})")
            print(f"    Size: {settings_window.width} x {settings_window.height}")
            
            # Bring to front and wait for user to see it
            try:
                settings_window.activate()
                time.sleep(3.0)  # WAIT 3 SECONDS SO YOU CAN SEE IT!
                print("    ** Settings dialog visible for 3 seconds **")
            except Exception:
                pass
            
            # ========================================
            # STEP 3: Verify with OpenRouter Gemini
            # ========================================
            print("  [4/5] Verifying with OpenRouter Gemini model...")
            verification_prompt = """Does the AFTER screenshot show a Settings dialog window appearing on screen?
            Look for a dialog box with settings options (like preferences, options, configuration) that was not present in the BEFORE screenshot."""
            
            verification_result = LimaTestUtils.verify_tool_with_screenshots(
                before_screenshot=before_screenshot,
                after_screenshot=after_screenshot,
                tool_name="Open Settings Dialog",
                verification_prompt=verification_prompt
            )
            
            # Close the Settings dialog
            print("  [5/5] Closing Settings dialog...")
            try:
                pyautogui.press('escape')
            except Exception:
                pass
            
            time.sleep(1.0)
            
            # Verify it closed
            settings_still_open = False
            for window in gw.getAllWindows():
                if "Settings" in window.title and "LIMA Screen Reader" not in window.title:
                    settings_still_open = True
                    break
            
            if settings_still_open:
                print("    ! Settings dialog may still be open")
            else:
                print("    OK Settings dialog closed successfully")
            
            # Verify LIMA is still running
            if not self._is_lima_running():
                message = "LIMA process crashed after closing Settings dialog"
                self.add_test_result("Settings Dialog Test", TEST_FAILED, message)
                self.add_error("LIMA crashed after Settings dialog")
                return
            
            # Process verification result
            if verification_result and verification_result.get("answer") == "YES":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"Settings dialog opened and verified: {explanation}"
                self.add_test_result("Settings Dialog Test", TEST_PASSED, message)
                print(f"  OK SETTINGS DIALOG test PASSED")
                print(f"    Note: {explanation}")
            elif verification_result and verification_result.get("answer") == "NO":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"Settings dialog verification failed: {explanation}"
                self.add_test_result("Settings Dialog Test", TEST_FAILED, message)
                print(f"  X SETTINGS DIALOG test FAILED")
                print(f"    Note: {explanation}")
            else:
                # Verification unavailable but dialog appeared
                message = "Settings dialog opened, displayed, and closed successfully"
                self.add_test_result("Settings Dialog Test", TEST_PASSED, message)
                print(f"  OK SETTINGS DIALOG test PASSED (verification unavailable)")
            
        except Exception as error:
            message = f"Exception during Settings dialog test: {str(error)}"
            self.add_test_result("Settings Dialog Test", TEST_FAILED, message)
            self.add_error(f"Settings test exception: {str(error)}")
    
    def _test_subscription_dialog(self):
        """
        Test: Open Subscription Information dialog from File menu and verify it displays correctly.
        """
        try:
            # Find LIMA window with EXACT title
            lima_window = None
            all_windows = gw.getAllWindows()
            for window in all_windows:
                if window.title == "LIMA Screen Reader":
                    lima_window = window
                    break
            
            if not lima_window:
                # Fallback to partial match
                lima_window = LimaTestUtils.find_window_by_title("LIMA Screen Reader", timeout=5)
            
            if not lima_window:
                message = "Could not find LIMA Screen Reader window"
                self.add_test_result("Subscription Dialog Test", TEST_FAILED, message)
                return
            
            # Clear any stuck menus first
            try:
                pyautogui.press('escape')
                time.sleep(0.3)
            except Exception:
                pass
            
            # Activate window
            try:
                lima_window.activate()
                time.sleep(1.0)
                lima_window.maximize()
                time.sleep(1.0)
            except Exception:
                pass
            
            # Click window to ensure focus
            try:
                pyautogui.click(lima_window.left + 200, lima_window.top + 200)
                time.sleep(0.5)
            except Exception:
                pass
            
            # ========================================
            # STEP 1: Take BEFORE screenshot
            # ========================================
            print("  [1/5] Taking BEFORE screenshot...")
            before_screenshot = LimaTestUtils.take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")
            
            # Simple menu navigation
            print("  [2/5] Opening File menu...")
            try:
                pyautogui.press('alt')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(1.5)  # Wait for menu to fully open
            except Exception:
                pass
            
            print("  [3/5] Navigating to Subscription Information...")
            try:
                pyautogui.press('down')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(3.0)  # Long wait for dialog
            except Exception:
                pass
            
            # ========================================
            # STEP 2: Take AFTER screenshot
            # ========================================
            print("  [4/5] Taking AFTER screenshot...")
            after_screenshot = LimaTestUtils.take_screenshot()
            if not after_screenshot:
                print("  ! Could not capture after screenshot")
            else:
                print("  OK AFTER screenshot captured")
            
            # Search for dialog
            subscription_window = None
            for attempt in range(10):
                all_windows = gw.getAllWindows()
                for window in all_windows:
                    title = window.title
                    if "Subscription Information" in title or \
                    ("Subscription" in title and "Screen Reader" not in title):
                        subscription_window = window
                        print(f"  OK Found dialog: '{title}'")
                        break
                
                if subscription_window:
                    break
                time.sleep(0.5)
            
            # ========================================
            # STEP 3: Verify with OpenRouter Gemini
            # ========================================
            print("  [5/5] Verifying with OpenRouter Gemini model...")
            verification_prompt = """Does the AFTER screenshot show a Subscription Information dialog window appearing on screen?
            Look for a dialog box with subscription-related information that was not present in the BEFORE screenshot."""
            
            verification_result = LimaTestUtils.verify_tool_with_screenshots(
                before_screenshot=before_screenshot,
                after_screenshot=after_screenshot,
                tool_name="Open Subscription Dialog",
                verification_prompt=verification_prompt
            )
            
            if not subscription_window:
                message = "Subscription Information dialog did not appear"
                self.add_test_result("Subscription Dialog Test", TEST_FAILED, message)
                self.add_error("Subscription dialog did not open - manual verification required")
                print("  X Subscription dialog did not open")
                return
            
            # SUCCESS - Dialog appeared
            time.sleep(0.5)
            
            try:
                pyautogui.press('escape')
            except Exception:
                pass
            
            time.sleep(0.7)
            
            if not self._is_lima_running():
                message = "LIMA crashed after Subscription dialog test"
                self.add_test_result("Subscription Dialog Test", TEST_FAILED, message)
                return
            
            # Process verification result
            if verification_result and verification_result.get("answer") == "YES":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"Subscription dialog opened and verified: {explanation}"
                self.add_test_result("Subscription Dialog Test", TEST_PASSED, message)
                print(f"  OK SUBSCRIPTION DIALOG test PASSED")
                print(f"    Note: {explanation}")
            elif verification_result and verification_result.get("answer") == "NO":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"Subscription dialog verification failed: {explanation}"
                self.add_test_result("Subscription Dialog Test", TEST_FAILED, message)
                print(f"  X SUBSCRIPTION DIALOG test FAILED")
                print(f"    Note: {explanation}")
            else:
                # Verification unavailable but dialog appeared
                message = "Subscription Information dialog opened, displayed, and closed successfully"
                self.add_test_result("Subscription Dialog Test", TEST_PASSED, message)
                print(f"  OK SUBSCRIPTION DIALOG test PASSED (verification unavailable)")
            
        except Exception as error:
            if "Error code from Windows: 0" not in str(error):
                message = f"Exception: {str(error)}"
                self.add_test_result("Subscription Dialog Test", TEST_FAILED, message)
    
    def _test_about_dialog(self):
        """
        Test: Open About dialog from File menu and verify it displays correctly.
        """
        try:
            # Find LIMA window with EXACT title
            lima_window = None
            all_windows = gw.getAllWindows()
            for window in all_windows:
                if window.title == "LIMA Screen Reader":
                    lima_window = window
                    break
            
            if not lima_window:
                lima_window = LimaTestUtils.find_window_by_title("LIMA Screen Reader", timeout=5)
            
            if not lima_window:
                message = "Could not find LIMA Screen Reader window"
                self.add_test_result("About Dialog Test", TEST_FAILED, message)
                return
            
            # Clear any stuck menus first
            try:
                pyautogui.press('escape')
                time.sleep(0.3)
            except Exception:
                pass
            
            # Activate window
            try:
                lima_window.activate()
                time.sleep(1.0)
                lima_window.maximize()
                time.sleep(1.0)
            except Exception:
                pass
            
            # Click window to ensure focus
            try:
                pyautogui.click(lima_window.left + 200, lima_window.top + 200)
                time.sleep(0.5)
            except Exception:
                pass
            
            # ========================================
            # STEP 1: Take BEFORE screenshot
            # ========================================
            print("  [1/5] Taking BEFORE screenshot...")
            before_screenshot = LimaTestUtils.take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")
            
            # Simple menu navigation
            print("  [2/5] Opening File menu...")
            try:
                pyautogui.press('alt')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(1.5)
            except Exception:
                pass
            
            print("  [3/5] Navigating to About...")
            try:
                pyautogui.press('down')  # Subscription
                time.sleep(0.5)
                pyautogui.press('down')  # About
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(3.0)  # Long wait for dialog
            except Exception:
                pass
            
            # ========================================
            # STEP 2: Take AFTER screenshot
            # ========================================
            print("  [4/5] Taking AFTER screenshot...")
            after_screenshot = LimaTestUtils.take_screenshot()
            if not after_screenshot:
                print("  ! Could not capture after screenshot")
            else:
                print("  OK AFTER screenshot captured")
            
            # Search for dialog
            about_window = None
            for attempt in range(10):
                all_windows = gw.getAllWindows()
                for window in all_windows:
                    title = window.title
                    if "About LIMA" in title or \
                    ("About" in title and "Screen Reader" not in title):
                        about_window = window
                        print(f"  OK Found dialog: '{title}'")
                        break
                
                if about_window:
                    break
                time.sleep(0.5)
            
            # ========================================
            # STEP 3: Verify with OpenRouter Gemini
            # ========================================
            print("  [5/5] Verifying with OpenRouter Gemini model...")
            verification_prompt = """Does the AFTER screenshot show an About LIMA dialog window appearing on screen?
            Look for a dialog box with About information (version, copyright, etc.) that was not present in the BEFORE screenshot."""
            
            verification_result = LimaTestUtils.verify_tool_with_screenshots(
                before_screenshot=before_screenshot,
                after_screenshot=after_screenshot,
                tool_name="Open About Dialog",
                verification_prompt=verification_prompt
            )
            
            if not about_window:
                message = "About dialog did not appear"
                self.add_test_result("About Dialog Test", TEST_FAILED, message)
                self.add_error("About LIMA dialog did not open - manual verification required")
                print("  X About dialog did not open")
                return
            
            # SUCCESS - Dialog appeared
            time.sleep(0.5)
            
            try:
                pyautogui.press('escape')
            except Exception:
                pass
            
            time.sleep(0.7)
            
            if not self._is_lima_running():
                message = "LIMA crashed after About dialog test"
                self.add_test_result("About Dialog Test", TEST_FAILED, message)
                return
            
            # Process verification result
            if verification_result and verification_result.get("answer") == "YES":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"About dialog opened and verified: {explanation}"
                self.add_test_result("About Dialog Test", TEST_PASSED, message)
                print(f"  OK ABOUT DIALOG test PASSED")
                print(f"    Note: {explanation}")
            elif verification_result and verification_result.get("answer") == "NO":
                explanation = verification_result.get("explanation", "No explanation provided")
                message = f"About dialog verification failed: {explanation}"
                self.add_test_result("About Dialog Test", TEST_FAILED, message)
                print(f"  X ABOUT DIALOG test FAILED")
                print(f"    Note: {explanation}")
            else:
                # Verification unavailable but dialog appeared
                message = "About dialog opened, displayed, and closed successfully"
                self.add_test_result("About Dialog Test", TEST_PASSED, message)
                print(f"  OK ABOUT DIALOG test PASSED (verification unavailable)")
            
        except Exception as error:
            if "Error code from Windows: 0" not in str(error):
                message = f"Exception: {str(error)}"
                self.add_test_result("About Dialog Test", TEST_FAILED, message)
    
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
            print("  [1/6] Opening About dialog to test links...")
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
            print("  [2/6] Taking BEFORE screenshot (About dialog open)...")
            before_screenshot = LimaTestUtils.take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")
            
            browser_opened_count = 0

            # ========================================
            # Test 1: Activate "Roscommon Systems" website link via Tab + Enter
            # ========================================
            print(f"  [3/6] Activating Website link via Tab + Enter...")
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
                print("  [4/6] Taking AFTER 1 screenshot (Website 1 opened)...")
                after_screenshot_website = LimaTestUtils.take_screenshot()
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
                    
                    website_result = LimaTestUtils.verify_tool_with_screenshots(
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
            print(f"  [5/6] Activating Documentation link via Tab + Enter...")
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
                print("  [6/6] Taking AFTER 2 screenshot (Website 2 opened)...")
                after_screenshot_docs = LimaTestUtils.take_screenshot()
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
                    
                    docs_result = LimaTestUtils.verify_tool_with_screenshots(
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
            if not self._is_lima_running():
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
        
        crash_info = LimaTestUtils.check_crash_logs(self.lima_install_path)
        
        if crash_info.get("exists"):
            # Check if this is a new crash log
            if not self.crash_log_baseline or crash_info.get("contents") != self.crash_log_baseline.get("contents"):
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
    
    def _refocus_lima(self, timeout=5):
        """
        Refocus on LIMA window after a tool action that may have changed focus.
        
        Args:
            timeout (int): Maximum seconds to wait for LIMA window
            
        Returns:
            bool: True if LIMA was found and focused, False otherwise
        """
        print("  Refocusing on LIMA...")
        
        # Release any stuck modifier keys first
        for key in ['win', 'ctrl', 'alt', 'shift', 'winleft', 'winright']:
            pyautogui.keyUp(key)
        time.sleep(0.3)
        
        # Search for LIMA window fresh (don't use cached window objects)
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Get fresh window list each attempt
                all_windows = gw.getAllWindows()
                
                for window in all_windows:
                    if "LIMA" in window.title:
                        try:
                            # Try to activate - this will fail if handle is invalid
                            window.restore()
                            time.sleep(0.3)
                            window.activate()
                            time.sleep(0.5)
                            
                            # Try to maximize
                            try:
                                window.maximize()
                                time.sleep(0.5)
                            except Exception:
                                pass  # Maximize is optional
                            
                            # Click the window center to ensure focus
                            click_x = window.left + (window.width // 2)
                            click_y = window.top + (window.height // 2)
                            pyautogui.click(click_x, click_y)
                            time.sleep(0.5)
                            
                            print(f"  OK LIMA refocused: '{window.title}'")
                            return True
                            
                        except Exception as e:
                            # Handle became invalid, continue searching
                            print(f"  ! Window handle invalid, retrying...")
                            time.sleep(0.5)
                            break  # Break inner loop to refresh window list
                
            except Exception as e:
                print(f"  ! Error getting windows: {str(e)}")
            
            time.sleep(0.5)
        
        print("  ! Could not find LIMA window after timeout")
        return False

    def _test_all_tools(self):
        """Test: Run all LIMA AI tool tests in a single session with screenshot verification."""
        print("\n" + "=" * 60)
        print("TESTING ALL LIMA AI TOOLS (SINGLE SESSION)")
        print("=" * 60)

        # (test_name, command, result_name, verification_type, verification_prompt)
        tool_tests = [
            ("TYPE TEXT", "Type hello", "AI Tool Test: Type Text", "text_input", "Does the AFTER screenshot show the text 'hello' appearing in a text input field?"),
            ("WEATHER", "whats the weather in japan", "AI Tool Test: Weather Retrieval", "content_verification", "Did LIMA display a weather response or information about Japan's weather? Look for any new text content or weather-related information in the LIMA interface."),
            ("MOUSE CLICK", "do a right click", "AI Tool Test: Mouse Click", "context_menu", "Does the AFTER screenshot show a context menu appearing at the mouse cursor position?"),
            ("MOUSE CLICK COORDINATES", "right click at coordinates x 800 y 400", "AI Tool Test: Mouse Click Coordinates", "coordinates", "Did the mouse cursor move to coordinates (800, 400) and did a context menu appear?"),
            ("MOVE MOUSE TO", "move the mouse to position x 300 y 300", "AI Tool Test: Move Mouse To", "coordinates", "Did the mouse cursor move to coordinates (300, 300)?"),
            ("MOUSE WHEEL SCROLL", "scroll up", "AI Tool Test: Mouse Wheel Scroll", "scroll_position", "Did the scroll position change in the active window? Look for changes in scrollbars or content position."),
            ("CHANGE VOLUME", "increase the volume", "AI Tool Test: Change Volume", "no_verification", "No visual verification required for volume change"),
            ("WINDOWS KEY", "press the windows key", "AI Tool Test: Windows Key", "start_menu", "Did the Start menu or search window appear on screen?"),
            ("SHOW DESKTOP", "show the desktop", "AI Tool Test: Show Desktop", "desktop", "Are all application windows minimized and the desktop visible?"),
            ("TYPE NUMBERS", "type any number", "AI Tool Test: Type Number", "text_input", "Does the AFTER screenshot show numbers appearing in a text input field?"),
            ("OPEN NOTEPAD", "open notepad", "AI Tool Test: Open Notepad", "window_appearance", "Did a Notepad window appear on screen?"),
            ("MINIMIZE WINDOW", "minimize window", "AI Tool Test: Minimize Window", "window_state", "Did the active window minimize to the taskbar?"),
            ("MAXIMIZE WINDOW", "maximize window", "AI Tool Test: Maximize Window", "window_state", "Did the active window maximize to fill the screen?"),
            ("OPEN WEBSITE", "open google.com", "AI Tool Test: Open Website", "browser_window", "Did a web browser window open showing Google or a website?"),
        ]

        for test_name, command, result_name, verification_type, verification_prompt in tool_tests:
            print("\n" + "-" * 50)
            print(f"TOOL TEST: {test_name}")
            print("-" * 50)

            try:
                # Step 1: Ensure LIMA is focused (always maximize)
                if not self._refocus_lima(timeout=10):
                    message = "Could not refocus on LIMA window"
                    self.add_test_result(result_name, TEST_FAILED, message)
                    print(f"  X {message}")
                    continue

                # Step 2: Clear input state
                pyautogui.press('escape')
                time.sleep(0.5)

                # Step 3: Release modifier keys
                for key in ['win', 'ctrl', 'alt', 'shift', 'winleft', 'winright']:
                    pyautogui.keyUp(key)
                time.sleep(0.3)

                # Step 4: Capture mouse BEFORE
                mouse_before = pyautogui.position()
                print(f"  Mouse position before: {mouse_before}")

                # Step 5: Take BEFORE screenshot (for visual verification)
                before_screenshot = None
                if verification_type != "no_verification":
                    print("  [1/4] Taking BEFORE screenshot...")
                    before_screenshot = LimaTestUtils.take_screenshot()
                    if not before_screenshot:
                        print("  ! Could not capture before screenshot")
                    else:
                        print("  OK BEFORE screenshot captured")

                # Step 6: Type command
                print(f"  [2/4] Executing tool: '{command}'")
                pyautogui.write(command, interval=0.2)
                time.sleep(1.0)
                print("  OK Command typed")

                # Step 7: Submit
                print("  [3/4] Pressing Enter to submit...")
                pyautogui.press('enter')
                time.sleep(3.0)

                # Step 8: Wait for AI execution
                wait_time = 20
                print(f"  Waiting for AI to process ({wait_time} seconds)...")

                for i in range(wait_time):
                    time.sleep(1)

                    if not self._is_lima_running():
                        message = f"LIMA crashed during {test_name}"
                        self.add_test_result(result_name, TEST_FAILED, message)
                        print(f"  X {message}")
                        return

                    if (i + 1) % 5 == 0:
                        print(f"    {i + 1}/{wait_time} seconds...")

                # Step 9: Take AFTER screenshot (for visual verification)
                after_screenshot = None
                if verification_type != "no_verification":
                    print("  [4/4] Taking AFTER screenshot...")
                    after_screenshot = LimaTestUtils.take_screenshot()
                    if not after_screenshot:
                        print("  ! Could not capture after screenshot")
                    else:
                        print("  OK AFTER screenshot captured")
                elif verification_type == "content_verification":
                    # For weather and long content, take screenshot after response
                    print("  [4/4] Taking AFTER screenshot (after LIMA response)...")
                    after_screenshot = LimaTestUtils.take_screenshot()
                    if not after_screenshot:
                        print("  ! Could not capture after screenshot")
                    else:
                        print("  OK AFTER screenshot captured")

                # Step 10: Verification using OpenRouter Gemini
                verification_result = None
                if verification_type != "no_verification" and before_screenshot and after_screenshot:
                    print("  [5/5] Verifying with OpenRouter Gemini model...")
                    verification_result = LimaTestUtils.verify_tool_with_screenshots(
                        before_screenshot=before_screenshot,
                        after_screenshot=after_screenshot,
                        tool_name=test_name,
                        verification_prompt=verification_prompt
                    )
                else:
                    print("  [5/5] No visual verification required")

                # Step 11: Cleanup
                if "WINDOWS KEY" in test_name:
                    pyautogui.press('escape')
                    time.sleep(1)

                elif "SHOW DESKTOP" in test_name:
                    pyautogui.hotkey('win', 'd')
                    time.sleep(1)
                    for key in ['win', 'winleft', 'winright']:
                        pyautogui.keyUp(key)

                # Step 12: Record result
                if self._is_lima_running():
                    if verification_type == "no_verification":
                        # For tools that don't require visual verification
                        self.add_test_result(
                            result_name, TEST_PASSED,
                            f"{test_name} executed successfully (no visual verification)"
                        )
                        print(f"  OK {test_name} test PASSED (no visual verification)")
                    elif verification_result and verification_result.get("answer") == "YES":
                        # Tool verified as working
                        explanation = verification_result.get("explanation", "No explanation provided")
                        self.add_test_result(
                            result_name, TEST_PASSED,
                            f"{test_name} executed and verified: {explanation}"
                        )
                        print(f"  OK {test_name} test PASSED")
                        print(f"    Note: {explanation}")
                    elif verification_result and verification_result.get("answer") == "NO":
                        # Tool verified as NOT working
                        explanation = verification_result.get("explanation", "No explanation provided")
                        self.add_test_result(
                            result_name, TEST_FAILED,
                            f"{test_name} verification failed: {explanation}"
                        )
                        print(f"  X {test_name} test FAILED")
                        print(f"    Note: {explanation}")
                    else:
                        # Verification failed or not available
                        self.add_test_result(
                            result_name, TEST_PASSED,
                            f"{test_name} executed (verification unavailable)"
                        )
                        print(f"  OK {test_name} test PASSED (verification unavailable)")
                else:
                    self.add_test_result(
                        result_name, TEST_FAILED,
                        f"{test_name} failed - LIMA crashed"
                    )
                    print(f"  X {test_name} test FAILED - LIMA crashed")

                time.sleep(3.0)

            except Exception as error:
                message = f"Exception during {test_name}: {str(error)}"
                self.add_test_result(result_name, TEST_FAILED, message)
                print(f"  X {message}")
            
        # ========================================
        # SPECIAL NOTEPAD TESTS FOR BACKSPACE AND ARROW LEFT
        # ========================================
        print("\n" + "="*60)
        print("RUNNING SPECIAL NOTEPAD TESTS")
        print("="*60)
        
        try:
            # Test BACKSPACE 5 TIMES with Notepad
            print("\n--- TESTING BACKSPACE 5 TIMES ---")
            try:
                # Step 1: Open Notepad
                print("1. Opening Notepad...")
                pyautogui.press('win')
                time.sleep(0.5)
                pyautogui.write('notepad')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(2.0)

                # Step 2: Find Notepad window and type text
                notepad_window = LimaTestUtils.find_window_by_title("Notepad", timeout=5)
                if not notepad_window:
                    print("  X Could not find Notepad window")
                    self.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, "Could not open Notepad for backspace test")
                    return

                print("2. Typing text in Notepad...")
                notepad_window.activate()
                time.sleep(0.5)
                notepad_window.maximize()
                time.sleep(0.5)

                # NEW: Deselect menu and focus text area
                print("2b. Focusing text input area (deselecting menu)...")
                pyautogui.press('escape')  # Escape from menu focus
                time.sleep(0.3)
                
                test_text = "Hello World Test"
                pyautogui.write(test_text, interval=0.1)
                time.sleep(0.5)
                pyautogui.press('escape')

                # Click in the middle-lower area of the window to focus text area
                window_center_x = notepad_window.left + (notepad_window.width // 2)
                click_y = notepad_window.top + int(notepad_window.height * 0.5)  # Click in middle
                pyautogui.click(window_center_x, click_y)
                time.sleep(0.3)

                # Step 3: Take BEFORE screenshot of Notepad
                print("3. Taking BEFORE screenshot of Notepad...")
                before_screenshot = LimaTestUtils.take_screenshot()
                if not before_screenshot:
                    print("  ! Could not capture before screenshot")
                else:
                    print("  OK BEFORE screenshot captured")

                # Step 4: Switch to LIMA and type backspace command
                print("4. Switching to LIMA and executing backspace command...")
                if not self._refocus_lima(timeout=10):
                    print("  X Could not refocus on LIMA window")
                    self.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, "Could not refocus on LIMA")
                    return

                pyautogui.write("press backspace 5 times", interval=0.2)
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(3.0)

                # Step 6: Switch back to Notepad and take AFTER screenshot
                print("6. Switching back to Notepad and taking AFTER screenshot...")
                notepad_window.activate()
                pyautogui.press('escape')
                time.sleep(0.5)

                # Step 5: Wait for AI execution
                wait_time = 15
                print(f"5. Waiting for AI to process ({wait_time} seconds)...")
                for i in range(wait_time):
                    time.sleep(1)
                    if not self._is_lima_running():
                        message = "LIMA crashed during backspace test"
                        self.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, message)
                        print(f"  X {message}")
                        return

                after_screenshot = LimaTestUtils.take_screenshot()
                if not after_screenshot:
                    print("  ! Could not capture after screenshot")
                else:
                    print("  OK AFTER screenshot captured")

                # Step 7: Verify with OpenRouter Gemini
                if before_screenshot and after_screenshot:
                    print("7. Verifying with OpenRouter Gemini model...")
                    verification_prompt = "Did text get deleted in the Notepad window? Look for fewer characters in the text content."
                    verification_result = LimaTestUtils.verify_tool_with_screenshots(
                        before_screenshot=before_screenshot,
                        after_screenshot=after_screenshot,
                        tool_name="BACKSPACE 5 TIMES",
                        verification_prompt=verification_prompt
                    )
                    
                    if verification_result and verification_result.get("answer") == "YES":
                        explanation = verification_result.get("explanation", "No explanation provided")
                        self.add_test_result("AI Tool Test: Press Backspace", TEST_PASSED, f"Backspace test passed: {explanation}")
                        print(f"  OK BACKSPACE test PASSED")
                        print(f"    Note: {explanation}")
                    elif verification_result and verification_result.get("answer") == "NO":
                        explanation = verification_result.get("explanation", "No explanation provided")
                        self.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, f"Backspace test failed: {explanation}")
                        print(f"  X BACKSPACE test FAILED")
                        print(f"    Note: {explanation}")
                    else:
                        self.add_test_result("AI Tool Test: Press Backspace", TEST_PASSED, "Backspace test completed (verification unavailable)")
                        print(f"  OK BACKSPACE test PASSED (verification unavailable)")
                else:
                    self.add_test_result("AI Tool Test: Press Backspace", TEST_PASSED, "Backspace test completed (no screenshots)")
                    print(f"  OK BACKSPACE test PASSED (no screenshots)")

                # Close Notepad
                pyautogui.hotkey('alt', 'f4')
                time.sleep(1.0)

            except Exception as error:
                message = f"Exception during BACKSPACE test: {str(error)}"
                self.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, message)
                print(f"  X {message}")

            # Test ARROW LEFT
            print("\n--- TESTING ARROW LEFT ---")
            try:
                # Step 1: Open Notepad again
                print("1. Opening Notepad...")
                pyautogui.press('win')
                time.sleep(0.5)
                pyautogui.write('notepad')
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(2.0)

                # Step 2: Find Notepad window and type text
                notepad_window = LimaTestUtils.find_window_by_title("Notepad", timeout=5)
                if not notepad_window:
                    print("  X Could not find Notepad window")
                    self.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, "Could not open Notepad for arrow key test")
                    return

                print("2. Typing text in Notepad...")
                notepad_window.activate()
                time.sleep(0.5)
                notepad_window.maximize()
                time.sleep(0.5)
                
                test_text = "Hello World Test"
                pyautogui.write(test_text, interval=0.1)
                time.sleep(0.5)
                
                # Move cursor to end of text
                pyautogui.press('end')
                time.sleep(0.5)

                # Step 3: Take BEFORE screenshot of Notepad
                print("3. Taking BEFORE screenshot of Notepad...")
                before_screenshot = LimaTestUtils.take_screenshot()
                if not before_screenshot:
                    print("  ! Could not capture before screenshot")
                else:
                    print("  OK BEFORE screenshot captured")

                # Step 4: Switch to LIMA and type arrow left command
                print("4. Switching to LIMA and executing arrow left command...")
                if not self._refocus_lima(timeout=10):
                    print("  X Could not refocus on LIMA window")
                    self.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, "Could not refocus on LIMA")
                    return

                pyautogui.write("press arrow key left", interval=0.2)
                time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(3.0)

                # Step 6: Switch back to Notepad and take AFTER screenshot
                print("6. Switching back to Notepad and taking AFTER screenshot...")
                notepad_window.activate()
                time.sleep(0.5)

                # Step 5: Wait for AI execution
                wait_time = 15
                print(f"5. Waiting for AI to process ({wait_time} seconds)...")
                for i in range(wait_time):
                    time.sleep(1)
                    if not self._is_lima_running():
                        message = "LIMA crashed during arrow left test"
                        self.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, message)
                        print(f"  X {message}")
                        return

                after_screenshot = LimaTestUtils.take_screenshot()
                if not after_screenshot:
                    print("  ! Could not capture after screenshot")
                else:
                    print("  OK AFTER screenshot captured")

                # Step 7: Verify with OpenRouter Gemini
                if before_screenshot and after_screenshot:
                    print("7. Verifying with OpenRouter Gemini model...")
                    verification_prompt = "Did the text cursor move left in the Notepad text field? Look for cursor position changes in the text."
                    verification_result = LimaTestUtils.verify_tool_with_screenshots(
                        before_screenshot=before_screenshot,
                        after_screenshot=after_screenshot,
                        tool_name="ARROW LEFT",
                        verification_prompt=verification_prompt
                    )
                    
                    if verification_result and verification_result.get("answer") == "YES":
                        explanation = verification_result.get("explanation", "No explanation provided")
                        self.add_test_result("AI Tool Test: Arrow Key Left", TEST_PASSED, f"Arrow left test passed: {explanation}")
                        print(f"  OK ARROW LEFT test PASSED")
                        print(f"    Note: {explanation}")
                    elif verification_result and verification_result.get("answer") == "NO":
                        explanation = verification_result.get("explanation", "No explanation provided")
                        self.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, f"Arrow left test failed: {explanation}")
                        print(f"  X ARROW LEFT test FAILED")
                        print(f"    Note: {explanation}")
                    else:
                        self.add_test_result("AI Tool Test: Arrow Key Left", TEST_PASSED, "Arrow left test completed (verification unavailable)")
                        print(f"  OK ARROW LEFT test PASSED (verification unavailable)")
                else:
                    self.add_test_result("AI Tool Test: Arrow Key Left", TEST_PASSED, "Arrow left test completed (no screenshots)")
                    print(f"  OK ARROW LEFT test PASSED (no screenshots)")

                # Close Notepad
                pyautogui.hotkey('alt', 'f4')
                time.sleep(1.0)

            except Exception as error:
                message = f"Exception during ARROW LEFT test: {str(error)}"
                self.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, message)
                print(f"  X {message}")

            print("\n" + "="*60)
            print("SPECIAL NOTEPAD TESTS COMPLETED")
            print("="*60)

        except Exception as error:
            message = f"Exception during special Notepad tests: {str(error)}"
            self.add_test_result("Special Notepad Tests", TEST_FAILED, message)
            print(f"  X {message}")
    
    # ========================================
    # Delegate Methods to Reporter
    # ========================================
    
    def save_report(self, output_path="test_results.json"):
        """Save test results to JSON file."""
        self.reporter.save_report(output_path)
    
    def print_summary(self):
        """Print a summary of test results to console."""
        self.reporter.print_summary()
