"""
LIMA Settings Tests Module
Contains run_settings_hotkey_reconfigure_test: verifies that saving a changed
hotkey in the Settings dialog leaves the global hotkey system alive.

REGRESSION GUARD - why this test exists
=======================================
In the lima repo, commit 2de02a4 ("refactor(hotkey): pass config to hotkey
manager init") added a required `config` parameter to
MainWindow._init_hotkey_manager but missed the second call site in
MainWindow._reconfigure_hotkey. From that commit until the fix, changing ANY
hotkey in the Settings dialog and pressing Save did the following in the
shipped app:

    1. _apply_settings_changes diffed the old/new config, saw the hotkey
       change, and called _reconfigure_hotkey.
    2. _reconfigure_hotkey STOPPED the running GlobalHotkeyManager and set
       it to None...
    3. ...then raised TypeError (missing `config` argument) BEFORE creating
       the replacement manager.

Net effect: every global hotkey (Stop Speech, Observe Screen, Quick Input,
Mute Microphone) went dead until the app was restarted - and depending on how
the exception escaped the Qt slot, LIMA's global excepthook could show the
crash dialog and hard-exit the process. For a blind user the hotkeys are the
primary escape hatch (e.g. stopping runaway speech), so "saving settings kills
hotkeys" is a critical failure. The lima repo has a unit test for the call
signature (tests/test_global_hotkey_manager.py::TestMainWindowHotkeyReconfigure),
but only this live test exercises the real dialog -> Save -> re-register path
in the installed production build.

How the test detects it
=======================
The probe is the Quick Input hotkey (default Ctrl+Alt+H): pressing it makes
LIMA open the "Ask Lima" popup window. A window-appearance check is used
instead of audio metering because it is binary and immune to timing overlap
with LIMA's startup narration. The popup is driven by the same
GlobalHotkeyManager instance the regression destroys, so:

    popup appears  -> the hotkey system is alive
    no popup       -> the hotkey system is dead (the historical symptom)

Steps:
    1. Snapshot <install>/data/config.json and seed the stop-speech hotkey
       modifier to "ctrl+alt" so the End keypress in step 4 is GUARANTEED to
       change it (End selects the last modifier option, "Ctrl + Shift").
       The snapshot is restored in a finally block no matter what happens.
    2. Launch a fresh LIMA session.
    3. BASELINE probe: Quick Input popup must appear BEFORE settings are
       touched. This proves the probe route works, so a dead probe after the
       save can be attributed to the reconfigure path and not to a broken
       probe (e.g. a changed quick_input_hotkey or popup title).
    4. Open File -> Settings, then navigate by keyboard: focus starts on the
       Language dropdown, Tab twice to the Stop Speech MODIFIER dropdown,
       End to select "Ctrl + Shift", Enter to trigger the default Save button.
    5. After the save settles, assert in order:
       a. LIMA process still running (crash-and-exit variant),
       b. no "LIMA Crash" dialog on screen (crash-dialog variant),
       c. the Settings dialog actually closed - otherwise the keyboard
          navigation drifted, the reconfigure path was never exercised, and
          the test fails as INCONCLUSIVE rather than silently passing.
    6. LIVE probe: Quick Input popup must appear again. No popup here is the
       exact symptom of the regression: the manager was stopped and never
       replaced.

Maintenance notes
=================
- TABS_TO_STOP_MODIFIER mirrors the Settings dialog's widget creation order
  in the lima repo's settings_dialog.py: Language combo -> Text Size combo ->
  Stop Speech modifier combo. If controls are added to the Appearance group
  (or initial focus changes from the Language combo), update the tab count.
- The End keypress relies on the seeded modifier being "ctrl+alt" (middle of
  the three options) so the last option "Ctrl + Shift" is always a change.
- Window titles assume the English UI, like the rest of this suite.
"""

import json
import os
import time

import pyautogui
import pygetwindow as gw

from lima_test_utils import (
    find_window_by_title, speak_tts, TEST_PASSED, TEST_FAILED,
    SLEEP_A, SLEEP_B, SLEEP_C,
)

RESULT_NAME = "Settings Hotkey Reconfigure Test"

SETTINGS_WINDOW_TITLE = "LIMA Settings"
CRASH_WINDOW_TITLE = "LIMA Crash"
QUICK_INPUT_WINDOW_TITLE = "Ask Lima"

# Tab presses from the Settings dialog's initial focus (Language dropdown) to
# the Stop Speech MODIFIER dropdown. See "Maintenance notes" in the module
# docstring before changing.
TABS_TO_STOP_MODIFIER = 2


def _config_file_path(executor):
    """Path to the installed LIMA's config.json."""
    return os.path.join(executor.process_manager.install_path, "data", "config.json")


def _hotkey_keys(hotkey_config, default_modifier, default_key):
    """Convert a config hotkey dict like {"modifier": "ctrl+alt", "key": "h"}
    into a pyautogui key list like ["ctrl", "alt", "h"]."""
    modifier = (hotkey_config or {}).get("modifier", default_modifier)
    key = (hotkey_config or {}).get("key", default_key)
    return [part.strip() for part in modifier.split("+")] + [key]


def _probe_quick_input_hotkey(keys, label):
    """Press the Quick Input hotkey and confirm the Ask Lima popup appears.

    Returns True if the popup appeared (and closes it again with Escape),
    False if it never showed up within the timeout.
    """
    print(f"  Probing global hotkeys ({label}): pressing {'+'.join(keys)}...")
    pyautogui.hotkey(*keys)
    popup = find_window_by_title(QUICK_INPUT_WINDOW_TITLE, timeout=10)
    if popup is None:
        print(f"  X Ask Lima popup did NOT appear ({label} probe)")
        return False
    print(f"  OK Ask Lima popup appeared ({label} probe)")
    time.sleep(SLEEP_A)
    pyautogui.press('escape')  # QuickInputDialog closes silently on Escape
    time.sleep(SLEEP_B)
    return True


def run_settings_hotkey_reconfigure_test(executor):
    """Verify that saving a changed hotkey in Settings leaves global hotkeys alive.

    Manages its own LIMA session (like run_all_voice_tests) and always restores
    the pre-test config.json.
    """
    print("\n" + "=" * 60)
    print("TESTING SETTINGS HOTKEY RECONFIGURATION")
    print("=" * 60)
    speak_tts("Settings hotkey reconfigure test")

    config_path = _config_file_path(executor)
    if not os.path.exists(config_path):
        message = f"config.json not found at {config_path} - cannot seed hotkey state"
        executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
        print(f"  X {message}")
        return

    with open(config_path, 'rb') as f:
        original_config_bytes = f.read()

    try:
        config = json.loads(original_config_bytes.decode('utf-8'))
    except Exception as error:
        message = f"config.json unreadable ({error}) - cannot seed hotkey state"
        executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
        print(f"  X {message}")
        return

    # Seed a known stop-speech modifier so the End keypress is guaranteed to
    # change it (see module docstring). The key is left as configured.
    seeded_stop_hotkey = dict(config.get("stop_speech_hotkey") or {})
    seeded_stop_hotkey["modifier"] = "ctrl+alt"
    seeded_stop_hotkey.setdefault("key", "insert")
    config["stop_speech_hotkey"] = seeded_stop_hotkey

    quick_input_keys = _hotkey_keys(config.get("quick_input_hotkey"), "ctrl+alt", "h")

    print("  Seeding stop-speech hotkey to ctrl+alt in config.json...")
    executor.process_manager.close()
    time.sleep(SLEEP_B)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

    try:
        print("  Launching fresh LIMA...")
        if not executor.process_manager.launch(
            executor.process_manager.exe_full_path,
            executor.process_manager.install_path
        ):
            message = "Could not launch LIMA for settings hotkey test"
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            print(f"  X {message}")
            return
        time.sleep(SLEEP_C)

        if not executor.process_manager.refocus(timeout=10):
            message = "Could not refocus on LIMA window"
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            print(f"  X {message}")
            return

        # BASELINE probe: hotkeys must work before settings are touched,
        # otherwise a dead probe after the save proves nothing.
        if not _probe_quick_input_hotkey(quick_input_keys, "baseline"):
            message = ("Baseline probe failed - global hotkeys not working BEFORE the "
                       "settings change. Inconclusive: check quick_input_hotkey config "
                       "and the Ask Lima popup title before suspecting the reconfigure path.")
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            executor.add_error(message)
            print(f"  X {message}")
            return

        # Re-focus the main window so File-menu navigation lands on LIMA
        if not executor.process_manager.refocus(timeout=10):
            message = "Could not refocus on LIMA window after baseline probe"
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            print(f"  X {message}")
            return

        # Open File -> Settings (first menu item), same route as the dialog tests
        print("  Opening Settings via File menu...")
        pyautogui.press('alt')
        time.sleep(SLEEP_A)
        pyautogui.press('enter')
        time.sleep(SLEEP_B)
        pyautogui.press('enter')
        time.sleep(SLEEP_C)

        if find_window_by_title(SETTINGS_WINDOW_TITLE, timeout=10) is None:
            message = "Settings dialog did not open - File menu navigation failed"
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            print(f"  X {message}")
            return
        print("  OK Settings dialog open")

        # Navigate: Tab to the Stop Speech modifier dropdown, End to select the
        # last option ("Ctrl + Shift" - guaranteed different from the seeded
        # "Ctrl + Alt"), Enter to trigger the default Save button.
        print("  Changing stop-speech modifier and saving...")
        for _ in range(TABS_TO_STOP_MODIFIER):
            pyautogui.press('tab')
            time.sleep(SLEEP_A)
        pyautogui.press('end')
        time.sleep(SLEEP_A)
        pyautogui.press('enter')

        # Saving runs _apply_settings_changes -> _reconfigure_hotkey in LIMA.
        # Give the broken build time to crash / show its crash dialog.
        print("  Waiting for save to settle...")
        time.sleep(SLEEP_C)

        # Check (a): crash-and-exit variant
        if not executor.process_manager.is_running():
            message = ("LIMA exited after saving a hotkey change - crash variant of the "
                       "_reconfigure_hotkey regression (lima commit 2de02a4)")
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            executor.add_error(message)
            print(f"  X {message}")
            return

        # Check (b): crash-dialog variant (process alive, dialog blocking)
        if gw.getWindowsWithTitle(CRASH_WINDOW_TITLE):
            message = ("LIMA Crash dialog appeared after saving a hotkey change - crash "
                       "variant of the _reconfigure_hotkey regression (lima commit 2de02a4)")
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            executor.add_error(message)
            print(f"  X {message}")
            return

        # Check (c): the dialog must actually have closed, or the navigation
        # drifted and the reconfigure path was never exercised.
        if gw.getWindowsWithTitle(SETTINGS_WINDOW_TITLE):
            message = ("Settings dialog still open after Save keystrokes - keyboard "
                       "navigation drifted, reconfigure path NOT exercised (inconclusive). "
                       "Check TABS_TO_STOP_MODIFIER against the current dialog layout.")
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            print(f"  X {message}")
            pyautogui.press('escape')  # close the dialog so later cleanup is clean
            time.sleep(SLEEP_A)
            return
        print("  OK Settings dialog closed, LIMA still running, no crash dialog")

        # LIVE probe: the Quick Input hotkey is unchanged, so if the popup no
        # longer appears the hotkey manager was stopped and never replaced -
        # the historical symptom of the regression.
        if _probe_quick_input_hotkey(quick_input_keys, "after hotkey save"):
            message = ("Hotkey change saved and global hotkeys still respond - "
                       "hotkey manager was re-registered correctly")
            executor.add_test_result(RESULT_NAME, TEST_PASSED, message)
            print(f"  OK {message}")
        else:
            message = ("GLOBAL HOTKEYS DEAD after saving a hotkey change - the hotkey "
                       "manager was stopped and not re-created. This is the exact symptom "
                       "of the _reconfigure_hotkey regression (lima commit 2de02a4).")
            executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
            executor.add_error(message)
            print(f"  X {message}")

    except Exception as error:
        message = f"Exception during settings hotkey reconfigure test: {str(error)}"
        executor.add_test_result(RESULT_NAME, TEST_FAILED, message)
        print(f"  X {message}")

    finally:
        # Always close LIMA first, then restore the pre-test config so the
        # modified hotkey state can never leak into later tests or real use.
        executor.process_manager.close()
        time.sleep(SLEEP_B)
        try:
            with open(config_path, 'wb') as f:
                f.write(original_config_bytes)
            print("  OK Restored original config.json")
        except Exception as error:
            message = f"Could not restore original config.json: {error}"
            executor.add_error(message)
            print(f"  ! {message}")
