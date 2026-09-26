# Full-bundle construction tendering review, candidate v0.1

Status: isolated Phase 2 development candidate. The frozen REAL45, QX, expert
ratings and existing production outputs are unchanged. This package has **not**
been independently validated on a previously unseen complete project.

`ACCEPTANCE_CONTRACT.md` fixes the system's intended input, two tasks / three
checks, deliverable and safety boundary. The manifest is explicit so that an
award/evaluation record cannot be silently mixed into the original tender or
final bid. This is a human pre-review aid, never an automatic bid decision.

## Stage 1: offline intake and discovery

`bundle_review.py --manifest PATH --output-root NEW_EMPTY_DIRECTORY` ingests
only the declared PDF/DOCX files through the existing `DocumentIngestor`.
It creates original-hash-bound locator maps, extraction quality records,
`candidates.json`, `coverage.json` and three label streams. No API is called.

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

`assemble.py --bundle-output DIR --core-results LEGAL_DIR --pair-results
PAIR_DIR --output NEW.json --excel NEW.xlsx` binds results back to their exact
candidate and document hashes, preserves raw/gated results, adds coverage
notices and calls the existing human-review Excel exporter. Missing results
remain `not_run`; unpaired response candidates remain `not_eligible_unpaired`.
The optional `--handoff-records FILE` takes complete raw three-layer protocol
responses plus their trusted contexts, validates the exact task/source
bindings and calls the existing three-layer gate. The resulting claim
completion and handoff status is displayed **in addition to** the substantive
risk finding. No fabricated three-layer response is generated from a legacy
risk label. No `ready_for_*` handoff status means a correct legal judgement.

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
not a verified semantic correspondence. The legal-core dependencies and
embedding model must be present for online runs; they were not invoked in the
offline fixture. Legal applicability and final bid completeness still require
specialist review. An unavailable physical locator is never invented.
