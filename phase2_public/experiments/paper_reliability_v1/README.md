# Phase 2 experiment B — audit and reliability preparation

This opt-in development branch preserves the existing expert-study system.
It does **not** replace expert-rated outputs or claim improved legal accuracy.
No law-corpus expansion, new embedding model, re-chunking, early-stop change,
retrieval-weight adjustment, expert-label revision, or prompt rewrite is included.

## Implemented

- Private request journal: effective prompt, actual evidence/context, both raw
  response channels, finish reason, usage, gate-before/after evidence and reasons.
- Exact-request cache: binds body, model parameters, corpus/code/method and history.
  `--resume` recomputes retrieval; it does not skip an issue just because a file exists.
- Failures stay visible: execution failure, invalid/truncated output, gate blocking
  and substantive N/R/U verdicts are distinct. Human review is not itself abstention.
- Predeclared transport-only retry: default **one attempt**, optional at most two;
  only timeout/connection failure or HTTP 429/502/503/504 qualify. HTTP 400,
  incorrect conclusions, invalid JSON, length truncation and safety blocks do not.
- Source metadata survives candidate conversion and gate canonicalisation.
  Missing applicability/version information is not fabricated. Private local paths
  are not newly added to model evidence.
- Separate fixed-evidence intervention execution and evaluator processes.
  Prepared runtime packets require human-verification manifest and exact file hash.
- Candidate one-round clarification interface, not enabled in the current model.
  At most three requests; real, owner-verified material only; one re-review; no
  automatic admission into the law corpus or creation of runtime legal confirmation.

## Entry points

From the repository root, using an environment with existing Phase 2 dependencies:

```text
python phase2_public/src/run_offline_regression.py --output .local_runs/validation/new_report.json
python phase2_public/src/run_intervention_experiment.py --help
python phase2_public/src/analyse_intervention_experiment.py --help
python phase2_public/src/freeze_model_inputs.py --help
```

The offline regression script runs both unittest-style tests and legacy function/
main regression groups, blocks network connections, and writes to a new report.
If optional Excel dependencies are held in another compatible environment, use
`--optional-python-path` to append its site-packages; do not replace the ML runtime.

## Runtime packet versus evaluator record

The runtime JSONL envelope has exactly these fields:

```json
{
  "observation_id": "unique-id",
  "mother_case_id": "mother-id",
  "variant_id": "original-or-variant-id",
  "method_id": "frozen-method-id",
  "repeat_id": 0,
  "project_id": "project-id",
  "runtime_input": {}
}
```

`runtime_input` must contain actual contract evidence, project context, admitted
legal evidence and the reviewer's genuine runtime audits. Reuse the existing
input contract; do not fabricate search completion or confirmation records.
References, expected changes, hidden material mappings and expert labels are
forbidden runtime fields. Source documents remain untrusted data.

The **separate** human-approval manifest must include `status=human_verified`,
`runtime_packets_sha256`, `reviewed_by`, `reviewed_at`, and `external_policy`
(`disabled` or `frozen_evidence_only`). This manifest confirms input construction,
not the model's conclusions. The execution process does not load answer labels.

The **separate evaluator enrollment** describes each `pair_id`, `mother_case_id`,
`project_id`, original/variant observation IDs, allowed N/R/U verdicts,
`expected_relation` (`same`, `decisive_change`, `safe_missing`), and
`verification_status=human_verified`. Duplicate observations are rejected rather
than choosing the best run. Missing/failed observations stay in the denominator.

## Experimental boundaries and next approval

1. Identify the exact expert-rated AI output/version. User-reported partial returns
   are acknowledged; the filename alone does not establish model provenance.
2. Verify a competitive same-input reasoning baseline. Historical BM25/dense/hybrid
   retrieval comparisons are not automatically matched reasoning comparisons.
3. Prepare a small development-side variant batch; independent human verification
   is required. There are no newly approved 96 cases or new expert gold labels here.
4. Approve the fixed-evidence method and upload scope/budget before online execution.
   Default runner mode is preflight and makes zero provider calls. The optional
   `--online-authorized-deepseek` flag requires genuine authorization, not just a key.
5. Clarification request strategies are not yet a completed comparative experiment.
   The adapter reuses existing coverage/gaps. Both old-advice and structured-request
   arms must use the same material access rules, budgets and one re-review.

The original main entry point retains its one-shot external recheck policy. The
new fixed-corpus mechanism runner never discovers new external sources. These are
different experiment scopes and must not be pooled as one benchmark.

## Metrics correction without historical rewriting

Historical `recall_at_k` was implemented as “at least one reference ID found.” It
is **Hit@K**, not multi-evidence completeness recall. Historical values and names
remain untouched. New evaluator reports:

- Hit@K: at least one reference evidence item among the first K;
- reference-evidence Recall@K: matched reference IDs / all recorded reference IDs;
- reciprocal rank at the recorded ranking depth (mean gives MRR);
- complete-necessary-evidence recall only if reference-set completeness was
  separately established. A list of cited provisions is not necessarily complete.

An empty reference set is unscorable, not a successful zero-risk case. Pre-gate
and post-gate behavior are separately recorded. Stability without correctness is
not reliability; no subgroup or repeated outputs are treated as independent projects.

## Privacy and versioning

Only generic model code, tests and documentation belong in the public branch.
Keep run payloads under ignored `.local_runs/` and human-study material outside
the model repository. Do not publish law corpora, real project excerpts, participant
scores, identity fields, workbook contents, private manifests or API credentials.

The B branch is not merged into the expert system. User-returned expert data remain
unchanged. Old output-quality/usability scores cannot be reassigned to B; independent
reference judgments can support comparisons only under the original protocol.
