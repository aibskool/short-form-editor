#!/usr/bin/env python3
"""Run the pinned local renderer with its documented analytics opt-out enabled."""
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent


def no_telemetry_env():
    env = os.environ.copy()
    env["HYPERFRAMES_NO_TELEMETRY"] = "1"
    env["DO_NOT_TRACK"] = "1"
    return env


def run(args, check=True):
    return subprocess.run([str(HERE / "node_modules/.bin/hyperframes"), *args],
                          env=no_telemetry_env(), check=check)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:], check=False).returncode)
