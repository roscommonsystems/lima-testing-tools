"""
check_auth.py - quick verification that the suite can authenticate for LIMA 1.9.0.5+.

Confirms the suite can obtain OPEN_ROUTER_API_KEY from the auth server by reusing your
signed-in LIMA session, WITHOUT running the full regression suite. Use it to verify setup
before a run so a misconfiguration fails in seconds instead of mid-run.

Prerequisites:
  1. LIMA 1.9.0.5+ installed and signed in with your Google account.
  2. The Firebase Web API key provided via the LIMA_FIREBASE_API_KEY environment variable
     OR a gitignored secret_config.py on the path (FIREBASE_API_KEY = "...") - the same
     file the LIMA client uses, so a LIMA dev checkout already has it.
  3. lima_config.json contains the dev auth server URL (see lima_config.json.example).

Run (from the project root, inside the venv):
  python check_auth.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lima_auth import LimaAuth


def main():
    result = LimaAuth().validate_license()
    if not isinstance(result, dict):
        print("X Unexpected result:", result)
        return 1
    if result.get("error"):
        print("X Auth failed:", result["error"])
        return 1

    keys = result.get("api_keys", {})
    open_router_key = keys.get("OPEN_ROUTER_API_KEY")
    print("valid:", result.get("valid"))
    print("OPEN_ROUTER_API_KEY:",
          f"present (length {len(open_router_key)})" if open_router_key else "MISSING")
    print("other keys present:", {k: bool(v) for k, v in keys.items()})

    if open_router_key:
        print("\nOK - the suite can authenticate via your LIMA session. Ready to run.")
        return 0
    print("\nX No OpenRouter key returned - is your account provisioned on this auth server?")
    return 1


if __name__ == "__main__":
    sys.exit(main())
