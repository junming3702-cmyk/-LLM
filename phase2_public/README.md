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
   Prompt v10 and recommendation contract v3 additionally require every risk
   recommendation to show the located contract text, the admitted legal
   requirement, their concrete difference, and the recommended human action.

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
- `prompts/system_prompt_final.md`: active reasoning and output contract;
- `skill/evidence-grounded-contract-review/SKILL.md`: the same policy organised
  as a reusable skill;
- `data/gold/`: the frozen 60-item synthetic development set and schemas;
- `data/law/`: four-level and external-source manifests;
- `data/rag/`: a public corpus sample and instructions for building a local corpus;
- `evaluation/`: benchmark summaries and the separate expert-review protocol;
- `evaluation/reasoning/full60_one_shot_external_recheck_protocol_v1.md`: the
  active 60-item external-recheck sequence and audit contract;
- `docs/PROJECT_REPORT_PUBLIC.md`: Phase 2 project record and evidence boundaries.

## Local setup

1. Create a Python environment and install `requirements.txt`.
2. Copy `.env.example` to `.env`; add credentials only to the local untracked file.
3. Place legally redistributable extracted sources under `law_extracted/` and run
   `src/build_rag_index.py`, or set `RAG_CORPUS_FILE` to an existing local corpus.
4. Set `EMBEDDING_MODEL_CACHE` to a local SentenceTransformers cache. The strict
   retriever fails closed rather than silently downloading a different model.
5. Run the offline tests before any API execution.

The source code accepts `MODEL_PHASE_ROOT`, `RAG_CORPUS_FILE`,
`EMBEDDING_MODEL_CACHE`, `GOLD_LABELS_FILE`, `SYSTEM_PROMPT_FILE`,
`PROJECT_CONTEXT_FILE`, `EXTERNAL_SOURCE_MANIFEST` and `MODEL_ENV_FILE` as local
configuration variables. No private absolute path is embedded in the public code.

## Evidence boundary

The 60 synthetic issues are a development benchmark, not 60 real projects and
not an independently adjudicated legal-verdict dataset. The real-project branch
is retained privately and is not mixed into synthetic metric denominators. Expert
validation remains a separate, ethics-gated study.
