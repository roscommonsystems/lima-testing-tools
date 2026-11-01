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
