# QX30 approved repair v13 — formative readout

This is an opt-in repair candidate for a previously used development project. It does not overwrite v11/v12 results, does not use award or expert outcomes as model input, and is not an independent accuracy estimate. New private outputs are in separate ignored `.local_runs` directories.

## Scope and interventions

| Arm | Change | Result | Causal boundary |
|---|---|---|---|
| 2022 source-version overlay | Quarantine 61 chunks from a stale departmental-regulation source; admit three officially checked excerpts with the 2018 numbering as affected by the 2019 partial amendment | Three version-tagged Level-3 candidates; original corpus unchanged | This is deliberately incomplete. It must not be enabled as a full replacement source for other articles or years. |
| QX-U01 retrieval | Expand document-acquisition-duration queries without inserting a statutory article or answer; keep Level-2 retrieval separate | Local Article 16 absent from original Level-2 Top 5 and present in expanded Top 5 | Retrieval/hand-off correction, not a gate-only gain. |
| QX-U01 targeted online check | Add only the locally retrieved Level-2 Article 16 to the original sent inference input; reuse the v12 prompt, DeepSeek model and settings | HTTP 200, `finish_reason=stop`; delivered `no_supported_issue_found_within_review_scope`, cited Article 16; no stale Level-3 article cited | One previously used case. Original lower-level evidence and historical level-triage audit were retained and marked as such. No whole-project clearance. |
| QX-U28 text route | Compare locked tender/technical text pairs with source locators and offsets; no legal LLM call | 13/13 selected numeric/term pairs matched; `observed_within_supplied_scope`; human review required | Does **not** prove full-text equivalence, full bid responsiveness or legal compliance. The comparison is a separate non-legal route. |
| Four accepted alerts | Hash-check the frozen v12 deliverables for U12/U23/U25/U26 | All four remain delivered as human-review risk candidates | They are not confirmed violations. No model re-run was used to raise their apparent success rate. |

The one online call used 58,946 prompt tokens and 7,624 completion tokens. The long historical evidence packet is a cost/latency limitation, not a reason to omit relevant Article 16.

## Remaining five holds

| Unit | Typed cause | Safe next check |
|---|---|---|
| QX-U08 | Specific applicable qualification rule not established | Verify the specialist source and the project's applicability; general authorization is not the specific parameter rule. |
| QX-U13 | Operative tender condition / specific rule unresolved | Confirm final tender clause and any authoritative rule for the certificate-unit mismatch. |
| QX-U19 | Local extension notice and certificate coverage unverified | Independently verify issuing authority, 2022 temporal effect and whether the notice covers the particular certificate. A bid attachment cannot authenticate itself. |
| QX-U20 | OCR/field mapping problem | Recover the licence's actual start/end dates and verify the readable source before a time-coverage judgment. |
| QX-U21 | Decisive calculation base absent | Retrieve the **project estimate** relevant to Level-2 Article 26; total investment and the bid ceiling are not automatic substitutes. An older departmental article number must not be cited as current law. |

All five remain processing holds in the frozen output; none is auto-converted to legal U or N. QX-U07, the separately attested actual-upload legal U, is unchanged.

## Law-source boundary

The [2019 revised implementation regulation](https://fgw.beijing.gov.cn/fgwzwgk/2024zcwj/flfggz/fg/xzfg/202004/t20200421_3728866.htm) provides Article 16's minimum document-sale period and Article 26's bid-security base. The [2018 revised departmental regulation](https://fgw.beijing.gov.cn/fgwzwgk/2024zcwj/flfggz/gz/bmgz/202004/t20200416_3727856.htm) and [2019 partial amendment](https://zjw.beijing.gov.cn/bjjs/xxgk/543346069/543346064/325997378/index.shtml) support the three targeted numbering corrections. The superior Level-2 rule is not displaced by a similar-sounding lower-level provision. Other articles in the old source remain quarantined until full official re-ingestion and verification.

## Reproduction and release guard

The offline experiment is `experiments/qx30_approved_repair_v13_offline.py`; its complete U28 text-pair record is local only. The one-case online experiment is `experiments/qx30_u01_retrieval_retest_v13.py`; its preflight verifies the v12 prompt hash and the previously sent input hash. It calls `deepseek-v4-flash` only when explicitly run without `--offline-only`. Neither script reads reference answers, award records, expert scores, or original whole PDFs.

Run unit guards in `tests/test_qx_approved_repair_v13.py` and existing Phase-2 regression tests before activation. The version overlay, query expansion and text route are opt-in; broader production deployment still requires a complete dated law source and review of the five unresolved holds. Keep `.local_runs`, `.env` and raw tender/bid inputs out of GitHub.
