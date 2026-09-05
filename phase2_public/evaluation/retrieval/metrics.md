# Retrieval benchmark record

## Historical flat-corpus baselines

Measured on 52 scorable supported issues from the frozen 60-item synthetic set:

| Retriever | Recall@5 | MRR |
|---|---:|---:|
| BM25 | 86.5385% | 0.743590 |
| Dense embedding | 71.1538% | 0.555067 |
| BM25 + dense hybrid | 90.3846% | 0.804029 |

## Phase 2 strict hierarchy benchmark

| Metric | Result |
|---|---:|
| Supported Level 1–4 issues | 52 |
| Unsupported/abstention issues | 8 |
| Hierarchical Evidence Hit@1 | 84.62% |
| Hierarchical Evidence Hit@3 | 98.08% |
| Hierarchical Evidence Hit@5 | 98.08% |
| Hierarchical Evidence Hit@10 | 100.00% |
| MRR within expected level/phase | 0.9135 |
| Pool-normalised nDCG@5 | 0.9250 |

The strict benchmark ranks evidence within the expected normative level and
retrieval phase. It is not directly interchangeable with the historical flat
metric. No Recall@5 or MRR increase is attributed to MinerU/OCR because those
branches were evaluated as document-admission mechanisms, not as an end-to-end
retrieval benchmark.
