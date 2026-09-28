# Phase 2 public release

Phase 2 is the current, model-only development line. It consolidates the work
performed after the Phase 1 baseline without publishing application materials,
real tender files, private API payloads, local cache paths or credentials.

## What changed

1. Retrieval is an executable hierarchy rather than metadata-only ranking.
   Level 1 is evaluated before Level 2, Level 2 before Level 3 and Level 3 before
   Level 4. The runner proceeds downward only when the current level yields no
   usable supported issue. Supplement-only evidence cannot stop the cascade.
2. Level 4 evidence is gated by confirmed jurisdiction and project type. A
   geographically local rule without the required context remains low-confidence
   and cannot independently support a legal conclusion.
3. External retrieval is a one-shot recheck rather than a blocking prerequisite.
   The runner first produces a gated, local-only preliminary decision. Only
   `insufficient_information_needs_human_confirm` triggers one external discovery
   call. Article-level evidence must still pass provenance and human admission
   before it can change the conclusion; pending, failed, no-hit, manifest-only or
   unverified results preserve the information-insufficient conclusion.
4. Document ingestion uses a main/backup pattern: deterministic baseline parser,
   MinerU API for documents already marked `needs_human_review`, and coordinate
   OCR as the backup when MinerU remains incomplete. Locator quality controls
   admission to the retrieval corpus.
5. DeepSeek `deepseek-v4-flash` remains the application reasoning model. A
   deterministic post-LLM gate normalises response channels, repairs safe schema
   defects, blocks unsafe outputs and keeps every deliverable under human review.
   Active Prompt v11 and recommendation contract v3 require every risk
   recommendation to show the located contract text, the admitted legal
   requirement, their concrete difference, and the recommended human action.
6. The approved QX30 repairs are now in the active runtime: a locked
   clause-design question compares conditional legal effects rather than word
   overlap or hypothetical future conduct; a legal U requires an independently
   audited decisive task-bound gap; transport, schema and source-processing
   failures stay in separate hold classes. The active full-file addendum uses
   the same professional legal-effect and three-layer gap vocabulary as the
   gate. The answer-free duration query expansion is enabled by default.
7. A known outdated Level-3 source is quarantined for all dates. With an
   explicit 2022 project date, only three checked replacement articles are
   admitted, not the full regulation. Without a verified matching date, no
   replacement is admitted. Source-version coverage is recorded in the run
   audit; missing coverage is not counted as a no-issue finding.
8. Explicit tender-to-bid textual response questions can use a separate,
   bounded two-source comparison path. Matching selected numbers alone cannot
   assert full textual identity or legal sufficiency. Differences go to human
   review and never become automatic legal violations.

## Operational result states

- `requires_human_legal_confirm`: strong, locatable legal and factual support;
- `requires_human_legal_review`: a supported potential risk still requiring
  professional interpretation;
- `insufficient_information_needs_human_confirm`: relevant material exists but
  decisive facts, applicability or documents are missing;
- `no_applicable_legal_basis_found_needs_human_confirm`: the admitted local and
  external search found no applicable article-level basis;
- `no_supported_issue_found_within_review_scope`: the reviewed material does not
  support the alleged issue within the stated scope.

Every state retains `requires_human_second_review` as the overall delivery status.

## Repository layout

- `src/`: ingestion, strict retrieval, external fallback, LLM response parsing,
  deterministic gate, evaluation and Excel export;
- `tests/`: offline gate, parser and external-fallback regression tests;
- `prompts/system_prompt_final.md`: active v11 reasoning and output contract;
- `prompts/bundle_professional_addendum_final.md`: active full-file
  professional review and typed-gap addendum;
- `skill/evidence-grounded-contract-review/SKILL.md`: reusable operator skill
  for the active legal core and the explicitly opt-in full-bundle route; its
  references distinguish the two V1 design documents from code already
  implemented and tested;
- `data/gold/`: the frozen 60-item synthetic development set and schemas;
- `data/law/`: four-level and external-source manifests;
- `data/rag/`: a public corpus sample and instructions for building a local corpus;
- `candidates/evidence_lineage_v01/`: opt-in, offline source-to-citation
  diagnostics and pre-inference task/evidence checks; not production-enabled;
- `candidates/full_bundle_review_v01/`: isolated whole-file-package intake,
  candidate discovery, tender-to-bid matching, legal/pair reasoning routes and
  human-review assembly. Development-fixture checks only; not independently
  validated or production-enabled;
- `candidates/qx30_approved_repair_v13/`: frozen formative readout that
  preceded the active promotion. It records source-date/numbering, Level-2
  evidence delivery, narrow text comparison, unchanged risk alerts, and typed
  remaining holds. Private QX excerpts and API responses are not included;
- `evaluation/`: benchmark summaries and the separate expert-review protocol;
- `evaluation/reasoning/full60_one_shot_external_recheck_protocol_v1.md`: the
  active 60-item external-recheck sequence and audit contract;
- `docs/PROJECT_REPORT_PUBLIC.md`: Phase 2 project record and evidence boundaries.

## Local setup

1. For an offline public regression, use the one-command procedure below;
   no API key, private project or downloaded model weight is needed.
2. For optional online use, copy `.env.example` to `.env`; add credentials only
   to the local untracked file. Do not commit, print or share the key.
3. For an actual retrieval run, place legally redistributable extracted sources under `law_extracted/` and run
   `src/build_rag_index.py`, or set `RAG_CORPUS_FILE` to an existing local corpus.
4. Set `EMBEDDING_MODEL_CACHE` to a local SentenceTransformers cache. The strict
   retriever fails closed rather than silently downloading a different model.
5. Run the offline regression before any API execution.

## One-command public offline reproduction

Prerequisite: Python 3.10 or newer with `venv` and `pip`; on the first run,
network access and space for the packages in `requirements.txt` are needed.
From the repository root, run one command:

```powershell
python phase2_public/reproduce_offline.py
```

On first use, the script creates an ignored `phase2_public/.venv` and installs
the listed dependencies. It then runs the active core tests and full-bundle
fixture tests. A successful run prints `PASS: public offline regression`;
at this revision, the expected counts are **97 core + 28 bundle = 125 tests**.
It prints the active Prompt's SHA-256 so runs can be tied to a specific file.
Subsequent runs reuse the local environment. With dependencies already
installed in a different Python environment, use:

```powershell
python phase2_public/reproduce_offline.py --no-install --python "PATH_TO_PYTHON"
```

This command makes **no DeepSeek, MinerU, OCR-provider or external-law API
call**, does not require `.env`, and does not load private QX30 files. It is a
one-command *functional regression*, not a reproduction of published
retrieval scores, real-project outcomes or professional review results. The
public corpus file is a schema sample, not the full local legal corpus; see
`data/rag/README.md`. Full QX30 reproduction additionally requires the
restricted original inputs, admissible source versions, local embedding
snapshot, API authorization and a separately recorded run. Do not substitute
award status for a legal ground truth.

## Reusable skill and real-run boundary

The installable skill package is
[`skill/evidence-grounded-contract-review/`](skill/evidence-grounded-contract-review/SKILL.md).
Its [runbook](skill/evidence-grounded-contract-review/references/RUNBOOK.md)
provides the offline one-command check and the **separate**, permission-gated
steps for bundle intake, conditional MinerU/OCR, task routing, legal/pair
reasoning and Excel assembly. The
[V1 alignment ledger](skill/evidence-grounded-contract-review/references/V1_ALIGNMENT_AND_STATUS.md)
records which parts of the user-supplied full-workflow and compliance-mode V1
instructions are active, candidate-only or still unimplemented. Copy the
entire skill directory into a Codex skills directory if local skill activation
is desired, and keep this repository checkout available for its code and active
prompts. The skill package is not a standalone copy of the model; copying it
does not enable online API execution.

The full-bundle entry point currently uses block/cue discovery and provisional
tender-to-bid matching. It is useful for a controlled preliminary review, not
proof of exhaustive issue discovery or whole-file legal accuracy. Addenda
remain an inventory rather than fully integrated effective-version text.
Unreviewed pages, unresolved pairs and processing holds must remain visible.

The source code accepts `MODEL_PHASE_ROOT`, `RAG_CORPUS_FILE`,
`EMBEDDING_MODEL_CACHE`, `GOLD_LABELS_FILE`, `SYSTEM_PROMPT_FILE`,
`PROJECT_CONTEXT_FILE`, `EXTERNAL_SOURCE_MANIFEST` and `MODEL_ENV_FILE` as local
configuration variables. No private absolute path is embedded in the public code.

## Evidence boundary

The 60 synthetic issues are a development benchmark, not 60 real projects and
not an independently adjudicated legal-verdict dataset. The real-project branch
is retained privately and is not mixed into synthetic metric denominators. Expert
validation remains a separate, ethics-gated study.

The QX30 risk candidates U12, U23, U25 and U26 were approved for **human
review**, not established as final violations. U01's Level-2 basis and U28's
bounded text comparison no longer default to a legal-U route. The five
remaining holds U08, U13, U19, U20 and U21 are not automatically changed to
`no_supported_issue_found_within_review_scope`. Promotion was checked with
offline regression tests; no new independent effectiveness or complete-file
accuracy estimate follows from it. Existing result files are not overwritten.
