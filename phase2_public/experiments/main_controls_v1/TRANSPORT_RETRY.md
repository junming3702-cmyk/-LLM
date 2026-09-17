# Separate transport-retry sensitivity

`retry_transport.py` requires a completed primary batch and explicit, separate
consent. It checks frozen code, prompt, corpus and input hashes, and considers
only failed arms with a recorded transport exception. Successes, invalid JSON,
gate blocks and HTTP errors alone are not retry-eligible.

Each eligible failed arm receives one additional attempt in a fresh output
directory. LLM-only/flat request bodies are asserted identical to the original;
strict hierarchy, when eligible, re-executes the unchanged stochastic pipeline
on the same facts and settings. Primary files are never written by this runner.

Report the first-attempt analysis as primary and the joined retry outcomes as
a separate sensitivity analysis. Preserve original failures, incremental
requests/tokens and second failures. Do not call this an independent repeated
experiment, or select a response by its agreement with a reference.
