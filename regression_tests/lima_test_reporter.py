"""
LIMA Test Reporter Module
Handles test result reporting, verification helpers, and output generation.
"""

import os
import json
import time
import ctypes
import pyautogui
import pygetwindow as gw
import psutil
from datetime import datetime

from lima_test_utils import TEST_PASSED, TEST_FAILED


class LimaTestReporter:
    """Handles test result reporting and verification for LIMA regression tests."""
    
    def __init__(self):
        """Initialize the reporter with default test results structure."""
        self.test_results = {
            "test_suite": "LIMA Regression Tests",
            "timestamp": datetime.now().isoformat(),
            "overall_status": TEST_PASSED,
            "execution_time_seconds": 0,
            "tests": [],
            "crash_logs": {
                "detected": False,
                "location": None,
                "contents": ""
            },
            "errors": [],
            "stdout_output": "",
            "stderr_output": ""
        }
        self.start_time = time.time()
    
    def add_test_result(self, test_name, status, message):
        """
        Add a test result to the report.
        
        Args:
            test_name (str): Name of the test
            status (str): TEST_PASSED or TEST_FAILED
            message (str): Result message
        """
        test_result = {
            "name": test_name,
            "status": status,
            "message": message
        }
        self.test_results["tests"].append(test_result)
        
        # Update overall status if any test failed
        if status == TEST_FAILED:
            self.test_results["overall_status"] = TEST_FAILED
    
    def add_error(self, error_message):
        """
        Add an error message to the test results.
        
        Args:
            error_message (str): Error message to add
        """
        self.test_results["errors"].append(error_message)
    
    def set_crash_log_info(self, detected, location=None, contents=""):
        """
        Set crash log information in the test results.
        
        Args:
            detected (bool): Whether crash logs were detected
            location (str): Path to crash log file
            contents (str): Contents of the crash log
        """
        self.test_results["crash_logs"]["detected"] = detected
        self.test_results["crash_logs"]["location"] = location
        self.test_results["crash_logs"]["contents"] = contents
    
    def finalize_results(self):
        """Finalize test results and calculate execution time."""
        self.test_results["execution_time_seconds"] = round(time.time() - self.start_time, 3)
    
    def save_report(self, output_path="test_results.json"):
        """
        Save test results to JSON file.
        
        Args:
            output_path (str): Path where to save the JSON report
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as report_file:
                json.dump(self.test_results, report_file, indent=2)
            print(f"\nReport saved to: {output_path}")
        except Exception as error:
            print(f"Error saving report: {str(error)}")
    
    def print_summary(self):
        """Print a summary of test results to console."""
        # Calculate the number of tests that passed and failed
        tests_passed_count = sum(1 for test in self.test_results["tests"] if test["status"] == TEST_PASSED)
        tests_failed_count = sum(1 for test in self.test_results["tests"] if test["status"] == TEST_FAILED)
        total_tests_count = len(self.test_results['tests'])
        
        print("\n" + "="*60)
        print("LIMA REGRESSION TEST RESULTS")
        print("="*60)
        print(f"Overall Status: {self.test_results['overall_status']}")
        print(f"Execution Time: {self.test_results['execution_time_seconds']} seconds")
        print(f"\nTests Run: {total_tests_count}")
        print(f"Tests Passed: {tests_passed_count}")
        print(f"Tests Failed: {tests_failed_count}")
        
        for test in self.test_results["tests"]:
            status_symbol = "OK" if test["status"] == TEST_PASSED else "X"
            print(f"  [{status_symbol}] {test['name']}: {test['status']}")
            if test["status"] == TEST_FAILED:
                print(f"      Message: {test['message']}")
        
        if self.test_results["crash_logs"]["detected"]:
            print("\nWARNING: CRASH LOGS DETECTED")
            print(f"Location: {self.test_results['crash_logs']['location']}")
        
        if self.test_results["errors"]:
            print(f"\nErrors ({len(self.test_results['errors'])})")
            for error in self.test_results["errors"]:
                print(f"  - {error}")
        
        print("="*60 + "\n")
    
    def get_test_results(self):
        """
        Get the test results dictionary.
        
        Returns:
            dict: Test results dictionary
        """
        return self.test_results
    
    def set_test_results(self, test_results):
        """
        Set the test results dictionary.
        
        Args:
            test_results (dict): Test results dictionary to set
        """
        self.test_results = test_results
    
    def get_overall_status(self):
        """
        Get the overall test status.
        
        Returns:
            str: TEST_PASSED or TEST_FAILED
        """
        return self.test_results["overall_status"]
    
    # ========================================
    # Verification Helper Methods
    # ========================================
    
    @staticmethod
    def verify_mouse_moved(mouse_before):
        """
        Verify mouse moved from its original position.
        
        Args:
            mouse_before: Tuple of (x, y) mouse position before action
            
        Returns:
            tuple: (bool, str) - (True if moved, message)
        """
        for _ in range(5):
            mouse_after = pyautogui.position()
            dx = abs(mouse_after.x - mouse_before.x)
            dy = abs(mouse_after.y - mouse_before.y)

            if dx > 30 or dy > 30:
                return True, f"Mouse moved from {mouse_before} to {mouse_after}"

            time.sleep(1)

        return False, f"Mouse did not move (still at {pyautogui.position()})"

    @staticmethod
    def verify_mouse_at_coords(target_coords, tolerance=10):
        """
        Verify mouse is at expected coordinates (with tolerance).
        
        Args:
            target_coords: Tuple of (x, y) target coordinates
            tolerance: Acceptable distance from target in pixels
            
        Returns:
            tuple: (bool, str) - (True if at coords, message)
        """
        target_x, target_y = target_coords

        for _ in range(5):
            mouse_x, mouse_y = pyautogui.position()
            dx = abs(mouse_x - target_x)
            dy = abs(mouse_y - target_y)

            if dx <= tolerance and dy <= tolerance:
                return True, (
                    f"Mouse at ({mouse_x}, {mouse_y}) "
                    f"within {tolerance}px of {target_coords}"
                )

            time.sleep(1)

        mouse_x, mouse_y = pyautogui.position()
        return False, (
            f"Mouse at ({mouse_x}, {mouse_y}) "
            f"NOT near {target_coords}"
        )

    @staticmethod
    def verify_start_menu_opened():
        """
        Verify the Start menu opened.

        Returns:
            tuple: (bool, str) - (True if opened, message)
        """
        time.sleep(1.0)

        user32 = ctypes.windll.user32

        # Primary: check if the foreground window belongs to StartMenuExperienceHost.exe
        try:
            hwnd = user32.GetForegroundWindow()
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc = psutil.Process(pid.value)
            if proc.name().lower() == "startmenuexperiencehost.exe":
                return True, "Start menu detected (StartMenuExperienceHost in foreground)"
        except Exception:
            pass

        # Fallback: enumerate all visible windows and check if any belongs to
        # StartMenuExperienceHost.exe. This catches the case where the menu opened
        # but lost focus before we checked (e.g. another window grabbed it).
        try:
            found = []

            def _enum_callback(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    try:
                        if psutil.Process(pid.value).name().lower() == "startmenuexperiencehost.exe":
                            found.append(hwnd)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
            user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
            if found:
                return True, "Start menu detected (StartMenuExperienceHost has visible window)"
        except Exception:
            pass

        return False, "Start menu NOT detected"

    @staticmethod
    def verify_desktop_shown():
        """
        Verify the desktop is shown (all windows minimized).
        
        Returns:
            tuple: (bool, str) - (True if desktop shown, message)
        """
        time.sleep(1.0)
        
        try:
            # Check if all application windows are minimized
            all_windows = gw.getAllWindows()
            visible_app_windows = 0
            
            for window in all_windows:
                # Skip system windows
                if window.title in ["", "Program Manager", "Windows Shell Experience Host"]:
                    continue
                # Check if window is visible (not minimized)
                if window.visible and not window.isMinimized:
                    visible_app_windows += 1
            
            if visible_app_windows <= 1:  # Only taskbar/system tray visible
                return True, f"Desktop shown ({visible_app_windows} visible windows)"
            else:
                return False, f"Desktop NOT shown - {visible_app_windows} windows still visible"
        except Exception as e:
            return False, f"Could not verify desktop: {str(e)}"
