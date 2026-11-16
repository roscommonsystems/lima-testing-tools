"""
LIMA feature tests
Tests for features added in LIMA 2.x that the tool sweep doesn't reach: switching to, restoring
and closing other windows, opening/reading/writing files, typing letters that aren't on the
keyboard, screenshots, memories, /new, and the newer Settings and Subscription details.

Unlike the tool sweep, these tests check the outcome directly - a window's state, a file on
disk, the text in Notepad, LIMA's saved conversation - instead of asking a vision model to
judge before/after screenshots. The background approver answers Yes to every action, as in the
tool sweep.

Each test is one module in this package with a ``run(executor)`` function and a
``RESULT_NAME``. Modules are found by discovery (see ``lima_test_packages.py``, sorted by
module name), so adding a test means adding one file - no edits to this file or to the
executor. Files are numbered (``test_10_...``, ``test_20_...``) to keep the order stable;
modules starting with an underscore (``_common``) are shared helpers and are not run.
"""
