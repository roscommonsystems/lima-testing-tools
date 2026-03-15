# LIMA Testing Suite

A regression testing framework for LIMA Screen Reader.

## Overview

This testing suite automates functional testing of the LIMA Screen Reader application. It validates core functionality by launching the application, executing test scenarios, and verifying results through visual comparison.

## Prerequisites

- Windows operating system
- LIMA Screen Reader installed on your system
- Python 3.8 or higher
- Valid LIMA license key

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Authentication

Create a `lima_config.json` file in the project root with your authentication server URL and license key:

```json
{
    "auth_url": "https://your-auth-server.example.com/validate",
    "license_key": "YOUR_LICENSE_KEY_HERE"
}
```

> **Note:** Contact Roscommon Systems to obtain the authentication server URL and a valid license key.

> **Important:** Never commit `lima_config.json` to version control. This file is excluded via `.gitignore`.

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
├── lima_auth.py                # Authentication module
├── lima_config.json.example    # Example config file
└── regression_tests/
    ├── lima_regression_tests.py    # Regression tests entry point
    ├── lima_test_executor.py       # Test execution logic
    ├── lima_test_reporter.py       # Result reporting
    └── lima_test_utils.py          # Utility functions
```

## Security Notes

- **Never commit sensitive files:** `lima_config.json` contains your credentials and is excluded from version control.
- **License keys are personal:** Do not share your license key or include it in public repositories.
- **API keys are retrieved dynamically:** The authentication server provides API keys at runtime; they are never stored in code.

## Troubleshooting

### "Config file not found"
Create `lima_config.json` using the example file as a template.

### "license_key not found in config file"
Add your `license_key` to the `lima_config.json` file.

### "License validation failed"
- Verify your license key is correct and active
- Check that the `auth_url` in your config file is correct
- Ensure you have network connectivity to the authentication server

## License

This testing suite is part of LIMA Screen Reader. Contact Roscommon Systems for licensing information.