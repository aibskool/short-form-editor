#!/usr/bin/env python3
"""Run the pinned local renderer with its documented analytics opt-out enabled."""
import glob
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent


HEADLESS_CANDIDATES = (
    "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
    "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell",
    "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-mac*/headless_shell",
)


def installed_headless_shell():
    """A Chrome Headless Shell already on this machine (e.g. Playwright's), if any."""
    for pattern in HEADLESS_CANDIDATES:
        matches = sorted(glob.glob(os.path.expanduser(pattern)))
        for match in reversed(matches):
            if os.access(match, os.X_OK):
                return match
    return None


def no_telemetry_env():
    env = os.environ.copy()
    env["HYPERFRAMES_NO_TELEMETRY"] = "1"
    env["DO_NOT_TRACK"] = "1"
    # HyperFrames downloads its own browser when none is configured; offline or
    # locked-down machines can reuse an installed headless shell instead.
    if not env.get("PRODUCER_HEADLESS_SHELL_PATH"):
        shell = installed_headless_shell()
        if shell:
            env["PRODUCER_HEADLESS_SHELL_PATH"] = shell
    return env


def run(args, check=True):
    return subprocess.run([str(HERE / "node_modules/.bin/hyperframes"), *args],
                          env=no_telemetry_env(), check=check)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:], check=False).returncode)
