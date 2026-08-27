# Candidate enhancement stability experiment — result

**Status:** completed; no embedding, LLM, RAG write or external fallback was executed.

## A. PaddleOCR coordinate OCR

| Page | Text lines | Chars | Coordinate coverage | Smoke-token recall | Blank preserved |
|---:|---:|---:|---:|---:|---:|
| 2 | 0 | 0 | 0.0% | — | PASS |
| 5 | 24 | 729 | 100.0% | 100.0% | — |
| 320 | 5 | 120 | 100.0% | 100.0% | — |

- Minimum non-empty-page coordinate coverage: **100.0%**
- All non-empty lines have coordinates: **True**
- Scored smoke-token recall: **100.0%**
- Blank page false-recovery check: **PASS**
- Human confirmation: **pending**; the smoke-token set is an analyst-curated technical check, not a legal adjudication.

## B. DOCX → formatted PDF → MinerU API

| Chunk | Original pages | Blocks | Backmatch | Blocked | Critical-token recall |
|---|---:|---:|---:|---:|---:|
| chunk-002-pages-0021-0040.pdf | 21-40 | 222 | 79.7% | 45 | 100.0% |
| chunk-005-pages-0081-0100.pdf | 81-100 | 17 | 64.7% | 6 | — |
| chunk-007-pages-0121-0140.pdf | 121-140 | 25 | 60.0% | 10 | 100.0% |

- Minimum selected-chunk backmatch: **60.0%**
- All selected chunks meet 80% threshold: **False**
- Scored critical-token recall against formatted-PDF text: **100.0%**
- Blocked-reason completeness: **100.0%**
- Source-identity preservation: **True**

## Gate decision

Both branches remain candidate enhancements. PaddleOCR passes the coordinate/blank-page smoke checks but remains human-review gated. The selected MinerU chunks include 65% and 60% backmatch cases, so the branch remains `needs_human_review` and cannot be promoted to RAG.
