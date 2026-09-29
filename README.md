# EndNote

A document-grounded chat platform. Upload PDFs, Office documents, Markdown, text and code;
ask questions; get answers that cite the exact page, with the passage highlighted.

## Status

Planning complete. Not yet scaffolded. See [PROGRESS.md](PROGRESS.md) for the live tracker
and [roadmap.md](roadmap.md) for phase gates.

## The one constraint that shapes everything

Groq's free tier is **1,000 requests/day and 100K–500K tokens/day, shared across the entire
organization**. That works out to roughly 30–160 answers per day for all users combined.

The product is free forever by decision. That makes quota enforcement not a billing feature
but a survival requirement. It is designed in from the start rather than bolted on after the
first outage. See [quotas.md](quotas.md).

## Documents

| File | What it covers |
|---|---|
| [project.md](project.md) | What we are building, for whom, and what we are deliberately not building |
| [architecture.md](architecture.md) | System design, components, request flows, hosting |
| [data-model.md](data-model.md) | Postgres schema, pgvector setup, indexes |
| [api.md](api.md) | Endpoint surface, auth, streaming contract, error shapes |
| [ingestion.md](ingestion.md) | Resumable cursor-based parsing pipeline |
| [retrieval.md](retrieval.md) | Hybrid search, RRF fusion, reranking, the citation contract |
| [quotas.md](quotas.md) | Per-user and global quota enforcement, cost ceilings |
| [naming.md](naming.md) | Name research, domain options, brand reservations |
| [decisions.md](decisions.md) | Decision log, including the ones reversed |
| [risks.md](risks.md) | Known limits, failure modes, what breaks first |
| [roadmap.md](roadmap.md) | Six phases with acceptance gates |
| [PROGRESS.md](PROGRESS.md) | Current state, next action, blockers |

## Phases

| Phase | Scope | Gate |
|---|---|---|
| [0](phases/phase-0-auth-and-repl.md) | Auth end to end | Browser call reaches Django with verified JWT |
| [1](phases/phase-1-upload-and-parse.md) | Upload and parsing | Per-page text with correct page numbers; ingest survives restart |
| [2](phases/phase-2-retrieval.md) | Hybrid retrieval | ≥80% page-level recall@k=12 on golden set |
| [3](phases/phase-3-chat-and-citations.md) | Chat and citations | Zero fabricated citations; page highlight works |
| [4](phases/phase-4-quotas-and-polish.md) | Quotas and states | Clean 429 at cap; never a raw Groq 429 |
| [5](phases/phase-5-deploy.md) | Deploy and tune | No failed ingest or lost history after cold start |

## Stack

Next.js on Vercel Hobby · Django on Render Free · Supabase (auth, Postgres + pgvector,
Storage) · Groq for generation · local ONNX Runtime (`bge-small-en-v1.5`) for embeddings ·
LangChain core primitives · pdfminer.six / python-docx / python-pptx / openpyxl for parsing.
