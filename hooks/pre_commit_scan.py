"""Pre-commit scanner: block sensitive developer output from being committed.

Runs before every commit (see hooks/pre-commit and the activation note in the README).
It inspects the STAGED content of each added/modified file and blocks the commit when it
finds:

  * a local absolute path that embeds a developer's machine/username
    (C:\\Users\\<name>\\..., /home/<name>/..., /Users/<name>/...) - this is how stray pip
    output and tool-config files leaked into the repo before; or
  * a credential-shaped string (private-key blocks, Google/Firebase API keys, AWS/Slack
    tokens).

Configuration is the constants below - edit those, not the code. To bypass the check for a
single commit (rarely needed, e.g. a genuine false positive), run:  git commit --no-verify
"""

import re
import subprocess
import sys

# --- Configuration (edit these) ------------------------------------------------------

# Path prefixes (relative to repo root, forward slashes) skipped entirely. The hooks
# folder is skipped so the example patterns in this very file can't block a commit.
SKIP_PREFIXES = (
    "hooks/",
)

# Specific files never scanned (repo-relative, forward slashes).
SKIP_FILES = set()

# Patterns that must NOT appear in committed content: (label, compiled regex).
FORBIDDEN_PATTERNS = [
    ("local Windows user path", re.compile(r"[a-z]:[\\/]{1,2}users[\\/]{1,2}[^\\/\s\"',]+", re.IGNORECASE)),
    ("local macOS user path", re.compile(r"/Users/[^/\s\"']+/")),
    ("local Linux home path", re.compile(r"/home/[^/\s\"']+/")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Google/Firebase API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
]

# A staged line containing any of these substrings is exempt (placeholders, etc.).
LINE_ALLOWLIST = (
    "your Firebase Web API key here",
)

# Skip blobs larger than this, or containing NUL bytes (treated as binary).
MAX_BYTES = 2 * 1024 * 1024

# -------------------------------------------------------------------------------------


def staged_files():
    """Repo-relative paths of files added/copied/modified in the index."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def staged_blob(path):
    """Staged (index) content of path as text, or None if binary/oversized/unreadable."""
    res = subprocess.run(["git", "show", f":{path}"], capture_output=True)
    if res.returncode != 0:
        return None
    data = res.stdout
    if len(data) > MAX_BYTES or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def is_skipped(path):
    return path in SKIP_FILES or any(path.startswith(p) for p in SKIP_PREFIXES)


def scan():
    findings = []
    for path in staged_files():
        if is_skipped(path):
            continue
        content = staged_blob(path)
        if content is None:
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            if any(tok in line for tok in LINE_ALLOWLIST):
                continue
            for label, pattern in FORBIDDEN_PATTERNS:
                match = pattern.search(line)
                if match:
                    findings.append((path, lineno, label, match.group(0)))
    return findings


def main():
    try:
        findings = scan()
    except subprocess.CalledProcessError as exc:
        print(f"[pre-commit] could not inspect staged files: {exc}", file=sys.stderr)
        return 1

    if not findings:
        return 0

    print("\nCOMMIT BLOCKED - possible sensitive content in staged files:\n")
    for path, lineno, label, snippet in findings:
        shown = snippet if len(snippet) <= 60 else snippet[:57] + "..."
        print(f"  {path}:{lineno}  [{label}]  {shown}")
    print("\nRemove or redact the above, then re-stage and commit.")
    print("If it is a genuine false positive, commit with:  git commit --no-verify\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
