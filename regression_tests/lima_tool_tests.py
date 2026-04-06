"""
LIMA Tool Tests Module
Contains run_all_tool_tests for testing LIMA AI tools in a single session.
"""

import time
import webbrowser
import pyautogui

from lima_test_utils import (
    take_screenshot, verify_tool_with_screenshots, overlay_cursor_on_screenshot,
    find_window_by_title, TEST_PASSED, TEST_FAILED,
    speak_tts, type_into_lima,
    SLEEP_A, SLEEP_B, SLEEP_C, SLEEP_D
)


def run_all_tool_tests(executor):
    """Run all LIMA AI tool tests, relaunching LIMA fresh before each test."""
    print("\n" + "=" * 60)
    print("TESTING ALL LIMA AI TOOLS")
    print("=" * 60)

    # (test_name, command, result_name, verification_type, verification_prompt)
    tool_tests = [
        ("TYPE TEXT", "Type hello", "AI Tool Test: Type Text", "text_input", "Does the AFTER screenshot show the text 'hello' appearing in a text input field?"),
        ("WEATHER", "whats the weather in japan", "AI Tool Test: Weather Retrieval", "content_verification", "Did LIMA display a weather response or information about Japan's weather? Look for any new text content or weather-related information in the LIMA interface."),
        ("MOUSE CLICK", "do a right click", "AI Tool Test: Mouse Click", "context_menu", "Does the AFTER screenshot show a context menu appearing at the mouse cursor position?"),
        ("MOUSE CLICK COORDINATES", "click on the file menu", "AI Tool Test: Mouse Click Coordinates", "content_verification", "Did a File menu dropdown or menu bar open in the AFTER screenshot? Look for a dropdown menu appearing, or LIMA's response confirming it clicked the File menu."),
        ("MOVE MOUSE TO", "move the mouse to position x 300 y 300", "AI Tool Test: Move Mouse To", "mouse_position", "Did the mouse cursor move to approximately position (300, 300) — the upper-left area of the screen? A red circle marks the cursor's current position in the AFTER screenshot."),
        ("MOUSE WHEEL SCROLL", "scroll down", "AI Tool Test: Mouse Wheel Scroll", "scroll_position", "Did the Google News webpage scroll down between the before and after screenshots? Look for different news articles or content being visible, or the page shifted downward."),
        ("CHANGE VOLUME", "increase the volume", "AI Tool Test: Change Volume", "no_verification", "No visual verification required for volume change"),
        ("WINDOWS KEY", "press the windows key", "AI Tool Test: Windows Key", "start_menu", "Did the Start menu or search window appear on screen?"),
        ("SHOW DESKTOP", "show the desktop", "AI Tool Test: Show Desktop", "desktop", "Are all application windows minimized and the desktop visible?"),
        ("TYPE NUMBERS", "type any number", "AI Tool Test: Type Number", "text_input", "Does the AFTER screenshot show numbers appearing in a text input field?"),
        ("OPEN NOTEPAD", "open notepad", "AI Tool Test: Open Notepad", "window_appearance", "Did a Notepad window appear on screen?"),
        ("MINIMIZE WINDOW", "minimize window", "AI Tool Test: Minimize Window", "window_state", "Did the active window minimize to the taskbar?"),
        ("MAXIMIZE WINDOW", "maximize window", "AI Tool Test: Maximize Window", "window_state", "Did the active window maximize to fill the screen?"),
        ("OPEN WEBSITE", "open google.com", "AI Tool Test: Open Website", "browser_window", "Did a web browser window open showing Google or a website?"),
    ]

    total = len(tool_tests)
    for i, (test_name, command, result_name, verification_type, verification_prompt) in enumerate(tool_tests, start=1):
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

            # Special pre-screenshot setup
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
            if verification_type != "no_verification":
                print("  Taking BEFORE screenshot...")
                before_screenshot = take_screenshot()
                if not before_screenshot:
                    print("  ! Could not capture before screenshot")
                else:
                    print("  OK BEFORE screenshot captured")

            # Step 7: Type command directly into LIMA's text input
            print(f"  Executing tool: '{command}'")
            type_into_lima(command)
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

            # Special: MOUSE WHEEL SCROLL — switch back to Google News to capture the after state
            if test_name == "MOUSE WHEEL SCROLL":
                news_window = find_window_by_title("Google News", timeout=5)
                if news_window:
                    try:
                        news_window.activate()
                    except Exception:
                        pass
                    time.sleep(SLEEP_B)

            # Step 10: Take AFTER screenshot (for visual verification)
            after_screenshot = None
            if verification_type != "no_verification":
                print("  Taking AFTER screenshot...")
                after_screenshot = take_screenshot()
                if not after_screenshot:
                    print("  ! Could not capture after screenshot")
                else:
                    print("  OK AFTER screenshot captured")

            # Special: MOVE MOUSE TO — overlay cursor position so AI can see it
            if test_name == "MOVE MOUSE TO" and after_screenshot:
                after_screenshot = overlay_cursor_on_screenshot(after_screenshot, pyautogui.position())

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

            # Step 11: Cleanup
            if "WINDOWS KEY" in test_name:
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

            # Step 12: Cleanup and record result
            if executor.process_manager.is_running():
                if verification_type == "no_verification":
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

