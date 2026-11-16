"""
Backing up and restoring LIMA's data around a test.

Some features can only be tested by changing what LIMA keeps in its data folder: a setting in
config.json, a memory, the saved conversations, a connected app. A test that does so must
leave the folder exactly as it found it, or it changes every later test in the run (a leftover
memory rides along in every later prompt) and, on a machine someone also uses, their LIMA.

The pattern for such a test:

    backup = backup_data(executor, "config.json", "conversations")
    try:
        seed_config(executor, max_agent_loops=10)
        ... the test ...
    finally:
        cleanup_note = close_lima_and_restore(executor, backup)
    if cleanup_note:
        passed = False
        message += cleanup_note

LIMA is closed before anything is put back, because it keeps some of this in memory and writes
it out again (the conversation on exit, memories on every change), which would overwrite the
restore. A restore that fails is a failed test even when the feature worked: the run is no
longer clean, and the result has to say so.
"""

import json
import os
import shutil
import tempfile
import time

from lima_test_utils import SLEEP_A, SLEEP_B

# Prefix of the temporary files and folders made here, so a leftover is easy to recognise.
BACKUP_PREFIX = ".lima-test-backup-"


def lima_data_dir(executor):
    """LIMA's data folder. LIMA runs with its install folder as the working directory."""
    data_dir = os.path.join(executor.process_manager.install_path or "", "data")
    return data_dir


def config_path(executor):
    path = os.path.join(lima_data_dir(executor), "config.json")
    return path


class FileBackup:
    """The exact bytes of one file before a test, and how to put them back."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.existed = os.path.exists(path)
        self.original = b""
        if self.existed:
            with open(path, "rb") as handle:
                self.original = handle.read()
            print(f"  Backed up {self.name} ({len(self.original)} bytes)")
        else:
            print(f"  {self.name} does not exist yet; cleanup will delete anything created")

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
                    reason = f"{self.path} still exists after cleanup"
                    return False, reason
                return True, None

            folder = os.path.dirname(self.path)
            os.makedirs(folder, exist_ok=True)
            # Same-directory temporary file so os.replace stays atomic, and on Windows it must
            # be closed before the replace.
            with tempfile.NamedTemporaryFile(mode="wb", dir=folder, prefix=BACKUP_PREFIX,
                                             suffix=".tmp", delete=False) as handle:
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
                reason = (f"restored {self.name} is {len(restored)} bytes, not the "
                          f"original {len(self.original)}")
                return False, reason
            return True, None
        except OSError as error:
            reason = f"could not restore {self.name}: {error}"
            return False, reason


def _folder_contents(folder):
    """Every file under folder as {relative path: bytes}."""
    contents = {}
    for root, _directories, file_names in os.walk(folder):
        for file_name in file_names:
            file_path = os.path.join(root, file_name)
            with open(file_path, "rb") as handle:
                contents[os.path.relpath(file_path, folder)] = handle.read()
    return contents


class FolderBackup:
    """A copy of one folder (conversations, a connected app's saved sign-in) before a test."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.existed = os.path.isdir(path)
        self.copy_root = None
        self.copy_path = None
        if self.existed:
            self.copy_root = tempfile.mkdtemp(prefix=BACKUP_PREFIX)
            self.copy_path = os.path.join(self.copy_root, self.name)
            shutil.copytree(path, self.copy_path)
            print(f"  Backed up the {self.name} folder ({len(_folder_contents(self.copy_path))} file(s))")
        else:
            print(f"  The {self.name} folder does not exist yet; cleanup will delete anything created")

    def restore(self):
        """
        Put the folder back exactly as it was: same files, same bytes, nothing extra.

        Returns:
            (True, None) when the folder is back, or (False, reason).
        """
        try:
            if os.path.isdir(self.path):
                shutil.rmtree(self.path)
            if not self.existed:
                if os.path.exists(self.path):
                    reason = f"{self.path} still exists after cleanup"
                    return False, reason
                return True, None

            shutil.copytree(self.copy_path, self.path)
            if _folder_contents(self.path) != _folder_contents(self.copy_path):
                reason = f"the restored {self.name} folder does not match its backup"
                return False, reason
            shutil.rmtree(self.copy_root, ignore_errors=True)
            return True, None
        except OSError as error:
            # The copy is deliberately kept when the restore failed, so nothing is lost.
            reason = (f"could not restore the {self.name} folder: {error}. "
                      f"Its backup is still at {self.copy_path}")
            return False, reason


class DataBackup:
    """The backups one test took, restored together."""

    def __init__(self, backups):
        self.backups = backups

    def restore(self):
        """Restore every item; return the reasons for any that could not be put back."""
        failures = []
        for backup in self.backups:
            restored, reason = backup.restore()
            if not restored:
                failures.append(reason)
        return failures


def backup_data(executor, *names):
    """
    Back up items in LIMA's data folder by name, e.g. "config.json", "conversations".

    A name that exists as a folder is backed up as a folder; anything else as a file, so a
    file the test is about to create for the first time is deleted again afterwards. A folder
    that doesn't exist yet must be named with a trailing slash ("mcp_credentials/"), because
    nothing on disk says it is going to be one.
    """
    backups = []
    for name in names:
        path = os.path.join(lima_data_dir(executor), name.rstrip("/\\"))
        is_folder = os.path.isdir(path) or name.endswith(("/", "\\"))
        backups.append(FolderBackup(path) if is_folder else FileBackup(path))
    data_backup = DataBackup(backups)
    return data_backup


def close_lima_and_restore(executor, data_backup):
    """
    Close LIMA, then put back everything in data_backup.

    Returns:
        str: "" when everything is back; otherwise a note to append to the test's message,
        starting with " CLEANUP FAILED". The caller must fail the test when it is not empty.
    """
    note = ""
    close_error = executor.process_manager.close()
    if close_error:
        note += f" {close_error}"
    # LIMA writes on its way out (the active conversation); let that finish before restoring.
    time.sleep(SLEEP_A)
    if data_backup is None:
        return note
    failures = data_backup.restore()
    if failures:
        reasons = "; ".join(failures)
        note += (f" CLEANUP FAILED: {reasons}. LIMA's data folder is not as this test found it, "
                 f"which can change every later test in the run.")
        print(f"  ! {reasons}")
    else:
        print("  Restored LIMA's data")
    return note


def read_config(executor):
    """LIMA's config.json as a dict ({} when it is missing or unreadable)."""
    try:
        with open(config_path(executor), "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        config = {}
    return config


def seed_config(executor, **settings):
    """
    Set keys in LIMA's config.json for one test, with LIMA closed.

    LIMA is closed first: it reads config.json at startup, and a running LIMA that saves its
    own settings would write over the seeded values. Back config.json up before calling this
    (backup_data) so the user's settings come back afterwards.
    """
    close_error = executor.process_manager.close()
    if close_error:
        print(f"  ! {close_error}")
    time.sleep(SLEEP_B)
    config = read_config(executor)
    config.update(settings)
    os.makedirs(lima_data_dir(executor), exist_ok=True)
    with open(config_path(executor), "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=4)
    print(f"  Seeded config.json: {settings}")
