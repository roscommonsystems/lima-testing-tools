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
import shutil
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


# Each credential the suite can read, with a short note on where the value comes from.
# Used to scaffold secret_config.py and to tell the user where to look.
CREDENTIALS = (
    ("OPEN_ROUTER_API_KEY",
     "https://openrouter.ai/settings/keys - or leave it empty and use the LIMA sign-in "
     "option, which needs FIREBASE_API_KEY and AUTH_URL instead"),
    ("FIREBASE_API_KEY",
     "Firebase console -> Project Settings -> General -> Web API Key "
     "(ask the LIMA team which Firebase project this suite uses)"),
    ("AUTH_URL",
     "ask the LIMA team, or copy it from the Cloud Run console for the LIMA project"),
)


def _read_module_strings(path):
    """
    Read a Python file's module-level assignments without executing it.

    Returns:
        tuple: (set of assigned names, dict of name -> literal string value)
    """
    import ast

    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)

    assigned = set()
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            assigned.add(target.id)
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                values[target.id] = node.value.value
    return assigned, values


def _append_credential(path, name, help_text):
    """Append a missing credential to secret_config.py, noting where to find its value."""
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"\n# Where to find it: {help_text}\n{name} = \"\"\n")


def check_credentials():
    """Make sure secret_config.py exists and defines every credential the suite reads.

    This is setup help, not a gate. A missing variable is appended to the file (which is
    gitignored) together with a note on where its value comes from, and the check passes
    either way: whether auth actually works is not what this suite tests, and having only
    one of the two auth options configured is fine.
    """
    from lima_auth import is_placeholder

    config_path = os.path.join(PROJECT_ROOT, "secret_config.py")
    example_path = os.path.join(PROJECT_ROOT, "secret_config.py.example")
    notes = []

    # A tester can supply everything through environment variables and skip the file.
    env_names = [f"LIMA_{name}" for name, _ in CREDENTIALS]
    if not os.path.exists(config_path) and any(os.environ.get(name) for name in env_names):
        return True, "credentials supplied via environment variables", notes

    created = False
    if not os.path.exists(config_path):
        if not os.path.exists(example_path):
            return True, "secret_config.py is missing (no example file to copy from)", notes
        shutil.copyfile(example_path, config_path)
        created = True
        notes.append("created secret_config.py from secret_config.py.example")

    assigned, values = _read_module_strings(config_path)

    added = []
    for name, help_text in CREDENTIALS:
        if name in assigned:
            continue
        _append_credential(config_path, name, help_text)
        added.append(name)

    if added:
        assigned, values = _read_module_strings(config_path)
        notes.append(f"added the missing variable(s) {', '.join(added)} to secret_config.py")

    if created:
        message = "secret_config.py created from the example"
    elif added:
        message = "secret_config.py updated"
    else:
        message = "secret_config.py present"

    setup_notes = list(notes)

    def has_value(name):
        value = values.get(name, "")
        return bool(value.strip()) and not is_placeholder(value)

    # One complete option is all the suite needs, so don't nag about the other one.
    if has_value("OPEN_ROUTER_API_KEY"):
        setup_notes.append("auth: using the pasted OpenRouter key (option 1)")
        return True, message, setup_notes
    if has_value("FIREBASE_API_KEY") and has_value("AUTH_URL"):
        setup_notes.append("auth: using your LIMA sign-in (option 2)")
        return True, message, setup_notes

    for name, help_text in CREDENTIALS:
        if has_value(name):
            continue
        notes.append(f"{name} has no value yet - where to find it: {help_text}")

    return True, message, notes


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
    """
    Report whether the suite can already obtain an OpenRouter key right now.

    Advisory only - see check_credentials: auth is not what the suite tests, and either
    auth option on its own is enough. A "not ready" answer here never fails preflight.
    """
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
    # Auth is informational: the suite accepts either a pasted OpenRouter key or the LIMA
    # sign-in, and auth is not what it tests, so a "not ready" auth never blocks a run.
    advisory_labels = {"Auth"}

    print("LIMA Testing Suite - preflight checks")
    print("=" * 50)

    failures = 0
    advisory_problems = []
    for label, check in checks:
        if label in advisory_labels and skip_auth:
            print(f"  [--] {label}: skipped (--no-auth)")
            continue

        try:
            result = check()
        except Exception as error:
            result = (False, f"check crashed: {error}")

        ok, message = result[0], result[1]
        notes = result[2] if len(result) > 2 else ()
        is_advisory = label in advisory_labels

        mark = "OK" if ok else ("! " if is_advisory else "X ")
        print(f"  [{mark}] {label}: {message}")
        for note in notes:
            print(f"         {note}")

        if ok:
            continue
        if is_advisory:
            advisory_problems.append(label)
            continue

        failures += 1
        # The remaining checks import or drive the environment, so there is no point
        # running them when the basics are missing.
        if label in ("Python version", "Dependencies"):
            print("\n  Install the prerequisites above, then run this check again.")
            return 1

    print("=" * 50)
    if failures:
        print(f"X Preflight failed ({failures} problem(s)). Fix the items above, then re-run.")
        return 1

    print("OK - this machine is ready for a full run (python main.py).")
    if advisory_problems:
        print("   Note: auth is not ready yet, which does not block a run - the suite stops at")
        print("   startup with the exact missing piece if it still cannot get a key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
