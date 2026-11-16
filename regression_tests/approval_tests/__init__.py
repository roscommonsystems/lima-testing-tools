"""
LIMA approval tests
Tests for LIMA 2.x's step-through approval loop: when the app asks before an action, when it
waits, how a No ends the turn, what a replacement instruction does, and the ways the user can
answer (buttons, Y/N keys, the Ctrl+Alt+Y/N hotkeys).

Each test is one module in this package with a ``run(executor)`` function. Modules are found
by discovery (see ``lima_test_packages.py``, sorted by module name), so adding a test means
adding one file - no edits to this file or to the executor. Files are numbered
(``test_10_...``, ``test_20_...``) to keep the order stable; modules starting with an
underscore (``_common``) are shared helpers and are not run.
"""
