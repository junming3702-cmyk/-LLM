# Public model synchronization — 2026-10-13

This synchronization publishes the existing approved Phase 2 model development
line to the repository's default branch. The source revision is
`a47f1c71d0f5b2c5621e9f9f6791fa6b2940edba`. Model inference behavior is unchanged
by this documentation and ignore-policy update.

## Included model components

- Frozen Phase 1 baseline and 60-item synthetic development data.
- Strict four-level retrieval, local applicability checks and bounded external
  recheck with its existing evidence-admission policy.
- Baseline document extraction, conditional MinerU API parsing, source-locator
  adaptation and coordinate OCR backup.
- Active reasoning prompt, professional full-file addendum, task-aware gate,
  typed task-gap audit, response-channel diagnostics and Excel review exporter.
- Explicitly opt-in experimental modules, source-version checks, synthetic
  regression fixtures, public reproduction command and operator skill.

The application reasoning model remains `deepseek-v4-flash`. Online execution
uses locally supplied credentials and the existing authorization and source
checks. This synchronization does not run the model or any external API.

## Publication boundary

API keys, environment values, raw project files, OCR/API payloads, returned
expert workbooks, participant records, paper drafts, research analyses and
application materials stay outside this public release. The ignore policy now
explicitly covers paper directories, generated `outputs/`, private receipt
directories and `*.private.json`, in addition to existing credential rules.

Only the existing empty `.env.example` templates are version controlled.
Copies with real credentials must remain local. Current expert evaluations
remain attached to their frozen response/gate versions in private records;
they are not incorporated into the public synthetic benchmark metrics.

## Reproduction and version interpretation

Run the existing public offline regression from the repository root:

```powershell
python phase2_public/reproduce_offline.py
```

This checks code contracts and synthetic fixtures. It does not reproduce a
private project's accuracy, expert agreement, or time-saving estimate.

`release_manifest.json` contains the historical 2026-09-05 release record;
its hashes and numerical results should be interpreted at that historical
revision. For the current runtime, use the checked-out Git commit and hashes
of the actual active prompt, addendum, gate and runner. This synchronization
does not overwrite historical evaluation results or introduce new performance
claims.
