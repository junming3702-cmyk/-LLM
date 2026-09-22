"""Exact supplied-source citation checks. No fuzzy repair or auto admission.

Legacy quotes are unchanged. Explicit fragments can describe discontiguous
evidence only if each quote binds one declared source span. The summary fields
must be a mechanical join, not new model prose. This validates provenance only.
"""

VERSION = 'exact-citation-fragments-v1'


def check_document_binding(check, spans, excerpt):
    quote, locator = check.get('document_quote'), check.get('document_locator')
    errors = []
    if 'document_fragments' not in check:
        if not isinstance(quote, str) or len(quote.strip()) < 4 or quote not in excerpt:
            errors.append('document_quote_not_bound')
        if not isinstance(locator, str) or locator not in spans:
            errors.append('document_locator_not_bound')
        elif isinstance(quote, str) and not any(quote in s for s in spans[locator]):
            errors.append('quote_locator_mismatch')
        return {'version': VERSION, 'mode': 'legacy_exact_single_span', 'errors': errors,
                'bound': not errors, 'legal_entailment_verified': False}
    fragments = check['document_fragments']
    if not isinstance(fragments, list) or not 2 <= len(fragments) <= 8:
        return {'version': VERSION, 'mode': 'explicit_fragments', 'errors': ['document_fragments_invalid'],
                'bound': False, 'legal_entailment_verified': False}
    records = []
    for i, part in enumerate(fragments):
        if not isinstance(part, dict) or set(part) != {'document_quote', 'document_locator'}:
            errors.append(f'fragment_{i}:invalid_shape'); continue
        q, loc = part['document_quote'], part['document_locator']
        if not isinstance(q,str) or len(q.strip()) < 4:
            errors.append(f'fragment_{i}:invalid_quote'); continue
        if not isinstance(loc,str) or loc not in spans or len(spans[loc]) != 1:
            errors.append(f'fragment_{i}:locator_not_unique_supplied_span'); continue
        body = spans[loc][0]
        offsets = [j for j in range(len(body)) if body.startswith(q,j)]
        if not offsets:
            errors.append(f'fragment_{i}:quote_locator_mismatch'); continue
        # Ambiguous repeated quotes require a more specific quote, not guessing.
        if len(offsets) != 1:
            errors.append(f'fragment_{i}:quote_occurrence_ambiguous'); continue
        records.append({'document_locator':loc, 'document_quote':q,
                        'start_in_supplied_span':offsets[0], 'end_in_supplied_span':offsets[0]+len(q)})
    if len(records)==len(fragments):
        if len({(p['document_locator'],p['document_quote']) for p in records}) != len(records):
            errors.append('duplicate_document_fragments')
        if quote != '\n'.join(p['document_quote'] for p in records):
            errors.append('fragment_summary_quote_mismatch')
        if locator != ';'.join(p['document_locator'] for p in records):
            errors.append('fragment_summary_locator_mismatch')
    return {'version': VERSION, 'mode': 'explicit_fragments', 'bound': not errors,
            'errors': errors, 'fragments': records, 'contiguous_quote_claimed': False,
            'original_response_modified': False, 'legal_entailment_verified': False}
