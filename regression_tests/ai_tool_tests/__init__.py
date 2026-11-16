"""
LIMA AI tool tests
Tests for the tools LIMA's AI calls to act on the computer: clicking, moving the mouse, typing
and pressing keys.

Each test asks LIMA to do one thing to the practice page (``lima_practice_page.py``) and then
reads the event the page recorded: which button was clicked, which key arrived, what a field
holds. That is the outcome itself, so no model is asked to judge a screenshot.

The instruction is sent the way a keyboard user sends one from another program: the quick
input hotkey opens LIMA's Ask Lima popup over the page, and when it closes the page is in
front again, so the page is what LIMA sees and acts on.

Modules are found by discovery (see ``lima_test_packages.py``, sorted by module name). Most
are tables: one row per button action, per key, so every row is its own result in its own
fresh LIMA. Modules starting with an underscore (``_common``) are shared helpers.
"""
