# Security and data handling

## Do not commit

- .env or any file containing DEEPSEEK_API_KEY or MINERU_API_KEY;
- bearer tokens, signed URLs, cookies, private endpoints, or credentials;
- real tender, bid, contract, permit, drawing, BIM, or application documents;
- raw external retrieval payloads containing private project context;
- local embedding weights and generated runtime logs;
- Excel/PDF/DOCX exports derived from private projects.

## Local credential setup

Use a local untracked .env file or process environment:

~~~text
DEEPSEEK_API_KEY=
MINERU_API_KEY=
~~~

Never place real values in .env.example, README files, test fixtures, source
code, or issue comments.

## External API use

Only send de-identified excerpts and the minimum project context needed for the
approved test. Record provider, model, timestamp, response-channel diagnostics,
and provenance without recording credentials. All legal conclusions remain
subject to human second review.

## Public-data policy

The public package uses synthetic gold issues and legal-source metadata. Users
must confirm that any law text, standards text, example documents, and external
retrieval results are permitted for redistribution before adding them locally.
