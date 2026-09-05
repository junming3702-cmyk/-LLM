# Phase 2 architecture

## End-to-end flow

```text
PDF/DOCX input
  ↓
Baseline parser ── needs_human_review ──→ MinerU API
  │                                      ↓ unresolved
  │                                coordinate OCR backup
  └──────────────────────────────┬───────────────┘
                                 ↓
                  locator and extraction quality gate
                                 ↓
              admitted text blocks + source locators
                                 ↓
       Level 1 → Level 2 → Level 3 → Level 4 retrieval
                                 ↓ local exhaustion / verification need
                  article-level external fallback
                                 ↓
                   deepseek-v4-flash reasoning
                                 ↓
      deterministic schema/evidence/abstention/recommendation gate
                                 ↓
          JSON + Markdown + Excel-ready human-review record
```

## Document admission

- Baseline parsing is the default and preserves deterministic text and locators.
- MinerU is a conditional cross-parser for documents already failing the baseline
  quality check; it is not a universal replacement parser.
- Coordinate OCR is the backup path for unresolved image-based pages.
- Backmatch coverage of at least 80% is eligible for the high-trust corpus.
- Coverage from 60% to below 80% may enter a supplementary candidate pool only
  when the block is unmapped. It cannot act as independent legal evidence and any
  dependent answer must be escalated.
- Coverage below 60%, missing physical locators, critical-number/negation loss or
  unresolved page mapping requires manual structuring.

## Legal retrieval and applicability

The four levels are searched sequentially, not globally blended:

1. Level 1 — laws;
2. Level 2 — administrative regulations;
3. Level 3 — departmental regulations, with technical/practice material kept in
   a separate supplementary role;
4. Level 4 — local regulations and standard documents, subject to confirmed
   project location and type.

Within each eligible level the default hybrid score uses BM25 0.60 and dense
retrieval 0.40. The hierarchy is a control-flow constraint: semantic similarity
cannot promote a lower-authority or supplementary passage above an unresolved
higher-level decision.

## External fallback

External retrieval is bounded by an allow-listed source manifest, query
sanitisation, network and redirect controls, provenance capture and article-level
admission. A search result or page title is not legal evidence. Local rules found
externally follow the same Level 4 applicability logic.

## Deterministic post-LLM gate

The gate validates the response schema, conclusion vocabulary, source locators,
evidence eligibility, legal-element coverage, abstention conditions, substantive
recommendations and human-review status. Safe metadata can be normalised; missing
or contradictory core reasoning is blocked rather than invented.
