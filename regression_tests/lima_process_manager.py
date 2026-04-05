"""
LIMA Process Manager
Handles LIMA application process lifecycle: health checks, focus, and shutdown.
"""

import time
import pyautogui
import pygetwindow as gw
import psutil


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

    def refocus(self, timeout=5):
        """
        Refocus on LIMA window after a tool action that may have changed focus.

        Returns:
            bool: True if LIMA was found and focused, False otherwise.
        """
        print("  Refocusing on LIMA...")

        for key in ['win', 'ctrl', 'alt', 'shift', 'winleft', 'winright']:
            pyautogui.keyUp(key)
        time.sleep(0.3)

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                all_windows = gw.getAllWindows()
                for window in all_windows:
                    if "LIMA" in window.title:
                        try:
                            window.restore()
                            time.sleep(0.3)
                            window.activate()
                            time.sleep(0.5)
                            try:
                                window.maximize()
                                time.sleep(0.5)
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
                                time.sleep(0.3)
                            except Exception:
                                # Fallback: click near window bottom if UIA fails
                                click_x = window.left + (window.width // 2)
                                click_y = window.top + int(window.height * 0.88)
                                pyautogui.click(click_x, click_y)
                                time.sleep(0.3)
                            print(f"  OK LIMA refocused: '{window.title}'")
                            return True
                        except Exception:
                            print(f"  ! Window handle invalid, retrying...")
                            time.sleep(0.5)
                            break
            except Exception as e:
                print(f"  ! Error getting windows: {str(e)}")
            time.sleep(0.5)

        print("  ! Could not find LIMA window after timeout")
        return False
