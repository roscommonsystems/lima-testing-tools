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

The suite uses your existing LIMA sign-in to obtain the API keys it needs, so setup is:

1. **Sign into LIMA once** beforehand.
2. **Provide the Firebase Web API key** one of two ways:
   - copy `secret_config.py.example` to `secret_config.py` and fill in `FIREBASE_API_KEY`, **or**
   - set the `LIMA_FIREBASE_API_KEY` environment variable.
3. **Create `lima_config.json`** by copying `lima_config.json.example` and setting `auth_url`.

Verify the setup before a full run (~5 seconds):

```bash
python check_auth.py
```

A green `OPEN_ROUTER_API_KEY: present ... Ready to run` means you're set.

> **Note:** Your LIMA account must be provisioned on the auth server for it to return keys.

> **Important:** Never commit `lima_config.json` or `secret_config.py` — both are excluded via `.gitignore`.

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

## Project Structure

```
lima-testing-suite/
├── .gitignore                  # Excludes sensitive files from version control
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── main.py                     # Main entry point
├── run_regression_tests.bat    # Windows batch launcher
├── lima_auth.py                # Authentication for the suite
├── check_auth.py               # Quick auth-setup verification before a run
├── lima_config.json.example    # Example config (auth_url only)
├── secret_config.py.example    # Example Firebase Web API key file (copy to secret_config.py)
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

- **Never commit sensitive files:** `lima_config.json` and `secret_config.py` are excluded from version control.
- **Keep the Firebase Web API key out of code:** keep it in the gitignored `secret_config.py` (or an env var), never in committed code.
- **API keys are retrieved dynamically:** they are provided at runtime, never stored in code.

## Troubleshooting

### "Config file not found"
Create `lima_config.json` from `lima_config.json.example`.

### "No LIMA sign-in session found"
Sign into LIMA first; the suite uses that session.

### "LIMA_FIREBASE_API_KEY is not set"
Create `secret_config.py` from `secret_config.py.example` (or set the env var).

### "Could not refresh the LIMA session"
Your session expired or was revoked. Open LIMA, sign in again, then re-run.

### "Authentication failed" / no OpenRouter key returned
- Check `auth_url` points at the correct auth server
- Confirm your LIMA account is provisioned on that server
- Ensure network connectivity to the auth server

## License

This testing suite is part of LIMA Screen Reader. Contact Roscommon Systems for licensing information.