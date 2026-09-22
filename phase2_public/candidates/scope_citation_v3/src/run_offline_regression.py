"""Run both unittest cases and legacy function/main regression groups offline."""
from __future__ import annotations
import argparse
import ast
from contextlib import redirect_stdout, redirect_stderr
import importlib
import io
from pathlib import Path
import socket
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch
from experiment_integrity import utc_now, write_new_json, code_inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--optional-python-path", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = args.output.parent / "temporary_tests"
    temp_root.mkdir(exist_ok=True)
    tempfile.tempdir = str(temp_root)
    if args.optional_python_path:
        # Appended only: never replace the original numpy/ML environment.
        sys.path.append(str(args.optional_python_path))
    sys.path.insert(0, str(root / "tests"))
    started = time.monotonic()
    records, captured = [], io.StringIO()
    def no_network(*args, **kwargs):
        raise RuntimeError("network_disabled_in_offline_regression")
    with patch.object(socket.socket, "connect", no_network), patch.object(socket, "create_connection", no_network):
        for path in sorted((root / "src").glob("*.py")):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        with redirect_stdout(captured), redirect_stderr(captured):
            for path in sorted((root / "tests").glob("test_*.py")):
                try:
                    module = importlib.import_module(path.stem)
                    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
                    if suite.countTestCases():
                        result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
                        records.append({"module": path.stem, "kind": "unittest", "tests": result.testsRun,
                                        "failures": len(result.failures), "errors": len(result.errors),
                                        "skipped": len(result.skipped), "passed": result.wasSuccessful()})
                    functions = [(name, value) for name, value in vars(module).items()
                                 if name.startswith("test_") and callable(value)]
                    if functions:
                        for name, function in functions:
                            try:
                                function()
                                records.append({"module": path.stem, "test": name, "kind": "function_group", "passed": True})
                            except Exception:
                                captured.write(traceback.format_exc())
                                records.append({"module": path.stem, "test": name, "kind": "function_group", "passed": False})
                    elif not suite.countTestCases() and callable(getattr(module, "main", None)):
                        code = module.main()
                        records.append({"module": path.stem, "kind": "legacy_main_group", "passed": code in (0, None)})
                except Exception:
                    captured.write(traceback.format_exc())
                    records.append({"module": path.stem, "kind": "import_or_execution_error", "passed": False})
    result = {"created_at": utc_now(), "offline": True, "provider_calls": 0,
              "scope": "engineering regression; not legal accuracy or expert validation",
              "elapsed_seconds": time.monotonic() - started, "python": sys.version,
              "code_inventory": code_inventory(root), "records": records,
              "unittest_count": sum(r.get("tests", 0) for r in records),
              "function_group_count": sum(r["kind"] == "function_group" for r in records),
              "legacy_main_group_count": sum(r["kind"] == "legacy_main_group" for r in records),
              "passed": all(r["passed"] for r in records), "log": captured.getvalue()}
    write_new_json(args.output, result)
    print({k: v for k, v in result.items() if k not in {"log", "records", "code_inventory"}}, flush=True)
    for record in records:
        if not record["passed"]:
            print(record, flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
