# Synthetic gold set

contract_review_final_synthetic_gold_v1.jsonl contains 60 manually adjudicated
synthetic issue-level examples. It includes negative samples, insufficient
information, local-regulation applicability, supplement-only evidence,
unsupported-by-corpus cases, and multi-law cases.

The set is a regression and retrieval benchmark, not a collection of real
procurement records and not legal advice. The 52 rows with legal-basis chunk
IDs are used for evidence-retrieval Recall/MRR scoring; rows without a usable
legal basis are retained as abstention cases.
