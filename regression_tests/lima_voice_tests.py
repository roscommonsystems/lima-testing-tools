"""
LIMA Voice Tests Module
Contains run_all_voice_tests: verifies each selectable TTS voice can be switched
to and produces audio output. Part of the Regression Test Enhancement epic
(voice-coverage slice).
"""

import time
import pyautogui

from lima_test_utils import (
    measure_peak_audio, type_into_lima, TEST_PASSED, TEST_FAILED,
    speak_tts, SLEEP_A, SLEEP_B, SLEEP_C,
)

# The TTS voices LIMA actually supports, matching the Settings dialog "TTS Voice"
# dropdown. NOTE: available_tools.py in the lima repo advertises 8 voices (it also
# lists Algenib, Aoede, Sadaltager, Callirrhoe), but the running app only accepts
# these 4 — the others return "Voice not found". If LIMA's voice set changes, update
# this list to match the Settings dropdown (the source of truth).
VOICES = ["Despina", "Enceladus", "Rasalgethi", "Laomedeia"]


def run_all_voice_tests(executor):
    """Verify each selectable TTS voice can be switched to and produces audio.

    Launches LIMA once, then for each voice: switches to it (the switch shows only
    a text confirmation, no audio), asks LIMA to speak, and confirms audio output
    via per-session peak metering. Audio-only criterion — confirms the voice makes
    sound, not that the timbre matches the named voice.
    """
    print("\n" + "=" * 60)
    print("TESTING ALL LIMA TTS VOICES")
    print("=" * 60)

    # One fresh LIMA session for the whole voice sweep. Voice switching is stateful
    # and benign (it's exactly what the tool is for), so a single session is enough
    # and far faster than relaunching per voice.
    executor.process_manager.close()
    time.sleep(SLEEP_B)
    print("  Launching fresh LIMA...")
    if not executor.process_manager.launch(
        executor.process_manager.exe_full_path,
        executor.process_manager.install_path
    ):
        for voice in VOICES:
            executor.add_test_result(f"Voice Test: {voice}", TEST_FAILED,
                                     "Could not launch LIMA for voice tests")
        print("  X Could not launch LIMA for voice tests")
        return
    time.sleep(SLEEP_C)

    if not executor.process_manager.refocus(timeout=10):
        for voice in VOICES:
            executor.add_test_result(f"Voice Test: {voice}", TEST_FAILED,
                                     "Could not refocus on LIMA window")
        print("  X Could not refocus on LIMA window")
        return

    # LIMA narrates the screen on startup; silence it before the sweep so it doesn't
    # overlap the first voice's test. Sent twice (with a gap) in case narration starts
    # a beat after launch. Ctrl+Alt+Insert is LIMA's default "Stop Speech" hotkey.
    print("  Silencing LIMA's startup narration...")
    pyautogui.hotkey('ctrl', 'alt', 'insert')
    time.sleep(SLEEP_B)
    pyautogui.hotkey('ctrl', 'alt', 'insert')
    time.sleep(SLEEP_A)

    total = len(VOICES)
    for i, voice in enumerate(VOICES, start=1):
        result_name = f"Voice Test: {voice}"
        print("\n" + "-" * 50)
        print(f"VOICE TEST {i}/{total}: {voice}")
        print("-" * 50)
        speak_tts(f"Voice test {i} of {total}: {voice}")

        try:
            if not executor.process_manager.is_running():
                executor.add_test_result(result_name, TEST_FAILED,
                                         f"LIMA not running before {voice} voice test")
                print(f"  X LIMA not running before {voice} voice test")
                return

            # Clear any pending input state
            pyautogui.press('escape')
            time.sleep(SLEEP_A)

            # Step 1: Switch voice (text confirmation only — no audio here)
            print(f"  Switching voice: 'change your voice to {voice}'")
            type_into_lima(f"change your voice to {voice}")
            time.sleep(SLEEP_A)
            pyautogui.press('enter')
            time.sleep(SLEEP_C)  # let the switch register

            # Silence any ongoing screen-description narration before we measure, so the
            # audio window captures the count-to-5 response in the switched voice — not
            # ambient narration. This matters for an UNATTENDED run (no one to click Stop):
            # otherwise leftover narration could let a silent/broken voice false-pass.
            # Ctrl+Alt+Insert is LIMA's default "Stop Speech" hotkey.
            print("  Stopping any ongoing narration (Stop Speech)...")
            pyautogui.hotkey('ctrl', 'alt', 'insert')
            time.sleep(SLEEP_A)

            # Step 2: Make LIMA speak so the new voice actually produces audio
            print("  Asking LIMA to speak: 'count to 5'")
            type_into_lima("count to 5")
            time.sleep(SLEEP_A)
            pyautogui.press('enter')

            # Step 3: Measure per-session audio peak during the spoken response
            print("  Listening for audio (up to 15s)...")
            audio_result = measure_peak_audio(max_duration_s=15, poll_hz=20)

            # Step 4: Record result
            if not executor.process_manager.is_running():
                executor.add_test_result(result_name, TEST_FAILED, f"{voice} - LIMA crashed")
                print(f"  X {voice} FAILED - LIMA crashed")
                return

            peak = audio_result["max_peak"]
            if audio_result["detected"]:
                message = f"Voice '{voice}' switched and produced audio (max peak {peak:.3f})"
                executor.add_test_result(result_name, TEST_PASSED, message)
                print(f"  OK {message}")
            else:
                message = f"Voice '{voice}' produced NO audio in 15s window (max peak {peak:.3f})"
                executor.add_test_result(result_name, TEST_FAILED, message)
                executor.add_error(message)
                print(f"  X {message}")

            # Let this voice's count-to-5 finish speaking before the next switch, so
            # voices don't cut each other off (cleaner audio + less command collision).
            time.sleep(SLEEP_C)

        except Exception as error:
            message = f"Exception during {voice} voice test: {str(error)}"
            executor.add_test_result(result_name, TEST_FAILED, message)
            print(f"  X {message}")

    # Let the last voice finish speaking before closing (so manual runs are audible),
    # then close LIMA after the voice sweep.
    time.sleep(SLEEP_C)
    executor.process_manager.close()
    time.sleep(SLEEP_B)
