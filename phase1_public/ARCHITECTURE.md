# Phase 1 final application architecture

~~~text
PDF / DOCX / de-identified project excerpt
                  |
                  v
DocumentIngestor
  +-- Baseline Parser: deterministic text and source locator
  +-- extraction-quality gate
  +-- MinerU API: conditional OCR/layout enhancement
  +-- PaddleOCR: candidate coordinate-OCR branch
                  |
                  v
source-locator adapter
  +-- document manifest
  +-- Markdown document
  +-- locator map
  +-- extraction quality record
                  |
                  v
quality gate
  +-- backmatch >= 80%: high-trust retrieval corpus
  +-- 60-80% Unmapped: supplementary candidate pool only
  +-- incomplete locator/critical-token loss: human review
                  |
                  v
four-level legal corpus + S2 supplementary material
  +-- Level 1: laws
  +-- Level 2: administrative regulations
  +-- Level 3: departmental regulations and technical supplements
  +-- Level 4: local regulations subject to location/type applicability
  +-- S2: standards/practice material, never sole legal basis
                  |
                  v
sequential hierarchy-aware retrieval
  +-- BM25 lexical retrieval
  +-- dense embedding retrieval
  +-- BM25+dense hybrid reranking
                  |
                  v
EvidencePacketBuilder
                  |
                  v
LLMReviewer
                  |
                  v
deterministic post-LLM schema/abstention gate
                  |
                  v
review_table / table_markdown / JSON / local Excel export
                  |
                  v
HumanReviewRecord
  overall state: requires_human_second_review
~~~

## Design principles

1. Retrieval relevance cannot override legal hierarchy or applicability.
2. A retrieved provision is not, by itself, proof of a violation.
3. Missing evidence is not proof that the underlying fact is absent.
4. Local authoritative sources are primary; external results are fallback or
   verification inputs and require manual confirmation.
5. Low-quality OCR is retained as a review candidate, not silently promoted.
6. LLM reasoning is advisory and is mechanically checked before delivery.
