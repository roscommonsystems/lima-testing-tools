"""
LIMA Model Tests Module
Contains run_all_model_tests: verifies each selectable Base AI Model can be set via
the Settings dialog and that LIMA then responds using it. Part of the Regression
Test Enhancement epic (model-coverage slice).
"""

import re
import time
import pyautogui
import uiautomation as uia

from lima_test_utils import (
    take_screenshot, verify_tool_with_screenshots, minimize_all_other_windows,
    type_into_lima, speak_tts, open_file_menu_item, TEST_PASSED, TEST_FAILED, TEST_SKIPPED,
    save_failure_artifacts, with_artifact_note,
    SLEEP_A, SLEEP_B, SLEEP_C,
)

# The models are discovered straight from the Settings "Base AI Model" dropdown at
# runtime (see _discover_available_models) instead of a hardcoded list, so the test
# stays robust to base-LLM changes: new models are covered automatically and retired
# ones simply aren't tested (no false failures when e.g. Opus 4.8 is replaced by 5.x).

# The accessible name matches settings_dialog.py's setAccessibleName exactly
# ("AI Model Selection Dropdown", not "Base AI Model ...") — the combo is found
# by UIA Name, so the discovery depends on the exact app-side accessible name.
MODEL_COMBO_NAME = "AI Model Selection Dropdown"
SAVE_BUTTON_NAME = "Save Settings Button"

# A model above the account's plan is still listed, but LIMA (settings_dialog.py) swaps
# its description for the plan gate: '— Pro plan only', '— Standard plan or higher',
# '— Go plan or higher'. Selecting one would land on a neighbouring allowed model, so
# these are reported SKIPPED rather than tested. Ungated rows end in a description.
GATED_LABEL_RE = re.compile(r"—\s*[^—]+?\bplan\s+(?:only|or higher)\s*$", re.IGNORECASE)

# How many Down presses the keyboard fallback may use when walking the dropdown. The
# list is well under this; the cap only stops the walk running away if something is odd.
MODEL_KEYBOARD_STEPS = 24


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
    """Open LIMA's Settings dialog; return the UIA control or None.

    Minimizes other windows first so the Alt menu keystroke lands on LIMA, then
    opens the Settings File-menu item by UIA accessible name (legacy
    Alt -> Enter -> Enter key sequence as a fallback) — the same UIA-by-name
    approach as the About dialog test. A swallowed keystroke (menu not focused,
    focus moved between calls, timing, etc.) would otherwise leave the dialog
    unopened, so the open is retried a few times, polling UIA after each attempt
    — the dialog can lag a moment settling into the UI Automation tree.
    """
    for attempt in range(1, 4):
        minimize_all_other_windows()
        time.sleep(SLEEP_B)
        executor.process_manager.refocus(timeout=10)
        time.sleep(SLEEP_B)
        pyautogui.press('escape'); time.sleep(SLEEP_A)
        open_file_menu_item("Settings", ["enter"])

        deadline = time.time() + 10
        while time.time() < deadline:
            win = _find_settings_window()
            if win:
                return win
            time.sleep(SLEEP_A)

        if attempt < 3:
            print(f"  ! Settings dialog not open, retrying ({attempt}/3)")
            pyautogui.press('escape')
            time.sleep(SLEEP_A)

    return None


def _model_key(label):
    """Reduce a dropdown label to a short, stable key for selection + display,
    e.g. 'Opus 4.8 (Anthropic) — Best for everyday, complex tasks' -> 'Opus 4.8'.
    Splits on the provider parenthesis (present on every model), then the dash."""
    for sep in (" (", " —", " -"):
        idx = label.find(sep)
        if idx != -1:
            return label[:idx].strip()
    return label.strip()


def _plan_restriction(label):
    """Return the plan gate text from a dropdown label, or None if the account can use it.

    LIMA lists every model but replaces a gated one's description with its plan gate, so
    the label alone says whether this account can select it (see GATED_LABEL_RE).
    """
    match = GATED_LABEL_RE.search(label or "")
    return match.group(0).strip() if match else None


def _combo_value(combo):
    """Read the combo's current value, or '' if UIA can't read it."""
    try:
        return combo.GetValuePattern().Value or ""
    except Exception as err:
        print(err)
        return ""


def _value_is_model(value, key):
    """True if the combo's value is the model ``key`` (matched on the model name, so a
    near-miss like 'Opus 5.55' can't satisfy a check for 'Opus 5.5')."""
    return bool(value) and _model_key(value) == key


def _find_options_list(current, depth_limit=8):
    """Find the ListControl holding the model combo's dropdown options.

    The dropdown is a ListControl in the UI tree, but a whole-tree scan for ListItems
    also picks up unrelated items (taskbar, desktop icons, browser tabs, LIMA's own chat
    log). So we anchor on the combo's current value: the single ListControl that contains
    it is the dropdown. If the saved model is itself plan-gated (e.g. the account was
    downgraded, so its label isn't in the list), fall back to the list whose options start
    with the same model name.
    """
    current = (current or "").strip()
    current_key = _model_key(current) if current else ""
    fallback = None
    root = uia.GetRootControl()
    stack = [(c, 0) for c in root.GetChildren()]
    while stack:
        ctrl, depth = stack.pop()
        try:
            if ctrl.ControlTypeName == "ListControl":
                names = [c.Name for c in ctrl.GetChildren()
                         if c.ControlTypeName == "ListItemControl" and c.Name]
                if current and current in names:
                    return ctrl
                if fallback is None and current_key and any(
                        _model_key(name) == current_key for name in names):
                    fallback = ctrl
        except Exception as err:
            print(err)
        if depth < depth_limit:
            try:
                stack.extend((c, depth + 1) for c in ctrl.GetChildren())
            except Exception as err:
                print(err)
    return fallback


def _expand_model_options(combo):
    """Open the combo's dropdown and return the ListControl holding its options."""
    current = _combo_value(combo)
    if not current:
        print("  ! Could not read the model combo's current value; cannot anchor the dropdown")
    try:
        combo.GetExpandCollapsePattern().Expand()
    except Exception as err:
        print(err)
        combo.Click()
    time.sleep(SLEEP_B)
    options_list = _find_options_list(current)
    if options_list is None:
        print("  ! Could not find the model dropdown's option list")
    return options_list


def _collapse_model_options(combo):
    """Close the dropdown if it is still open, so it can't swallow the next click."""
    try:
        expanded = combo.GetExpandCollapsePattern().ExpandCollapseState
    except Exception as err:
        print(err)
        expanded = False
    if not expanded:
        return
    try:
        combo.GetExpandCollapsePattern().Collapse()
    except Exception as err:
        print(err)
        pyautogui.press('escape')
    time.sleep(SLEEP_A)


def _find_option_item(options_list, key):
    """Return the dropdown's ListItemControl for ``key``, or None.

    Matched on the model name (``_model_key``) rather than a substring, so 'Opus 5.5'
    can't match 'Opus 5.55' and a chat-log line can't match anything.
    """
    if options_list is None:
        return None
    try:
        items = options_list.GetChildren()
    except Exception as err:
        print(err)
        return None
    for ctrl in items:
        try:
            if (ctrl.ControlTypeName == "ListItemControl" and ctrl.Name
                    and _model_key(ctrl.Name) == key):
                return ctrl
        except Exception as err:
            print(err)
    return None


def _read_model_options(settings_win):
    """Expand the Base AI Model combo and return only its option labels."""
    combo = settings_win.ComboBoxControl(Name=MODEL_COMBO_NAME)
    if not combo.Exists(2):
        return []

    labels = []
    options_list = _expand_model_options(combo)
    if options_list is not None:
        try:
            labels = [c.Name for c in options_list.GetChildren()
                      if c.ControlTypeName == "ListItemControl" and c.Name]
        except Exception as err:
            print(err)
    _collapse_model_options(combo)
    return labels


def _discover_available_models(executor):
    """Launch LIMA, open Settings, and read the Base AI Model dropdown so the test
    covers exactly the models the app currently offers.

    Returns a de-duplicated list of ``{"key": short name, "label": full dropdown label}``
    dicts, or [] if the dropdown couldn't be read. The full label is kept because it
    carries LIMA's plan gate (e.g. '— Pro plan only'), which decides whether this
    account can use the model at all.
    """
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

    models = []
    for label in labels:
        key = _model_key(label)
        if key and all(key != model["key"] for model in models):
            models.append({"key": key, "label": label})
    return models


def _select_model_by_keyboard(combo, key, max_steps=MODEL_KEYBOARD_STEPS):
    """Walk the focused, closed dropdown with the keyboard until its value is ``key``.

    Proven on the test VM: with focus on the closed combo, Down moves the selection
    (Qwen3.8 -> Kimi K2.6 -> V4.1 Flash -> Muse Glimmer). Home returns to the first row
    so models above the current one are reachable too. Returns True if the value matched.
    """
    combo.SetFocus()
    time.sleep(SLEEP_A)
    pyautogui.press("home")
    time.sleep(SLEEP_A)

    for _ in range(max_steps):
        if _value_is_model(_combo_value(combo), key):
            return True
        pyautogui.press("down")
        time.sleep(SLEEP_A)
    return _value_is_model(_combo_value(combo), key)


def _select_model(settings_win, key):
    """Select the model named ``key`` from the Base AI Model combo, then verify it took.

    LIMA's combo is a Qt widget: UIA's SelectionItemPattern.Select() sets the item's
    IsSelected but never commits the value (it reads back the old model for every entry —
    see the model_select_probe diagnostic), so the choice is committed with a real mouse
    Click on the dropdown item. If clicking doesn't take either, the combo is driven with
    the keyboard instead. The value is read back after every attempt and the whole thing
    retried up to 3 times, because a click can silently miss.
    """
    combo = settings_win.ComboBoxControl(Name=MODEL_COMBO_NAME)
    if not combo.Exists(2):
        return None

    value = ""
    for attempt in range(1, 4):
        options_list = _expand_model_options(combo)
        target = _find_option_item(options_list, key)
        if target is None:
            print(f"  ! '{key}' not in the model dropdown (attempt {attempt}/3)")
        else:
            try:
                target.Click()
            except Exception as err:
                print(err)
            time.sleep(SLEEP_B)
        # A dropdown left open would swallow the Save click later on.
        _collapse_model_options(combo)

        value = _combo_value(combo)
        if _value_is_model(value, key):
            return value
        time.sleep(SLEEP_A)

    print("  ! Clicking the model didn't change it — trying the keyboard")
    _select_model_by_keyboard(combo, key)
    return _combo_value(combo)


def run_all_model_tests(executor):
    """Verify each Base AI Model can be set via Settings and that LIMA responds using it.

    The model list is discovered from the live Settings dropdown first, then per model:
    launch LIMA, open Settings, pick the model, Save, relaunch LIMA so the new model
    loads, then send a question and confirm a response appears (vision check).
    "Works" = a response is produced; verifying WHICH model served it isn't practical.
    Models the account's plan doesn't include are reported SKIPPED, never FAILED.
    """
    print("\n" + "=" * 60)
    print("TESTING ALL LIMA BASE AI MODELS")
    print("=" * 60)

    # Discover the models the app currently offers so coverage tracks the live dropdown
    # instead of a hardcoded list (robust to base-LLM additions/removals).
    models = _discover_available_models(executor)
    if not models:
        executor.add_test_result("Model Discovery", TEST_FAILED,
                                 "Could not read the Base AI Model dropdown to discover models")
        print("  X Could not discover any models — skipping model tests")
        executor.process_manager.close()
        time.sleep(SLEEP_B)
        return
    print(f"Discovered {len(models)} model(s): {', '.join(m['key'] for m in models)}")

    # Each model test Saves a new base model into the installed config.json, so
    # remember the app's original choice and restore it when the sweep finishes
    # (mirrors the Settings Hotkey test, which also restores config.json after it).
    import os
    config_path = os.path.join(executor.process_manager.install_path, "data", "config.json")
    original_model = None
    try:
        import json
        with open(config_path, encoding='utf-8') as _f:
            original_model = json.load(_f).get("base_ai_model")
    except Exception as error:
        print(f"  ! Could not read original base model from config: {error}")

    total = len(models)
    for i, model in enumerate(models, start=1):
        key, label = model["key"], model["label"]
        result_name = f"Model Test: {key}"
        print("\n" + "-" * 50)
        print(f"MODEL TEST {i}/{total}: {key}")
        print("-" * 50)

        # LIMA lists models above the account's plan but marks them with the plan they
        # need. Selecting one would silently land on a neighbouring allowed model, so
        # report it as skipped (not failed) and move on without touching Settings.
        restriction = _plan_restriction(label)
        if restriction:
            message = f"Not available on this account's plan: {label}"
            executor.add_test_result(result_name, TEST_SKIPPED, message)
            print(f"  - SKIPPED {key}: {message}")
            speak_tts(f"Model test {i} of {total}: {key} skipped, not available on this plan")
            continue

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
            if not _value_is_model(value, key):
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
                # Keep the screenshots the verdict was based on so the failure can be
                # reviewed afterwards.
                evidence_folder = save_failure_artifacts(result_name, before, after)
                executor.add_test_result(result_name, TEST_FAILED,
                                         with_artifact_note(
                                             f"Model '{key}' set but LIMA did not respond: "
                                             f"{result.get('explanation', '')}",
                                             evidence_folder))
                print(f"  X {key} did not respond")
            else:
                evidence_folder = save_failure_artifacts(result_name, before, after)
                executor.add_test_result(result_name, TEST_FAILED,
                                         with_artifact_note(
                                             f"Model '{key}' - API verification unavailable",
                                             evidence_folder))
                print(f"  X {key} - verification unavailable")

            time.sleep(SLEEP_B)

        except Exception as error:
            executor.add_test_result(result_name, TEST_FAILED, f"Exception during {key}: {error}")
            print(f"  X Exception during {key}: {error}")

    if original_model:
        try:
            import json
            with open(config_path, encoding='utf-8') as _f:
                config = json.load(_f)
            config["base_ai_model"] = original_model
            with open(config_path, 'w', encoding='utf-8') as _f:
                json.dump(config, _f, indent=4)
            print(f"  Restored original base model to config.json: {original_model}")
        except Exception as error:
            print(f"  ! Could not restore original base model: {error}")

    executor.process_manager.close()
    time.sleep(SLEEP_B)
