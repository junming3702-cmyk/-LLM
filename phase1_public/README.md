# Phase 1 public implementation package

## Research purpose

This package demonstrates an evidence-grounded LLM/RAG workflow for
procurement-document compliance pre-review. Its transferable research object is
the mechanism that links regulatory requirements to traceable evidence in
complex construction documents. The procurement-law task is not presented as a
building-permit system.

Building-permit assessment is a proposed second-stage transfer-validation
scenario: the same evidence-linking, provenance, abstention, and human-review
mechanisms can later be evaluated against drawings, BIM information, and permit
application materials.

## System contract

Input: de-identified contract/tender/bid excerpts plus project context.

Output: a review table containing the excerpt, conclusion, risk category,
substantive assistant recommendation, legal basis, evidence boundary,
confidence, human handling recommendation, and the fixed overall state
requires_human_second_review.

The model must not issue an automatic award, disqualification, or final legal
decision.

## Run order

1. Ingest PDF/DOCX into Markdown and locator records.
2. Apply extraction-quality and source-locator gates.
3. Retrieve legal evidence sequentially by Level 1, Level 2, Level 3, and
   Level 4 applicability, with S2 material kept supplementary.
4. Compare BM25, dense, and hybrid retrieval when benchmarking.
5. Build an evidence packet.
6. Optionally call an LLM using a locally configured API key.
7. Parse reasoning_content first when it contains valid JSON; otherwise use
   content.
8. Apply the deterministic post-LLM schema/abstention gate.
9. Export Markdown/JSON for human review and optionally build an Excel copy
   locally.

## API policy

The public code reads credentials from environment variables only. API keys
must never be written into source files, runtime inputs, logs, notebooks,
manifests, or Git history. See .gitignore, .env.example, and SECURITY.md.
