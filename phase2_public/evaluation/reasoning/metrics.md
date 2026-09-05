# Frozen 60-item reasoning replay

The replay applies the final deterministic gate to saved responses from
`deepseek-v4-flash`; it makes no new API calls.

| Metric | Result |
|---|---:|
| Issues scored | 60 |
| Deliverable after gate | 59 |
| Safely blocked | 1 |
| Three-class exact agreement | 49/60 (81.67%) |
| Three-class macro-F1 | 0.8121 |
| Risk precision / recall / F1 | 0.8485 / 0.8485 / 0.8485 |
| No-supported-issue precision / recall / F1 | 1.0000 / 0.6667 / 0.8000 |
| Insufficient-information precision / recall / F1 | 0.7222 / 0.8667 / 0.7879 |
| Over-alert rate on expected no-issue items | 3/12 (25.00%) |
| Parseable final JSON | 60/60 |
| Pre-gate core schema valid | 59/60 |
| Final truncation rate | 0% |

The immutable gold supports three comparison classes only. It does not support
five-state subclass accuracy or independently adjudicated legal correctness.
Grounding precision/recall and unsupported-citation rate are not reported for
this replay because the derived files do not retain complete runtime evidence
packets. Missing runtime context must not be interpreted as missing evidence.
