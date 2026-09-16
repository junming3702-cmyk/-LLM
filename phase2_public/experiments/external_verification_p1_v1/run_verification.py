"""Explicit opt-in live verification or offline replay, with public-law inputs only."""
from pathlib import Path
import argparse,json,sys,hashlib
from verification import fetch_public,html_text,verify_target

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--live',action='store_true');ap.add_argument('--out',type=Path,required=True);ap.add_argument('--replay',type=Path);ap.add_argument('--reuse',type=Path)
    args=ap.parse_args()
    if args.live==bool(args.replay):ap.error('choose exactly --live or --replay SNAPSHOT_DIR')
    if args.reuse and not args.live:ap.error('--reuse requires --live')
    here=Path(__file__).resolve().parent;manifest=json.loads((here/'source_targets.json').read_text(encoding='utf-8'))
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'snapshots').mkdir()
    health=[];packets=[];allowed=[s['url'] for s in manifest['sources']]
    for s in manifest['sources']:
        sid=s['source_id'];record={'source_id':sid,'source_url':s['url']}
        try:
            if args.live:
                reused=False
                if args.reuse and (args.reuse/'snapshots'/f'{sid}.metadata.json').exists():
                    old=json.loads((args.reuse/'report.json').read_text(encoding='utf-8'))
                    prior=next(h for h in old['sources'] if h['source_id']==sid)
                    if prior['source_url']!=s['url']:raise ValueError('cache_url_binding_mismatch')
                    raw=(args.reuse/'snapshots'/f'{sid}.html').read_bytes();transport=json.loads((args.reuse/'snapshots'/f'{sid}.metadata.json').read_text(encoding='utf-8'))
                    if hashlib.sha256(raw).hexdigest()!=transport['raw_sha256']:raise ValueError('snapshot_hash_mismatch')
                    reused=True
                else:raw,transport=fetch_public(s['url'],allowed)
                text=html_text(raw,transport['encoding']);record['reused_verified_snapshot']=reused
                (args.out/'snapshots'/f'{sid}.html').write_bytes(raw)
                (args.out/'snapshots'/f'{sid}.txt').write_text(text,encoding='utf-8')
                (args.out/'snapshots'/f'{sid}.metadata.json').write_text(json.dumps(transport,indent=2),encoding='utf-8')
            else:
                prior_report=json.loads((args.replay/'report.json').read_text(encoding='utf-8'))
                prior=next(h for h in prior_report['sources'] if h['source_id']==sid)
                if prior['source_url']!=s['url']:raise ValueError('replay_url_binding_mismatch')
                base=args.replay/'snapshots';raw=(base/f'{sid}.html').read_bytes();transport=json.loads((base/f'{sid}.metadata.json').read_text(encoding='utf-8'))
                if hashlib.sha256(raw).hexdigest()!=transport['raw_sha256']:raise ValueError('snapshot_hash_mismatch')
                text=html_text(raw,transport['encoding'])
            record.update(status='fetched',**transport)
            for t in s['targets']:packets.append(verify_target(s,t,text,transport['raw_sha256']))
        except Exception as exc:
            # Do not log exception strings: proxy credentials may occur in them.
            record.update(status='failed',reason_type=type(exc).__name__,http_status=getattr(exc,'code',None))
            for t in s['targets']:packets.append({'target_id':t['target_id'],'source_id':sid,'article':t['article'],'machine_verification_passed':False,'admission_status':'source_unavailable','independent_legal_evidence':False})
        health.append(record);print(sid,record['status'],flush=True)
    result={'schema':'external-verification-p1.run.v1','mode':'live' if args.live else 'snapshot_replay','sources':health,'packets':packets,
      'summary':{'targets':len(packets),'sources_fetched':sum(h['status']=='fetched' for h in health),'machine_passed':sum(p['machine_verification_passed'] for p in packets),'human_confirmed':0,'independent_legal_evidence':0},
      'not_a_retrieval_benchmark':True,'no_expert_or_contract_data_used':True,'production_model_modified':False}
    (args.out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary']))
if __name__=='__main__':main()
