# Task-gate v2 candidate (opt-in; not production promotion)

## Scope

This candidate keeps the original task/question, four-level retrieval, source
admission, geographic applicability, external fallback and human-review policy.
It changes the post-generation task/gap audit and review handoff only. The prompt
candidate is available for a separately authorized future generation experiment.
Default calls continue to use the existing policy. The provider/model and
generation parameters are not changed by this candidate.

## Decision contract

`review_task_contract_v2.build_contract` freezes question, stage, evidence boundary
and the input digest before generation. Its scope metadata is machine-derived,
not human approval. It uses no issue IDs, expected answers or expert labels.
Ambiguous questions remain `scope_needs_confirmation`; they are not rewritten
into easy wording questions. A partial excerpt is not a complete submitted package.

Material/input gaps can become follow-up only when all these checks hold:

1. The input itself identifies a bounded wording or internal-consistency task.
2. The model explicitly says the gap does not block that question.
3. The deterministic dependency rule matches an excluded external-requirement,
   actual-performance or other-document-disclosure task.
4. No exception/priority/current-clause context is lost.
5. The remaining N requirements (supplied independent applicable law, grounded
   completed comparison, adequate facts and existing source guards) still pass.

These lexical dependency rules are deliberately narrow engineering heuristics,
not proof of legal correctness. Human confirmation is still required. Missing
key law, decisive applicability, unreadable evidence and decisive comparison
values are never waived merely because a model sets a false flag. Raw U is not
automatically converted to N. Confirmed missing required material and material
not provided to the system remain distinguishable U when decisive.

## Separate status axes

- Decision: existing N/R/U canonical conclusion codes.
- Processing: valid, schema_blocked, evidence_binding_blocked, or execution failure.
- Workflow: always requires_human_second_review.

A fabricated/mislocated quote or unsupplied citation ID is not a successful
legal abstention. A supplied but supplement-only or inapplicable source remains
a semantic evidence gap. A blocked finding may retain a diagnostic U label,
but evaluators must count the processing failure, not score that U as successful
delivery. The handoff preserves unverified model explanations without restoring
blocked legal claims or treating those explanations as evidence.

## Locator correction (v2.1)

Only bracket markers present in the input's declared source-locator list delimit
spans. Redaction placeholders such as `[name withheld]` remain document text.
The historical v1 matcher stays unchanged by default. Quotes from adjacent
source spans are not silently joined or rewritten. Multiple unsegmented
locators do not certify a span; a sole declared locator may bind the whole excerpt.

## Reproduce offline

Use the model Python environment with its existing dependencies. No credential is
needed. `replay_task_gate_v2.py` disables socket connections, reads no labels,
creates contracts before reading responses and creates a fresh output directory.

```text
python src/replay_task_gate_v2.py --inputs PRIVATE_FROZEN_INPUTS --results PRIVATE_RESULTS --output NEW_PRIVATE_RUN --external-auto-candidates
python src/run_task_gate_guards.py --output NEW_PRIVATE_TEST_LOG.json
```

The external flag must match the frozen comparator; it does not execute a new
external search. All source hashes and code hashes are recorded. Baseline labels
must reproduce stored observations. Inference/prompt effects cannot be inferred
from a same-response replay. A separate evaluation process may load frozen
reference labels after replay; never include them in model inputs.

## Prompt and exporter interfaces

`task_gate_v2_prompt.candidate_prompt()` builds a separate candidate from the
unchanged production file. Exact-match edits fail closed if that base drifts.
It removes the targeted blanket no-conflict-to-U rules and reconciles missing
material with the N/U policy. `run_final_reasoning(task_contract_v2=True)` binds
the input contract before calling the provider and applies the candidate gate.
This is a programmatic opt-in; no CLI default or production deployment is changed.

`export_review_excel.py --include-handoff` appends status, scope, concrete model
comparison, completed checks, blocking reasons, follow-up items, role metadata
and blank human-review fields. It rejects cell overflow and treats input strings
as text, not formulas. Existing 13-column mode stays available. Candidate output
paths cannot overwrite an existing workbook.

`export_task_gate_review.mjs` is an optional artifact-tool renderer. Its prepared
private payload uses comparison_headers/comparison_rows plus
handoff_headers/handoff_rows. Long fields are losslessly segmented into an
evidence sheet; the original JSON remains authoritative. Do not commit its inputs,
workbooks, expert references, raw contracts or screenshots.

## Validation and next approval boundary

Public guards cover necessary U, no-law/supplement-only conditions, exceptions,
factual/completeness tasks, forged scope, incorrect locators, redaction brackets,
raw input preservation, prompt drift, offline replay and literal Excel text.
These tests verify software invariants, not legal entailment or generalization.

Before any new provider run: review ambiguous task boundaries and the candidate
prompt; preregister the frozen input/evidence set and paired comparison. Do not
combine corpus expansion, reranking, provider changes or expert-reference edits
with a gate-only experiment. Keep historical expert acceptance bound to the
historical outputs. Report all cases and all failures, including out-of-domain cases.
