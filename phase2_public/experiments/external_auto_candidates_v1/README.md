# Automatic external supplementary candidates (opt-in)

The adapter removes human **pre-admission** for source-verifiable external
articles. It verifies exact source catalogue bindings, snapshot bytes and text
hashes, article spans, title/version anchors, routing jurisdiction/project type,
and explicit historical-expiry exclusions. It never fabricates human approval,
statutory dates or legal applicability.

This version automatically admits **supplementary candidates only**. Matching a
version header is not proof that a source applied at a historical project date.
It therefore does not enable independent external legal-basis admission. The
shared final gate can preserve exact supplementary citations through the opt-in
`external_auto_candidates=True` flag, but cannot promote them to independent
evidence. Unknown version validity remains an explicit boundary. Existing
human-reviewed source admission and default production behavior are unchanged.

Use a separately frozen runtime harness to run matched final generations with
and without these candidates. Keep original observations immutable. Do not send
reference answers or expert scores to the provider. New outcomes do not inherit
historical expert ratings. Empty discovery is not evidence of compliance.

Offline tests use fictional fixtures. No credentials, actual project excerpts,
expert records or execution outputs belong in this directory.
