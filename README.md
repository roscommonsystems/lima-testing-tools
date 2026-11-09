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
    └── lima_settings_tests.py      # Settings hotkey-reconfigure regression guard
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
