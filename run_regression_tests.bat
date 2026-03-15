@echo off
setlocal enabledelayedexpansion

REM ==================================================
REM LIMA Testing Suite - Regression Test Runner
REM ==================================================
REM This script handles:
REM - Python environment detection
REM - Virtual environment creation/activation
REM - Dependency installation
REM - Configuration setup
REM - Test execution and results display
REM ==================================================

echo.
echo ==================================================
echo LIMA Testing Suite - Regression Test Runner
echo ==================================================
echo.

REM --------------------------------------------------
REM Step 1: Check if Python is installed
REM --------------------------------------------------
echo [1/6] Checking Python installation...
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ==================================================
    echo ERROR: Python Not Found
    echo ==================================================
    echo.
    echo Python is required to run the LIMA Testing Suite.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo After installing Python, run this script again.
    echo ==================================================
    echo.
    pause
    exit /b 1
)
echo       Python found.
echo.

REM --------------------------------------------------
REM Step 2: Check/Create virtual environment
REM --------------------------------------------------
echo [2/6] Checking virtual environment...
if exist ".venv" (
    echo       Virtual environment found.
) else (
    echo       Creating virtual environment...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to create virtual environment.
        echo Please ensure Python is properly installed with venv module.
        echo.
        pause
        exit /b 1
    )
    echo       Virtual environment created.
)
echo.

REM --------------------------------------------------
REM Step 3: Activate virtual environment
REM --------------------------------------------------
echo [3/6] Activating virtual environment...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to activate virtual environment.
    echo.
    pause
    exit /b 1
)
echo       Virtual environment activated.
echo.

REM --------------------------------------------------
REM Step 4: Install/Update dependencies
REM --------------------------------------------------
echo [4/6] Installing dependencies...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo WARNING: Some dependencies may have failed to install.
    echo Attempting to continue...
)
echo       Dependencies installed.
echo.

REM --------------------------------------------------
REM Step 5: Check/Create configuration
REM --------------------------------------------------
echo [5/6] Checking configuration...
if exist "lima_config.json" (
    echo       Configuration file found.
) else (
    echo.
    echo ==================================================
    echo LIMA Testing Suite - Configuration Required
    echo ==================================================
    echo.
    echo This appears to be your first run. Please provide
    echo your authentication details.
    echo.
    
    REM Prompt for auth server URL
    set /p AUTH_URL="Enter your authentication server URL: "
    if "!AUTH_URL!"=="" (
        echo.
        echo ERROR: Authentication server URL cannot be empty.
        echo.
        pause
        exit /b 1
    )
    
    REM Prompt for license key
    set /p LICENSE_KEY="Enter your license key: "
    if "!LICENSE_KEY!"=="" (
        echo.
        echo ERROR: License key cannot be empty.
        echo.
        pause
        exit /b 1
    )
    
    REM Create the config file
    echo {> lima_config.json
    echo     "auth_url": "!AUTH_URL!",>> lima_config.json
    echo     "license_key": "!LICENSE_KEY!">> lima_config.json
    echo }>> lima_config.json
    
    echo.
    echo       Configuration saved to lima_config.json
    echo ==================================================
    echo.
)
echo.

REM --------------------------------------------------
REM Step 6: Run tests
REM --------------------------------------------------
echo [6/6] Running regression tests...
echo.
echo ==================================================
echo.

python main.py
set TEST_RESULT=%ERRORLEVEL%

echo.
echo ==================================================
if %TEST_RESULT% EQU 0 (
    echo TEST RESULT: ALL TESTS PASSED
) else (
    echo TEST RESULT: SOME TESTS FAILED ^(Exit Code: %TEST_RESULT%^)
)
echo ==================================================
echo.
echo Test results have been saved to:
echo       regression_tests\test_results.json
echo.
echo Press any key to exit...
pause >nul
exit /b %TEST_RESULT%