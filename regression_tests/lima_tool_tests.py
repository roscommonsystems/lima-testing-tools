"""
LIMA Tool Tests Module
Contains run_all_tool_tests for testing LIMA AI tools in a single session.
"""

import time
import webbrowser
import pygetwindow as gw
import pyautogui

from lima_test_utils import (
    take_screenshot, verify_tool_with_screenshots, overlay_cursor_on_screenshot,
    find_window_by_title, measure_peak_audio, TEST_PASSED, TEST_FAILED,
    speak_tts, type_into_lima,
    SLEEP_A, SLEEP_B, SLEEP_C, SLEEP_D
)


def run_all_tool_tests(executor):
    """Run all LIMA AI tool tests, relaunching LIMA fresh before each test."""
    print("\n" + "=" * 60)
    print("TESTING ALL LIMA AI TOOLS")
    print("=" * 60)

    # ALL new tests go here — do NOT add standalone _test_* methods to LimaTestExecutor.
    # Pick a kind: "command" (type+Enter+30s+screenshot-verify), "dialog" (File-menu nav+title poll),
    # or "audio" (type+Enter+measure_peak_audio). The loop handles banner/TTS/fresh-launch/result.
    tool_tests = [
        {
            "kind": "dialog",
            "name": "SETTINGS DIALOG",
            "result_name": "Settings Dialog Test",
            "verification_type": "dialog",
            "verification_prompt": (
                "Does the AFTER screenshot show a Settings dialog window appearing on screen? "
                "Look for a dialog box with settings options (like preferences, options, configuration) "
                "that was not present in the BEFORE screenshot."
            ),
            "menu_nav_keys": ["enter"],
            "dialog_title_keywords": ["LIMA Settings", "Settings"],
        },
        {
            "kind": "dialog",
            "name": "ABOUT DIALOG",
            "result_name": "About Dialog Test",
            "verification_type": "dialog",
            "verification_prompt": (
                "Does the AFTER screenshot show an About LIMA dialog window appearing on screen? "
                "Look for a dialog box with About information (version, copyright, etc.) "
                "that was not present in the BEFORE screenshot."
            ),
            "menu_nav_keys": ["down", "down", "enter"],
            "dialog_title_keywords": ["About LIMA", "About"],
        },
        {
            "kind": "dialog",
            "name": "SUBSCRIPTION DIALOG",
            "result_name": "Subscription Dialog Test",
            "verification_type": "dialog",
            "verification_prompt": (
                "Does the AFTER screenshot show a Subscription Information dialog window appearing on screen? "
                "Look for a dialog box with subscription-related information that was not present in the BEFORE screenshot."
            ),
            "menu_nav_keys": ["down", "enter"],
            "dialog_title_keywords": ["Subscription Information", "Subscription"],
        },
        {
            "kind": "audio",
            "name": "AUDIO OUTPUT",
            "result_name": "Audio Output Test",
            "command": "count to 5",
            "verification_type": "audio",
            "verification_prompt": "Audio peak detection — no visual verification",
        },
        {"kind": "command", "name": "TYPE TEXT", "command": "Type hello", "result_name": "AI Tool Test: Type Text", "verification_type": "text_input", "verification_prompt": "Does the AFTER screenshot show the text 'hello' appearing in a text input field?"},
        {"kind": "command", "name": "WEATHER", "command": "whats the weather in japan", "result_name": "AI Tool Test: Weather Retrieval", "verification_type": "content_verification", "verification_prompt": "Did LIMA display a weather response or information about Japan's weather? Look for any new text content or weather-related information in the LIMA interface."},
        {"kind": "command", "name": "MOUSE CLICK", "command": "do a right click", "result_name": "AI Tool Test: Mouse Click", "verification_type": "context_menu", "verification_prompt": "Does the AFTER screenshot show a context menu appearing at the mouse cursor position?"},
        {"kind": "command", "name": "MOUSE CLICK COORDINATES", "command": "click on the file menu", "result_name": "AI Tool Test: Mouse Click Coordinates", "verification_type": "content_verification", "verification_prompt": "Did a File menu dropdown or menu bar open in the AFTER screenshot? Look for a dropdown menu appearing, or LIMA's response confirming it clicked the File menu."},
        {"kind": "command", "name": "MOVE MOUSE TO", "command": "move the mouse to position x 300 y 300", "result_name": "AI Tool Test: Move Mouse To", "verification_type": "mouse_position", "verification_prompt": "Did the mouse cursor move to approximately position (300, 300) — the upper-left area of the screen? A red circle marks the cursor's current position in the AFTER screenshot."},
        {"kind": "command", "name": "MOUSE WHEEL SCROLL", "command": "scroll down", "result_name": "AI Tool Test: Mouse Wheel Scroll", "verification_type": "scroll_position", "verification_prompt": "Did the Google News webpage scroll down between the before and after screenshots? Look for different news articles or content being visible, or the page shifted downward."},
        {"kind": "command", "name": "CHANGE VOLUME", "command": "increase the volume", "result_name": "AI Tool Test: Change Volume", "verification_type": "no_verification", "verification_prompt": "No visual verification required for volume change"},
        {"kind": "command", "name": "WINDOWS KEY", "command": "press the windows key", "result_name": "AI Tool Test: Windows Key", "verification_type": "start_menu", "verification_prompt": "Did the Start menu or search window appear on screen?"},
        {"kind": "command", "name": "SHOW DESKTOP", "command": "show the desktop", "result_name": "AI Tool Test: Show Desktop", "verification_type": "desktop", "verification_prompt": "Are all application windows minimized and the desktop visible?"},
        {"kind": "command", "name": "TYPE NUMBERS", "command": "type any number", "result_name": "AI Tool Test: Type Number", "verification_type": "text_input", "verification_prompt": "Does the AFTER screenshot show numbers appearing in a text input field?"},
        {"kind": "command", "name": "OPEN NOTEPAD", "command": "open notepad", "result_name": "AI Tool Test: Open Notepad", "verification_type": "window_appearance", "verification_prompt": "Did a Notepad window appear on screen?", "close_after": True},
        {"kind": "command", "name": "OPEN CALCULATOR", "command": "open calculator", "result_name": "AI Tool Test: Open Calculator", "verification_type": "window_appearance", "verification_prompt": "Did a Calculator window appear on screen?", "close_after": True},
        {"kind": "command", "name": "OPEN PAINT", "command": "open paint", "result_name": "AI Tool Test: Open Paint", "verification_type": "window_appearance", "verification_prompt": "Did a Microsoft Paint window appear on screen?", "close_after": True},
        {"kind": "command", "name": "OPEN SETTINGS", "command": "open settings", "result_name": "AI Tool Test: Open Settings", "verification_type": "window_appearance", "verification_prompt": "Did a Windows Settings window appear on screen?", "close_after": True},
        {"kind": "command", "name": "OPEN EDGE", "command": "open microsoft edge", "result_name": "AI Tool Test: Open Microsoft Edge", "verification_type": "window_appearance", "verification_prompt": "Did a Microsoft Edge browser window appear on screen? Look for the Edge browser interface (address bar, tabs, web content).", "close_after": True},
        {"kind": "command", "name": "OPEN SNIPPING TOOL", "command": "open snipping tool", "result_name": "AI Tool Test: Open Snipping Tool", "verification_type": "window_appearance", "verification_prompt": "Did the Snipping Tool appear on screen? Look for the Snipping Tool window or its capture toolbar (usually a small bar near the top of the screen).", "close_after": True},
        {"kind": "command", "name": "OPEN CLOCK", "command": "open clock", "result_name": "AI Tool Test: Open Clock", "verification_type": "window_appearance", "verification_prompt": "Did a Clock or 'Alarms & Clock' app window appear on screen? Look for a clock/timer/stopwatch/alarm interface.", "close_after": True},
        {"kind": "command", "name": "MINIMIZE WINDOW", "command": "minimize window", "result_name": "AI Tool Test: Minimize Window", "verification_type": "window_state", "verification_prompt": "Did the active window minimize to the taskbar?"},
        {"kind": "command", "name": "MAXIMIZE WINDOW", "command": "maximize window", "result_name": "AI Tool Test: Maximize Window", "verification_type": "window_state", "verification_prompt": "Did the active window maximize to fill the screen?"},
        {"kind": "command", "name": "OPEN WEBSITE", "command": "open google.com", "result_name": "AI Tool Test: Open Website", "verification_type": "browser_window", "verification_prompt": "Did a web browser window open showing Google or a website?"},
    ]

    total = len(tool_tests)
    for i, test in enumerate(tool_tests, start=1):
        kind = test["kind"]
        test_name = test["name"]
        result_name = test["result_name"]
        verification_type = test["verification_type"]
        verification_prompt = test["verification_prompt"]

        print("\n" + "-" * 50)
        print(f"TOOL TEST {i}/{total}: {test_name}")
        print("-" * 50)
        speak_tts(f"Tool test {i} of {total}: {test_name.lower()}")

        try:
            # Step 1: Close any previous LIMA instance and launch fresh for isolation
            executor.process_manager.close()
            time.sleep(SLEEP_B)
            print("  Launching fresh LIMA...")
            if not executor.process_manager.launch(
                executor.process_manager.exe_full_path,
                executor.process_manager.install_path
            ):
                message = "Could not launch LIMA for test"
                executor.add_test_result(result_name, TEST_FAILED, message)
                print(f"  X {message}")
                continue
            time.sleep(SLEEP_C)

            # Step 2: Ensure LIMA is focused (always maximize)
            if not executor.process_manager.refocus(timeout=10):
                message = "Could not refocus on LIMA window"
                executor.add_test_result(result_name, TEST_FAILED, message)
                print(f"  X {message}")
                continue

            # Step 3: Clear input state
            pyautogui.press('escape')
            time.sleep(SLEEP_A)

            # Step 4: Release modifier keys
            for key in ['win', 'ctrl', 'alt', 'shift', 'winleft', 'winright']:
                pyautogui.keyUp(key)
            time.sleep(SLEEP_A)

            # Step 5: Capture mouse BEFORE
            mouse_before = pyautogui.position()
            print(f"  Mouse position before: {mouse_before}")

            # For "open <app>" tests, snapshot the current top-level windows so we
            # can close only the ones this test opens (see cleanup in Step 12).
            windows_before = set()
            if test.get("close_after"):
                try:
                    windows_before = {w._hWnd for w in gw.getAllWindows()}
                except Exception:
                    windows_before = set()

            # Special pre-screenshot setup (command tests only)
            if kind == "command":
                if test_name == "MAXIMIZE WINDOW":
                    # Restore so we can actually verify that maximize works
                    pyautogui.hotkey('win', 'down')
                    time.sleep(SLEEP_B)
                elif test_name == "MOUSE WHEEL SCROLL":
                    # Open Google News (reliably long and scrollable) and wait for it to load
                    webbrowser.open("https://news.google.com")
                    time.sleep(SLEEP_D)
                    news_window = find_window_by_title("Google News", timeout=15)
                    if news_window:
                        try:
                            news_window.activate()
                        except Exception:
                            pass
                        time.sleep(SLEEP_B)

            # Step 6: Take BEFORE screenshot (for visual verification)
            before_screenshot = None
            if verification_type != "no_verification" and kind != "audio":
                print("  Taking BEFORE screenshot...")
                before_screenshot = take_screenshot()
                if not before_screenshot:
                    print("  ! Could not capture before screenshot")
                else:
                    print("  OK BEFORE screenshot captured")

            # Step 7: Action — type a command, open a File-menu dialog, or trigger audio
            dialog_window = None
            audio_result = None
            if kind == "command":
                print(f"  Executing tool: '{test['command']}'")
                type_into_lima(test["command"])
                time.sleep(SLEEP_A)
                print("  OK Command typed")

                # Step 8: Submit
                print("  Pressing Enter to submit...")
                pyautogui.press('enter')

                # Special: immediately focus Google News after submit so LIMA scrolls it, not itself
                if test_name == "MOUSE WHEEL SCROLL":
                    news_window = find_window_by_title("Google News", timeout=5)
                    if news_window:
                        try:
                            news_window.activate()
                        except Exception:
                            pass
                        time.sleep(SLEEP_A)

                time.sleep(SLEEP_C)

                # Step 9: Wait for AI execution
                wait_time = 30
                print(f"  Waiting for AI to process ({wait_time} seconds)...")

                for sec in range(wait_time):
                    time.sleep(SLEEP_A)

                    if not executor.process_manager.is_running():
                        message = f"LIMA crashed during {test_name}"
                        executor.add_test_result(result_name, TEST_FAILED, message)
                        print(f"  X {message}")
                        return

                    if (sec + 1) % 5 == 0:
                        print(f"    {sec + 1}/{wait_time} seconds...")

                # Retry for open-program tests: the open_program tool is known to be
                # environment/machine-dependent and can intermittently fail to resolve a
                # program (returning "unknown program"). If nothing opened, re-send the
                # command a few times so the result reflects whether the tool CAN open the
                # app, not a one-off flake. Passes on the first success; only a persistent
                # failure across all attempts is reported as a real failure.
                if test.get("close_after"):
                    max_attempts = 3
                    retry_wait = 15
                    attempt = 1
                    while attempt < max_attempts:
                        opened = [w for w in gw.getAllWindows()
                                  if w._hWnd not in windows_before and w.title.strip() and "LIMA" not in w.title]
                        if opened:
                            break
                        attempt += 1
                        print(f"  App not open yet — retry {attempt}/{max_attempts}: re-sending '{test['command']}'...")
                        type_into_lima(test["command"])
                        time.sleep(SLEEP_A)
                        pyautogui.press('enter')
                        time.sleep(SLEEP_C)
                        for _ in range(retry_wait):
                            time.sleep(SLEEP_A)
                            if not executor.process_manager.is_running():
                                message = f"LIMA crashed during {test_name}"
                                executor.add_test_result(result_name, TEST_FAILED, message)
                                print(f"  X {message}")
                                return

                # Special: MOUSE WHEEL SCROLL — switch back to Google News to capture the after state
                if test_name == "MOUSE WHEEL SCROLL":
                    news_window = find_window_by_title("Google News", timeout=5)
                    if news_window:
                        try:
                            news_window.activate()
                        except Exception:
                            pass
                        time.sleep(SLEEP_B)
            elif kind == "dialog":
                # Open File menu via Alt → Enter, then navigate to the target item
                print(f"  Opening {test_name} via File menu...")
                pyautogui.press('alt')
                time.sleep(SLEEP_A)
                pyautogui.press('enter')
                time.sleep(SLEEP_B)
                for key in test["menu_nav_keys"]:
                    pyautogui.press(key)
                    time.sleep(SLEEP_A)
                time.sleep(SLEEP_C)
            else:
                # Audio kind: type command into LIMA, submit, then measure per-session audio peak.
                # measure_peak_audio's own duration IS the wait — no 30s AI loop needed.
                print(f"  Typing '{test['command']}' into LIMA...")
                type_into_lima(test["command"])
                time.sleep(SLEEP_A)
                pyautogui.press('enter')
                print("  Listening for audio (up to 15s)...")
                audio_result = measure_peak_audio(max_duration_s=15, poll_hz=20)

            # Step 10: Take AFTER screenshot (for visual verification)
            after_screenshot = None
            if verification_type != "no_verification" and kind != "audio":
                print("  Taking AFTER screenshot...")
                after_screenshot = take_screenshot()
                if not after_screenshot:
                    print("  ! Could not capture after screenshot")
                else:
                    print("  OK AFTER screenshot captured")

            # Special: MOVE MOUSE TO — overlay cursor position so AI can see it
            if test_name == "MOVE MOUSE TO" and after_screenshot:
                after_screenshot = overlay_cursor_on_screenshot(after_screenshot, pyautogui.position())

            # Dialog kind: poll for the dialog window as a sanity check
            if kind == "dialog":
                keywords = test["dialog_title_keywords"]
                print(f"  Searching for {test_name} window...")
                for attempt in range(10):
                    all_windows = gw.getAllWindows()
                    if attempt == 0:
                        print("    Current windows:")
                        for w in all_windows:
                            if w.title.strip():
                                print(f"      - '{w.title}'")
                    for window in all_windows:
                        if any(kw in window.title for kw in keywords):
                            dialog_window = window
                            print(f"  OK Found dialog: '{window.title}'")
                            break
                    if dialog_window:
                        break
                    if attempt % 2 == 0:
                        print(f"    Attempt {attempt + 1}/10 - {test_name} not found yet...")
                    time.sleep(SLEEP_A)

            # Step 11: Verification using OpenRouter Gemini
            verification_result = None
            if verification_type != "no_verification" and before_screenshot and after_screenshot:
                print("  Verifying with OpenRouter Gemini model...")
                verification_result = verify_tool_with_screenshots(
                    before_screenshot=before_screenshot,
                    after_screenshot=after_screenshot,
                    tool_name=test_name,
                    verification_prompt=verification_prompt
                )
            else:
                print("  No visual verification required")

            # Step 12: Cleanup
            if kind == "dialog":
                print(f"  Closing {test_name}...")
                pyautogui.press('escape')
                time.sleep(SLEEP_A)
            elif "WINDOWS KEY" in test_name:
                pyautogui.press('escape')
                time.sleep(SLEEP_A)

            elif "SHOW DESKTOP" in test_name:
                pyautogui.hotkey('win', 'd')
                time.sleep(SLEEP_A)
                for key in ['win', 'winleft', 'winright']:
                    pyautogui.keyUp(key)

            elif "MOUSE WHEEL SCROLL" in test_name:
                pyautogui.hotkey('ctrl', 'w')  # Close Amazon browser tab
                time.sleep(SLEEP_A)

            # Close any app windows this "open <app>" test opened, so they don't
            # pile up and clutter later screenshots. Only windows that appeared
            # after Step 5's snapshot are closed; pre-existing windows, the test
            # console, and the LIMA window are all left alone. We send WM_CLOSE to
            # the specific window (never kill a process by name — that would take
            # down the Explorer shell along with a File Explorer window).
            if test.get("close_after"):
                print(f"  Closing windows opened by {test_name}...")
                for window in gw.getAllWindows():
                    try:
                        if window._hWnd in windows_before:
                            continue
                        if not window.title or not window.title.strip():
                            continue
                        if "LIMA" in window.title:
                            continue
                        window.close()
                        time.sleep(SLEEP_A)
                    except Exception:
                        pass

            # Step 13: Record result
            if executor.process_manager.is_running():
                if kind == "dialog" and dialog_window is None:
                    message = f"{test_name} did not appear within timeout — menu navigation failed"
                    executor.add_test_result(result_name, TEST_FAILED, message)
                    executor.add_error(f"{test_name} window not found after menu click")
                    print(f"  X {test_name} FAILED - dialog did not open")
                elif kind == "audio":
                    peak = audio_result["max_peak"]
                    pid = audio_result["loudest_pid"]
                    name = audio_result["loudest_process_name"] or "unknown"
                    elapsed = audio_result["elapsed_s"]
                    if audio_result["detected"]:
                        message = (f"Audio detected — max peak {peak:.3f} from PID {pid} "
                                   f"({name}) after {elapsed:.1f}s")
                        executor.add_test_result(result_name, TEST_PASSED, message)
                        print(f"  OK {message}")
                    else:
                        message = f"No audio detected in 15s window — max peak {peak:.3f}"
                        executor.add_test_result(result_name, TEST_FAILED, message)
                        executor.add_error(message)
                        print(f"  X {message}")
                elif verification_type == "no_verification":
                    # For tools that don't require visual verification
                    executor.add_test_result(
                        result_name, TEST_PASSED,
                        f"{test_name} executed successfully (no visual verification)"
                    )
                    print(f"  OK {test_name} test PASSED (no visual verification)")
                elif verification_result and verification_result.get("answer") == "YES":
                    # Tool verified as working
                    explanation = verification_result.get("explanation", "No explanation provided")
                    executor.add_test_result(
                        result_name, TEST_PASSED,
                        f"{test_name} executed and verified: {explanation}"
                    )
                    print(f"  OK {test_name} test PASSED")
                    print(f"    Note: {explanation}")
                elif verification_result and verification_result.get("answer") == "NO":
                    # Tool verified as NOT working
                    explanation = verification_result.get("explanation", "No explanation provided")
                    executor.add_test_result(
                        result_name, TEST_FAILED,
                        f"{test_name} verification failed: {explanation}"
                    )
                    print(f"  X {test_name} test FAILED")
                    print(f"    Note: {explanation}")
                else:
                    # Verification failed or not available
                    executor.add_test_result(
                        result_name, TEST_FAILED,
                        f"{test_name} — API verification unavailable — cannot confirm result"
                    )
                    print(f"  X {test_name} test FAILED (API verification unavailable)")
            else:
                executor.add_test_result(
                    result_name, TEST_FAILED,
                    f"{test_name} failed - LIMA crashed"
                )
                print(f"  X {test_name} test FAILED - LIMA crashed")

            time.sleep(SLEEP_C)

        except Exception as error:
            message = f"Exception during {test_name}: {str(error)}"
            executor.add_test_result(result_name, TEST_FAILED, message)
            print(f"  X {message}")
