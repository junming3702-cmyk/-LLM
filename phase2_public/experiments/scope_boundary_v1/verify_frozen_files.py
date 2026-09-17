"""Read-only recheck of an existing path/hash inventory; new private report."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from experiment_integrity import file_digest, write_new_json, utc_now

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--scope-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    records=json.loads(a.inventory.read_text(encoding='utf-8'))
    root=a.scope_root.resolve(strict=True)
    checks=[]
    for name,expected in records.items():
        file=Path(name).resolve()
        if not file.is_relative_to(root): raise ValueError('inventory path outside declared scope')
        actual=file_digest(file) if file.is_file() else None
        checks.append({'path':str(file),'expected_sha256':expected,'actual_sha256':actual,'unchanged':actual==expected})
    summary={'checked_at':utc_now(),'inventory_sha256':file_digest(a.inventory),
        'files':len(checks),'unchanged':sum(r['unchanged'] for r in checks),
        'all_unchanged':all(r['unchanged'] for r in checks),'writes_to_sources':0,'checks':checks}
    write_new_json(a.output,summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='checks'},ensure_ascii=False))
    return 0 if summary['all_unchanged'] else 2

if __name__=='__main__':raise SystemExit(main())
