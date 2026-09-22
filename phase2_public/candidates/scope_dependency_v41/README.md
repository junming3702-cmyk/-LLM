# Phase 2 scope/dependency v4.1.1 — isolated task-mode mapping repair

Candidate only; no production promotion and no new online observations.
This revision moves task modes, expected response targets, allowed document
stages and text-exclusion eligibility into the same executable schema. The
generated prompt includes every mode/target pair; the pre-inference contract
contains `expected_review_target`, which is included in its digest and checked
against the schema by the gate. A valid but wrong target stays blocked, even
with mechanical normalization enabled. Historical responses are not repaired.
The import path/flag remains `scope_dependency_v41` for compatibility; the
contract version and digest identify v4.1.1. The separate v4 route is unchanged.
See `docs/CHANGELOG_SCOPE_PROTOCOL_V411.md` for scope and validation boundaries.
The executable schema in `src/scope_dependency_v41_schema.py` is the single
source for required fields, enum values, dependency/kind pairs, generated prompt
instructions, and structural validation. It is a small documented schema
dialect, not an implementation of all JSON Schema features.

Use `scope_dependency_v41=scope_spec` on `run_final_reasoning` or `apply_gate`.
The runner binds the input, scope and schema digest before inference.
Do not enable v4 and v4.1 simultaneously. Old routes remain unchanged.
`normalize_protocol_v41=False` is the default. Optional mechanical normalization
only renames an explicit `check_name` alias when `check` is absent, or normalizes
case/whitespace of an already-known enum. It never generates missing names,
interpretations, citations, claim bindings or dependency classifications.
Raw and normalized protocol diagnostics are recorded separately, including
unparsed/empty output. No protocol pass is evidence of legal accuracy.

Material state (`kind/dependency_key`), task relation and gate-owned output
group are distinct. Unresolved/mixed relationships enter
`scope_review_required`, with no valid legal verdict. The legacy compatibility
U remains traceable but is not shown as a legal verdict in candidate review
tables, Markdown or exported review rows. Explicit decisive gaps remain U;
source admission, quotation, geography and human review are not relaxed.

Generate/verify mirrors:

```text
python src/generate_scope_dependency_v41.py --write
python src/generate_scope_dependency_v41.py
```

See `docs/CHANGELOG_SCOPE_DEPENDENCY_V41.md`,
`prompts/scope_dependency_v41_candidate.md`, and
`schemas/scope_dependency_v41.schema.json`.

## Preserved v4 foundation (historical description)

This snapshot adds **explicit pre-inference scope configuration**, typed text
observations vs legal comparisons, and claim-bound gaps to the preserved v3
implementation below. Production is not promoted or modified.

Enable v4 only through the trusted caller's `scope_dependency_v4=scope_spec`
argument to `run_final_reasoning` and `apply_gate`. The runner constructs
`review_task_contract_v4` before inference. Do not derive this specification from
model answers, reference labels, expert scores, or desired evaluation outcomes.
The caller must enumerate the fixed question, mode, required legal subclaims,
their dependencies and explicit exclusions. Missing/changed contracts fail closed.
The digest binds input/configuration, not human approval or legal truth.

See `docs/CHANGELOG_SCOPE_DEPENDENCY_V4.md` and the compiled, reviewable
`prompts/scope_dependency_v4_candidate.md`. The original production prompt and
all old tests are retained. Calls without the new option retain prior behavior.
Old responses lack the new typed protocol; do not silently retrofit them and
report the result as a fresh model observation. No online v4 inference or
accuracy/recall/clinical/legal efficacy is claimed by software tests.

## Preserved v3 foundation

Status: **candidate only**. The production package, historical outputs and reference
labels remain unchanged. This package is an offline-testable snapshot, not a new
claim of legal accuracy. It must not issue automatic rejection or award decisions.

## Changes

1. An input-bound, conservative question-scope audit distinguishes directly
   attached factual-task exclusions from affirmative verification requests.
   Double negation, quoted/unclear scope and genuine positive requests remain
   restrictive. This is a narrow rule-based repair, not a general Chinese parser.
2. Optional `document_fragments` supports 2–8 explicit exact quotations. Each
   fragment must bind one declared source span. Repeated/ambiguous quotes,
   undeclared locators, altered dates/numbers/negations and invented text fail.
3. The display quote must be the newline join of the fragments; display locators
   must be the semicolon join in the same order. Joining display fields does not
   imply contiguous evidence, legal entailment or completeness of the source.
4. The candidate final-reasoning entry includes the matching prompt addendum.
   The production `system_prompt_final.md` itself is not edited. Default calls
   without `task_contract_v2=True` retain the legacy route.

No fuzzy quote repair is allowed. Existing responses with paraphrased quotations
or only semicolon-concatenated locators remain blocked. No reference answers,
project-specific unit exceptions or desired conclusions are embedded in the policy.
Applicable independent law, decisive facts, geographical/temporal safeguards and
human review remain required. Supplement-only evidence cannot establish N.

## Reproduce the software tests

Use an environment with the dependencies in `requirements.txt`. Do not install
new model weights or configure API credentials just to run these offline tests.

```text
python src/run_offline_regression_suite.py --package . --output /path/to/new-private-test-directory
```

The runner covers unittest methods and plain test functions, disables socket
connections, stores temporary test files under the specified output directory,
and refuses to overwrite an existing run. Offline exporter tests create synthetic
temporary workbooks only. The test count is a count of test methods/function
groups; subcases are not independent research samples.

The isolated candidate has a mocked final-reasoning entry test: no provider call
is made. Keep API keys outside Git and local/private results outside this package.

## Frozen-response diagnostics

`src/replay_scope_citation_v3.py` can compare a supplied baseline package with
this candidate in separate processes. Its local-only catalogue contains just
`unit_id` and `result_path`; it reads no reference workbook or expert ratings.
The candidate recomputes machine scope metadata but preserves the question,
document excerpts and generated response. Do not publish the catalogue or raw
replay outputs for real projects.

This replay tests deterministic gate behavior, not prompt effectiveness, new LLM
generations, retrieval gains or independent legal accuracy. Changed provenance
metadata does not itself count as a better outcome. New online evaluation and any
production promotion are separate, approval-gated steps.

## Next evaluation boundary

Before a targeted online check, freeze the candidate code/prompt, keep model and
generation settings fixed, preserve old responses, send no author/REF answers,
and request exact fragment output. Do not automatically repeat until a desired
label appears. Real-project human scoring is not included in this public package.
