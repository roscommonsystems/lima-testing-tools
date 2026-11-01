"""
preflight.py - verify the machine is ready before a full regression run.

A full run takes roughly an hour and needs a signed-in LIMA, an unlocked desktop, an
audio output device and working auth. This script checks all of that in seconds, so a
misconfigured machine fails immediately instead of an hour into the run.

Run (from the project root, inside the venv):
  python preflight.py             # full check, including auth
  python preflight.py --no-auth   # skip the auth/network check
"""

import ctypes
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "regression_tests"))

MIN_PYTHON = (3, 8)
MIN_SCREEN_WIDTH = 1024
MIN_SCREEN_HEIGHT = 768

REQUIRED_MODULES = (
    "pyautogui", "pygetwindow", "psutil", "PIL", "requests", "openai",
    "uiautomation", "pyttsx3", "pycaw", "comtypes", "keyring",
)

# OpenInputDesktop flags: the call only succeeds on the interactive, unlocked desktop.
DESKTOP_SWITCHDESKTOP = 0x0100


def check_python_version():
    """The suite targets Python 3.8+ (README prerequisite)."""
    version = sys.version_info
    ok = tuple(version[:2]) >= MIN_PYTHON
    message = (f"Python {version.major}.{version.minor}.{version.micro} "
               f"(need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)")
    return ok, message


def check_dependencies():
    """Every package in requirements.txt must be importable in this interpreter."""
    missing = []
    for module_name in REQUIRED_MODULES:
        try:
            __import__(module_name)
        except Exception:
            missing.append(module_name)

    if missing:
        return False, (f"missing package(s): {', '.join(missing)} - run: "
                       f"pip install -r requirements.txt")
    return True, f"all {len(REQUIRED_MODULES)} required packages import"


def check_credentials():
    """secret_config.py (or the equivalent environment variables) must be present."""
    if os.path.exists(os.path.join(PROJECT_ROOT, "secret_config.py")):
        return True, "secret_config.py present"

    env_vars = ("LIMA_OPEN_ROUTER_API_KEY", "LIMA_FIREBASE_API_KEY", "LIMA_AUTH_URL")
    if any(os.environ.get(name) for name in env_vars):
        return True, "credentials supplied via environment variables"

    return False, ("secret_config.py not found - copy secret_config.py.example "
                   "(or set LIMA_OPEN_ROUTER_API_KEY / LIMA_FIREBASE_API_KEY / LIMA_AUTH_URL)")


def check_lima_installed():
    """The suite drives an installed copy of LIMA, so it must be discoverable."""
    from lima_test_utils import find_lima_executable

    exe_path = find_lima_executable()
    if not exe_path:
        return False, "LIMA executable not found in the standard install locations"
    return True, f"found {exe_path}"


def check_display():
    """Tests read windows by position, so the screen must be big enough to lay them out."""
    import pyautogui

    width, height = pyautogui.size()
    if width < MIN_SCREEN_WIDTH or height < MIN_SCREEN_HEIGHT:
        return False, (f"screen is {width}x{height} - tests need at least "
                       f"{MIN_SCREEN_WIDTH}x{MIN_SCREEN_HEIGHT}")
    return True, f"screen {width}x{height}"


def check_session_unlocked():
    """A locked or disconnected session has no desktop for the tests to drive."""
    user32 = ctypes.windll.user32
    desktop = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not desktop:
        return False, ("the desktop session is locked or not interactive - tests send "
                       "real keystrokes and clicks, so unlock the machine and re-run")
    user32.CloseDesktop(desktop)
    return True, "interactive desktop session is unlocked"


def check_audio_output():
    """Voice and audio tests measure real output, so a playback device must exist."""
    from pycaw.pycaw import AudioUtilities

    try:
        speakers = AudioUtilities.GetSpeakers()
        session_count = len(AudioUtilities.GetAllSessions())
    except Exception as error:
        return False, f"no audio output device available: {error}"

    if speakers is None:
        return False, "no audio output device found - voice/audio tests cannot pass"
    return True, f"audio endpoint available ({session_count} session(s))"


def check_auth():
    """The suite needs an OpenRouter key for its screenshot checks (see README)."""
    from lima_auth import LimaAuth

    result = LimaAuth().validate_license()
    if not isinstance(result, dict):
        return False, f"unexpected auth result: {result!r}"
    if result.get("error"):
        return False, f"auth failed: {result['error']}"

    api_key = (result.get("api_keys") or {}).get("OPEN_ROUTER_API_KEY")
    if not api_key:
        return False, ("no OPEN_ROUTER_API_KEY returned - is your account provisioned "
                       "on the auth server?")
    return True, f"OPEN_ROUTER_API_KEY retrieved (length {len(api_key)})"


def main():
    skip_auth = "--no-auth" in sys.argv[1:]

    checks = [
        ("Python version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Credentials", check_credentials),
        ("LIMA install", check_lima_installed),
        ("Display", check_display),
        ("Session", check_session_unlocked),
        ("Audio output", check_audio_output),
        ("Auth", check_auth),
    ]

    print("LIMA Testing Suite - preflight checks")
    print("=" * 50)

    failures = 0
    for label, check in checks:
        if label == "Auth" and skip_auth:
            print(f"  [--] {label}: skipped (--no-auth)")
            continue

        try:
            ok, message = check()
        except Exception as error:
            ok, message = False, f"check crashed: {error}"

        print(f"  [{'OK' if ok else 'X '}] {label}: {message}")
        if not ok:
            failures += 1
            # The remaining checks import or drive the environment, so there is no
            # point running them when the basics are missing.
            if label in ("Python version", "Dependencies"):
                print("\n  Install the prerequisites above, then run this check again.")
                return 1

    print("=" * 50)
    if failures:
        print(f"X Preflight failed ({failures} problem(s)). Fix the items above, then re-run.")
        return 1

    print("OK - this machine is ready for a full run (python main.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
