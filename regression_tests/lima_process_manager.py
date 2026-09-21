"""
LIMA Process Manager
Handles LIMA application process lifecycle: health checks, focus, and shutdown.
"""

import ctypes
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

    def _terminate_stale_instances(self, exe_path):
        """Kill any pre-existing LIMA processes for ``exe_path``.

        LIMA enforces a single instance (a QSharedMemory guard in lima.py), so a
        leftover process from an aborted run would make a freshly launched copy
        show "LIMA Is Already Running" and exit without a window. Terminating
        stale copies first keeps every launch genuinely fresh and isolated.
        """
        import psutil
        exe_name = os.path.basename(exe_path).lower()
        killed = []
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                name_matches = proc.info['name'] and proc.info['name'].lower() == exe_name
                exe_matches = proc.info['exe'] and proc.info['exe'].lower() == exe_path.lower()
                if name_matches or exe_matches:
                    proc.terminate()
                    killed.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if killed:
            print(f"  Terminated stale LIMA instance(s): {killed}")
            time.sleep(SLEEP_A)

    def launch(self, exe_path, install_path, window_timeout=30):
        """
        Launch LIMA and wait for both the process and a window to appear.

        Kills pre-existing same-name instances first (see
        _terminate_stale_instances), then starts the executable and polls until a
        LIMA window is on screen. A launch that finds only a process — but no
        window — is reported as failed instead of letting the caller later fail
        with a misleading "could not refocus".

        Returns:
            bool: True on success (process running with a window on screen).
        """
        from lima_test_utils import (find_process_by_name, find_windows_by_title,
                                     SLEEP_A, SLEEP_D)
        self._terminate_stale_instances(exe_path)
        original_dir = os.getcwd()
        os.chdir(install_path)
        try:
            os.startfile(exe_path)
            deadline = time.time() + SLEEP_D + window_timeout
            while time.time() < deadline:
                try:
                    process_alive = self.process is not None and self.process.is_running()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    process_alive = False
                if not process_alive:
                    self.process = find_process_by_name(exe_path)
                    if self.process:
                        self.pid = self.process.pid
                if self.process:
                    candidates = find_windows_by_title("LIMA", pid=self.pid)
                    if not candidates:
                        candidates = find_windows_by_title("LIMA")
                    if candidates:
                        print(f"  OK LIMA window on screen: {candidates[0][1]!r}")
                        return True
                time.sleep(SLEEP_A)
            print("  ! LIMA process and window did not appear in time")
            return False
        finally:
            os.chdir(original_dir)

    def refocus(self, timeout=10):
        """
        Refocus on LIMA window after a tool action that may have changed focus.

        Finds the LIMA window by title and, when known, by the process id the
        suite launched (so a stray message box from another instance cannot steal
        the match), restores it if minimized, brings it to the foreground via
        Win32, and clicks into the text input so typing lands in the chat box.

        Returns:
            bool: True if LIMA was found and focused, False otherwise.
        """
        from lima_test_utils import (find_windows_by_title, activate_window,
                                     get_window_rect, SLEEP_A)
        import uiautomation as uia

        print("  Refocusing on LIMA...")

        for key in ['win', 'ctrl', 'alt', 'shift', 'winleft', 'winright']:
            pyautogui.keyUp(key)
        time.sleep(SLEEP_A)

        user32 = ctypes.windll.user32
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Prefer windows owned by the launched process; fall back to any
            # window titled "LIMA" (e.g. when process tracking is unavailable).
            candidates = find_windows_by_title("LIMA", pid=self.pid)
            if not candidates:
                candidates = find_windows_by_title("LIMA")

            for hwnd, title in candidates:
                if not user32.IsWindow(hwnd):
                    continue
                activate_window(hwnd)
                try:
                    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                except Exception:
                    pass
                time.sleep(SLEEP_A)

                # Click into the text input so typing lands in the chat box.
                # Use UIA first; fall back to clicking near the window bottom.
                try:
                    self._focus_lima_text_input(uia)
                except Exception:
                    rect = get_window_rect(hwnd)
                    if rect:
                        click_x = (rect[0] + rect[2]) // 2
                        click_y = rect[1] + int((rect[3] - rect[1]) * 0.88)
                        pyautogui.click(click_x, click_y)
                        time.sleep(SLEEP_A)

                print(f"  OK LIMA refocused: {title!r}")
                return True

            # UIA-only sweep: a window UIA exposes but Win32 EnumWindows missed
            # can still be focused; some tool windows only settle into the UIA
            # tree after the Win32 EnumWindows snapshot.
            try:
                for ctrl in uia.GetRootControl().GetChildren():
                    if ctrl.Name and "LIMA" in ctrl.Name:
                        try:
                            ctrl.SetFocus()
                        except Exception:
                            pass
                        print(f"  OK LIMA refocused via UIA: {ctrl.Name!r}")
                        return True
            except Exception:
                pass

            time.sleep(SLEEP_A)

        print("  ! Could not find a LIMA window after timeout")
        return False

    def _focus_lima_text_input(self, uia):
        """Focus and click LIMA's text input via UI Automation."""
        lima_window = None
        for ctrl in uia.GetRootControl().GetChildren():
            if ctrl.Name and "LIMA" in ctrl.Name:
                lima_window = ctrl
                break
        if lima_window is None:
            raise Exception("LIMA window not found via UIA")
        edit = lima_window.EditControl()
        if not (edit and edit.Exists()):
            raise Exception("Edit control not found via UIA")
        edit.SetFocus()
        edit.Click()
        time.sleep(SLEEP_A)
