"""
LIMA Testing Suite - Global Tunables

The handful of values a developer is likely to change when running this suite. Everything
else (install locations, window titles, UI Automation names, per-test data) stays next to
the code that uses it.

Nothing here is secret - credentials live in the gitignored secret_config.py.
"""

# --- Vision verification (OpenRouter) --------------------------------------------------
# The suite's screenshot checks ask an OpenRouter-hosted Gemini model whether a tool worked.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
VISION_MODEL = "google/gemini-3-flash-preview"
VISION_TEMPERATURE = 0

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
