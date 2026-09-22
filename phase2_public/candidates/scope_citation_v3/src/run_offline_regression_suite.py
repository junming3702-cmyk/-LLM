"""Run unittest classes and plain test functions, with transport disabled."""
from pathlib import Path
import argparse, hashlib, importlib, inspect, io, json, socket, sys, tempfile, time, unittest

def deny_network(*args, **kwargs):
    raise RuntimeError('Network disabled for offline regression')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();a.package=a.package.resolve();a.output=a.output.resolve()
    if a.output.exists():raise FileExistsError('Use a fresh output directory')
    a.output.mkdir(parents=True);(a.output/'temp').mkdir();tempfile.tempdir=str(a.output/'temp')
    sys.dont_write_bytecode=True
    socket.socket.connect=deny_network;socket.create_connection=deny_network
    sys.path[:0]=[str(a.package/'src'),str(a.package/'tests')]
    files=[*sorted((a.package/'src').glob('*.py')),*sorted((a.package/'tests').glob('*.py')),*sorted((a.package/'prompts').glob('*.md'))]
    hashes={str(p.relative_to(a.package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    suite=unittest.TestSuite();imports=[]
    for path in sorted((a.package/'tests').glob('test_*.py')):
        module=importlib.import_module(path.stem);imports.append(path.name)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for name,func in inspect.getmembers(module,inspect.isfunction):
            if name.startswith('test_') and func.__module__==module.__name__:
                if inspect.signature(func).parameters:raise ValueError('Unregistered test fixture: '+name)
                suite.addTest(unittest.FunctionTestCase(func,description=module.__name__+'.'+name))
    log=io.StringIO();tick=time.monotonic();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'successful':result.wasSuccessful(),'elapsed_seconds':time.monotonic()-tick,'network_calls':0,
            'test_modules':imports,'source_hashes':hashes,'test_unit':'test methods/function groups; subcases not independent samples',
            'failures_detail':[(str(t),s) for t,s in result.failures+result.errors]}
    report['source_hashes_preserved']=all(hashlib.sha256((a.package/path).read_bytes()).hexdigest()==h for path,h in hashes.items())
    (a.output/'test_log.txt').write_text(log.getvalue(),encoding='utf-8')
    (a.output/'test_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['tests_run','failures','errors','skipped','successful','elapsed_seconds','source_hashes_preserved']},ensure_ascii=False))
    return 0 if result.wasSuccessful() and report['source_hashes_preserved'] else 1

if __name__=='__main__':raise SystemExit(main())
