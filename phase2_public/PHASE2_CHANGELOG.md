# Phase 2 development record

All post-Phase 1 model development is recorded here as Phase 2. Historical local
execution labels such as “Stage 1”, “Stage 2” and “Stage 3” are internal Phase 2
milestones and do not create additional public product phases.

## 2026-09-05 — Phase 2 release baseline

- froze the active prompt and five-state conclusion contract;
- implemented strict Level 1–4 retrieval control flow and Level 4 applicability;
- added bounded external discovery/verification fallback;
- retained baseline parser → MinerU → coordinate OCR as a gated main/backup chain;
- hardened JSON response-channel selection and deterministic post-LLM gating;
- completed the frozen 60-item offline replay and corrected unsupported grounding
  metrics to `Not evaluated` where complete runtime context was absent;
- added an Excel-ready review export and a separate expert blind-review protocol;
- separated public model artifacts from private real-project materials;
- relocated the active Git worktree and local model cache to the E-drive workspace.

## 2026-09-05 — Stage 3 recommendation contract v3

- promoted the approved system prompt from v9 to final v10;
- added a mandatory `fact_law_comparison` for risk findings;
- rebuilt recommendations in the order contract evidence → admitted legal
  requirement → concrete difference → human-review action;
- limited definite “不符合” wording to trusted runtime-confirmed relations and
  retained qualified “可能不符合” wording for potential risks;
- normalised Arabic and Chinese article-number forms such as `第23条` and
  `第二十三条` before unsupported-citation checks;
- retained the five-state conclusion contract and mandatory human second review.

## Pending work

- create an independently sampled hold-out or coverage/control set;
- bind complete runtime evidence packets before reporting citation-grounding metrics;
- complete high-trust document admission for real-project source pages;
- run the ethics-gated expert study on real review units;
- evaluate transfer to an additional approval/compliance domain without changing
  the Phase 2 tender-review benchmark denominator.
