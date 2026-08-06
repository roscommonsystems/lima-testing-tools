"""
LIMA Model Tests Module
Contains run_all_model_tests: verifies each selectable Base AI Model can be set via
the Settings dialog and that LIMA then responds using it. Part of the Regression
Test Enhancement epic (model-coverage slice).
"""

import time
import pyautogui
import uiautomation as uia

from lima_test_utils import (
    take_screenshot, verify_tool_with_screenshots, minimize_all_other_windows,
    type_into_lima, speak_tts, TEST_PASSED, TEST_FAILED,
    SLEEP_A, SLEEP_B, SLEEP_C,
)

# The models are discovered straight from the Settings "Base AI Model" dropdown at
# runtime (see _discover_available_models) instead of a hardcoded list, so the test
# stays robust to base-LLM changes: new models are covered automatically and retired
# ones simply aren't tested (no false failures when e.g. Opus 4.8 is replaced by 5.x).

MODEL_COMBO_NAME = "Base AI Model Selection Dropdown"
SAVE_BUTTON_NAME = "Save Settings Button"


def _find_settings_window(maxdepth=6):
    """Find LIMA's Settings dialog anywhere in the tree (it is nested, not top-level)."""
    root = uia.GetRootControl()
    stack = [(c, 0) for c in root.GetChildren()]
    while stack:
        ctrl, depth = stack.pop()
        try:
            nm = (ctrl.Name or "").lower()
            if "setting" in nm and "lima" in nm:
                return ctrl
        except Exception as err:
            print(err)
        if depth < maxdepth:
            try:
                stack.extend((c, depth + 1) for c in ctrl.GetChildren())
            except Exception as err:
                print(err)
    return None


def _open_settings(executor):
    """Open LIMA's Settings dialog; return the window control or None.

    Minimizes other windows first so the Alt menu keystroke lands on LIMA, then
    File menu via Alt -> Enter -> Enter (Settings is the first item).
    """
    minimize_all_other_windows()
    time.sleep(SLEEP_B)
    executor.process_manager.refocus(timeout=10)
    time.sleep(SLEEP_B)
    pyautogui.press('escape'); time.sleep(SLEEP_A)
    pyautogui.press('alt'); time.sleep(SLEEP_B)
    pyautogui.press('enter'); time.sleep(SLEEP_B)
    pyautogui.press('enter'); time.sleep(SLEEP_C)
    return _find_settings_window()


def _model_key(label):
    """Reduce a dropdown label to a short, stable key for selection + display,
    e.g. 'Opus 4.8 (Anthropic) — Best for everyday, complex tasks' -> 'Opus 4.8'.
    Splits on the provider parenthesis (present on every model), then the dash."""
    for sep in (" (", " —", " -"):
        idx = label.find(sep)
        if idx != -1:
            return label[:idx].strip()
    return label.strip()


def _read_model_options(settings_win):
    """Expand the Base AI Model combo and return only its option labels.

    The combo's dropdown is a ListControl in the UI tree, but a whole-tree scan for
    ListItems also picks up unrelated items (taskbar, desktop icons, browser tabs,
    LIMA's own chat log). So we anchor on the combo's current value and read only the
    single ListControl that actually contains it.
    """
    combo = settings_win.ComboBoxControl(Name=MODEL_COMBO_NAME)
    if not combo.Exists(2):
        return []

    current = ""
    try:
        current = combo.GetValuePattern().Value
    except Exception as err:
        print(err)
    if not current:
        print("  ! Could not read the model combo's current value; cannot anchor discovery")
        return []

    try:
        combo.GetExpandCollapsePattern().Expand()
    except Exception as err:
        print(err)
        combo.Click()
    time.sleep(SLEEP_B)

    labels = []
    root = uia.GetRootControl()
    stack = [(c, 0) for c in root.GetChildren()]
    while stack:
        ctrl, depth = stack.pop()
        try:
            if ctrl.ControlTypeName == "ListControl":
                names = [c.Name for c in ctrl.GetChildren()
                         if c.ControlTypeName == "ListItemControl" and c.Name]
                if current in names:
                    labels = names
                    break
        except Exception as err:
            print(err)
        if depth < 8:
            try:
                stack.extend((c, depth + 1) for c in ctrl.GetChildren())
            except Exception as err:
                print(err)

    try:
        combo.GetExpandCollapsePattern().Collapse()
    except Exception as err:
        print(err)
        pyautogui.press('escape')
    return labels


def _discover_available_models(executor):
    """Launch LIMA, open Settings, and read the Base AI Model dropdown so the test
    covers exactly the models the app currently offers. Returns a de-duplicated list
    of short model keys, or [] if the dropdown couldn't be read."""
    executor.process_manager.close()
    time.sleep(SLEEP_B)
    if not executor.process_manager.launch(
        executor.process_manager.exe_full_path,
        executor.process_manager.install_path
    ):
        print("  X Could not launch LIMA for model discovery")
        return []
    time.sleep(SLEEP_C)

    settings_win = _open_settings(executor)
    if not settings_win:
        print("  X Could not open Settings for model discovery")
        executor.process_manager.close()
        time.sleep(SLEEP_B)
        return []

    labels = _read_model_options(settings_win)
    executor.process_manager.close()
    time.sleep(SLEEP_B)

    keys = []
    for label in labels:
        key = _model_key(label)
        if key and key not in keys:
            keys.append(key)
    return keys


def _select_model(settings_win, key):
    """Expand the Base AI Model combo, click the item whose name contains `key`, and
    return the combo's value afterwards (so the caller can confirm the change took)."""
    combo = settings_win.ComboBoxControl(Name=MODEL_COMBO_NAME)
    if not combo.Exists(2):
        return None
    try:
        combo.GetExpandCollapsePattern().Expand()
    except Exception as err:
        print(err)
        combo.Click()
    time.sleep(SLEEP_B)

    target = None
    root = uia.GetRootControl()
    stack = [(c, 0) for c in root.GetChildren()]
    while stack:
        ctrl, depth = stack.pop()
        try:
            if ctrl.ControlTypeName == "ListItemControl" and ctrl.Name and key in ctrl.Name:
                target = ctrl
                break
        except Exception as err:
            print(err)
        if depth < 8:
            try:
                stack.extend((c, depth + 1) for c in ctrl.GetChildren())
            except Exception as err:
                print(err)

    if not target:
        try:
            combo.GetExpandCollapsePattern().Collapse()
        except Exception as err:
            print(err)
            pyautogui.press('escape')
        return None

    target.Click()
    time.sleep(SLEEP_A)
    try:
        return combo.GetValuePattern().Value
    except Exception as err:
        print(err)
        return "<selected>"


def run_all_model_tests(executor):
    """Verify each Base AI Model can be set via Settings and that LIMA responds using it.

    The model list is discovered from the live Settings dropdown first, then per model:
    launch LIMA, open Settings, pick the model, Save, relaunch LIMA so the new model
    loads, then send a question and confirm a response appears (vision check).
    "Works" = a response is produced; verifying WHICH model served it isn't practical.
    """
    print("\n" + "=" * 60)
    print("TESTING ALL LIMA BASE AI MODELS")
    print("=" * 60)

    # Discover the models the app currently offers so coverage tracks the live dropdown
    # instead of a hardcoded list (robust to base-LLM additions/removals).
    model_keys = _discover_available_models(executor)
    if not model_keys:
        executor.add_test_result("Model Discovery", TEST_FAILED,
                                 "Could not read the Base AI Model dropdown to discover models")
        print("  X Could not discover any models — skipping model tests")
        executor.process_manager.close()
        time.sleep(SLEEP_B)
        return
    print(f"Discovered {len(model_keys)} model(s): {', '.join(model_keys)}")

    total = len(model_keys)
    for i, key in enumerate(model_keys, start=1):
        result_name = f"Model Test: {key}"
        print("\n" + "-" * 50)
        print(f"MODEL TEST {i}/{total}: {key}")
        print("-" * 50)
        speak_tts(f"Model test {i} of {total}: {key}")

        try:
            # 1. Fresh LIMA so we can open Settings and change the model.
            executor.process_manager.close()
            time.sleep(SLEEP_B)
            if not executor.process_manager.launch(
                executor.process_manager.exe_full_path,
                executor.process_manager.install_path
            ):
                executor.add_test_result(result_name, TEST_FAILED, "Could not launch LIMA")
                print("  X Could not launch LIMA")
                continue
            time.sleep(SLEEP_C)

            # 2. Open Settings and select the model.
            print("  Opening Settings...")
            settings_win = _open_settings(executor)
            if not settings_win:
                executor.add_test_result(result_name, TEST_FAILED, "Could not open Settings dialog")
                print("  X Could not open Settings dialog")
                continue

            print(f"  Selecting model '{key}'...")
            value = _select_model(settings_win, key)
            if not value or key not in value:
                executor.add_test_result(result_name, TEST_FAILED,
                                         f"Could not select model '{key}' (combo reads {value!r})")
                print(f"  X Could not select '{key}' (reads {value!r})")
                pyautogui.press('escape'); time.sleep(SLEEP_A)
                continue
            print(f"  OK combo now reads: {value!r}")

            # 3. Save (this closes the dialog).
            save = settings_win.ButtonControl(Name=SAVE_BUTTON_NAME)
            if not save.Exists(2):
                executor.add_test_result(result_name, TEST_FAILED, "Could not find Save button")
                print("  X Could not find Save button")
                continue
            save.Click()
            time.sleep(SLEEP_C)

            # 4. Relaunch LIMA so it actually loads the newly-selected model.
            print("  Relaunching LIMA to apply the model...")
            executor.process_manager.close()
            time.sleep(SLEEP_B)
            if not executor.process_manager.launch(
                executor.process_manager.exe_full_path,
                executor.process_manager.install_path
            ):
                executor.add_test_result(result_name, TEST_FAILED, "Could not relaunch LIMA after model change")
                print("  X Could not relaunch LIMA")
                continue
            time.sleep(SLEEP_C)
            executor.process_manager.refocus(timeout=10)
            pyautogui.press('escape'); time.sleep(SLEEP_A)

            # 5. Send a question and confirm LIMA responds (proves the model works).
            before = take_screenshot()
            print("  Sending test command: 'what is two plus two'")
            type_into_lima("what is two plus two")
            time.sleep(SLEEP_A)
            pyautogui.press('enter')
            print("  Waiting for response (30s)...")
            crashed = False
            for _ in range(30):
                time.sleep(SLEEP_A)
                if not executor.process_manager.is_running():
                    executor.add_test_result(result_name, TEST_FAILED, f"{key} - LIMA crashed")
                    print(f"  X {key} - LIMA crashed")
                    crashed = True
                    break
            if crashed:
                continue

            after = take_screenshot()
            result = verify_tool_with_screenshots(
                before, after, f"Base AI Model {key}",
                "Did LIMA generate a new text response in the chat answering the question "
                "(a new assistant reply that was not in the before screenshot)?"
            )
            if result and result.get("answer") == "YES":
                executor.add_test_result(result_name, TEST_PASSED,
                                         f"Model '{key}' set and LIMA responded: {result.get('explanation', '')}")
                print(f"  OK {key} responded")
            elif result and result.get("answer") == "NO":
                executor.add_test_result(result_name, TEST_FAILED,
                                         f"Model '{key}' set but LIMA did not respond: {result.get('explanation', '')}")
                print(f"  X {key} did not respond")
            else:
                executor.add_test_result(result_name, TEST_FAILED,
                                         f"Model '{key}' - API verification unavailable")
                print(f"  X {key} - verification unavailable")

            time.sleep(SLEEP_B)

        except Exception as error:
            executor.add_test_result(result_name, TEST_FAILED, f"Exception during {key}: {error}")
            print(f"  X Exception during {key}: {error}")

    executor.process_manager.close()
    time.sleep(SLEEP_B)
