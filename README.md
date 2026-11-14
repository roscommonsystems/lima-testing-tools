# LIMA Testing Suite

A regression testing framework for LIMA Screen Reader.

## Overview

This testing suite automates functional testing of the LIMA Screen Reader application. It validates core functionality by launching the application, executing test scenarios, and verifying results through visual comparison.

## Prerequisites

- Windows operating system
- LIMA Screen Reader installed on your system
- Python 3.8 or higher
- A LIMA account you can sign into

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Authentication

The suite needs an OpenRouter API key for its screenshot checks. Copy `secret_config.py.example` to `secret_config.py` (the only file you need to set up) and choose one option:

- **Option 1 — paste an OpenRouter API key:** fill in `OPEN_ROUTER_API_KEY`. The suite uses it as-is and ignores the other two values.
- **Option 2 — reuse your LIMA sign-in:** leave `OPEN_ROUTER_API_KEY` empty, sign into LIMA once beforehand, and fill in both `FIREBASE_API_KEY` and `AUTH_URL`. The suite then fetches its keys from the LIMA auth server.

The file explains where to find each value. Alternatively, each value can be supplied via an environment variable instead: `LIMA_OPEN_ROUTER_API_KEY`, `LIMA_FIREBASE_API_KEY` and `LIMA_AUTH_URL`.

Verify the setup before a full run (~5 seconds):

```bash
python check_auth.py
```

A green `OPEN_ROUTER_API_KEY: present ... Ready to run` means you're set.

To check the whole environment at once (dependencies, LIMA install, display, audio output, ~5 seconds):

```bash
python preflight.py
```

It also sets up `secret_config.py` for you: if the file is missing it is created from the example, and any variable it lacks is added along with a note on where to find the value. Auth is only reported, never enforced — one working option is enough, and it is not what this suite tests. `run_regression_tests.bat` runs this automatically before the tests and stops if the machine is not ready, so a misconfigured machine fails in seconds rather than an hour into a run.

> **Note:** For option 1, this only confirms a key is set, not that OpenRouter accepts it. For option 2, your LIMA account must be provisioned on the auth server for it to return keys.

> **Important:** Never commit `secret_config.py` — it is excluded via `.gitignore`.

#### Why the sign-in option exists

- **No shared key to hand out.** Testers with a LIMA account don't need to be given an API key, so no shared key has to be passed around or kept out of this public repo.
- **No second sign-in.** The tests drive a real copy of LIMA, which needs you to be signed in anyway, so the suite reuses that session.

Option 1 is a shortcut for when you already have your own OpenRouter key.

## Running Tests

Execute the regression test suite from the project root:

```bash
python main.py
```

Or use the provided batch file:

```bash
run_regression_tests.bat
```

## Test Results

Test results are saved to `regression_tests/test_results.json` and include:
- Pass/fail status for each test
- Error messages for failed tests
- Crash log information (if any)

Each test's status is `PASSED`, `FAILED` or `SKIPPED`. A skipped check is one this machine or account can't run — for example an AI model above the signed-in account's plan, which LIMA still lists but labels with the plan it needs (`— Pro plan only`). Skips are reported with their reason and do not fail the run.

When a test fails its screenshot check, the before/after images that verdict was based on are saved under `reports/artifacts/` (gitignored) and the folder is named in the failure message, so the failure can be reviewed afterwards.

## Prod builds and test builds

The suite runs against either kind of LIMA installer, and `test_results.json` records which one it tested in `build_type` (`prod` or `test`):

- **Prod builds** (`vX.Y.Z.W`, `LIMA_Install.exe`, made by the `[PROD]` workflow) are what users get: windowed, no console.
- **Test builds** (`Test-vX.Y.Z.W-runN`, `LIMA_Install_Test.exe`, made by the `[DEV]` workflow) sign in to the dev backend, title the main window `LIMA Desktop - Test Build`, keep a console window open behind LIMA with its debug log scrolling in it, and ship `debug.json`, which makes LIMA log every prompt, reply and tool call to `data\.lima_voice_sessions\<launch time>\` in its install folder.

The suite tells them apart by `debug.json` in the install folder, or by the `LIMA_BUILD_TYPE` environment variable (`prod`/`test`) when it is set. On a test build:

- **Console Window Absence Check** is skipped: the console is expected there. Prod builds still have to pass it.
- The screenshot judge is told that the console belongs to LIMA and that text in its log is not evidence a tool worked (the log echoes what LIMA types).
- The console is never picked as LIMA's window when the suite looks for it by title.
- Each failure's artifact folder also gets `lima_log/`: the text logs of the LIMA launch under test, so you can see what LIMA actually asked the model and which tools it called.

A dev sign-in only sees the dev backend's plans, so the same account can be on a different plan there (and see a different set of models) than on prod.

## Approval tests

LIMA 2.x asks before every action that changes the screen — clicking, typing, opening a program or website, pressing keys — and can ask several times in one turn. During an ordinary run the suite answers Yes automatically (`lima_action_approver.py`), so the run needs no human input.

The approval tests need the opposite: to see that popup and answer it deliberately. They therefore run inside `manual_approvals()`, which pauses both the background approver and the pre-typing approval in `type_into_lima`, and always restores them — including when a test fails. While it is paused nothing auto-approves a popup, so answer or close any open popup before typing into LIMA: an `n` typed while the popup is open would deny it.

They live in `regression_tests/approval_tests/`, one file per scenario. `__init__.py` finds every `test_*` module in that package (sorted by module name) and runs each module's `run(executor)`. To add a test:

1. Add one new file, e.g. `test_20_replacement_instruction.py`.
2. Give it a `RESULT_NAME` and a `def run(executor)` that reports exactly one result with `executor.add_test_result(RESULT_NAME, TEST_PASSED|TEST_FAILED, message)`.
3. Use the shared steps in `approval_tests/_common.py` (`ensure_lima_ready`, `close_apps`, `wait_for_app`, `send_instruction`, `cleanup`) and the popup helpers in `lima_action_approver.py` (`manual_approvals`, `wait_for_action_prompt`, `answer_action_prompt`, `wait_for_replacement_prompt`, `close_replacement_prompt`, `submit_replacement_instruction`).
4. Number the file with the next free number (10, 20, 30, …): the number fixes the run order, and one file per test means separate changes never collide. Files starting with `_` (`_common.py`) are helpers and are not run.

`run_all_approval_tests(executor)` runs the package and closes LIMA between tests, like the tool and model sweeps.

## Feature tests

`regression_tests/feature_tests/` covers LIMA 2.x features the tool sweep doesn't reach: switching to, restoring and closing another app's window, opening, reading and writing files, typing letters that aren't on the keyboard, screenshots, memories, `/new`, and the newer Settings and Subscription details.

These tests check the outcome itself instead of asking the vision model about screenshots:

- **Another app's window:** its state over Win32 (minimized, maximized, in front, closed).
- **Typed text:** Notepad's own text area over UI Automation. Never LIMA's window, log or console: they echo what LIMA meant to type, not what landed.
- **Files:** on disk.
- **What LIMA did and said:** its saved conversation (`<install folder>\data\conversations\<id>.json`, written at the end of every turn with each tool call and its result).

The background approver answers Yes to every action, as in the tool sweep. The package works like `approval_tests/`: one `test_*` file per feature, found by discovery, with a `RESULT_NAME` and a `run(executor)` that reports exactly one result. LIMA is closed after every test, so each starts with a fresh LIMA and a fresh conversation. Shared steps are in `feature_tests/_common.py`: `wait_for_turn_end`, `assistant_text`, `tool_calls`, `open_notepad`, `notepad_text`, `new_test_file_path`, plus the approval tests' `ensure_lima_ready` and `send_instruction`.

Every file a feature test creates starts with `lima-feature-test-`, and the test deletes it again. Tests that change LIMA's own data (memories) back the file up first and put it back afterwards.

## Project Structure

```
lima-testing-suite/
├── .gitignore                  # Excludes sensitive files from version control
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── main.py                     # Main entry point
├── globals.py                  # Suite tunables (vision model, sleeps, AI wait, audio window)
├── run_regression_tests.bat    # Windows batch launcher
├── lima_auth.py                # Authentication for the suite
├── check_auth.py               # Quick auth-setup verification before a run
├── preflight.py                # Environment readiness checks before a run
├── secret_config.py.example    # Example config: copy to secret_config.py, fill in one option
└── regression_tests/
    ├── lima_process_manager.py     # LIMA application lifecycle management
    ├── lima_test_executor.py       # Test execution logic
    ├── lima_test_reporter.py       # Result reporting
    ├── lima_test_utils.py          # Utility functions
    ├── lima_tool_tests.py          # AI tool test scenarios
    ├── lima_model_tests.py         # Base AI model-coverage sweep
    ├── lima_voice_tests.py         # TTS voice-coverage sweep
    ├── lima_settings_tests.py      # Settings hotkey-reconfigure regression guard
    ├── lima_action_approver.py     # Answers LIMA's approval popups (auto, or per-test)
    └── approval_tests/             # Approval-loop tests: one test_*.py file per scenario
        ├── __init__.py             # Discovery + run_all_approval_tests
        ├── _common.py              # Shared steps (LIMA ready, apps, instruction, cleanup)
        └── test_10_deny_stops_action.py  # Approval: No stops the action
    └── feature_tests/              # LIMA 2.x feature tests: one test_*.py file per feature
        ├── __init__.py             # Discovery + run_all_feature_tests
        └── _common.py              # Shared checks (windows, Notepad, files, saved conversation)
```

## Security Notes

- **Never commit sensitive files:** `secret_config.py` is excluded from version control.
- **Keep credentials out of code:** keep `OPEN_ROUTER_API_KEY`, `FIREBASE_API_KEY` and `AUTH_URL` in the gitignored `secret_config.py` (or in env vars), never in committed code. This repo is public.
- **Limit a pasted OpenRouter key:** give it a credit limit on OpenRouter, so a leaked key can only spend that much.

## Troubleshooting

### "AUTH_URL is not set"
No credentials are configured. In `secret_config.py`, either paste an `OPEN_ROUTER_API_KEY` (option 1), or fill in `AUTH_URL` and `FIREBASE_API_KEY` (option 2). Env vars work too.

### "No LIMA sign-in session found"
Sign into LIMA first; the suite uses that session.

### "FIREBASE_API_KEY is not set"
Fill in `FIREBASE_API_KEY` in `secret_config.py` (or set the `LIMA_FIREBASE_API_KEY` env var).

### "Could not refresh the LIMA session"
Your session expired or was revoked. Open LIMA, sign in again, then re-run.

### "Authentication failed" / no OpenRouter key returned
- Check `AUTH_URL` points at the correct auth server
- Confirm your LIMA account is provisioned on that server
- Ensure network connectivity to the auth server

## License

This testing suite is part of LIMA Screen Reader. Contact Roscommon Systems for licensing information.
