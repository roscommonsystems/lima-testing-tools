"""One-off runner: execute only the dialog tool tests (Settings/About/Subscription).

Run with:  .venv\\Scripts\\python.exe run_dialog_tests.py

Windows consoles default to cp1252, which cannot encode non-Latin1 characters
(e.g. Vietnamese window titles printed during dialog polling) and would abort
the run with a UnicodeEncodeError. Force UTF-8 on stdout/stderr up front.
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'regression_tests'))

from lima_test_executor import LimaTestExecutor
from lima_test_utils import find_lima_executable, initialize_openrouter_api_key
from lima_tool_tests import run_all_tool_tests


def main():
    ex = LimaTestExecutor()

    if not initialize_openrouter_api_key():
        print("ERROR: could not initialize OpenRouter API key - cannot verify dialogs.")
        return 1

    exe = find_lima_executable()
    if not exe:
        print("ERROR: LIMA executable not found.")
        return 1
    ex.process_manager.exe_full_path = exe
    ex.process_manager.install_path = os.path.dirname(exe)
    print(f"LIMA executable: {exe}")

    run_all_tool_tests(ex, kinds=["dialog"])

    report = os.path.join('regression_tests', 'test_results_dialog.json')
    ex.save_report(report)
    print(f"\nReport saved to {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
