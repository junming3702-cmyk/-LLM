# Main system controls and paired gate ablation

Isolated from the frozen production and expert-evaluated release. No training,
parameter tuning, corpus expansion, source admission or P3 integration occurs.

## Comparisons

- LLM-only: same facts, response schema and provider settings; internal legal
  knowledge is explicitly allowed and marked unverified. Do not apply the RAG
  in-package citation gate to this arm or call its missing chunk IDs errors.
- Flat hybrid: search the same eligible Level 1-4 corpus globally, dual-query
  reciprocal-rank fusion, 25-candidate maximum, no hierarchical LLM triage.
- Strict hierarchy: unchanged base runner, 5 per level/phase, at most 25 retrieved
  candidates in the frozen corpus's five nonempty level/phase pools. The
  existing LLM triage and early stop remain part of this implemented system.
- Minimum ablation: compare parsed raw and gated output of the SAME response in
  each RAG arm. It removes post-generation gate effects, not all applicability
  checks or instructions. Never call this a full applicability-removal ablation.

Provider model request: deepseek-v4-flash; record actual returned model name.
Temperature .1, final thinking enabled/effort low/max_tokens 16384; strict
triage thinking disabled/max_tokens 2048. External discovery disabled in all
arms to isolate the local pipeline; no claim of successful external verification.
Three arms run once on the identical 45 frozen runtime inputs; order rotates
per unit index. Three concurrent units, no automatic retries. First unit is
an included transport/schema pilot; a failed pilot stops later units.
405-request, 24-million-character, 2,703,360 reserved-output-token and 2-hour
limits. Failures remain in the denominator. No selection by agreement/quality.

This is a whole-system comparison: triage, early stopping, selected evidence
and call budgets vary by design. Report these costs and actual evidence counts.
The equal 25-candidate upper bound is not equal final context or equal compute.
It cannot isolate hierarchy alone, establish causal human time savings, or
transfer historical expert usefulness scores to the new outputs.

## Evaluation boundaries

The runtime cannot read reference labels or expert scores. The separate local
evaluator joins by issue ID. Existing adjudicated references remain partial
and selected; original rater judgments and adjudicated references are reported
separately. No imputation. Unverified legal citation correctness needs human
assessment and is not established by automated chunk-ID checks.

Retrieval: same eligible corpus/query scope for BM25, dense and flat hybrid;
report Hit@5, macro reference-evidence Recall@5, and MRR@10 separately. Strict
delivered evidence is post-LLM selected; do not pool it into pure retriever
metrics or use gold normative levels. Existing synthetic data are development
benchmarks, not held-out generalization evidence.

No study data, credentials, private source paths, scores or raw provider logs
belong in this public directory. All runs require explicit content consent.
