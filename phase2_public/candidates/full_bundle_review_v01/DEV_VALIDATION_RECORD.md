# Development verification record — candidate v0.1

Date: 2026-09-26. Scope: offline synthetic files only. No DeepSeek, MinerU,
PaddleOCR, external legal website, real tender/bid package or expert data was
used in these checks. Existing REAL45 is not reclassified as a held-out set.

The synthetic fixture contains two intentionally visible tender requirements,
two corresponding bid paragraphs and non-requirement filler. Against this
**fixed fixture annotation only**, the heuristic selected 2/2 required tender
paragraphs and its provisional top match pointed to the two written bid
counterparts (2/2). This demonstrates wiring and a small positive control,
not population recall, precision, legal accuracy or reliable semantic matching.

Negative/boundary checks exercised: missing final-submission declaration;
award-record role rejection; an ambiguous identical bid match; a blank PDF
whose physical page remains unreviewed and is excluded from the pair/LLM
route; a paired-response quote mismatch; a non-stop/truncated response;
synthetic mock gated-result binding; a manually constructed, valid three-layer
packet with source/task binding; and an Excel-readback with human-second-review
status. These binding tests do not demonstrate live legal reasoning or live
generation of the three-layer packet. The existing three-layer
protocol's 35 offline tests and the legacy Excel-export regression passed.

Unexecuted: neural/hybrid RAG loading, article retrieval, legal applicability,
DeepSeek reasoning on these bundle inputs, MinerU/PaddleOCR enhancement,
external fallback, real full-file item recall, professional judgement quality,
workload/time impact and independent-project validation. New labels and output
paths are candidate-only; no historic metrics or expert ratings were changed.

Acceptance decision for this development stage: the intake/route/assembly
interfaces can proceed to controlled specialist review, but the automatic
discovery and cross-file matching quality cannot yet be accepted as complete.
The next material gate is a manually enumerated review-item inventory for a
previously unseen construction project, which the user deferred as Stage 3.
