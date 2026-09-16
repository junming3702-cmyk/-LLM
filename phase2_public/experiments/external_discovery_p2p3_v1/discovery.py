"""Bounded, operator-curated discovery; isolated from the expert-rated runner.

Inputs from web pages never control URLs, reviews, instructions or credentials.
This is article discovery within a finite, manually discovered source catalogue,
not an autonomous Internet search. P1's extractor and scope gate are reused.
"""
from __future__ import annotations
import hashlib
import json
import multiprocessing as mp
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

P1 = Path(__file__).resolve().parents[1] / 'external_verification_p1_v1'
sys.path.insert(0, str(P1))
from verification import HEADER, assess_admission, digest, fetch_public, html_text, verify_target

VERSION = 'bounded-curated-discovery-p2.v1'
INSUFFICIENT = 'insufficient_information_needs_human_confirm'

def canonical_hash(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())

def safe_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None, 443):
        raise ValueError('unsafe_url')
    if re.search(r'(?i)(token|secret|password|api.?key|authorization)', p.query):
        raise ValueError('sensitive_url_query')
    return url

def load_catalogue():
    p1 = json.loads((P1 / 'source_targets.json').read_text(encoding='utf-8'))['sources']
    extra = json.loads((Path(__file__).parent / 'catalogue_extension.json').read_text(encoding='utf-8'))['sources']
    result = []
    for entry in p1 + extra:
        s = dict(entry)
        s.pop('targets', None)  # Discovery must not consume expected article IDs/quotes.
        s.setdefault('regimes', ['construction_tender'])
        s.setdefault('project_types', ['construction'])
        s.setdefault('topics', ['招标', '投标', '资格', '保证金', '期限'])
        s.setdefault('discovery_provenance', 'operator_curated_P1_catalogue; not automatic search')
        safe_url(s['url'])
        result.append(s)
    if len({s['source_id'] for s in result}) != len(result):
        raise ValueError('duplicate_source_id')
    return result

def public_terms(terms):
    # Caller supplies short public legal themes, NOT a contract excerpt.
    if not isinstance(terms, list) or not 1 <= len(terms) <= 6:
        raise ValueError('invalid_public_terms')
    for term in terms:
        if not isinstance(term, str) or not re.fullmatch(r'[\u4e00-\u9fffA-Za-z]{2,16}', term):
            raise ValueError('non_public_query_shape')
    return list(dict.fromkeys(terms))

def route_sources(catalogue, terms, context, max_details=4):
    terms = public_terms(terms)
    if not isinstance(context, dict):
        raise ValueError('invalid_context')
    if not context.get('procurement_regime') or not context.get('project_type'):
        return [], [{'reason': 'missing_routing_context'}]
    selected, excluded = [], []
    for source in catalogue:
        reason = None
        if context['procurement_regime'] not in source['regimes']:
            reason = 'wrong_procurement_regime'
        elif context['project_type'] not in source['project_types']:
            reason = 'wrong_project_type'
        elif source['geographic_scope'] != 'national' and context.get('jurisdiction') != source['geographic_scope']:
            reason = 'local_jurisdiction_missing_or_mismatch'
        if reason:
            excluded.append({'source_id': source['source_id'], 'reason': reason})
            continue
        score = sum(t in ' '.join(source['topics']) + source['law_title'] for t in terms)
        if score:
            selected.append((score, source['source_id'], source))
    selected.sort(key=lambda x: (-x[0], x[1]))
    if len(selected) > max_details:
        excluded.extend({'source_id': s[1], 'reason': 'detail_budget'} for s in selected[max_details:])
    return [s[2] for s in selected[:max_details]], excluded

def _fetch_worker(conn, url, allowlist, timeout):
    try:
        raw, meta = fetch_public(url, allowlist, timeout=timeout)
        conn.send(('ok', raw, meta))
    except Exception as exc:
        # Do not serialize arbitrary exception text (proxy credentials can leak).
        code = getattr(exc, 'code', None)
        reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch('[a-z_]+', str(exc)) else type(exc).__name__
        conn.send(('failed', {'reason': reason, 'http_status': code}))
    finally:
        conn.close()

def bounded_fetch(url, allowlist, timeout=15):
    safe_url(url)
    if url not in allowlist:
        raise ValueError('url_not_allowlisted')
    # Killable child gives the *whole* fetch a deadline, including DNS and reads.
    ctx = mp.get_context('spawn')
    reader, writer = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_fetch_worker, args=(writer, url, allowlist, timeout))
    process.start()
    writer.close()
    try:
        if not reader.poll(timeout):
            return None, {'reason': 'total_fetch_timeout', 'http_status': None}
        result = reader.recv()
        if result[0] == 'ok':
            return result[1], result[2]
        return None, result[1]
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        reader.close()

class SnapshotStore:
    """Content-addressed raw snapshots. Cache never supplies a human review."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, url, raw, metadata):
        safe_url(url)
        sha = digest(raw)
        if metadata.get('raw_sha256') != sha:
            raise ValueError('snapshot_hash_mismatch')
        key = digest(url.encode())
        blob = self.root / (sha + '.html')
        if not blob.exists():
            blob.write_bytes(raw)
        index = self.root / (key + '.json')
        data = {**metadata, 'source_url': url, 'raw_sha256': sha}
        # Separate run directories prevent overwriting earlier evidence versions.
        if index.exists() and json.loads(index.read_text('utf-8')) != data:
            raise ValueError('cache_version_conflict_use_new_directory')
        if not index.exists():
            index.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def get(self, url):
        path = self.root / (digest(url.encode()) + '.json')
        if not path.exists():
            return None
        meta = json.loads(path.read_text('utf-8'))
        if meta.get('source_url') != url:
            raise ValueError('cache_url_binding_mismatch')
        sha = meta.get('raw_sha256', '')
        if not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('invalid_cache_hash')
        raw = (self.root / (sha + '.html')).read_bytes()
        if digest(raw) != sha:
            raise ValueError('snapshot_hash_mismatch')
        return raw, meta

def discover_articles(source, text, raw_hash, terms):
    """No gold IDs/expected quotes required. Ranking is exploratory lexical."""
    terms = public_terms(terms)
    packets, failures = [], []
    for article in dict.fromkeys(h[1] for h in HEADER.finditer(text)):
        target = {'target_id': 'discovery', 'article': article, 'anchor': ''}
        packet = verify_target(source, target, text, raw_hash)
        if not packet['machine_verification_passed']:
            failures.append({'article': article, 'reasons': packet['block_reasons']})
            continue
        quote = packet['legal_quote']
        matches = [t for t in terms if t in quote]
        if not matches:
            continue
        packet.update(candidate_id=canonical_hash([source['url'], raw_hash, article, packet['article_sha256']])[:24],
                      evidence_id=source['source_id']+':'+article+':'+packet['article_sha256'],
                      acquisition_channel='external_curated_discovery', retrieval_score=len(matches), matched_public_terms=matches,
                      required_dependency_review=True, discovery_version=VERSION, regimes=source['regimes'])
        packets.append(packet)
    return packets, failures

def packet_integrity(packet, snapshot):
    if not snapshot:
        return ['independent_snapshot_required']
    try:
        raw, meta = snapshot
        text = html_text(raw, meta['encoding'])
        if digest(raw) != packet['raw_snapshot_sha256'] or digest(raw) != meta['raw_sha256']:
            return ['snapshot_hash_mismatch']
        if meta.get('source_url') != packet['source_url']:
            return ['snapshot_url_mismatch']
        loc = packet['source_locator']
        if not isinstance(loc['start'], int) or not isinstance(loc['end_exclusive'], int) or not 0 <= loc['start'] < loc['end_exclusive'] <= len(text):
            return ['invalid_locator']
        if text[loc['start']:loc['end_exclusive']] != packet['legal_quote']:
            return ['locator_quote_mismatch']
        if digest(text.encode()) != packet['normalized_snapshot_sha256'] or digest(packet['legal_quote'].encode()) != packet['article_sha256']:
            return ['content_hash_mismatch']
    except (KeyError, TypeError, ValueError, UnicodeError):
        return ['invalid_snapshot_or_locator']
    return []

def admit_candidate(packet, review, context, snapshot=None):
    context = context if isinstance(context, dict) else {}
    base = assess_admission(packet, review, context)
    reasons = list(base['reasons']) + packet_integrity(packet, snapshot)
    if isinstance(review, dict):
        # An experimental approval is not reusable for other projects/dates.
        # Absence preserves the legacy explicit-scope review contract; an
        # explicitly provided but malformed scope fails closed.
        if 'approval_scope' in review:
            scope = review['approval_scope']
            if not isinstance(scope, dict):
                reasons.append('invalid_approval_scope')
            else:
                ids = scope.get('allowed_issue_ids')
                if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x for x in ids):
                    reasons.append('invalid_approval_scope_issue_ids')
                    ids = []
                for key in ('scope_id', 'task_spec_sha256'):
                    if not scope.get(key) or context.get(key) != scope[key]:
                        reasons.append('approval_scope_mismatch_' + key)
                if not context.get('issue_id') or context['issue_id'] not in ids:
                    reasons.append('issue_not_in_approved_scope')
                if 'context_hashes' in scope:
                    fields = ('jurisdiction','project_type','procurement_regime','as_of')
                    bindings = scope['context_hashes']
                    actual = canonical_hash({k:context.get(k) for k in fields})
                    if not isinstance(bindings,dict) or bindings.get(context.get('issue_id')) != actual:
                        reasons.append('registered_project_context_mismatch')
        if review.get('candidate_id') != packet.get('candidate_id'):
            reasons.append('review_candidate_binding_mismatch')
        if review.get('procurement_regime') != context.get('procurement_regime') or context.get('procurement_regime') not in packet.get('regimes', []):
            reasons.append('procurement_regime_missing_or_mismatch')
        if review.get('dependency_review') not in ('complete', 'not_required'):
            reasons.append('conditions_exceptions_crossreferences_unreviewed')
        if review.get('source_provenance_confirmed') is not True:
            reasons.append('source_provenance_unconfirmed')
        if review.get('facts_sufficient_for_applicability') is not True:
            reasons.append('material_facts_unconfirmed')
    else:
        reasons.append('operator_sidecar_required')
    if not context.get('jurisdiction'):
        reasons.append('jurisdiction_missing')
    return {**base, 'status': 'eligible_for_reviewed_scope' if not reasons else 'not_admitted',
            'independent_legal_evidence': not reasons, 'reasons': sorted(set(reasons)),
            'acquisition_channel': 'external_curated_discovery'}

def recheck(preliminary, terms, context, catalogue, store, *, reviews=None, live=False, prior_attempts=0, fetcher=bounded_fetch, seconds=60):
    if seconds <= 0 or seconds > 60:
        raise ValueError('invalid_total_budget')
    start = time.monotonic()
    result = {'schema': VERSION, 'preliminary_conclusion': preliminary, 'final_conclusion': preliminary,
              'external_rounds': prior_attempts, 'network_requests': 0, 'cache_hits': 0,
              'sources': [], 'candidates': [], 'admitted_evidence': [], 'requires_human_second_review': True,
              'production_model_modified': False, 'comprehensive_legal_search': False}
    if preliminary != INSUFFICIENT or prior_attempts:
        result['status'] = 'not_triggered' if preliminary != INSUFFICIENT else 'one_shot_already_used'
        return result
    result['external_rounds'] = 1
    selected, exclusions = route_sources(catalogue, terms, context)
    result.update(public_terms=public_terms(terms), context=context, routing_exclusions=exclusions)
    allowed = [safe_url(s['url']) for s in selected]
    candidates, snapshots = [], {}
    for source in selected:
        rec = {'source_id': source['source_id'], 'source_url': source['url']}
        try:
            if time.monotonic() - start >= seconds:
                rec['status'] = 'budget_exhausted'
                continue
            cached = store.get(source['url'])
            if cached:
                raw, meta = cached
                result['cache_hits'] += 1
                rec['transport'] = 'frozen_snapshot'
            elif live:
                result['network_requests'] += 1
                raw, meta = fetcher(source['url'], allowed, timeout=min(15, max(.01, seconds - (time.monotonic() - start))))
                if raw is None:
                    rec.update(status='transport_failed', **meta)
                    continue
                store.put(source['url'], raw, meta)
                rec['transport'] = 'live'
            else:
                rec['status'] = 'offline_snapshot_missing'
                continue
            text = html_text(raw, meta['encoding'])
            snapshots[source['url']] = (raw, {**meta, 'source_url': source['url']})
            found, rejected = discover_articles(source, text, meta['raw_sha256'], terms)
            candidates.extend(found)
            rec.update(status='parsed', parsed_candidates=len(found), blocked_article_boundaries=rejected,
                       raw_sha256=meta['raw_sha256'], fetched_at=meta.get('fetched_at'))
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch('[a-z_]+', str(exc)) else type(exc).__name__
            rec.update(status='parse_or_cache_failed', reason=reason)
        finally:
            result['sources'].append(rec)
    # Keep distinct source/version provenance; deduplicate only exact candidate IDs.
    unique = {p['candidate_id']: p for p in candidates}
    ranked = sorted(unique.values(), key=lambda p: (-p['retrieval_score'], p['source_id'], p['article']))[:10]
    reviews = reviews if isinstance(reviews, dict) else {}
    for p in ranked:
        p['admission'] = admit_candidate(p, reviews.get(p['candidate_id']), context, snapshots.get(p['source_url']))
        if p['admission']['independent_legal_evidence']:
            admitted = {**p, 'independent_legal_evidence': True, 'admission_status': 'human_confirmed_for_context'}
            result['admitted_evidence'].append(admitted)
    result['candidates'] = ranked
    result['status'] = 'ready_for_controlled_reasoning' if result['admitted_evidence'] else 'pending_human_confirmation' if ranked else 'no_usable_evidence_within_bounded_scope'
    # Discovery NEVER changes a legal conclusion or treats failed search as valid.
    result['elapsed_seconds'] = round(time.monotonic() - start, 4)
    result['evidence_snapshot_sha256'] = canonical_hash(result['admitted_evidence'])
    return result

def citation_gate(output, result):
    """Fail closed before any downstream Markdown/Excel exporter sees citations."""
    valid = {p['candidate_id'] for p in result['admitted_evidence']}
    reasons = []
    if not isinstance(output, dict):
        output = {}
        reasons.append('invalid_output_object')
    citations = output.get('cited_candidate_ids', [])
    if not isinstance(citations, list) or not all(isinstance(x, str) for x in citations):
        citations = []
        reasons.append('invalid_citation_schema')
    if set(citations) - valid:
        reasons.append('unadmitted_or_unknown_citation')
    if output.get('conclusion') != INSUFFICIENT and not citations:
        reasons.append('unsupported_conclusion')
    if output.get('conclusion') not in (INSUFFICIENT, 'requires_human_legal_review', 'requires_human_legal_confirm', 'no_supported_issue_found_within_review_scope'):
        reasons.append('unknown_conclusion')
    return {**output, 'conclusion': INSUFFICIENT if reasons else output['conclusion'],
            'cited_candidate_ids': [] if reasons else citations, 'requires_human_second_review': True,
            'recommendation': '证据未满足准入或输出校验要求；保留信息不足并交人工核验。' if reasons else output.get('recommendation'),
            'gate_reasons': reasons}
