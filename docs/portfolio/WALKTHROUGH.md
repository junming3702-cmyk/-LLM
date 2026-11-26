# A review workflow you can inspect

**Public synthetic inputs. Actual offline execution. Human decisions left open.**

This walkthrough shows how the project makes evidence and uncertainty visible. It uses the existing public corpus sample and test fixtures. The results were generated on **26 November 2026** by [`run_demo.py`](run_demo.py).

**[Generated result summary](sample-results/RESULTS.md)** · **[Exact inputs](sample-results/gate-inputs.json)** · **[Execution manifest](sample-results/run-manifest.json)** · **[Back to the project](../../README.md)**

## 1. Find a source passage

An existing synthetic input describes a three-calendar-day sales window for tender documents:

> 招标文件发售期为3个自然日，自2026年9月1日至2026年9月3日止。

*Reading aid: the tender documents are offered for three calendar days, from 1 to 3 September 2026.*

The demo passes this excerpt to the repository's BM25 retrieval function. It ranks the **20 public sample chunks** using the excerpt alone; gold evidence IDs are not used to construct the query or rank candidates.

| Output | Actual result |
| --- | --- |
| Synthetic issue | `SYN-P1-001-I01` |
| First-ranked chunk | `d1a045e563eba90b8893` |
| Locator in the sample | `第十六条` — Article 16 |
| BM25 score | `17.543998` |

The [retrieval output](sample-results/retrieval.json) retains the candidate's title, article, locator and source text. The source is the repository's static sample; this demonstration does not establish its current legal applicability.

**What this shows:** a reviewer can inspect the retrieved passage and trace it to an identified source. It is a sample lexical-retrieval run, not the full four-level hybrid retriever or a new benchmark result.

## 2. Check a proposed conclusion

The next examples use **separate existing synthetic fixtures** from [`test_post_llm_gate_v2.py`](../../phase2_public/tests/test_post_llm_gate_v2.py). Their model-shaped responses are preset. They are not live LLM outputs and are not generated from the retrieval result in step 1.

Both fixtures describe missing supporting documents. The admitted evidence in the first fixture is an explicitly synthetic rule requiring valid documentation.

| Fixture | Proposed response | Actual gated result | Reviewer implication |
| --- | --- | --- | --- |
| `DEMO-REVIEW` | Requests a confirmed legal finding and cites registered source `law-1` | `requires_human_legal_review` | Inspect the source, applicability and interpretation; independent confirmation is still absent |
| `DEMO-UNKNOWN-SOURCE` | Requests confirmation but cites `unregistered-source` | `insufficient_information_needs_human_confirm` | Obtain admissible evidence before resolving the issue |

In the first fixture, the gate also replaces the preset model's placeholder document and source locations with runtime evidence. In the second, the delivered finding has no admitted legal evidence. Both results retain a human-review requirement.

Compare the [preset inputs](sample-results/gate-inputs.json) with the [actual review JSON](sample-results/review.json). The generated findings and audit fields remain in their original form.

## 3. Preserve what remains unread

The [existing document-visibility fixture](../../phase2_public/tests/test_task_subconclusion_v1.py) contains a readable progress-plan narrative and an index entry, but no parsed chart. The task-level gate returns:

```json
{
  "task_completion": "partially_observed_requires_review",
  "pending_claim_ids": ["chart"],
  "legal_conclusion_type": null
}
```

This excerpt is taken from the [generated task result](sample-results/task-result.json); the [full task input](sample-results/task-input.json) is also available. The result preserves useful progress without treating an index entry as proof that the chart has been reviewed.

## 4. Hand the evidence to a person

The intended next step is professional review: inspect the original passage, verify source applicability, resolve missing material and record a decision. **No human decision is filled in for these examples.**

The existing [Excel exporter](../../phase2_public/src/export_review_excel.py) supports that handoff with fields for the issue, original passage, conclusion, source, evidence boundary, recommendation, and the human reviewer's decision and notes. Its public tests were included in the current regression run.

## Run the examples yourself

After preparing the environment with the [project quick start](../../README.md#run-it-locally):

```bash
phase2_public/.venv/bin/python docs/portfolio/run_demo.py
```

On Windows, use `phase2_public\.venv\Scripts\python.exe`. An optional `--output-dir PATH` writes the same example files to a different folder.

| File | Contents |
| --- | --- |
| [`RESULTS.md`](sample-results/RESULTS.md) | Human-readable generated summary |
| [`retrieval.json`](sample-results/retrieval.json) | Synthetic query and the top three sample passages |
| [`gate-inputs.json`](sample-results/gate-inputs.json) | Runtime evidence and preset response fixtures |
| [`review.json`](sample-results/review.json) | Actual outputs of the evidence gate |
| [`task-input.json`](sample-results/task-input.json) / [`task-result.json`](sample-results/task-result.json) | Input contract and partial-completion output |
| [`run-manifest.json`](sample-results/run-manifest.json) | Execution date, environment, source revision and artifact hashes |

The wrapper imports existing functions and fixture factories; it changes no runtime algorithm or prompt. It makes no external API call, loads no model weights and uses no private project documents. These examples demonstrate component behavior; they do not measure end-to-end LLM quality, expert agreement or productivity gains.
