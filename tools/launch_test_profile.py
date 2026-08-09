"""Launch an ISOLATED Chrome for action-path testing.

WHY THIS EXISTS
---------------
Two properties of the user's everyday Chrome make it unusable as a test target
for the action path, and neither is fixable from inside the extension:

  1. Password managers (Passbolt here) inject a chrome-extension:// iframe into
     login pages. Chrome then refuses chrome.debugger.attach for the WHOLE tab,
     so TRUSTED INPUT is unavailable on exactly the forms worth testing. See
     CLAUDE.md limitation #12 — measured, not theorised.
  2. It is signed into real Gmail / Slack / Linear / Jira / Chargebee / admin
     dashboards. An agent testing "submit this form" there can do irreversible
     damage to real work.

A throwaway profile solves both at once: no password manager, no real sessions.

USAGE
-----
    .venv\\Scripts\\python.exe tools/launch_test_profile.py
    .venv\\Scripts\\python.exe tools/launch_test_profile.py --url https://www.saucedemo.com/

The profile lives in temp/test-profile/ and is disposable — delete it to reset.
Pass --fresh to delete and recreate it before launching.

ONE MANUAL STEP REMAINS: open the extension's side panel, paste BRIDGE_TOKEN
from .env, and click Save & Connect. Chrome gives no supported way to preseed
chrome.storage for an unpacked extension, so this cannot be automated. It is
once per profile, not once per run — the token persists until you --fresh.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"
PROFILE = ROOT / "temp" / "test-profile"

# Ordered by how likely each is to be the user's real install.
CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chrome.exe",
]


def find_chrome() -> str:
    for c in CANDIDATES:
        if c and os.path.isfile(c):
            return c
    which = shutil.which("chrome") or shutil.which("chrome.exe")
    if which:
        return which
    raise SystemExit(
        "Could not find chrome.exe. Pass --chrome <path> explicitly.\n"
        "Checked:\n  " + "\n  ".join(CANDIDATES)
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="about:blank", help="page to open on launch")
    ap.add_argument("--chrome", default=None, help="path to chrome.exe")
    ap.add_argument("--fresh", action="store_true", help="delete the profile first")
    args = ap.parse_args()

    if not EXT.is_dir():
        raise SystemExit(f"extension/ not found at {EXT}")

    if args.fresh and PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
        print(f"deleted {PROFILE}")
    PROFILE.mkdir(parents=True, exist_ok=True)

    chrome = args.chrome or find_chrome()

    flags = [
        chrome,
        f"--user-data-dir={PROFILE}",
        f"--load-extension={EXT}",
        # --load-extension is ignored on newer Chrome unless this is also passed;
        # without it the browser opens with NO extension and the failure looks
        # like a bridge problem rather than a launch-flag problem.
        "--disable-features=DisableLoadExtensionCommandLineSwitch",
        "--no-first-run",
        "--no-default-browser-check",
        # Keep the profile clean: no sync, no signin prompts, no imported state.
        "--disable-sync",
        "--disable-background-networking",
        args.url,
    ]

    print(f"chrome   : {chrome}")
    print(f"profile  : {PROFILE}")
    print(f"extension: {EXT}")
    print()
    subprocess.Popen(flags, close_fds=True)
    print("Launched. Remaining manual step (once per profile):")
    print("  1. open the ChromeBridge side panel")
    print("  2. paste BRIDGE_TOKEN from .env")
    print("  3. Save & Connect")
    print()
    print("This profile has NO password manager, so trusted input (CDP) works on")
    print("login forms here — the thing the everyday profile cannot test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
