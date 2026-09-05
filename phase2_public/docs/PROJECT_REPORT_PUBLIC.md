# Phase 2 public project report

## Objective

Phase 2 strengthens a text-first LLM/RAG prototype that scans contract,
tendering and bidding materials, links reviewable facts to locatable regulatory
evidence and produces conservative findings for human second review. It does not
make automatic award, rejection, disqualification or final legal decisions.

## Architecture delivered

The document path combines a deterministic baseline parser, MinerU as a
conditional enhancement engine and coordinate OCR as backup. Parser output is
admitted only after checks for extraction completeness, critical numbers and
negations, physical-page or coordinate locators and backmatch coverage. MinerU
blocks with at least 80% coverage may enter the high-trust corpus. Unmapped blocks
from 60% to below 80% may enter a supplementary pool but cannot independently
support a legal conclusion. Lower-quality material is withheld for manual
structuring.

The retrieval path enforces Level 1 → Level 2 → Level 3 → Level 4 as executable
control flow. Within a level, hybrid retrieval combines lexical and dense scores;
authority and applicability are not replaced by semantic similarity. Level 4
requires confirmed location and project type. When the four-level local corpus is
exhausted, a bounded external fallback may discover or verify article-level
sources. Search snippets, industry information and unconfirmed local rules remain
non-independent evidence.

DeepSeek `deepseek-v4-flash` performs evidence-bounded reasoning. The final prompt
specifies five operational conclusion states, traceable evidence, evidence gaps,
substantive recommendations and mandatory human review. A deterministic gate
then normalises response channels, validates schema and evidence eligibility,
enforces abstention, marks over-alert conditions and blocks malformed core output.

## Prompt and gate development

Prompt development progressed from general evidence-grounded review to explicit
hierarchical retrieval, Level 2 and Level 4 applicability rules, five-state
abstention semantics, substantive human-review recommendations and dual Markdown/
Excel-ready output. The decisive reliability change was moving critical policy
from prompt prose into deterministic code: retrieval order, source admission,
conclusion vocabulary and post-generation schema checks are now executable
constraints rather than model suggestions.

## Evaluation record

The flat retrieval baseline improved from BM25 Recall@5 86.5385% and MRR 0.743590
to hybrid Recall@5 90.3846% and MRR 0.804029. A later strict hierarchy benchmark
reported 98.08% Evidence Hit@5 and 0.9135 MRR within the expected level/phase on
52 supported synthetic issues. These two experimental definitions are reported
separately and must not be presented as a single continuous performance curve.

The final offline replay on the frozen 60-item synthetic set produced 49/60
three-class agreement (81.67%), macro-F1 0.8121, three false alerts among twelve
expected no-issue items and one safely blocked malformed response. Complete
runtime evidence packets were absent from the derived replay files, so grounding
precision/recall and unsupported-citation rate were withdrawn rather than inferred.

## Gold set and real-project boundary

The 60-item set is synthetic and supports controlled development testing across
positive risks, negative samples, insufficient information, local applicability,
supplement-only material, no applicable corpus evidence and multiple-law cases.
It is not 60 real projects. Real documents are retained privately and are evaluated
as separate review units. A future expert study should first obtain independent
ratings, then reveal frozen AI output for accepted/revised/rejected reassessment.

## Current limitations

- the synthetic set was used during development and is not a fully independent hold-out;
- strict and flat retrieval metrics have different ranking scopes;
- full-document locator admission is incomplete for some real source files;
- external evidence still requires article capture and human confirmation;
- the final gate corrects many structural fields, showing that raw model output is
  not yet suitable for direct delivery;
- legal interpretation and professional responsibility remain human tasks.

## Phase 2 next steps

The next evidence-generating work is to freeze a separate coverage/control or
hold-out set, preserve complete runtime evidence packets for grounding evaluation,
complete high-trust document admission and conduct the ethics-gated expert study.
