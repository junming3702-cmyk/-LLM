"""One-command, public-data-only regression for the active Phase-2 code.

Creates an ignored local virtual environment, installs requirements, and runs
the active core and full-bundle fixture tests. It never calls an LLM, OCR API,
external legal provider, or private QX30 file. This is a functional regression,
not a reproduction of historical retrieval or legal-accuracy metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
TESTS = ROOT / "tests"
BUNDLE = ROOT / "candidates" / "full_bundle_review_v01"
REQUIREMENTS = ROOT / "requirements.txt"
VENV = ROOT / ".venv"


def run(args: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable,
                        help="Base Python, or test Python with --no-install")
    parser.add_argument("--no-install", action="store_true",
                        help="Use --python with already installed requirements; do not create a venv")
    options = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required")
    if not REQUIREMENTS.is_file():
        parser.error("requirements.txt is missing")

    if options.no_install:
        python = options.python
    else:
        if not venv_python().is_file():
            run([options.python, "-m", "venv", str(VENV)])
        python = str(venv_python())
        run([python, "-m", "pip", "install", "-r", str(REQUIREMENTS)])

    names = sorted(path.stem for path in TESTS.glob("test_*.py"))
    if not names:
        parser.error("no core tests found")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(TESTS)))
    prompt = ROOT / "prompts" / "system_prompt_final.md"
    print("active_prompt_sha256=" + hashlib.sha256(prompt.read_bytes()).hexdigest(),
          flush=True)
    print(f"Running {len(names)} active core test modules (offline).", flush=True)
    run([python, "-m", "unittest", *names, "-q"], env=env)

    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(BUNDLE)))
    print("Running full-bundle fixture tests (offline).", flush=True)
    run([python, "-m", "unittest", "discover", "-s", str(BUNDLE),
         "-p", "test_*.py", "-q"], env=env)
    print("PASS: public offline regression. No private case, API, or model weight used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
