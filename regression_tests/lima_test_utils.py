"""
LIMA Test Utilities Module
Core utilities for process management, window handling, screenshots, and API integration.
"""

import os
import sys
import json
import time
import base64
import logging
import threading
from io import BytesIO
import pyautogui
import pygetwindow as gw
from PIL import ImageGrab
import psutil
from openai import OpenAI

# Add parent directory to path to import lima_auth
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lima_auth import LimaAuth

# Test result constants
TEST_PASSED = "PASSED"
TEST_FAILED = "FAILED"

# Sleep tier constants
SLEEP_A = 1   # Single UI action (key press, click, focus)
SLEEP_B = 2   # Window state change (activate, maximize, restore)
SLEEP_C = 10  # App/dialog appear, post-submit, post-launch settle, between-test pause
SLEEP_D = 20  # LIMA process startup

# Configure pyautogui
pyautogui.FAILSAFE = False

# Configure logging for regression tests
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Storage for API keys retrieved during license validation
_api_keys = {}


def speak_tts(text):
    """Announce text via TTS in a daemon thread so it never blocks test execution."""
    def _run():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def type_into_lima(text, max_tabs=10):
    """
    Type text into LIMA's text input. Uses UI automation to check which
    element currently has focus — if it is not a text input (Edit control),
    presses Tab and re-checks until it finds one, up to max_tabs times.
    """
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")

    def is_text_input(element):
        """
        Check if the element is a text input using multiple fallback methods.
        Returns True if the element is an Edit control, False otherwise.
        """
        try:
            # Method 1: Check control_type() which returns the UIA control type
            control_type = element.control_type()
            if control_type:
                # ControlType 50004 is Edit in UIA, or it might return "Edit" as string
                if control_type == "Edit" or str(control_type) == "50004":
                    return True

            # Method 2: Check friendly_class_name() as fallback
            friendly_class = element.friendly_class_name()
            if friendly_class:
                if friendly_class == "Edit":
                    return True

            # Method 3: Check element_info.control_type which may have the localized name
            try:
                element_info_control_type = element.element_info.control_type
                if element_info_control_type:
                    if element_info_control_type == "Edit" or str(element_info_control_type).lower() == "edit":
                        return True
            except Exception:
                pass

        except Exception:
            pass
        return False

    # Tab until the focused element is a text input (Edit control)
    for attempt in range(max_tabs):
        try:
            focused = desktop.focused_element()
            if is_text_input(focused):
                # Log what was detected for debugging purposes
                try:
                    control_type = focused.control_type()
                    friendly_class = focused.friendly_class_name()
                    print(f"  OK Found text input: control_type={control_type}, friendly_class={friendly_class}")
                except Exception:
                    pass
                break
            else:
                # Log what was found instead for debugging
                try:
                    control_type = focused.control_type()
                    friendly_class = focused.friendly_class_name()
                    print(f"  ! Focused element is not text input (attempt {attempt + 1}/{max_tabs}): control_type={control_type}, friendly_class={friendly_class}, tabbing...")
                except Exception:
                    print(f"  ! Focused element is not text input (attempt {attempt + 1}/{max_tabs}), tabbing...")
        except Exception as error:
            print(f"  ! Error checking focused element (attempt {attempt + 1}/{max_tabs}): {error}, tabbing...")
        pyautogui.press('tab')
        time.sleep(0.3)

    # Type into whichever Edit control now has focus
    try:
        lima_app = desktop.window(title_re=".*LIMA Screen Reader.*")
        edit = lima_app.child_window(control_type="Edit")
        edit.set_focus()
        edit.click_input()
        time.sleep(0.2)
        edit.type_keys(text, with_spaces=True)
    except Exception:
        pyautogui.write(text, interval=0.15)


def verify_text_in_lima_input(expected_text):
    """
    Check that expected_text is present in LIMA's Edit control.
    Returns True if found, False if not (or if pywinauto can't reach the control).
    """
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        lima_app = desktop.window(title_re=".*LIMA Screen Reader.*")

        # Try multiple methods to find the Edit control
        edit = None

        # Method 1: Try child_window with control_type="Edit"
        try:
            edit = lima_app.child_window(control_type="Edit")
            edit.wait('exists', timeout=1)
        except Exception:
            pass

        # Method 2: Try finding by class name (Edit control class is typically "Edit")
        if edit is None:
            try:
                edit = lima_app.child_window(class_name="Edit")
                edit.wait('exists', timeout=1)
            except Exception:
                pass

        # Method 3: Try to find all Edit controls and pick the first visible one
        if edit is None:
            try:
                edit_controls = lima_app.children(control_type="Edit")
                for ctrl in edit_controls:
                    try:
                        # Check if the control is visible and enabled
                        if ctrl.is_visible() and ctrl.is_enabled():
                            edit = ctrl
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if edit is None:
            print(f"  ! Could not find LIMA Edit control to verify text")
            return False

        # Get the text value from the Edit control
        try:
            value = edit.get_value()
        except Exception:
            # Fallback: try window_text() if get_value() fails
            try:
                value = edit.window_text()
            except Exception:
                print(f"  ! Could not retrieve text from LIMA Edit control")
                return False

        if expected_text in value:
            print(f"  OK Verified text in LIMA input: '{expected_text}'")
            return True
        else:
            print(f"  ! Text not found in LIMA input. Expected: '{expected_text}', Got: '{value}'")
            return False

    except Exception as error:
        print(f"  ! Error verifying text in LIMA input: {error}")
        return False


def find_lima_executable():
    """
    Search for LIMA executable in Program Files locations.

    Returns:
        str: Full path to LIMA executable if found, None otherwise
    """
    search_paths = [
        r"C:\Program Files\LIMA Screen Reader",
        r"C:\Program Files (x86)\LIMA Screen Reader",
        r"C:\Program Files\LIMA",
        r"C:\Program Files (x86)\LIMA"
    ]

    # Check potential executable names (setup.nsi uses "LIMA Screen Reader.exe")
    exe_names = ["LIMA Screen Reader.exe", "lima.exe"]

    for path in search_paths:
        for exe_name in exe_names:
            lima_exe = os.path.join(path, exe_name)
            if os.path.exists(lima_exe):
                return lima_exe

    return None


def find_process_by_name(exe_path):
    """
    Find process by executable path.

    Args:
        exe_path (str): Full path to executable

    Returns:
        psutil.Process or None: Process if found
    """
    try:
        exe_name = os.path.basename(exe_path).lower()

        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == exe_name:
                    return proc
                if proc.info['exe'] and proc.info['exe'].lower() == exe_path.lower():
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as error:
        print(f"Error finding process: {error}")

    return None


def check_crash_logs(lima_install_path):
    """
    Check for crash logs in LIMA's data directory.

    Args:
        lima_install_path (str): Path to LIMA installation directory

    Returns:
        dict: Information about crash logs found or empty dict if none
    """
    if not lima_install_path:
        return {}

    crash_log_dir = os.path.join(lima_install_path, "data")
    crash_log_path = os.path.join(crash_log_dir, "crash.log.txt")

    # Check if crash log exists and read its contents
    if os.path.exists(crash_log_path):
        try:
            with open(crash_log_path, 'r', encoding='utf-8', errors='ignore') as log_file:
                contents = log_file.read()
            return {
                "exists": True,
                "path": crash_log_path,
                "contents": contents
            }
        except Exception as error:
            return {
                "exists": True,
                "path": crash_log_path,
                "contents": f"Error reading crash log: {str(error)}"
            }

    return {"exists": False}


def take_screenshot():
    """
    Take a screenshot of the current screen.

    Returns:
        PIL.Image: Screenshot image object or None if capture failed
    """
    try:
        screenshot = ImageGrab.grab()
        return screenshot
    except Exception as error:
        print(f"Error taking screenshot: {str(error)}")
        return None


def screenshot_to_base64(screenshot_image):
    """
    Convert a PIL screenshot image to base64-encoded JPEG string.

    Args:
        screenshot_image: PIL.Image object to convert

    Returns:
        str: Base64-encoded JPEG image string, or None if conversion failed
    """
    try:
        rgb_image = screenshot_image.convert('RGB')
        image_buffer = BytesIO()
        rgb_image.save(image_buffer, format='JPEG', quality=95)
        base64_bytes = base64.b64encode(image_buffer.getvalue())
        return base64_bytes.decode('utf-8')
    except Exception as error:
        print(f"Error converting screenshot to base64: {str(error)}")
        return None


def find_window_by_title(title_substring, timeout=10):
    """
    Dynamically search for a window by title substring.

    Args:
        title_substring (str): Substring to search for in window titles
        timeout (float): Maximum time in seconds to wait for window to appear

    Returns:
        pygetwindow.Window: Window object if found, None otherwise
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            windows = gw.getWindowsWithTitle(title_substring)
            if windows:
                return windows[0]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def minimize_all_other_windows():
    """
    Minimize all windows except the current process to ensure clean test environment.
    """
    try:
        # Get all windows
        all_windows = gw.getAllWindows()

        for window in all_windows:
            try:
                # Skip LIMA window - we want it visible
                if "LIMA" in window.title:
                    continue
                # Skip system windows that shouldn't be minimized
                if window.title in ["", "Program Manager", "Windows Shell Experience Host"]:
                    continue
                # Minimize the window
                window.minimize()
            except Exception:
                pass  # Skip windows that can't be minimized

        time.sleep(1)
    except Exception as error:
        print(f"Warning: Could not minimize all windows: {str(error)}")


def maximize_window(window):
    """
    Maximize a window to ensure consistent menu positioning.

    Args:
        window: PyGetWindow object to maximize
    """
    try:
        window.activate()
        time.sleep(0.3)
        # Maximize using keyboard shortcut
        pyautogui.hotkey('alt', 'F10')  # Alt+F10 maximizes window in Windows
        time.sleep(0.5)
    except Exception as error:
        print(f"Warning: Could not maximize window: {str(error)}")


def initialize_openrouter_api_key():
    """
    Initialize the OpenRouter API key by validating the license key from activation_key.txt.

    Returns:
        bool: True if API key was successfully initialized, False otherwise
    """
    # Check if API key is already set
    if _api_keys.get('OPEN_ROUTER_API_KEY'):
        return True

    try:
        print(f"  [API] Validating license key to retrieve OpenRouter API key...")

        # Use LimaAuth to validate license and get API keys
        auth = LimaAuth()
        validation_result = auth.validate_license()

        if validation_result.get('valid'):
            api_keys_dict = validation_result.get('api_keys', {})
            open_router_api_key_value = api_keys_dict.get('OPEN_ROUTER_API_KEY')

            if open_router_api_key_value:
                # Store in module-level storage for use by other functions
                _api_keys['OPEN_ROUTER_API_KEY'] = open_router_api_key_value
                print(f"  [API] OpenRouter API key successfully retrieved")
                return True
            else:
                print("WARNING: License validation succeeded but OpenRouter API key was not included in response")
                return False
        else:
            error_msg = validation_result.get('error', 'Unknown error')
            print(f"WARNING: License validation failed: {error_msg}")
            return False

    except Exception as e:
        print(f"ERROR: Failed to initialize OpenRouter API key: {e}")
        return False


def verify_tool_with_screenshots(before_screenshot, after_screenshot, tool_name, verification_prompt):
    """
    Verify tool execution by comparing before/after screenshots using OpenRouter Gemini model.

    Args:
        before_screenshot: PIL.Image of screen before tool execution
        after_screenshot: PIL.Image of screen after tool execution
        tool_name: Name of the tool that was executed (for context)
        verification_prompt: Specific question to ask about the change

    Returns:
        dict: {"explanation": str, "answer": "YES" or "NO"} or None if verification failed
    """
    try:
        # Initialize API key if not already set
        initialize_openrouter_api_key()

        # Get OpenRouter API key from module-level storage
        open_router_api_key = _api_keys.get('OPEN_ROUTER_API_KEY', None)
        if not open_router_api_key or str(open_router_api_key).strip() == "":
            print("WARNING: OPEN_ROUTER_API_KEY not found")
            print("  Hint: Make sure activation_key.txt and lima_config.json are properly configured")
            return None

        # Convert screenshots to base64
        before_base64 = screenshot_to_base64(before_screenshot)
        after_base64 = screenshot_to_base64(after_screenshot)

        if not before_base64 or not after_base64:
            print("ERROR: Failed to convert screenshots to base64")
            return None

        # Create OpenRouter client
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=open_router_api_key
        )

        # Create data URLs for images
        before_data_url = f"data:image/jpeg;base64,{before_base64}"
        after_data_url = f"data:image/jpeg;base64,{after_base64}"

        # System prompt for verification
        system_prompt = f"""You are a visual verification assistant for automated UI testing.
        Your task is to verify if a tool executed correctly by comparing before and after screenshots.

        You will be given:
        1. A "before" screenshot (the state before the tool was executed)
        2. An "after" screenshot (the state after the tool was executed)
        3. The name of the tool that was executed
        4. A specific verification question

        You MUST respond in valid JSON format with exactly two keys:
        - "explanation": A brief description of what you observe in the screenshots
        - "answer": Either "YES" or "NO" (YES = tool worked correctly, NO = tool did not work)

        The tool that was executed: {tool_name}

        IMPORTANT: Your response must be ONLY valid JSON, no other text.
        Example response format:
        {{"explanation": "The text input field now contains the typed text 'Test keyboard input'", "answer": "YES"}}"""

        user_prompt = f"""Verification question: {verification_prompt}

        Please examine both screenshots and determine if the tool worked correctly.
        Remember to respond ONLY in JSON format with 'explanation' and 'answer' keys."""

        # Call OpenRouter API with Gemini 3 model
        response = client.chat.completions.create(
            model="google/gemini-3-flash-preview",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt
                        },
                        {
                            "type": "text",
                            "text": "BEFORE screenshot:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": before_data_url
                            }
                        },
                        {
                            "type": "text",
                            "text": "AFTER screenshot:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": after_data_url
                            }
                        }
                    ]
                }
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )

        # Parse the response
        response_text = response.choices[0].message.content
        print(f"Raw API response: {response_text}")

        # Parse JSON response
        result = json.loads(response_text)

        # Validate the response structure
        if "explanation" in result and "answer" in result:
            # Normalize answer to uppercase
            result["answer"] = result["answer"].upper()
            if result["answer"] not in ["YES", "NO"]:
                print(f"WARNING: Invalid answer value: {result['answer']}, expected YES or NO")
                result["answer"] = "NO"
            return result
        else:
            print(f"ERROR: Response missing required keys. Got: {result}")
            return None

    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON response: {e}")
        return None
    except Exception as e:
        print(f"ERROR: Screenshot verification failed: {e}")
        return None
