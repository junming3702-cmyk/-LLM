# Evidence-Grounded LLM/RAG Compliance Review

This repository contains public, reproducible releases of an evidence-grounded
LLM/RAG architecture for construction-procurement compliance review.

The system reviews procurement and contract-document excerpts against a
hierarchical legal corpus. It returns traceable evidence, an evidence boundary,
an abstention state when support is insufficient, and a recommendation for
human second review. It does not make an automatic bid/win/disqualification
decision and is not legal advice.

## Public releases

The Phase 1 baseline remains under `phase1_public/`. The current development
line is under `phase2_public/`.

### Phase 2 — current

Phase 2 consolidates all post-baseline engineering and evaluation work:

- strict Level 1 → Level 2 → Level 3 → Level 4 cascade retrieval enforced in code;
- Level 4 jurisdiction and project-type applicability gates;
- local-corpus exhaustion followed by an auditable external fallback;
- baseline parsing with MinerU as the conditional enhancement path and
  coordinate OCR as the backup path;
- a deterministic post-LLM schema, abstention, evidence and recommendation gate;
- five operational result states, all subject to human second review;
- JSON/Markdown outputs plus an Excel-ready review export;
- a 60-item synthetic development benchmark and a separate expert-review protocol.

Start with [`phase2_public/README.md`](phase2_public/README.md).

### Phase 1 — frozen baseline

The original implementation and research artifacts remain under the
`phase1_public/` folder:

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
review payloads, private paths, API keys, `.env` files, local model weights and
generated runtime outputs. The historical archive directory from the previous
backup is retained separately and is not a supported runnable entry point.

## Quick start

For the current version, create a local environment and install
`phase2_public/requirements.txt`. Copy `.env.example` to `.env` and fill
credentials locally; never commit it. Supply law text that you are permitted to
use and build a local corpus. The included corpus sample and synthetic gold set
are for smoke testing and schema inspection.

## Frozen retrieval benchmarks

On 52 scorable issues from the 60-row synthetic gold set:

| Retriever | Recall@5 | MRR |
|---|---:|---:|
| BM25 | 86.5385% | 0.743590 |
| Dense embedding | 71.1538% | 0.555067 |
| BM25 + dense hybrid | 90.3846% | 0.804029 |

The Phase 2 strict-cascade benchmark reported 98.08% hierarchical Evidence
Hit@5 and 0.9135 MRR within the expected level/phase on 52 supported synthetic
issues. This metric is not directly interchangeable with the flat-corpus table
above. MinerU and OCR remain conditional document-ingestion enhancements; no
end-to-end OCR recall improvement is claimed without physical-locator admission.

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
`requires_human_second_review`. This project is decision support, not legal
advice and not an automatic award, rejection or disqualification system.
