from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PORT = "5173"
HOST = "127.0.0.1"
ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    package_json = FRONTEND_DIR / "package.json"
    if not package_json.exists():
        return fail(f"Cannot find frontend package.json: {package_json}")

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        return fail("npm was not found. Install Node.js first.")

    if not (FRONTEND_DIR / "node_modules").exists():
        print("Frontend dependencies are not installed.", file=sys.stderr)
        print(f"Run: cd /d {FRONTEND_DIR} && npm.cmd install", file=sys.stderr)
        return 1

    print(f"Starting BalanceAlpha frontend at http://{HOST}:{PORT}")
    command = [npm, "run", "dev", "--", "--port", PORT, "--strictPort"]
    try:
        return subprocess.call(command, cwd=FRONTEND_DIR)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
