"""
LIMA Testing Suite - Global Tunables

The handful of values a developer is likely to change when running this suite. Everything
else (install locations, window titles, UI Automation names, per-test data) stays next to
the code that uses it.

Nothing here is secret - credentials live in the gitignored secret_config.py.
"""

# --- Vision verification (OpenRouter) --------------------------------------------------
# The suite's screenshot checks ask an OpenRouter-hosted model whether a tool worked.
# Any vision-capable OpenRouter model works here: the suite sends the screenshots as
# standard image_url content and reads back JSON, so nothing depends on one provider.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
VISION_MODEL = "deepseek/deepseek-v4.1-flash-1017"
VISION_TEMPERATURE = 0

# Reasoning effort for the vision judge: "minimal" | "low" | "medium" | "high". Sent as
# OpenRouter's generic "reasoning.effort" field; providers that don't support it ignore it.
# Thinking tokens are billed as output. None = omit the field and use the provider default.
VISION_REASONING_EFFORT = "low"

# --- Judgement checks (OpenRouter) ----------------------------------------------------
# Some outcomes can't be checked by code: whether LIMA's description of the screen is
# accurate, whether a summary is faithful to the page, whether a window's layout is broken.
# Those go to this model, which takes text and images. It is only used where no direct check
# (a file, a window's state, LIMA's saved conversation) exists. See regression_tests/lima_judge.py.
JUDGE_MODEL = "typesafe/jev-router"
JUDGE_TEMPERATURE = 0
# A judge call that errors or returns unusable JSON is tried this many times in total.
JUDGE_ATTEMPTS = 3

# --- Test runner ----------------------------------------------------------------------
# Most tests depend on what LIMA's AI model decides to do, which varies from run to run. A
# failed test is run again this many times in a fresh LIMA. A pass on a later attempt is
# reported as PASSED and marked "retried", with the first failure kept in its message, so an
# intermittent fault stays visible without failing the run. 0 = never retry.
RETRY_FAILED_TESTS = 1

# --- Practice page --------------------------------------------------------------------
# The mouse and keyboard tests act on a page the suite serves on this machine only
# (127.0.0.1). 0 = any free port. See regression_tests/lima_practice_page.py.
PRACTICE_PAGE_PORT = 0

# --- Timing ---------------------------------------------------------------------------
SLEEP_A = 1   # Single UI action (key press, click, focus)
SLEEP_B = 2   # Window state change (activate, maximize, restore)
SLEEP_C = 10  # App/dialog appear, post-submit, post-launch settle, between-test pause
SLEEP_D = 20  # LIMA process startup

# How long a tool test waits for LIMA's AI to finish before taking the AFTER screenshot.
AI_RESPONSE_WAIT_SECONDS = 30

# --- Audio detection ------------------------------------------------------------------
# How long audio checks listen for output after a TTS/tool command.
AUDIO_MAX_DURATION_S = 15
