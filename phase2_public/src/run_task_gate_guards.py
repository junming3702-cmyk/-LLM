"""Run public unit guards including legacy standalone tests; no provider calls."""
from argparse import ArgumentParser
import importlib.util
import inspect
import io
from pathlib import Path
import sys
import unittest
import socket
import faulthandler
from experiment_integrity import write_new_json, file_digest, utc_now

def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from replay_task_gate_v2 import offline_only
    socket.create_connection=offline_only
    socket.socket.connect=offline_only
    faulthandler.dump_traceback_later(45,repeat=True)
    tests=Path(__file__).resolve().parents[1]/'tests'
    sys.path.insert(0,str(tests))
    suite=unittest.TestSuite();files=sorted(tests.glob('test_*.py'))
    for path in files:
        print('Loading',path.name,flush=True)
        spec=importlib.util.spec_from_file_location(path.stem,path)
        module=importlib.util.module_from_spec(spec);sys.modules[path.stem]=module;spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for name,fn in vars(module).items():
            if name.startswith('test_') and inspect.isfunction(fn) and not inspect.signature(fn).parameters:
                suite.addTest(unittest.FunctionTestCase(fn))
    log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    payload={'created_at':utc_now(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'skipped':len(result.skipped),'successful':result.wasSuccessful(),'log':log.getvalue(),
             'test_hashes':{p.name:file_digest(p) for p in files},
             'coverage':'phase2_public/tests; does not include experiments subfolder suites'}
    write_new_json(args.output,payload)
    faulthandler.cancel_dump_traceback_later()
    print({k:v for k,v in payload.items() if k not in ('log','test_hashes')})
    if not result.wasSuccessful():print(log.getvalue())
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
