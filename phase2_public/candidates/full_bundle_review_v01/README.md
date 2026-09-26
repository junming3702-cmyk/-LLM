# Full-bundle construction tendering review, candidate v0.1

Status: isolated Phase 2 development candidate. The frozen REAL45, QX, expert
ratings and existing production outputs are unchanged. This package has **not**
been independently validated on a previously unseen complete project.

`ACCEPTANCE_CONTRACT.md` fixes the system's intended input, two tasks / three
checks, deliverable and safety boundary. The manifest is explicit so that an
award/evaluation record cannot be silently mixed into the original tender or
final bid. The intended product is an automated preliminary review with a
separate human legal sign-off, never an automatic bid decision.

## Stage 1: offline intake and discovery

`bundle_review.py --manifest PATH --output-root NEW_EMPTY_DIRECTORY` ingests
only the declared PDF/DOCX files through the existing `DocumentIngestor`.
It creates original-hash-bound locator maps, extraction quality records,
`candidates.json`, `coverage.json` and three label streams. No API is called.
For a previously parsed PDF, a manifest may explicitly supply a
`verified_pagewise_cache` with the source PDF hash, pagewise-block JSON hash,
preflight sidecar hash and document alias. This route verifies source/cache
identity, enumerates every physical page into `page_ledger.jsonl`, and refuses
hash or page-locator mismatches. It does **not** certify OCR transcription or
the completeness of a final submission; PDF preflight advisories remain visible.
Unlike baseline DOCX table parents (whose cells have separate locators), a
cached MinerU table can contain the only reviewable table text. The whole
table block is therefore retained as a candidate, marked
`table_structure_unverified`; cell-level conclusions remain out of scope.

- `legal_core_labels.jsonl`: tender-clause and bid-standalone legality. These
  can be passed as `--labels-file` to the existing strict hierarchy runner.
- `pair_labels.jsonl`: provisional tender ↔ bid text matches for the isolated
  paired-text LLM route. No standalone statute is inferred from a tender term.
- `candidate_labels.jsonl`: all eligible labels for result binding. Unmatched
  or ambiguous bid-response candidates stay in `candidates.json` but are not
  sent to the pair reasoner or legal cascade.

All automatic matching is provisional. The `candidate_source_blocks` fraction
is a processing diagnostic, **not** item recall. `not_selected_for_semantic_review_block_ids`
and `unreadable_or_empty_physical_pages` make omission visible. A DOCX
paragraph/table locator is never presented as a physical page number.
Documents needing OCR are flagged for the existing conditional MinerU → local
coordinate OCR path; this candidate does not automatically send files to a
third party or promote unchecked OCR text into the high-trust index.
Matching requires independent textual overlap before a shared clause number
can boost a score. Identical section numbers alone cannot justify a paired
response or a potential non-response claim. The `addenda_inventory` and
`excluded_or_reference_only` manifest fields are preserved in intake and
separate Excel coverage rows; an unverified addendum inventory is never
silently called complete.

## Stage 2: existing core and human-review output

The strict-hierarchy runner now accepts `bundle_evidence` and
`review_task_kind` on legal candidates, puts the declared document set and
coverage into the runtime message, and appends a narrowly scoped legal-task
prompt. It refuses the bid-response task. The existing legal retrieval, LLM,
external fallback policy and deterministic gate are otherwise untouched.

`pair_reasoner.py` uses the **same DeepSeek model/client** only when someone
explicitly invokes `--execute-online` for an already paired issue. Its
independent source-binding gate distinguishes potential difference, limited
textual consistency and insufficient comparison. A valid textual comparison
is not a statement of legal compliance or full-bundle responsiveness. This
route does not cite a law unless a separate legal task supplied and admitted it.
The bounded pair-comparison request uses disabled extended thinking; the legal
reasoner configuration is unchanged. If the model returns exactly one complete
finding at the JSON root instead of under `findings`, a deterministic wrapper
may normalize that *shape only*. Both the raw response and normalization are
retained. `--replay-result FILE` rechecks a stored, source-bound response
offline without a new API call; it never fills missing fields or repairs
truncated content.

`assemble.py --bundle-output DIR --core-results LEGAL_DIR --pair-results
PAIR_DIR --output NEW.json --excel NEW.xlsx` binds results back to their exact
candidate and document hashes, preserves raw/gated results, adds coverage
notices and calls the existing human-review Excel exporter. Missing results
remain `not_run`; unpaired response candidates remain `not_eligible_unpaired`.
The assembler accepts a `three_layer_protocol` packet embedded in the same
core-result record, or the optional `--handoff-records FILE` for a separate
replay, but never both for one issue. It requires a complete raw three-layer
response and trusted context, validates exact task/source bindings and calls
the existing three-layer gate. The resulting claim
completion and handoff status is displayed **in addition to** the substantive
risk finding. No fabricated three-layer response is generated from a legacy
risk label. No `ready_for_*` handoff status means a correct legal judgement.
Automatic generation of a semantically valid three-layer packet is not yet
proven; without a packet, the handoff is visibly `not_available`.

## Automatic preliminary assessment, separately from legal sign-off

`auto_pre_review.py --bundle-output DIR --output-root NEW_DIR --mode plan`
builds an **offline** route inventory. `--mode summarize` can read existing
legal/pair result directories without an API call. Its JSON keeps three states
separate: whether the machine actually assessed the unit, what bounded
preliminary conclusion it returned, and whether a human has signed off.
Unrun, unresolved-pairing and blocked units are never counted as clean.
Only machine-assessed items carry `preliminary_findings` with quoted source,
locator, admitted basis, evidence boundary and suggested next check; unrun and
blocked items have an empty findings list, not a fabricated clean verdict.
`processable_candidate_execution_complete` is not whole-file completeness.

`--mode execute-online` dispatches approved issue IDs to the existing strict
legal runner or bounded pair reasoner. It requires `--source-manifest`,
`--approval-file` and a positive `--max-issues`; no batch API call occurs in
plan/summary modes. First run `--mode plan --source-manifest PATH` so original
PDF/DOCX hashes, project context, source quotes and pair quotes can be rebound.
For a bounded throughput/format pilot, `--mode propose-pilot` can create a
task-balanced, privacy-screened approval **candidate** (optionally from a
private list of exact issue IDs). This does not authorize network execution:
the exact excerpts and the `privacy_review_complete` flag require separate
review, and the secondary identifier screen is not a de-identification
guarantee. The pilot is not an accuracy sample or a whole-bundle assessment.
The approval JSON must declare `project_id`, the exact
`candidate_labels_sha256`, `source_manifest_sha256` from that plan, and
`approved: [{"issue_id": "...", "label_sha256": "..."}]`.
This is an exact-input guard, **not** a replacement for actual permission or
human verification of de-identification. A conservative numeric identifier
screen may block an approved label; it cannot prove a label contains no
personal data. Results are written per issue with a bounded audit; malformed
responses are quarantined rather than silently converted into success. Token
limits are recorded separately for legal-final (default 16384), legal-triage
(2048) and pair comparison (2048, thinking disabled). The optional external
fallback requires an allowlisted source manifest. `--max-issues` limits issue
dispatches, **not** internal LLM requests: one legal issue can involve several
triage/final calls and potentially a bounded external recheck.

The candidate dispatcher does not yet solve incomplete item discovery,
ambiguous cross-file matches or unseen-project accuracy. On a real file bundle
with thousands of candidates, a large API batch may be expensive; plan and
privacy-review the exact items before authorizing any network run. The existing
Excel exporter can then present gated findings, while the JSON summary
distinguishes machine-assessed items from pending work. The human final-signoff
column does not erase an already completed preliminary machine conclusion.

`WORKFLOW_ALIGNMENT_CANDIDATE_V1.md` is an unapproved design proposal for
aligning a broader construction-tendering work instruction with the currently
implemented three-check pipeline. It does not replace the active system prompt,
enable evaluation/cost-estimation modules or trigger further online calls.

Before any real online run, separately confirm what text may be sent to
DeepSeek/MinerU and what must be redacted. The offline tests never read a real
project or API key. `bundle_manifest.example.json` is intentionally
non-runnable until example files are supplied.
The legal runner and paired-text runner both require the additional
`--approve-bundle-transmission` flag for these bundle excerpts. This flag is a
technical acknowledgement, not a substitute for actual data authorization or
de-identification.

## Development verification and limits

Run the synthetic checks from this directory using a Python environment with
the Phase 2 dependencies:

    python -m unittest discover -s . -p 'test_*.py' -v

The fixed synthetic fixture has two annotated tender requirements. Discovery
found 2/2, and provisional pairing found the prewritten counterpart for 2/2.
These tiny numbers are **pipeline checks**, not real-project Recall@K, legal
accuracy, sensitivity, or evidence of time savings. Separate guards test a
blank PDF, an ambiguous match, a source-quote mismatch, a truncated model
response, a bound legacy risk result, and a valid supplementary three-layer
handoff. The existing Excel-export and three-layer regression suites should
also pass. Stage 3 unseen-project validation remains explicitly deferred.

Known limits: current discovery uses a conservative cue list and block-level
text; it can miss split clauses, tables, synonyms, attachments and issues
without cue words. Pairing is character-overlap plus clause-number matching,
with a number-only guard, not a verified semantic correspondence. An unpaired
item is a search/coverage gap, not evidence of omission. The legal-core dependencies and
embedding model must be present for online runs; they were not invoked in the
offline fixture. Legal applicability and final bid completeness still require
specialist review. An unavailable physical locator is never invented.
