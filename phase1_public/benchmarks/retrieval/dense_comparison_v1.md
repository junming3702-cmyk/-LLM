# Dense embedding / hybrid retrieval comparison v1

本次运行使用60条 final synthetic gold issues、678个本地法规chunks和模型 `BAAI/bge-small-zh-v1.5`（维度 512）。

## Summary

| Mode | Supported cases | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | Unsupported/abstention cases |
|---|---:|---:|---:|---:|---:|---:|---:|
| lexical_bm25 | 52 | 0.635 | 0.827 | 0.865 | 0.923 | 0.744 | 8 |
| dense_embedding | 52 | 0.423 | 0.673 | 0.712 | 0.827 | 0.555 | 8 |
| hybrid_bm25_dense_embedding | 52 | 0.731 | 0.827 | 0.904 | 0.962 | 0.804 | 8 |

## Interpretation boundary

本报告比较本地 BM25、dense embedding 和带法规层级权重的 hybrid ranking。外部检索未调用，人工审查闭环未调用；gold evidence 只用于离线评价。
