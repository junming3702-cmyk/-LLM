# Phase 1: Evidence-Grounded LLM/RAG Compliance Review

This repository contains a public, reproducible release of the Phase 1 model
architecture developed as a capability demonstration for construction-domain
LLM/RAG research.

The system reviews procurement and contract-document excerpts against a
hierarchical legal corpus. It returns traceable evidence, an evidence boundary,
an abstention state when support is insufficient, and a recommendation for
human second review. It does not make an automatic bid/win/disqualification
decision and is not legal advice.

## Public release

The implementation and research artifacts are under the phase1_public folder:

- ARCHITECTURE.md: system components and control flow.
- src/: ingestion, retrieval, response parsing, deterministic gate, and
  MinerU source-locator adapter.
- prompts/system_prompt_final.md: final v9 output contract and reasoning rules.
- data/gold/: the 60-row synthetic gold set and annotation contracts.
- data/law/: legal-source hierarchy and external-fallback manifest.
- benchmarks/: retrieval metrics and model-behaviour summaries.
- experiments/design_revision_boq_fpa/: a deterministic 24-case pilot of
  forced-provenance attribution for design-revision-to-BoQ mapping.
- docs/PROJECT_REPORT_PUBLIC.md: public project report.

The repository intentionally excludes real project documents, full external
review payloads, private paths, API keys, .env files, local model weights, and
generated runtime outputs. The historical archive directory from the previous
backup is retained separately and is not the preferred runnable entrypoint.

## Quick start

Create a local environment and install phase1_public/requirements.txt. Copy
.env.example to .env and fill credentials locally; never commit it. Supply law
text that you are permitted to use, then run the ingestion and retrieval
scripts with local paths. The included corpus sample and synthetic gold set are
for smoke testing and schema inspection.

## Measured benchmark

On 52 scorable issues from the 60-row synthetic gold set:

| Retriever | Recall@5 | MRR |
|---|---:|---:|
| BM25 | 86.5385% | 0.743590 |
| Dense embedding | 71.1538% | 0.555067 |
| BM25 + dense hybrid | 90.3846% | 0.804029 |

These are local text-retrieval results. MinerU and OCR are conditional document
ingestion enhancements; a final end-to-end OCR retrieval metric must only be
reported after OCR blocks pass physical source-locator quality gates.

## Design-revision-to-BoQ experiment

The public experiment compares an unconstrained lexical mapper (M1) with the
same mapper plus a forced-provenance attribution gate (M2) on 24 deliberately
constructed synthetic cases. M2 accepted six explicitly supported mappings and
abstained on 18 ambiguous, conflicting or insufficient-evidence cases. In this
fixed mechanism pilot, unsupported attribution fell from 18/24 accepted M1
outputs to 0/6 accepted M2 outputs, while overall coverage fell from 1.00 to
0.25. These results demonstrate gate behaviour, not real-project performance or
generalisation.

See `phase1_public/experiments/design_revision_boq_fpa/README.md` for the exact
reproduction commands, metrics and limitations.

## Safety and scope

Use only de-identified or synthetic inputs. External retrieval results require
manual confirmation and provenance recording. Keep the overall state as
requires_human_second_review.
