# Public Phase 1 project report

## Purpose

Phase 1 is a small, evidence-grounded LLM/RAG prototype for procurement and
contract-document compliance pre-review. It was built to provide verifiable
LLM application evidence for a construction-domain research trajectory. It is
not presented as a completed building-permit assessment system.

Building permit assessment is the second-stage transfer-validation scenario.
The transferable object is the method for linking regulatory requirements to
traceable construction evidence, not the Chinese procurement law itself.

## Architecture

The pipeline is:

PDF/DOCX -> Baseline Parser -> quality gate -> conditional MinerU/PaddleOCR ->
source locator adapter -> four-level legal corpus -> BM25/dense/hybrid retrieval
-> evidence packet -> LLM reviewer -> deterministic schema/abstention gate ->
review table/Excel -> human second review.

The system distinguishes high-trust evidence, supplementary candidates,
unsupported-by-current-corpus states, insufficient information, and
requires-human-legal-review states. It never makes an automatic bid, award, or
disqualification decision.

## Gold set

The final synthetic gold set contains 60 manually adjudicated issue-level rows:
44 accepted, 16 insufficient-information review rows, 12 negative samples,
6 local-regulation examples, 2 supplement-only examples, 7 unsupported-by-current
corpus examples, and 2 multi-law examples. The 60 rows were derived from a
three-row confirmed set plus 57 candidate rows; adjudication accepted 56 and
revised 4.

## Retrieval results

The comparable benchmark uses 52 rows with usable legal-basis chunk IDs:

| Retriever | Recall@5 | MRR |
|---|---:|---:|
| BM25 | 86.5385% | 0.743590 |
| Dense embedding (BAAI/bge-small-zh-v1.5) | 71.1538% | 0.555067 |
| BM25 + dense hybrid | 90.3846% | 0.804029 |

Hybrid versus BM25 improved Recall@5 by 3.846 percentage points and MRR by
0.060439. The three-row early BM25 sanity check reached 100% Recall@5 and
1.000 MRR, but it is not comparable to the 60-row benchmark.

## Prompt and gate evolution

There were eight substantive prompt revisions from archived v1 to final v9:

1. evidence-grounded MVP and source boundary;
2. sequential Level 1-to-4 retrieval and OCR admission;
3. Level 2 human-legal-review precedence;
4. evidence-support/applicability confidence and Level 4 applicability;
5. lifecycle-aware compliance reasoning and negative-case protection;
6. formal review-table output and overall human-review status;
7. substantive assistant recommendation;
8. output contract, post-LLM gate and Excel-compatible delivery.

The deterministic gate checks schema, evidence boundaries, legal-level use,
applicability, supplement-only evidence, OCR quality, and the prohibition on
automatic legal decisions.

## MinerU/OCR result boundary

MinerU online API processing completed 24/24 chunk tasks for three authorised
Test2 PDFs and produced 2,186 OCR blocks. All 2,186 were held out by the
source-locator quality gate: zero high-trust blocks, zero supplementary-pool
blocks, and zero RAG-index updates. Therefore a valid end-to-end
hybrid+MinerU+OCR Recall/MRR has not yet been measured.

An earlier independent PaddleOCR smoke test on a separate public-standard
sample achieved 100% coordinate coverage for non-empty pages and 100% scored
smoke-token recall; this is feasibility evidence, not a Test2 end-to-end
result.

## Reproducibility and safety

This public package excludes real project documents, raw external-review
payloads, API keys, environment files, local model weights, and private runtime
logs. Use de-identified or synthetic input only. External retrieval requires
manual source confirmation. Overall output remains
requires_human_second_review.
