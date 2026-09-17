"""Opt-in evidence-role guard; never reclassifies a statute or edits a corpus.

Enforce an existing runtime declaration of supplement/warning status. This is
not a general rule that standards can never have legal or contractual force.
No authority is inferred from a document title, similarity score or model text.
"""
from copy import deepcopy

VERSION = 'source-role-guard-v1'
SUPPLEMENT_ROLES = frozenset({'supplementary_document', 'practice_material_only'})
SUPPLEMENT_PARTITIONS = frozenset({'supplement', 'warning'})


def restriction_reasons(row):
    # Stable priority makes repeated normalization idempotent. The eligibility
    # written by this guard cannot become a new independent audit reason.
    if row.get('source_role') in SUPPLEMENT_ROLES:
        return ['declared_supplementary_source_role']
    if row.get('corpus_partition') in SUPPLEMENT_PARTITIONS:
        return ['declared_supplement_or_warning_partition']
    if row.get('legal_evidence_eligibility') == 'supplement_only':
        return ['declared_supplement_only_eligibility']
    return []


def normalize_source(row):
    """Monotone denial, preserving text, locator, rank and normative level."""
    out = deepcopy(row)
    reasons = restriction_reasons(row)
    if reasons:
        out.update(independent_legal_evidence=False, independent_evidence=False,
            citation_ready=False, legal_evidence_eligibility='supplement_only',
            citation_mode='contextual_only', requires_human_review=True)
        out['source_role_policy'] = {'version': VERSION, 'reasons': reasons,
            'normative_authority_changed': False, 'independent_legal_basis': False}
        out['source_role_warning'] = (
            '本材料在来源登记中属于补充/警示材料；可定位引用供人工参考，'
            '不得单独支持违法、合规或废标判断。来源角色如需变更，须另行核验登记。')
    return out


def prepare_runtime(runtime):
    out = deepcopy(runtime)
    rows = out.get('retrieved_legal_evidence', [])
    if not isinstance(rows, list):
        raise ValueError('retrieved_legal_evidence_must_be_list')
    out['retrieved_legal_evidence'] = [normalize_source(row) if isinstance(row, dict) else row for row in rows]
    restricted = [{'chunk_id': row.get('chunk_id'), 'reasons': restriction_reasons(row)}
                  for row in rows if isinstance(row, dict) and restriction_reasons(row)]
    out['source_role_policy_audit'] = {'version': VERSION,
        'restricted_evidence_rows': len(restricted), 'restricted': restricted,
        'text_locator_rank_and_authority_unchanged': True,
        'does_not_certify_remaining_sources': True}
    return out


class SourceRoleGuardRetriever:
    """Per-case result adapter. It shares the original index without writing it.

    Wrap after geographic filtering. No row is dropped, no reranking is done.
    The same denied metadata therefore reaches triage and final reasoning.
    """
    def __init__(self, delegate):
        self.delegate = delegate
        self.audit = []

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def _rows(self, rows):
        output = []
        for row in rows:
            updated = normalize_source(row)
            if restriction_reasons(row):
                self.audit.append({'chunk_id': row.get('chunk_id'),
                    'reasons': restriction_reasons(row),
                    'was_marked_independent': row.get('independent_legal_evidence') is True})
            output.append(updated)
        return output

    def retrieve(self, *args, **kwargs):
        return self._rows(self.delegate.retrieve(*args, **kwargs))

    def retrieve_many(self, *args, **kwargs):
        return self._rows(self.delegate.retrieve_many(*args, **kwargs))
