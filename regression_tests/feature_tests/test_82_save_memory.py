"""
Feature: Save a memory.

LIMA 2.1.0.5 keeps persistent memories in ``<install folder>\\data\\memories.json``
(memory_store.py: ``_MEMORIES_FILE_PATH``, a numbered envelope of
``{"next_memory_number": n, "memories": [{memory_number, memory_content}, ...]}`` capped at
``MAX_MEMORIES = 20``). The ``create_memory`` tool (available_tools.py ~L271, tools.py ~L1549)
appends one record and runs without asking (llm_tts_worker.py ``_AUTO_RUN_TOOLS``), so a spoken
"remember this" is saved in the same turn.

Why the file: a memory that lands in the model's prompt but not on disk is gone at the next
launch, and a memory saved with the wrong text is worse than none. The saved file is the only
durable record, so the test reads it directly and looks for an unguessable code word.

Cleanup matters as much as the check. Every saved memory rides along in every later prompt, so
a leftover would pollute the whole rest of the run. The test snapshots the exact bytes of
memories.json before it starts and, in ``finally``, closes LIMA *first* (memory_store keeps the
shared dict in ``globals.short_term_memory``, and LIMA can still be holding the file), then
writes the snapshot back atomically or deletes the file when it did not exist. The restore is
verified by reading the bytes back; a restore that fails is reported in the result message and
fails the test, because the run would otherwise go on with a memory it should not have.
"""

import json
import os
import tempfile
import time

from lima_test_utils import TEST_PASSED, TEST_FAILED, SLEEP_A
from feature_tests import _common

RESULT_NAME = "Feature: Save a memory"

# "Remember this for later" plus an explicit code word: the tool needs memory_content, and a
# specific word gives the test something the model could not invent or already know.
INSTRUCTION_TEMPLATE = "Remember this for later: my test code word is {code_word}."

# create_memory runs before the reply, so the file is normally written by the time the turn
# ends. The extra wait covers a slow fsync/antivirus on the VM.
MEMORY_SAVE_TIMEOUT = 20.0


def _memory_file_path(executor):
    """memories.json inside LIMA's install folder (LIMA runs with it as the working directory)."""
    return os.path.join(_common.lima_data_dir(executor), "memories.json")


class MemoryFileBackup:
    """The exact bytes of memories.json before the test, and how to put them back."""

    def __init__(self, path):
        self.path = path
        self.existed = os.path.exists(path)
        self.original = b""
        if self.existed:
            with open(path, "rb") as handle:
                self.original = handle.read()
            print(f"  Backed up memories.json ({len(self.original)} bytes)")
        else:
            print("  memories.json does not exist yet; cleanup will delete anything created")

    def restore(self):
        """
        Put the file back exactly as it was.

        Returns:
            (True, None) when the file is back, or (False, reason).
        """
        try:
            if not self.existed:
                if os.path.exists(self.path):
                    os.remove(self.path)
                if os.path.exists(self.path):
                    return False, f"{self.path} still exists after cleanup"
                return True, None

            folder = os.path.dirname(self.path)
            os.makedirs(folder, exist_ok=True)
            # Same-directory temporary file so os.replace stays atomic, and on Windows it must
            # be closed before the replace.
            with tempfile.NamedTemporaryFile(mode="wb", dir=folder,
                                             prefix=".lima-feature-test-", suffix=".tmp",
                                             delete=False) as handle:
                temporary_path = handle.name
                handle.write(self.original)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temporary_path, self.path)
            finally:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)

            with open(self.path, "rb") as handle:
                restored = handle.read()
            if restored != self.original:
                return False, (f"restored memories.json is {len(restored)} bytes, not the "
                               f"original {len(self.original)}")
            return True, None
        except OSError as error:
            return False, f"could not restore memories.json: {error}"


def _memory_contents(path):
    """
    Every stored memory's text, or None while the file is missing or unreadable.

    Handles both the numbered envelope (v2.1.0.5) and the older list of
    ``{memory_topic, memory_content}`` records, because a machine upgraded from an older build
    may still be migrated on the first write.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return None
    if isinstance(document, dict):
        entries = document.get("memories") or []
        return [str(entry.get("memory_content", "")) for entry in entries
                if isinstance(entry, dict)]
    if isinstance(document, list):
        return [f"{entry.get('memory_topic', '')}: {entry.get('memory_content', '')}"
                for entry in document if isinstance(entry, dict)]
    return None


def _wait_for_code_word(path, code_word, timeout):
    """
    (entries, found entry) once an entry contains the code word, or (last entries, None).

    Searching every entry, not just the last, because LIMA may add the memory as one of several
    calls in a turn and the number it lands on is the store's choice.
    """
    deadline = time.time() + timeout
    entries = []
    while True:
        current = _memory_contents(path)
        if current is not None:
            entries = current
            for entry in current:
                if _common.contains_code_word(entry, code_word):
                    return entries, entry
        if time.time() >= deadline:
            return entries, None
        time.sleep(0.5)


def _run_case(executor, backup):
    """Do the scenario; return (passed, message)."""
    code_word = _common.make_code_word()
    instruction = INSTRUCTION_TEMPLATE.format(code_word=code_word)

    # Another LIMA-ready call immediately before typing: send_instruction types into the chat box.
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be brought to the front to take the instruction"

    _common.send_instruction(instruction)
    path, after = _common.wait_for_turn_end(executor, instruction)
    if path is None:
        return False, (f"LIMA never saved a conversation for {instruction!r}, so the turn did not "
                       f"reach the AI; {_common.describe_turn(after)}")

    entries, found = _wait_for_code_word(backup.path, code_word, MEMORY_SAVE_TIMEOUT)
    if found is None:
        seen = "; ".join(f"memory {index + 1}: {entry[:120]!r}"
                         for index, entry in enumerate(entries[:5])) or "no memories on disk"
        return False, (f"memories.json does not contain the code word {code_word!r} within "
                       f"{MEMORY_SAVE_TIMEOUT:.0f}s of {instruction!r}. Memories on disk: {seen}. "
                       f"{_common.describe_turn(after)}")

    total = len(entries)
    return True, (f"'{instruction}' was saved: memories.json now holds {total} memory record(s) "
                  f"and one contains {code_word!r} ({found[:120]!r}). The file is restored to its "
                  f"previous contents afterwards.")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    backup = None
    cleanup_note = ""
    try:
        if not _common.ensure_lima_ready(executor):
            passed, message = False, ("LIMA was not running with its window ready, so the test "
                                      "could not run")
        else:
            # Snapshot after the launch: install_path (and so the data folder) is known only then.
            backup = MemoryFileBackup(_memory_file_path(executor))
            passed, message = _run_case(executor, backup)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # Close LIMA before touching the file: it caches memories and could write over a restore.
        close_error = executor.process_manager.close()
        if close_error:
            cleanup_note += f" {close_error}"
        if backup is not None:
            restored, reason = backup.restore()
            if restored:
                print("  Restored memories.json")
            else:
                # A memory left on disk rides along in every later prompt, so this is a failed
                # test even when the feature itself worked: the run is no longer clean.
                passed = False
                cleanup_note += (f" CLEANUP FAILED: {reason}. A memory left behind pollutes "
                                 f"every later prompt in this run.")
                print(f"  ! {reason}")
        time.sleep(SLEEP_A)

    if cleanup_note:
        message += cleanup_note
    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
