"""
LIMA Tool Tests Module
Contains run_all_tool_tests for testing LIMA AI tools in a single session.
"""

import time
import pyautogui

from lima_test_utils import (
    take_screenshot, verify_tool_with_screenshots,
    find_window_by_title, TEST_PASSED, TEST_FAILED,
    speak_tts, type_into_lima
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

    total = len(tool_tests)
    for i, (test_name, command, result_name, verification_type, verification_prompt) in enumerate(tool_tests, start=1):
        print("\n" + "-" * 50)
        print(f"TOOL TEST {i}/{total}: {test_name}")
        print("-" * 50)
        speak_tts(f"Tool test {i} of {total}: {test_name.lower()}")

        try:
            # Step 1: Close any previous LIMA instance and launch fresh for isolation
            executor.process_manager.close()
            time.sleep(2)
            print("  Launching fresh LIMA...")
            if not executor.process_manager.launch(
                executor.process_manager.exe_full_path,
                executor.process_manager.install_path
            ):
                message = "Could not launch LIMA for test"
                executor.add_test_result(result_name, TEST_FAILED, message)
                print(f"  X {message}")
                continue
            time.sleep(3)

            # Step 2: Ensure LIMA is focused (always maximize)
            if not executor.process_manager.refocus(timeout=10):
                message = "Could not refocus on LIMA window"
                executor.add_test_result(result_name, TEST_FAILED, message)
                print(f"  X {message}")
                continue

            # Step 3: Clear input state
            pyautogui.press('escape')
            time.sleep(0.5)

            # Step 4: Release modifier keys
            for key in ['win', 'ctrl', 'alt', 'shift', 'winleft', 'winright']:
                pyautogui.keyUp(key)
            time.sleep(0.3)

            # Step 5: Capture mouse BEFORE
            mouse_before = pyautogui.position()
            print(f"  Mouse position before: {mouse_before}")

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
            time.sleep(1.0)
            print("  OK Command typed")

            # Step 8: Submit
            print("  Pressing Enter to submit...")
            pyautogui.press('enter')
            time.sleep(3.0)

            # Step 9: Wait for AI execution
            wait_time = 20
            print(f"  Waiting for AI to process ({wait_time} seconds)...")

            for i in range(wait_time):
                time.sleep(1)

                if not executor.process_manager.is_running():
                    message = f"LIMA crashed during {test_name}"
                    executor.add_test_result(result_name, TEST_FAILED, message)
                    print(f"  X {message}")
                    return

                if (i + 1) % 5 == 0:
                    print(f"    {i + 1}/{wait_time} seconds...")

            # Step 10: Take AFTER screenshot (for visual verification)
            after_screenshot = None
            if verification_type != "no_verification":
                print("  Taking AFTER screenshot...")
                after_screenshot = take_screenshot()
                if not after_screenshot:
                    print("  ! Could not capture after screenshot")
                else:
                    print("  OK AFTER screenshot captured")

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
                time.sleep(1)

            elif "SHOW DESKTOP" in test_name:
                pyautogui.hotkey('win', 'd')
                time.sleep(1)
                for key in ['win', 'winleft', 'winright']:
                    pyautogui.keyUp(key)

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

            time.sleep(3.0)

        except Exception as error:
            message = f"Exception during {test_name}: {str(error)}"
            executor.add_test_result(result_name, TEST_FAILED, message)
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
        speak_tts("Backspace test")
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
            notepad_window = find_window_by_title("Notepad", timeout=5)
            if not notepad_window:
                print("  X Could not find Notepad window")
                executor.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, "Could not open Notepad for backspace test")
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
            before_screenshot = take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")

            # Step 4: Switch to LIMA and type backspace command
            print("4. Switching to LIMA and executing backspace command...")
            if not executor.process_manager.refocus(timeout=10):
                print("  X Could not refocus on LIMA window")
                executor.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, "Could not refocus on LIMA")
                return

            type_into_lima("press backspace 5 times")
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
                if not executor.process_manager.is_running():
                    message = "LIMA crashed during backspace test"
                    executor.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, message)
                    print(f"  X {message}")
                    return

            after_screenshot = take_screenshot()
            if not after_screenshot:
                print("  ! Could not capture after screenshot")
            else:
                print("  OK AFTER screenshot captured")

            # Step 7: Verify with OpenRouter Gemini
            if before_screenshot and after_screenshot:
                print("7. Verifying with OpenRouter Gemini model...")
                verification_prompt = "Did text get deleted in the Notepad window? Look for fewer characters in the text content."
                verification_result = verify_tool_with_screenshots(
                    before_screenshot=before_screenshot,
                    after_screenshot=after_screenshot,
                    tool_name="BACKSPACE 5 TIMES",
                    verification_prompt=verification_prompt
                )

                if verification_result and verification_result.get("answer") == "YES":
                    explanation = verification_result.get("explanation", "No explanation provided")
                    executor.add_test_result("AI Tool Test: Press Backspace", TEST_PASSED, f"Backspace test passed: {explanation}")
                    print(f"  OK BACKSPACE test PASSED")
                    print(f"    Note: {explanation}")
                elif verification_result and verification_result.get("answer") == "NO":
                    explanation = verification_result.get("explanation", "No explanation provided")
                    executor.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, f"Backspace test failed: {explanation}")
                    print(f"  X BACKSPACE test FAILED")
                    print(f"    Note: {explanation}")
                else:
                    executor.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, "Backspace test — API verification unavailable — cannot confirm result")
                    print(f"  X BACKSPACE test FAILED (API verification unavailable)")
            else:
                executor.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, "Backspace test — screenshots unavailable — cannot confirm result")
                print(f"  X BACKSPACE test FAILED (screenshots unavailable)")

            # Close Notepad
            pyautogui.hotkey('alt', 'f4')
            time.sleep(1.0)

        except Exception as error:
            message = f"Exception during BACKSPACE test: {str(error)}"
            executor.add_test_result("AI Tool Test: Press Backspace", TEST_FAILED, message)
            print(f"  X {message}")

        # Test ARROW LEFT
        print("\n--- TESTING ARROW LEFT ---")
        speak_tts("Arrow left test")
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
            notepad_window = find_window_by_title("Notepad", timeout=5)
            if not notepad_window:
                print("  X Could not find Notepad window")
                executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, "Could not open Notepad for arrow key test")
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
            before_screenshot = take_screenshot()
            if not before_screenshot:
                print("  ! Could not capture before screenshot")
            else:
                print("  OK BEFORE screenshot captured")

            # Step 4: Switch to LIMA and type arrow left command
            print("4. Switching to LIMA and executing arrow left command...")
            if not executor.process_manager.refocus(timeout=10):
                print("  X Could not refocus on LIMA window")
                executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, "Could not refocus on LIMA")
                return

            type_into_lima("press arrow key left")
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
                if not executor.process_manager.is_running():
                    message = "LIMA crashed during arrow left test"
                    executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, message)
                    print(f"  X {message}")
                    return

            after_screenshot = take_screenshot()
            if not after_screenshot:
                print("  ! Could not capture after screenshot")
            else:
                print("  OK AFTER screenshot captured")

            # Step 7: Verify with OpenRouter Gemini
            if before_screenshot and after_screenshot:
                print("7. Verifying with OpenRouter Gemini model...")
                verification_prompt = "Did the text cursor move left in the Notepad text field? Look for cursor position changes in the text."
                verification_result = verify_tool_with_screenshots(
                    before_screenshot=before_screenshot,
                    after_screenshot=after_screenshot,
                    tool_name="ARROW LEFT",
                    verification_prompt=verification_prompt
                )

                if verification_result and verification_result.get("answer") == "YES":
                    explanation = verification_result.get("explanation", "No explanation provided")
                    executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_PASSED, f"Arrow left test passed: {explanation}")
                    print(f"  OK ARROW LEFT test PASSED")
                    print(f"    Note: {explanation}")
                elif verification_result and verification_result.get("answer") == "NO":
                    explanation = verification_result.get("explanation", "No explanation provided")
                    executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, f"Arrow left test failed: {explanation}")
                    print(f"  X ARROW LEFT test FAILED")
                    print(f"    Note: {explanation}")
                else:
                    executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, "Arrow left test — API verification unavailable — cannot confirm result")
                    print(f"  X ARROW LEFT test FAILED (API verification unavailable)")
            else:
                executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, "Arrow left test — screenshots unavailable — cannot confirm result")
                print(f"  X ARROW LEFT test FAILED (screenshots unavailable)")

            # Close Notepad
            pyautogui.hotkey('alt', 'f4')
            time.sleep(1.0)

        except Exception as error:
            message = f"Exception during ARROW LEFT test: {str(error)}"
            executor.add_test_result("AI Tool Test: Arrow Key Left", TEST_FAILED, message)
            print(f"  X {message}")

        print("\n" + "="*60)
        print("SPECIAL NOTEPAD TESTS COMPLETED")
        print("="*60)

    except Exception as error:
        message = f"Exception during special Notepad tests: {str(error)}"
        executor.add_test_result("Special Notepad Tests", TEST_FAILED, message)
        print(f"  X {message}")
