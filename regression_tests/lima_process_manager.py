"""
LIMA Process Manager
Handles LIMA application process lifecycle: health checks, focus, and shutdown.
"""

import os
import time
import pyautogui
import pygetwindow as gw
import psutil
from lima_test_utils import SLEEP_A, SLEEP_D


class LimaProcessManager:
    """Manages the LIMA application process lifecycle."""

    def __init__(self):
        self.process = None
        self.pid = None
        self.install_path = None
        self.exe_full_path = None
        self.crash_log_baseline = None

    def is_running(self):
        """Check if LIMA process is still running."""
        if self.process:
            try:
                return self.process.is_running()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        return False

    def close(self):
        """
        Close LIMA application gracefully.

        Returns:
            str or None: Error message if close failed, None on success.
        """
        error_message = None
        if self.process and self.is_running():
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    self.process.kill()
            except Exception as error:
                error_message = f"Note: Issue closing LIMA: {str(error)}"

        self.process = None
        self.pid = None
        return error_message

    def launch(self, exe_path, install_path):
        """
        Launch LIMA and wait for the process to appear.
        Does not record a test result — use this for per-test relaunches.

        Returns:
            bool: True on success, False if process not found after launch.
        """
        from lima_test_utils import find_process_by_name
        original_dir = os.getcwd()
        os.chdir(install_path)
        try:
            os.startfile(exe_path)
            time.sleep(SLEEP_D)
            self.process = find_process_by_name(exe_path)
            if self.process:
                self.pid = self.process.pid
                return True
            return False
        finally:
            os.chdir(original_dir)

    def refocus(self, timeout=5):
        """
        Refocus on LIMA window after a tool action that may have changed focus.

        Returns:
            bool: True if LIMA was found and focused, False otherwise.
        """
        print("  Refocusing on LIMA...")

        for key in ['win', 'ctrl', 'alt', 'shift', 'winleft', 'winright']:
            pyautogui.keyUp(key)
        time.sleep(SLEEP_A)

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                all_windows = gw.getAllWindows()
                for window in all_windows:
                    if "LIMA" in window.title:
                        try:
                            window.restore()
                            time.sleep(SLEEP_A)
                            window.activate()
                            time.sleep(SLEEP_A)
                            try:
                                window.maximize()
                                time.sleep(SLEEP_A)
                            except Exception:
                                pass
                            # Use Windows UI Automation to click the actual text input (Edit control)
                            try:
                                from pywinauto import Desktop
                                desktop = Desktop(backend="uia")
                                lima_app = desktop.window(title_re=".*LIMA Screen Reader.*")
                                edit = lima_app.child_window(control_type="Edit")
                                edit.set_focus()
                                edit.click_input()
                                time.sleep(SLEEP_A)
                            except Exception:
                                # Fallback: click near window bottom if UIA fails
                                click_x = window.left + (window.width // 2)
                                click_y = window.top + int(window.height * 0.88)
                                pyautogui.click(click_x, click_y)
                                time.sleep(SLEEP_A)
                            print(f"  OK LIMA refocused: '{window.title}'")
                            return True
                        except Exception:
                            print(f"  ! Window handle invalid, retrying...")
                            time.sleep(SLEEP_A)
                            break
            except Exception as e:
                print(f"  ! Error getting windows: {str(e)}")
            time.sleep(SLEEP_A)

        print("  ! Could not find LIMA window after timeout")
        return False
