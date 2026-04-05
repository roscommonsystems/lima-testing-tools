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
import uiautomation as uia

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

    def get_focused_element():
        """
        Get the currently focused UI element using uiautomation interface.
        Returns the focused element wrapper or None if not found.
        """
        try:
            # Use uiautomation to get the focused element
            focused_element = uia.GetFocusedControl()
            if focused_element:
                return focused_element
        except Exception as e:
            print(f"  ! Debug: get_focused_element error: {e}")
        return None

    def is_text_input(element):
        """
        Check if the element is a text input using multiple fallback methods.
        Returns True if the element is an Edit control, False otherwise.
        """
        if element is None:
            return False

        try:
            # Method 1: Check ControlTypeName in uiautomation
            control_type_name = element.ControlTypeName
            if control_type_name:
                if control_type_name == "Edit" or control_type_name == "EditControl":
                    return True

            # Method 2: Check ClassName as fallback
            class_name = element.ClassName
            if class_name and "edit" in class_name.lower():
                return True

            # Method 3: Check AutomationId
            automation_id = element.AutomationId
            if automation_id and ("edit" in automation_id.lower() or "input" in automation_id.lower()):
                return True

        except Exception as e:
            print(f"  ! Debug: is_text_input error: {e}")
        return False

    # Tab until the focused element is a text input (Edit control)
    for attempt in range(max_tabs):
        focused = get_focused_element()

        if focused is None:
            print(f"  ! Could not get focused element (attempt {attempt + 1}/{max_tabs}), tabbing...")
        elif is_text_input(focused):
            # Log what was detected for debugging purposes
            try:
                control_type_name = focused.ControlTypeName
                class_name = focused.ClassName
                name = focused.Name if focused.Name else 'N/A'
                print(f"  OK Found text input: ControlTypeName={control_type_name}, ClassName={class_name}, Name='{name}'")
            except Exception as e:
                print(f"  OK Found text input (details unavailable: {e})")
            break
        else:
            # Log what was found instead for debugging
            try:
                control_type_name = focused.ControlTypeName
                class_name = focused.ClassName
                name = focused.Name if focused.Name else 'N/A'
                print(f"  ! Focused element is not text input (attempt {attempt + 1}/{max_tabs}): ControlTypeName={control_type_name}, ClassName={class_name}, Name='{name}', tabbing...")
            except Exception as e:
                print(f"  ! Focused element is not text input (attempt {attempt + 1}/{max_tabs}): error getting details: {e}, tabbing...")

        pyautogui.press('tab')
        time.sleep(0.3)

    # Type into whichever Edit control now has focus using uiautomation
    try:
        # Find the LIMA window and its Edit control
        lima_windows = uia.GetRootControl().GetChildren()
        lima_window = None
        for window in lima_windows:
            if window.Name and "LIMA" in window.Name:
                lima_window = window
                break

        if lima_window is None:
            # Fallback: Use pyautogui if uiautomation cannot find LIMA window
            print(f"  ! Could not find LIMA window with uiautomation, falling back to pyautogui.write")
            pyautogui.write(text, interval=0.15)
            return

        # Find the Edit control within the LIMA window
        edit_control = lima_window.EditControl()
        if edit_control and edit_control.Exists():
            edit_control.SetFocus()
            edit_control.Click()
            time.sleep(0.2)
            edit_control.SendKeys(text)
            print(f"  OK Typed text using uiautomation")
        else:
            # Fallback: Search recursively for Edit controls
            edit_controls = lima_window.GetChildren()
            for child in edit_controls:
                if child.ControlTypeName == "Edit" or child.ControlTypeName == "EditControl":
                    child.SetFocus()
                    child.Click()
                    time.sleep(0.2)
                    child.SendKeys(text)
                    print(f"  OK Typed text using uiautomation (recursive search)")
                    break
            else:
                # No Edit control found, fallback to pyautogui
                print(f"  ! Could not find Edit control, falling back to pyautogui.write")
                pyautogui.write(text, interval=0.15)
    except Exception as e:
        print(f"  ! Could not use uiautomation to type, falling back to pyautogui.write: {e}")
        pyautogui.write(text, interval=0.15)


def verify_text_in_lima_input(expected_text):
    """
    Check that expected_text is present in LIMA's Edit control.
    Returns True if found, False if not (or if uiautomation can't reach the control).
    """
    try:
        # Find the LIMA window using uiautomation
        lima_window = None
        for window in uia.GetRootControl().GetChildren():
            if window.Name and "LIMA" in window.Name:
                lima_window = window
                break

        if lima_window is None:
            print(f"  ! Could not find LIMA window to verify text")
            return False

        # Try multiple methods to find the Edit control
        edit_control = None

        # Method 1: Try direct EditControl access
        try:
            edit_control = lima_window.EditControl()
            if edit_control and edit_control.Exists():
                pass  # Successfully found
            else:
                edit_control = None
        except Exception:
            pass

        # Method 2: Search recursively for Edit controls
        if edit_control is None:
            try:
                all_controls = lima_window.GetChildren()
                for ctrl in all_controls:
                    if ctrl.ControlTypeName in ["Edit", "EditControl"]:
                        edit_control = ctrl
                        break
            except Exception:
                pass

        if edit_control is None:
            print(f"  ! Could not find LIMA Edit control to verify text")
            return False

        # Get the text value from the Edit control
        try:
            value = None
            # Method 1: ValuePattern.Value (correct API for uiautomation library)
            try:
                value = edit_control.ValuePattern.Value
            except Exception:
                pass
            # Method 2: TextPattern (also available on QTextEdit)
            if not value:
                try:
                    value = edit_control.TextPattern.DocumentRange.GetText(-1)
                except Exception:
                    pass
            # Method 3: Name attribute (last resort)
            if not value and hasattr(edit_control, 'Name'):
                value = edit_control.Name
            if not value:
                print(f"  ! Could not retrieve text from LIMA Edit control")
                return False
        except Exception as error:
            print(f"  ! Error getting text from LIMA Edit control: {error}")
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
