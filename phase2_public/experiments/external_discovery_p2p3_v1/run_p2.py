"""Public-law live smoke or frozen replay. No contract/expert input accepted."""
import argparse
import json
from pathlib import Path
from discovery import INSUFFICIENT, SnapshotStore, load_catalogue, recheck

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--terms', nargs='+', required=True)
    parser.add_argument('--regime', required=True)
    parser.add_argument('--project-type', required=True)
    parser.add_argument('--jurisdiction', required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--reviews', type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    context = {'procurement_regime': args.regime, 'project_type': args.project_type,
               'jurisdiction': args.jurisdiction, 'as_of': args.as_of}
    reviews = json.loads(args.reviews.read_text('utf-8')) if args.reviews else {}
    result = recheck(INSUFFICIENT, args.terms, context, load_catalogue(), SnapshotStore(args.cache), reviews=reviews, live=args.live)
    (args.out / 'discovery_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    sidecar = {}
    for p in result['candidates']:
        sidecar[p['candidate_id']] = {
            'candidate_id': p['candidate_id'], 'status': 'pending', 'reviewer_id': None,
            'confirmed_at': None, 'law_title': p['law_title'], 'version_label': p['version_label'],
            'article_sha256': p['article_sha256'], 'raw_snapshot_sha256': p['raw_snapshot_sha256'],
            'geographic_scope': p['geographic_scope'], 'valid_from': None, 'valid_to_exclusive': None,
            'verified_through': None, 'allowed_project_types': [], 'procurement_regime': None,
            'dependency_review': None, 'source_provenance_confirmed': False,
            'facts_sufficient_for_applicability': False,
            'review_note': 'Confirm full conditions, exceptions and cross-references; never infer case facts.'}
    (args.out / 'human_reviews.pending.json').write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'sources': len(result['sources']), 'network_requests': result['network_requests'],
                      'cache_hits': result['cache_hits'], 'candidates': len(result['candidates']),
                      'admitted': len(result['admitted_evidence']), 'final': result['final_conclusion']}))

if __name__ == '__main__':
    main()
