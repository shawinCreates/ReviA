# EndNote

A study tool. Sign up, upload your lecture slides, papers and notes, then ask
questions and get answers that cite the exact page they came from.

## Status

The frontend is built and the backend has a working foundation: Django 6.1 with
DRF, authenticated against Supabase using the SSR session cookie the browser
already holds. Health, session and profile endpoints are live and tested.

Not built yet: the document schema, uploads, the ingestion pipeline, retrieval
and chat. Every list, document and answer on screen is still fixture data from
`frontend/lib/mock/data.ts`.

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

| Command | Purpose |
| --- | --- |
| `uv run pytest` | Test suite |
| `uv run ruff check backend` | Lint |
| `uv run ruff format backend` | Format |
| `uv run python backend/manage.py check` | Django system check |

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/health` | none | Liveness, plus whether Postgres is reachable |
| `GET /api/v1/session` | optional | Whether the caller is signed in |
| `GET /api/v1/me` | required | The caller's profile, created on first request |

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

### Testing

`uv run pytest` runs against in-memory SQLite. It is hermetic and takes well
under a second, and nothing a test does can reach the live database.

The alternative does not work against this project. Django creates and drops a
test database around every run, and neither route to Supabase allows the drop:
through the pooler, Supavisor holds an idle session open, and the direct host is
an unreliable IPv6 path. That combination left a stray `endnote_test` database
on the project, which still needs dropping by hand.

Once pgvector and full-text search land, SQLite stops being enough and the test
target has to become a real Postgres. Set `ENDNOTE_TEST_DB=postgres` and point
it at a local container or a dedicated project — not this one.

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

The signed-out experience is deliberately complete rather than a wall: `/chat`
answers questions against a sample library so there is something to judge, and
the upload panel is the gate — the login modal opens on the first upload
attempt, which is the first action that needs an account.

Session handling uses `@supabase/ssr` with httpOnly cookies, refreshed by
`proxy.ts` on every request. Chat history is server-side and account-scoped, so
a signed-out conversation is not written anywhere and is gone on refresh.

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
- `EMBED_MODEL` and `EMBEDDING_DIM` have to agree. Switching embedding models
  means re-embedding every stored chunk; vectors from two different models are
  not comparable even at the same dimension.
- `SUPABASE_DB_USER` is `postgres.<ref>` for the pooler. The direct host has no
  such role, which is why the backend strips the suffix when it needs one.

## Database

The `vector` extension is installed and the schema has just started: `profiles`,
created by `backend/api/migrations/0001_initial.py`. Everything else begins from
nothing. The old schema, its rows and all auth users were dropped rather than
migrated.

Two things need clearing by hand in the Supabase dashboard:

- **Storage → document** holds two orphaned files. Supabase blocks deleting
  them over SQL. Nothing references them.
- A stray `endnote_test` database, left by the first test run before the test
  database was moved off Supabase. `DROP DATABASE IF EXISTS endnote_test;` in the
  SQL editor. It is empty and unused.
