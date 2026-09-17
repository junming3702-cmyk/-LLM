# Phase 2: opt-in geography and review-task experiment

Status: isolated engineering candidate; **not a production release**. Base:
`4838cd9` (main-controls implementation). Existing system prompt file, corpus,
conclusion states, model identifier, API-key handling and external-recheck policy
are not replaced. There is no automatic network execution in this experiment.

## Factors and independent provenance

| Arm | Geographic filtering | Task contract / gate | Corpus expansion |
|---|---|---|---|
| baseline | off | off | none |
| geo_only | on | off | none |
| task_only | off | on | none |
| geo_task | on | on | none |

`ScopePolicy.for_arm(name, source_scopes)` explicitly opts a call to
`run_case(..., scope_policy=policy)` into an arm. Omission preserves the original
path. `run_final_reasoning` accepts the same option. Do not enable this through
LLM-provided JSON, contract text or expert judgments. A fresh online experiment
requires separate approval; offline replay is not an online execution substitute.

## Geographic admission

1. Filter the full per-level/per-phase candidate pool **before** BM25, dense
   top-K and reciprocal-rank fusion. Never filter only the returned top five.
2. A per-request shallow retriever copy shares immutable embeddings but owns
   its candidate index and annotated rows. The baseline object is unchanged.
3. Local sources require a confirmed location, exact province/city/county
   matching at every stated granularity, and a matched project type. No city to
   province guessing, fuzzy substring matching or automatic local-to-national
   conversion is used. Missing/conflicting metadata is quarantined, not called
   a completed legal no-hit.
4. Hash-bound source-scope metadata may be extracted from an existing frozen
   scope paragraph. This is not corpus expansion, new law, or temporal/source
   authenticity verification. A source's denial, expiry, supplement-only role
   and independence restrictions must remain intact.
5. The final input and gate recheck geography. External local sources use the
   same logic regardless of acquisition channel or a misleading level label.

## Review-task boundary

- Runtime stage and question distinguish clause design, document response,
  document completeness, actual conduct, and unknown/conflicting task scope.
- An opt-in prompt overlay is applied to BOTH triage and final reasoning.
  It requires preservation of conditions, exceptions, negations and stages,
  and a finding-level `claim_scope`. These are instructions, **not evidence
  that an LLM has obeyed them**; end-to-end adherence needs a later experiment.
- A narrow deterministic repair removes an actual-opening-event gap only for
  a prospective normative clause-design review. It does not remove other gaps,
  permit OCR failure to prove absence, establish compliance without law, or
  turn a template/promise into actual conduct.
- Explicit actual-conduct claims exceeding the task are held for confirmation.
  Missing/invalid tasks cannot be used to relax a gap. Legacy responses lacking
  `claim_scope` retain baseline checks; they are not retrospectively re-labelled.
- Observable internal document contradictions remain observations. Without a
  direct applicable legal basis they are not automatically converted into R.
- No case IDs, expert decisions, expected labels or scoring results are used in
  runtime rules. Unknown arbitrary fact-law relationships still require review.

## Validation and limits

`tests/test_scope_boundary_policy.py` uses synthetic fixtures and mocked model
responses. Run it through `src/run_offline_regression.py` to deny network access
and include the legacy regression suite.

`run_offline_validation.py --help` lists mandatory input/output paths. It:

- denies socket connections and loads only a local embedding snapshot;
- probes every level/phase, without inventing live triage/early-stop decisions;
- changes no law text, expert record, reference label or historical response;
- compares opt-out gate output byte-structurally with the baseline implementation;
- replays the SAME saved raw response under four policy settings, repeating
  deterministic gates to check reproducibility;
- retains all original failures and records input/code hashes;
- writes private, exclusive-create output files; cannot overwrite a prior run.

Saved-response replay tests safety and gate sensitivity, not what the LLM would
produce after different retrieval or prompts. It cannot establish new legal
accuracy, Recall@5, MRR, generalisation, or end-to-end efficiency. Previously
exposed examples remain development diagnostics, not independent holdout data.

## Deferred corpus expansion

Keep source acquisition/verification/admission in a separate manifest and commit.
No targeted legal additions are included here. Future comparison must fix the
corpus when testing these two factors, then vary the corpus in a separate arm.
External retrieval is another independently registered factor. Do not attribute
their combined effect to hierarchy, geography or the task prompt alone.

All results containing source documents or human assessments stay outside the
public repository. Only generic model code, synthetic tests and this protocol
are suitable for version control.

## Consent-scoped online factorial runner

`run_factorial_online.py --help` gives the required explicit input, corpus,
embedding-cache, environment and output paths. Run `--preflight` first, with
`--online-authorized-runtime-only` only when the user actually authorised this
provider and content class. Remove `--preflight` to execute the identical bound
configuration. Preflight performs no model request; it does not grant consent.

All four arms use fresh generations, the same original corpus and disabled
external retrieval. Input order rotates arm execution, not outcome selection.
The first issue's four arms are an included smoke check; a failed smoke stops
the remaining batch. Primary calls have one transport attempt; any separately
authorised retry belongs to a new sensitivity run, never overwriting primary
failures. Raw/gated outcomes, provider usage, request payloads, failures, source
hashes and helper-code hashes are retained in the private output directory.

The full excluded-source audit is stored locally. Only aggregate counts and
reason categories enter the LLM input; excluded rows are not legal evidence.
No expert reference or score file is accepted by the runtime runner.

`analyse_factorial.py` is a separate offline process. It refuses an unfinished
primary batch, checks input/response hashes, joins only the frozen A references,
and keeps all planned units and execution failures in the denominator. It
reports raw/gated observations, within-project summaries, paired factor
contrasts, source-applicability diagnostics and actual provider usage. It does
not transfer prior expert B ratings or invent exhaustive REAL45 relevance
judgments for Recall/MRR. `test_analysis.py` tests denominator and contrast
handling with synthetic records only.

`retry_transport_sensitivity.py` selects only audited transient transport failures
from a finished primary run, without consulting reference labels. It checks the
original package/input/corpus/prompt bindings, and repeats each eligible **whole
unit** once in a separate directory. This is a new stochastic generation, not
an exact replay of the successful request prefix. It cannot replace primary
failures or retry invalid/truncated outputs. Run its preflight first; use the
original frozen package rather than the editable follow-up worktree.

`analyse_transport_sensitivity.py` joins the separately retained repeat only in
an explicitly labelled sensitivity overlay. It checks the primary/result linkage
and keeps the first-run data intact, reporting additional API usage separately.

`render_analysis_report.py` renders all four groups, raw/gated stages, all planned
denominators, paired improvements AND deteriorations, project summaries, source
diagnostics and actual usage from the completed offline analysis. It makes no
network call and modifies neither the model nor the analysis input.
