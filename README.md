# ReviA

A study tool. Sign up, upload your lecture slides, papers and notes, then ask
questions and get answers that cite the exact page they came from.

## Status

The backend is functionally complete: Supabase cookie authentication, a document
schema with pgvector, uploads to Supabase Storage, an ingestion pipeline that
parses and chunks and embeds, retrieval, and chat that cites pages.

The frontend is wired to it. Libraries, uploads, pipeline stages, chat and
history all read from the API; the fixtures remain only as the sample library a
signed-out visitor sees, which is what they are for.

Not done: a full test and lint pass over the ingestion, retrieval and chat code,
which is deferred until the application is finished.

Ingestion runs itself. An upload creates a queued row, and a worker thread in
the web process picks it up and carries it through parsing, chunking and
embedding to ready. A Postgres advisory lock keeps exactly one worker
ingesting, so this stays safe when several web processes are running.

To run ingestion outside the web process instead — useful when the pipeline gets
busy — turn the in-process worker off and run the command separately:

```bash
REVIA_RUN_PIPELINE_IN_PROCESS=off uv run python backend/manage.py run_pipeline --loop
```

## Layout

```
backend/     Django 6.1 + DRF API
frontend/    Next.js 16 app router, TypeScript, Tailwind v4
```

## Backend

```bash
uv sync
uv run python backend/manage.py migrate
uv run python backend/manage.py runserver 127.0.0.1:8000
```

The ingestion pipeline is a worker thread, not work done inside the request, so a
slow embed never delays an upload response. It starts with the server and needs
no second command. See "Ingestion" above for running it as its own process
instead.

| Command | Purpose |
| --- | --- |
| `uv run pytest` | Test suite |
| `uv run ruff check backend` | Lint |
| `uv run ruff format backend` | Format |
| `uv run python backend/manage.py check` | Django system check |
| `uv run python backend/manage.py run_pipeline` | One pass over queued documents |
| `uv run python backend/manage.py run_pipeline --loop` | Keep polling (stands down if the in-process worker holds the lock) |
| `uv run python backend/manage.py verify_embeddings` | Embed samples through the production Cloudflare path and report dimensions and norms |

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/health` | none | Liveness, plus whether Postgres is reachable |
| `GET /api/v1/session` | optional | Whether the caller is signed in |
| `GET /api/v1/me` | required | The caller's profile, created on first request |
| `GET /api/v1/libraries` | required | The caller's libraries, default one guaranteed |
| `GET /api/v1/documents` | required | Documents in a library, with stage counts |
| `POST /api/v1/documents/upload` | required | Upload a PDF, DOCX or PPTX |
| `GET /api/v1/documents/{id}` | required | One document |
| `DELETE /api/v1/documents/{id}` | required | Delete the document and its stored file |
| `POST /api/v1/chat/ask` | required | Ask a question; returns an answer with citations |
| `GET /api/v1/chat/sessions` | required | The caller's conversations |
| `GET /api/v1/chat/sessions/{id}` | required | One conversation and its turns |

Errors share one shape everywhere: `{"error": {"code": ..., "message": ...}}`,
so the frontend has one thing to parse.

### How authentication works

There is no local user model and no Django `auth` app. Supabase owns identity;
`Profile` is a local row keyed by the Supabase user id, created the first time
someone calls `/api/v1/me`.

The browser never sends a bearer token. `@supabase/ssr` holds the session in an
httpOnly cookie, and the browser attaches it to the API. The backend reads that
cookie, then asks Supabase Auth to resolve the token to a user.

That last step is a deliberate trade. Verifying the JWT signature locally would
save a network round trip, but Supabase projects sign either with a legacy
shared secret or with newer asymmetric keys, and a local verifier has to be
configured to match whichever the project happens to use. Asking the authority
is one small request and cannot drift. Results are cached by token hash, and a
verified access token is immutable, so a cache hit cannot go stale.

A Supabase outage returns **503**, not 401. Collapsing those two is how a
dependency failure turns into every user appearing logged out.

### The cookie format

`@supabase/ssr` does not store the session as a plain cookie. It writes
`base64-` + base64url(JSON), split across `<name>.0`, `<name>.1` … chunks once
the session outgrows one cookie. `backend/api/supabase_cookies.py` implements
that, verified against the copy in `frontend/node_modules/@supabase/ssr`; the
tests build fixtures in the real format, because a fixture that invents its own
format just agrees with whatever the parser happens to do.

Two traps, both silent. The `base64-` prefix must be stripped *before*
decoding, and since `-` is itself a valid base64url character, decoding without
stripping it yields plausible garbage rather than an error. And a project set to
`cookieEncoding: "plain"` stores raw JSON with no prefix at all.

### Cross-origin writes

Django's CSRF protection is tied to session middleware, which is not installed
here, and DRF only enforces CSRF for its own `SessionAuthentication`. A
state-changing request would otherwise arrive carrying the session cookie and
nothing else, which is the shape of a cross-site request forgery.

The fix is an `Origin`/`Referer` check on every unsafe method, against
`DJANGO_CORS_ALLOWED_ORIGINS`. A browser sets `Origin` and forbids scripts from
writing it, so a cross-origin write cannot forge one. The service writes no CSRF
cookie of its own, so there is nothing for a double-submit pattern to work with;
`api/auth.py` explains that trade in full.

### How an answer gets its citations

Retrieval is the part most likely to look right and be wrong, so the decisions
are recorded where they are made rather than left to defaults.

**A cutoff, not just a top-k.** Returning the six nearest passages
unconditionally means a question nothing in the library answers still produces
six confident passages. `RETRIEVAL_MAX_DISTANCE` is a cosine distance, measured
for the default model: real matches landed at 0.18–0.34, unrelated text at 0.52
and above. Below the cutoff, the model is asked to say the documents do not
cover it.

**MMR, so five passages are not the same paragraph.** The nearest neighbours to
one topic are often restatements of it. Maximal marginal relevance trades a
little raw similarity for coverage of different ground, and caps any one
document's share.

**A chunk never spans pages.** A chunk is cited by page, so a chunk spanning
three pages could only be attributed to one of them.

**Citations come from numbers the model was given.** Passages are numbered in
the prompt and the model cites them by number. A number with no matching passage
is discarded rather than shown — a citation pointing at nothing makes the whole
list untrustworthy. An answer with no citations is kept: declining is a valid
answer.

**Citations are snapshots.** The document, page and quoted text are stored on the
message as JSON rather than as a relation, so re-ingesting a document cannot
retroactively change what an old answer claims it cited.

### Embeddings

Embedding runs on Cloudflare Workers AI, at model id `@cf/baai/bge-small-en-v1.5`
— the same weights the stored vectors were made with, so no migration and no
re-embedding was needed.

The request pins `pooling: "cls"` and L2-normalises what comes back. Both are
contract, not taste: the endpoint's default mean pooling is not comparable with
what produced the stored vectors, and retrieval's MMR compares stored vectors by
plain dot product, which is cosine similarity only when vectors are unit length.
`EMBEDDING_QUERY_PREFIX` carries the BGE query instruction — Cloudflare does not
apply it, and the chat path depends on it.

On the free tier the account gets 10,000 neurons/day (~85 lecture PDFs a day);
when a day is spent, uploads land in `failed` with a reason that says so, and
`manage.py reingest` clears them after the 00:00 UTC reset.

`EMBED_MODEL` and `EMBEDDING_DIM` have to agree, and the dimension is baked into
the `chunks.embedding` column width. Changing either means a migration and
re-embedding every stored chunk: vectors from two models are not comparable even
at the same dimension. `retrieval._check_dimension` refuses to search a library
whose stored vectors are the wrong width rather than returning nonsense.

Why hosted: the in-process model peaked past 500 MB during an embed on the 512 MB
free tier, which ended in gunicorn killing its worker mid-request (the "worker
timeout, worker killed" crash loop). Hosting the embedding dropped the same
batch-embed peak to ≈81 MB. Deep reference for the whole backend, including the
embedding contract: `docs/DESIGN.md`.

### Testing

`uv run pytest` defaults to in-memory SQLite, which is hermetic and fast. It
skips the pgvector tests, because the extension does not exist there.

`chunks.embedding` is a `VectorField` and the HNSW index needs real pgvector, so
the full suite needs a real Postgres. Set `REVIA_TEST_DB=postgres` and give it
an explicit local target:

```bash
REVIA_TEST_DB=postgres \
REVIA_TEST_PG_HOST=127.0.0.1 \
REVIA_TEST_PG_PORT=5433 \
REVIA_TEST_PG_NAME=revia \
REVIA_TEST_PG_USER=postgres \
REVIA_TEST_PG_PASSWORD=revia \
uv run pytest
```

The host is required, not defaulted. An earlier version fell back to Supabase
when it was missing, which is how a stray `revia_test` database ended up on
the project: Django creates and drops a test database around every run, and
neither route to Supabase allows the drop.

### How ingestion works

Four stages, named in `DocumentStage`, driven from one place so the ordering
cannot drift between callers:

1. **parse** — pypdf, python-docx or python-pptx, chosen by extension. The
   extension is trustworthy because `api/uploads.py` has already checked the
   magic bytes match it. Word has no pages, so it is presented as one.
2. **chunk** — ~900 characters, split at paragraph boundaries first and sentence
   ends second, never across a page. Both rules exist to keep a citation
   checkable: a chunk that stops mid-sentence is retrieved by neither that
   question nor the next.
3. **embed** — batched, with the model asserted against configuration.
4. **ready**

Chunk text is written before embedding, so a rate-limited embedding call does
not lose the parsing work. A failure always lands the document in `failed` with
a reason a user can read, never stranded mid-pipeline.

Documents that stall in a non-terminal stage for 15 minutes are returned to the
queue on the next pass. A worker killed mid-document leaves a row nothing else
would ever pick up, because a pass only looks at `queued`.

## Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

| Command | Purpose |
| --- | --- |
| `npm run dev` | Dev server |
| `npm run build` | Production build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint |

Routes: `/` marketing page, `/chat` the three-column interface, `/pipeline` the
ingestion board, `/login` sign in and sign up.

Session handling uses `@supabase/ssr` with httpOnly cookies, refreshed by
`proxy.ts` on every request. Chat history is server-side and account-scoped, so
a signed-out conversation is not written anywhere and is gone on refresh.

### How the wiring is laid out

| File | Role |
| --- | --- |
| `lib/api.ts` | The only module that knows the wire format. Wire types, the mappers onto `lib/types.ts`, and the browser transport. Free of `next/headers` so the client hooks can share it. |
| `lib/api-server.ts` | The same payloads loaded from a server component, forwarding the cookie by hand. |
| `lib/use-library.ts` | Documents, upload, delete, and the polling that makes pipeline stages live. |
| `lib/use-chat.ts` | Conversations, the transcript, and `ask`. |
| `lib/mock/data.ts` | The sample library, used only when signed out. |

Two decisions worth knowing about:

**The API hostname is derived from the page's hostname.** Cookies are scoped to a
host and ignore ports, so a page on `localhost:3000` calling
`127.0.0.1:8000` sends no auth cookie at all and every request 401s. `API_BASE_URL`
mirrors `window.location.hostname` unless `NEXT_PUBLIC_API_BASE_URL` overrides it.
Open the app on `localhost` and the API on `localhost`; do not mix the two
spellings.

**First load is server-side, everything after is the client.** The page fetches
libraries, documents and the newest conversation on the server so the transcript
is on screen at first paint. After that the hooks take over, because ingestion
progresses in a background worker and the only way to see it is to ask again.
Polling is every 3s while a document is moving and 25s once everything has
settled, and it stops on a hidden tab.

The signed-out experience is deliberately complete rather than a wall: `/chat`
shows a worked sample conversation so there is something to judge, and asking a
question or uploading is the gate — both open the login modal, because both need
an account. Nothing is simulated. A signed-out page makes no API calls at all.

### Checks

```bash
npm run typecheck      # tsc
npm run lint           # eslint
npm run check:mapping  # the mappers, against captured payloads
npm run check:api      # the mappers, against a live API
```

`check:mapping` and `check:api` exist because of one blind spot: both sides of
the API contract are typed against their own idea of it, so renaming a field on
the server breaks the UI with a green typecheck. `check:mapping` is that blind
spot against fixtures; `check:api` is it against a running API, and needs a
signed-in session (`API=... npm run check:api`). The first one is what caught a
bracketed year in an answer being rendered as a citation to a page that did not
exist.

## Configuration

Copy each template next to it and fill in the blanks:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

`.env` and `.env.local` are gitignored. Keep them that way — the backend one
holds database credentials and API keys. `backend/.env.example` documents every
variable the backend reads, including the ones that have sensible defaults.

Three notes on the values:

- `SUPABASE_DB_HOST` must be the **session pooler** host, not the direct host.
  Deploy targets without IPv6 fail to connect otherwise, and the failure looks
  like a bad password rather than a networking problem.
- `GROQ_MODEL` must be a model the key has access to. A restricted key gets 404
  for the larger models, which is not obvious from the error.
- `SUPABASE_DB_USER` is `postgres.<ref>` for the pooler. The direct host has no
  such role, which is why the backend strips the suffix when it needs one.

## Database

Migrations, in order:

| Migration | What it does |
| --- | --- |
| `0001_initial` | `profiles` |
| `0002_library_document_chunk_and_more` | `libraries`, `documents`, `chunks`, the `vector` extension, and the HNSW index over the embedding column |
| `0003_enable_row_level_security` | RLS on `profiles`, `libraries`, `documents`, `chunks` |
| `0004_chatsession_chatmessage_and_more` | `chat_sessions`, `chat_messages` |
| `0005_enable_row_level_security_on_chat` | RLS on the two chat tables |

### Row level security

Supabase grants `anon` and `authenticated` full access to every table in the
public schema, and PostgREST will serve any of them to a request carrying the
anon key — which ships in the frontend bundle. This project was live with RLS
disabled and those grants in place, so the schema was readable and writable by
anyone with the public anon key.

Enabling RLS with no policies denies those roles outright. This service is
unaffected: it connects as the database owner, and the owner bypasses RLS by
design.

RLS keeps everyone else out of Postgres. It cannot enforce ownership *within*
this service, so `api/access.py` does that — every read and write is scoped to
the authenticated user there.

Two things need clearing by hand in the Supabase dashboard:

- **Storage → document** holds two orphaned files. Supabase blocks deleting them
  over SQL. Nothing references them.
- A stray `revia_test` database, left by the first test run before the test
  database was moved off Supabase. `DROP DATABASE IF EXISTS revia_test;` in the
  SQL editor. It is empty and unused, and Supavisor holds a session open to it,
  so the drop fails until that session is closed.

