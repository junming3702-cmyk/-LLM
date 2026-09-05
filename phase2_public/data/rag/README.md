# RAG corpus data

`corpus_chunks_public_sample.jsonl` demonstrates the public chunk schema. It is
not the full 678-chunk local legal corpus and cannot reproduce the reported
benchmark by itself.

To run the strict retriever, build `corpus_chunks.jsonl` from law text that you
are permitted to use, or point `RAG_CORPUS_FILE` to an existing local corpus.
Preserve title, article, source locator, normative level, source role, evidence
eligibility, version/status metadata and file hash for every chunk.
