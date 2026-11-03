# Design reference

This is the deep reference for the backend: what every function does (one or two
lines each) and, per module, the choices that shaped it. The code carries almost
no comments — non-obvious contracts live here instead. README.md stays the
user-facing guide.

## Runtime shape

One Django deployment on Render (free tier, 512 MB, Docker). Supabase supplies
Postgres with pgvector, the S3-compatible object storage, and user identity.
Cloudflare Workers AI supplies embeddings. Groq supplies the chat model.

Request flow: the Next.js frontend calls the API with the browser's Supabase
session cookie attached. Ingestion runs in a worker thread inside the same web
process (`config/apps.py` starts it on boot); a Postgres advisory lock keeps it
to one globally.

---

## api/embedding_client.py

The whole embedding path. There is exactly one embedding provider: Cloudflare
Workers AI. Any other provider code was removed deliberately — a second
implementation to keep comparable is the cost, not the benefit.

| Function | Does |
| --- | --- |
| `embed_texts(texts)` | Passage embeddings: no prefix, batched, ordered. Returns one vector per input element. |
| `embed_query(text)` | Query embedding: prefixed, single vector. |
| `_embed(texts, kind)` | Shared path: asserts `EMBED_MODEL` against `SUPPORTED_MODEL`, configures credentials, applies prefix, batches through the provider, validates every vector's width against `EMBEDDING_DIM`. |
| `_cloudflare_config()` | The account id and token; fails fast and non-retryably if unset. |
| `_cloudflare_endpoint(account_id)` | `POST {base}/accounts/{id}/ai/run/@cf/baai/bge-small-en-v1.5`. |
| `_cloudflare_client()` | Cached `httpx.Client`, 30 s total timeout, 10 s connect. |
| `reset_client_cache()` | Handler for tests / settings changes only. |
| `_cloudflare_request(endpoint, token, texts)` | One POST, `pooling: "cls"`, with the retry ladder and error classification. |
| `_parse_cloudflare_response(body, expected)` | Builds `numpy` arrays of float32, L2-normalises rows, returns plain floats via `as_query_vector`. |
| `_cloudflare_error(body)` | Reads `{"success": false, "errors": [...]}` envelopes, sometimes delivered inside a 2xx. |
| `_cloudflare_quota_error()` | The everyday-quota `EmbeddingError` (non-retryable, user-readable). |
| `_backoff(attempt)` | 0.5 s → 1 s → 2 s, capped at 8 s regardless of attempt count. |

Constants: `BATCH_SIZE = 32` (requests per network call), `MAX_ATTEMPTS = 3`,
`QUOTA_ERROR_CODE = 4006`, `SUPPORTED_MODEL = "BAAI/bge-small-en-v1.5"`,
`SUPPORTED_MODEL_CLOUDFLARE_ID = "@cf/baai/bge-small-en-v1.5"`.

### Choices made

**Cloudflare, not in-process.** The local model measured ≈296 MB RSS at load and
peaked 518 MB on the first 32-chunk batch, against the 512 MB tier — gunicorn's
30 s worker timeout killed the worker mid-request, and the kill loop repeated
because the model cache died with the worker. The same 32×900-char batch
through Cloudflare peaks ≈81 MB. Hosting the embedding is the whole fix.

**The same weights.** Every stored vector was embedded with `bge-small-en-v1.5`.
Cloudflare Workers AI hosts the identical weights at 384 dimensions; measured
cosine between vectors from the old path and from Cloudflare was 1.0000, so
existing stored vectors needed no re-embedding and no migration.

**`pooling: "cls"` is load-bearing.** The old path pooled by first token (CLS)
and unit-normalised its output; Cloudflare's default for this model is mean
pooling, which is not comparable at query time. The request pins CLS pooling.

**Normalisation is load-bearing.** The response is L2-normalised because
retrieval's MMR compares stored vectors by plain dot product; dot product is
cosine only on unit-length vectors. An all-zero row is left at zero (divisor 1)
rather than becoming NaNs.

**Prefix only the query.** Passages go to the model raw; queries carry
`EMBEDDING_QUERY_PREFIX` (the BGE instruction sentence). Mixing that up degrades
recall rather than failing loudly.

**Error semantics.** Transient (network, timeout, 429, 5xx, model failure inside
a 200) → retried with backoff, then `retryable=True`. Quota (code 4006, "free
allocation" in the message) → non-retryable, mentions the 00:00 UTC reset. 401/403
→ non-retryable, names `CLOUDFLARE_API_TOKEN`. Other 4xx → non-retryable, names
`CLOUDFLARE_ACCOUNT_ID` and the model id. Wrong vector width → non-retryable,
because Postgres would otherwise surface the cause as a cryptic column mismatch.
`data` binds to `text` positionally — nothing to sort.

**Model identity is asserted, never inferred.** `_embed` refuses to run if
`EMBED_MODEL` differs from `SUPPORTED_MODEL`, so a mistyped env var cannot
silently write incompatible vectors into the database.

## api/embeddings.py

| Function | Does |
| --- | --- |
| `as_query_vector(embedding)` | Casts any array-like to flat float32 and returns plain floats. |

The single place the provider's numpy arrays become JSON/pgvector-serialisable
lists. `numpy` is required by pgvector anyway and does the response
normalisation.

## api/models.py

| Model | Is |
| --- | --- |
| `TimestampedModel` | Abstract base: `created_at` (indexed), `updated_at`. |
| `Profile` | Local identity keyed by the Supabase user id (`id` is the user id), `max_documents` quota (0 = unlimited). |
| `Library` | Owner-scoped collection. Two constraints: unique (owner, name) and exactly one default per owner (partial unique index). |
| `Document` | File, size, `storage_path`, `stage` (indexed, owner+stage composite), `error_message`. |
| `Chunk` | `ordinal` within document (unique per document), `page_number`, `content`, `heading_path`, `embedding` (`VectorField(dimensions=settings.EMBEDDING_DIM)`), `owner` denormalised for ownership filtering, `token_count`. |
| `ChatSession`, `ChatMessage` | Conversations per library; messages carry `role` and `citations` (JSON snapshot). |
| `DocumentStage` | `queued → parsing → chunking → embedding → ready`, plus `failed`. |

### Choices made

**The dimension is frozen into history.** Migration 0002 created
`chunks.embedding` as `vector(384)` (literal), with the HNSW index
`chunks_embedding_hnsw` built with `vector_cosine_ops`. Changing `EMBEDDING_DIM`
without writing a matching migration makes inserts fail; changing it with one
invalidates every stored vector. 384 is part of the one decision with `EMBED_MODEL`.

**Ownership is denormalised onto `Chunk`.** Only-chat-scoping and
search-scoping filter `owner` directly on the row instead of joining to
Document → Library → Profile.

**`profiles` is not managed by Django's auth.** Identity lives in Supabase;
this row only holds local settings (the document quota).

## api/ingestion.py

The 4-stage pipeline, `queued → parsing → chunking → embedding → ready`.

| Symbol | Does |
| --- | --- |
| `worker_lock()` | Context manager over `pg_try_advisory_lock(WORKER_LOCK_KEY)` / unlock. Yields `True` on non-Postgres (the test suite runs SQLite, where the worker never starts). |
| `ingest_document(document)` | Runs the four stages; any `IngestionError` marks the document `failed` and re-raises; any unexpected exception is logged with a traceback, marked `failed`, and re-raised as an internal error. |
| `_parse(document)` | Refuses no-`storage_path` rows, downloads bytes, calls `parsing.extract_pages`, saves `page_count`. Advances to `PARSING`. |
| `_split(document, pages)` | `chunking.chunk_document`; empty content becomes the `no_text` error. Advances to `CHUNKING`. |
| `_write_chunks(document, chunks)` | Deletes prior chunks, then `bulk_create` in batches of 100 within one transaction. |
| `_embed(document)` | Loads the document's chunks ordered by ordinal, calls `embed_texts`, writes vectors back with `bulk_update`, advances to `READY`, clears `error_message`. `EmbeddingError` propagates its `retryable` flag. |
| `_fail(document, reason)` | `library_service.fail_document`, degraded to a log line if the transition is refused. |
| `ingest_pending(limit)` | One worker pass: reap stalled, claim up to `limit` queued (oldest first), process, and for `retryable` errors return the document to `queued` with the reason preserved. Returns per-pass totals. |
| `_reap_stalled()` | Documents sitting in a mid-pipeline stage after `PIPELINE_STALLED_SECONDS` go straight back to `queued` (via a bulk update, not `advance_stage`). |
| `stalled_after_seconds()` | `PIPELINE_STALLED_SECONDS` with a built-in 15-minute fallback. |

### Choices made

**Chunk before embed.** Chunking is local and cheap; embedding is the network
call. A document already sized in chunks fails fast if it has no text, and the
batch sent to the provider is known.

**One transaction per batch of 100.** A large document does not hold a giant
transaction, and a part-way failure leaves the earlier rows committed rather
than rolled back into retry storm territory.

**Ordered writes.** Chunks are sent to embedding in ordinal order and the
vectors are paired back by position (`zip(..., strict=True)`), because the
provider's response binds positionally.

**Requeue, don't burn.** A retryable embedding error puts the document back in
`queued` with its reason visible; the next pass picks it up after
`PIPELINE_IDLE_SECONDS` (5 s). The retry transition clears the message, so the
reason is written after the transition.

**Stall reaping is repair, not recovery.** A worker death leaves documents in
`parsing`/`chunking`/`embedding` forever; the pass returns them to `queued`
directly (error message cleared — a new attempt is about to replace it anyway)
and the new attempt decides fresh.

**Log-only `_fail` degradation.** Failing is legal from every stage, so the
transition refusal cannot hide a real failure behind an exception.

## api/pipeline_worker.py

| Function | Does |
| --- | --- |
| `is_running()` | Whether the live thread exists and is alive. |
| `start()` | Spawns the daemon thread once, guarded by `_start_lock`; returns False if already running. |
| `stop(timeout)` | Sets `stop_requested`, joins with 5 s default. |
| `_run()` | Loop: pass, then sleep `PIPELINE_BUSY_SECONDS` when work happened, `PIPELINE_IDLE_SECONDS` when idle; `connections.close_all()` after every pass (failed passes included). |
| `_pass()` | Takes the advisory lock; a holder elsewhere means standing down (debug log, not an error). Calls `ingest_pending` with `PIPELINE_BATCH_SIZE`. |
| `_interval(worked)` | Sleep length, expressed as settings. |
| `_batch_size()` | `PIPELINE_BATCH_SIZE`. |

### Choices made

**One worker per process, one globally.** The thread-level guard stops two
threads in one process; the Postgres advisory lock stops two processes racing.
`run_pipeline` commands also take the lock, so an operator and the web process
can coexist.

**Daemon thread + logging in the loop.** An unhandled pass exception would kill
the thread silently and read as "ingestion is broken"; the loop catches, logs,
and continues. `close_all()` runs after failed passes too, or a dead pass's
connection would stay checked out for the thread's life.

**Stop is a request, not an interrupt.** A pass in flight finishes —
`stop_requested` is checked between passes only.

## api/apps.py

| Symbol | Does |
| --- | --- |
| `check_embedding_dimension` | System check: refuses to boot if `EMBEDDING_DIM` ≠ 384 (`MIGRATED_EMBEDDING_DIM`). |
| `check_allowed_upload_extensions` | System check: an empty `ALLOWED_UPLOAD_EXTENSIONS` is an Error; entries without a lower-case leading dot (which can never match) are a Warning. |
| `ApiConfig.ready()` | Entry: `manage.py check` / `migrate`, and `_maybe_start_pipeline_worker` when serving. |
| `_maybe_start_pipeline_worker()` | Starts the worker only when: not a test, serving a request-answering command, not the autoreload supervisor, and `REVIA_RUN_PIPELINE_IN_PROCESS` (default on). Skips quietly when another process holds the lock. |
| `_is_serving()` | `runserver` and the WSGI/ASGI servers via argv sniffing. |
| `_is_autoreload_supervisor()` | Detects `runserver`'s supervising process so the child — the real one — is the thread's home. |

### Choices made

**Commands that never serve requests must not start a worker.** `migrate`
would race table creation; `run_pipeline` exists precisely to do that work (its
own lock keeps the two safe if both are running anyway).

**The dimension guard is a boot-time Error, not a runtime surprise.** A wrong
`EMBEDDING_DIM` otherwise dies at first insert with an unreadable pgvector
message.

## api/parsing.py

| Function | Does |
| --- | --- |
| `extract_pages(filename, data)` | Picks the reader by extension, refuses empty/unreadable, groups blocks into pages. |
| `_read_pdf(data)` | `unstructured` `partition_pdf` with `PDF_PARTITION_STRATEGY` (default `hi_res`). |
| `_partition_pdf(...)` | Strategy fallback: `hi_res` failure retries once with `fast`; `fast` failure is final. |
| `_read_docx` / `_read_pptx` | Same reader, different partitioners; pptx keeps page breaks so slide = page. |
| `_elements_to_blocks(elements)` | Splits pages on PageBreak, drops Header/Footer/PageBreak noise, dedupes identical consecutive blocks, records heading level for Title elements from `category_depth`, and prefers the reader's own `page_number` metadata. |
| `_heading_level(element)` | 1-based depth for the hierarchy builder. |
| `_group_into_pages(blocks)` | Reconstructs `ExtractedPage`s sorted by number. |
| `_normalise(text)` | Nulls out, collapses per-line whitespace, squeezes blank runs. |
| `page_count(pages)` | Number of pages. |
| `usable_text(pages)` | All non-empty page text joined — used by nothing critical post-chunking, kept for tests. |

### Choices made

**`hi_res` where power is available, `fast` in the free-tier box.** `hi_res` is
layout-aware and better with slides; it is heavier. `render.yaml` sets `fast`
for production (512 MB tier), local development keeps `hi_res`; a `fast` failure
is never retried (the code has nothing more to give).

**A chunk's page is the page its pieces came from.** Blocks carry their reader's
page number so chunk citations land on one page (see chunking).

## api/chunking.py

| Function | Does |
| --- | --- |
| `TextChunk` | Final unit: `ordinal` (1-based), `page_number`, `content` (heading path + body), `heading_path` (`>`-joined chains). |
| `chunk_document(pages)` | Builds sections from headings, splits each into body pieces, prefixes the heading text, merges runt (<120 char, same heading) pieces into the previous chunk; refuses an entirely empty document (with OCR advice). |
| `_collect_sections(pages)` | Heading-driven stack: each Title block slices the stack at its level, so `Chapter > Section > Subsection` paths are built correctly. |
| `_split_body(section)` | Accumulates blocks toward `TARGET_CHARS` (900), forces pieces longer than `MAX_CHARS` (1400) through sentence splitting, and tracks each piece's source page. |
| `_split_long_paragraph(paragraph)` | Sentence-first, then whitespace, then hard cuts — the largest unit that fits stays intact when possible. |
| `_split_on_whitespace(text)` | Word-level regression path for monster sentences/words. |
| `estimated_tokens()` | `chars // 4` floor 1 — the budget arithmetic everywhere. |

### Choices made

**A chunk never spans pages.** Chunks are cited by page; a long chunk spanning
pages would force a wrong attribution (each `(piece)` remembers the page of its
first block). Only genuinely unbreakable spans of a single page cross that line.

**900-char targets, 120-char minimum.** Nearest-integer sweet spot for the 384-dim
bge model seen in practice on lecture material; runts merge forward when the
heading matches, so a one-line cell doesn't become its own citation.

**Heading path is part of the content.** The chunk's text begins with
`Chapter > Section`, so the embedding knows the context and the citation shows
where the user is.

## api/retrieval.py

| Function | Does |
| --- | --- |
| `retrieve(principal, library, question, top_k=6)` | Validates the question, `embed_query`es it, gathers candidates, filters by distance, MMR-reranks, enforces the token budget, numbers `[1..n]`. |
| `RetrievedPassage` | One numbered passage: `.citation()` — document, page, heading, ordinal, 400-char snippet — is the API shape. |
| `RetrievalResult` | Passages + the query vector; `as_prompt_block()` renders the numbered source list the model sees, with the instruction to cite by `[n]` and to say so if it can't. |
| `_candidates(...)` | `searchable_chunks` annotated with cosine distance against the query vector, ordered rising, over-fetched and capped per document. |
| `_check_dimension(candidates)` | Refuses to search a library whose stored vectors are the wrong width (missing embeddings, mixed-model library) instead of returning nonsense. |
| `_per_document(queryset, limit)` | Greedy walk of an over-fetched window (`limit × 4`), up to `PER_DOCUMENT_LIMIT = 3` per document, until `limit` (24 = 6 × 4) fill. |
| `_rerank(candidates, top_k)` | Two passes: keep only `distance <= MAX_COSINE_DISTANCE`; then maximal-marginal-relevance. |
| `_max_similarity(chunk, selected)` | Plain dot product against already-selected vectors; a width mismatch raises `incompatible_index`. |
| `context_token_budget()` | 25 % of the remaining window after `ANSWER_MAX_TOKENS` is reserved, floored at 1000. |
| `_fits_budget(chunks)` | Drops passages past the budget — oldest-selected last in, first cut — never below one. |

### Choices made

**A distance cutoff, not just top-k.** Six nearest passages to a question nothing
in the library answers are six confident-sounding nonsense passages. Measured
against the default model: real matches sit at 0.18–0.34 cosine distance,
unrelated text at 0.52 and above. `RETRIEVAL_MAX_DISTANCE` (default 0.45) sits
between them.

**MMR with λ = 0.7 (`MMR_LAMBDA`).** Nearest neighbours to one topic are
restatements of it, the norm in lecture notes. MMR trades a slice of similarity
(λ = 0.7 keeps most of it) for coverage of different ground. Stored vectors are
unit-normalised, so plain dot product = cosine — that is why the provider's
normalisation is part of the contract.

**Per-document cap inside candidate collection.** 3 per document, so one
borderline-relevant document cannot fill all of the slots with its padding.

**Over-fetch (`limit × 4` then scan window × 4).** HNSW returns nearest-first;
the walk applies the per-document cap on a 96-row window rather than issuing
per-document queries.

**Budget estimates are cheap and settled.** `chars // 4` is applied
consistently by `_fits_budget` and `_history_for` — one half-carried estimate,
used conservatively.

## api/chat.py

| Function | Does |
| --- | --- |
| `answer_question(principal, session, question)` | Clean question, retrieve, generate, persist, return `(Answer, RetrievalResult)` — the citations and the full retrieved list ride on the answer. |
| `_clean_question` | Rejects empty and over-`MAX_QUESTION_CHARS` input. |
| `_generate(session, question, result)` | System prompt (with or without context), prior history, then `question` with the prompt block prepended if there is context. |
| `_history_for(session)` | Last `CHAT_HISTORY_TURNS × 2` messages, token-budget filtered (`CHAT_HISTORY_MAX_TOKENS`), oldest-last reordered. |
| `_citations_for(text, result)` | Extracts `[n]` / `[n,m]`, dedupes, keeps only numbers that map to offered passages (a fabricated citation is dropped and logged), returns `passage.citation()` dicts. |
| `open_session(...)` | Resolves the session contract: explicit `session_id` validated against ownership; otherwise reuse the library's newest session unless `force_new`; otherwise create. |
| `list_sessions / messages_for` | Ownership-filtered listings; `messages_for` re-checks ownership on the session. |
| `_persist(session, question, answer)` | Two rows (user turn, assistant turn + citations JSON). First exchange also names the session. |
| `_title_for(question)` | Collapsed first 60 chars, cut on a word boundary. |
| `_complete(messages)` | The Groq call: `retries` exactly like embeddings (3 attempts, 0.5→8 s), refuses no-key, 429/5xx retry → `model_unavailable`, other non-200 → raises `'the model rejected the request'`. |
| `_extract_text(response)` | Unwraps `choices[0].message.content`, refuses empty/no-string. |

### Choices made

**The model may only cite what it was shown.** The system prompt names the rule;
`_citations_for` enforces it — a number with no matching passage is dropped, so
a leaky-bracket `[9]` in a 2-passage prompt cannot masquerade as a citation.
An answer with no citations stands: declining is a valid answer.

**System-then-history-then-prompt-block.** The `SYSTEM_PROMPT` rules are repeated
first in the visible block (`as_prompt_block` ends with the citation
instruction), because influences from the actual current turn outrank a system
paragraph from turns ago.

**History is a budget, not a window count.** 8 turns × 2 messages is drafted in
oldest-newest order, but the 3000-token cap is checked walking back from newest
first (cheap estimate), trimming the past — the most recent messages win.

**Sessions require the caller's explicit intent.** `session_id` binds to another
person's row to `AnswerError('no_session')`; a new user gets a fresh library
session. `force_new` is explicit and drains a stray title restatement.

**Groq errors are retryable only when pointless otherwise.** 429/5xx → retry with
backoff (`model_unavailable` if never resolved — `AskView` maps that to 503).
Missing key or malformed output → hard error, so a retry loop against a missing
key never spins.

## api/storage.py

S3-compatible (Supabase Storage) object store.

| Symbol | Does |
| --- | --- |
| `_credentials()` | Reads endpoint/access/secret/bucket settings and raises a clear error listing what's missing. |
| `_client()` | Cached boto3 client against the custom endpoint. |
| `StoredObject` | `path`, `size` (from HEAD), `content_type`. |
| `build_object_path(owner_id, filename)` | `{owner}/{slug}-{random12}{ext}` — slugified stem (dots re-attached), unique random |
| `guess_content_type(filename)` | mimetypes with `octet-stream` fallback. |
| `upload_file(owner_id, filename, fileobj)` | Credentials + path first, `upload_fileobj` (boto3's `upload_file` takes a filesystem path), then `head_object` for the size. Failures become `StorageError` with only the exception class name in the message. |
| `download_file(storage_path)` | Whole-object `get_object` into `read()`. |
| `delete_file(storage_path)` | `delete_object`, treating 404/NoSuchKey/NotFound as success. |
| `_is_missing(exc)` | The three bucket shots that all mean "already gone". |

### Choices made

**Bytes first, rows second.** Upload stores the object before the `document` row
is created — an upload whose row-creation fails deletes the object back
(orphan cleanup, `views.UploadDocumentView`), whereas the reverse order left the
worker failing rows whose bytes were still in flight.

**Random suffix per upload.** Deterministic naming would make a re-upload silently
replace the object under an existing `storage_path`, and the original's first
page would point at different content.

**Only class names in error messages.** boto3's exception bodies echo request
parameters; the class name is the useful minimum that cannot leak credentials.

## api/uploads.py

| Function | Does |
| --- | --- |
| `clean_filename(raw)` | Null bytes stripped, basename only, trimmed. |
| `check_extension(filename)` | Extension from an allowlist (`.pdf`, `.docx`, `.pptx`), else reject. |
| `check_size(size)` | `MAX_UPLOAD_BYTES` (25 MB); message says the limit in MB. |
| `check_magic_bytes(filename, head)` | Reads `_SNIFF_BYTES` (8) from the front, decodes the file's actual leading bytes against `_MAGIC_NUMBERS`, case-insensitive (PDF headers are conventionally upper case, not guaranteed). |
| `validate_upload(upload)` | The pipeline — clean, allowlist, size, sniff; returns `ValidatedUpload {filename, size, content_type}`. |

### Choices made

**Sniff the bytes, not the headers.** `size` from request headers is untrusted
(it is still the cheapest possible first check — a socket-wrong hard limit);
the content check reads the file's leading bytes instead.

**`.docx`/`.pptx` share one signature.** Every Office Open XML file is a zip
container, so `PK\x03\x04` is as specific as it gets; the extension does the rest.

**Null byte rejection first.** A trailing `\x00` can truncate a name in some
C libraries — the shape that lets `safe.pdf\x00.png` sneak past an
extension allowlist.

## api/auth.py

DRF authentication over the Supabase session.

| Function | Does |
| --- | --- |
| `SupabasePrincipal` | The request user: `id` = Supabase user id, `email`, `is_authenticated=True`. |
| `CookieSessionAuthentication.authenticate(request)` | Bearer header path first (the browser can't carry a session cookie across origins), then the session cookie via `extract_session`; unsafe methods get the origin check before verification. |
| `_verify(access_token)` | Resolves the token through `supabase_auth.verify_access_token` and maps errors: auth-service-down → `AuthenticationFailed` with a 503 status code, bad token → 401. |
| `authenticate_header()` | Says `Cookie` — not `Bearer`, which would invite clients to send one where no CSRF protection exists. |
| `enforce_csrf(request)` | The CSRF decision: untrusted origin on an unsafe method is a hard 403 with a warning log. |
| `_origin_is_trusted(request)` | `Origin` first (scripts can't set it), `Referer` fallback (browsers may omit it on GETs and some privacy features), else trust (`curl` always has neither, so a non-browser client is the only way to get here). |

### Choices made

**Origin check, not Django CSRF.** `django.middleware.csrf` is session-middleware
coupled and isn't installed; DRF only enforces CSRF on its own
`SessionAuthentication`. So the shape needing protection — a state-changing
request carrying the session cookie with no proof the user meant to send it —
is met with an origin check on every unsafe method instead.

**One trusted list.** `CORS_ALLOWED_ORIGINS` is read by both `django-cors-headers`
and `api.auth`, and `CSRF_TRUSTED_ORIGINS` defaults from the same string, so
there's a single list of origins to get right.

**A Supabase outage answers 503, not 401.** Mapping "our dependency is down" to
"you seem logged out" sends every user into a pointless re-login; the
`auth_unavailable` branch keeps the distinction visible.

**Unsafe methods only.** A GET cannot change state, and requiring origin proof
from it would break plain fetches and CORS preflight handling.

**No HTTP-check origins configured → trust all.** With nothing to compare to,
refusing everything makes `curl` and CI impossible for no security gain; the
actual threat model (cookie-carrying browsers) always sends an `Origin` or
`Referer`.

## api/supabase_auth.py

Verification against authority, with a tolerant cache.

| Symbol | Does |
| --- | --- |
| `_token_fingerprint(token)` | SHA-256 of the token — the cache key. Token never stored raw. |
| `_decode_jwt_claims(token)` | Best-effort claim read from the JWT payload, {} on any failure. |
| `_VerifiedUserCache` | Keyed by fingerprint, expiring after `SUPABASE_AUTH_CACHE_SECONDS` (300 default), bounded at 1024 entries with oldest-expiry eviction. |
| `_fetch_verified_user(token)` | `GET {SUPABASE_URL}/auth/v1/user` with anon key + user bearer; transport and 5xx → `supabase_auth_unavailable`, 401/403 → `invalid_token`, malformed → `supabase_auth_unexpected`. |
| `verify_access_token(token)` | Cache hit short-circuits, otherwise fetch, then read the email from the Supabase payload, falling back to the JWT claim. |
| `clear_cache()` | Tests. |

### Choices made

**Ask the authority, don't verify locally.** Verifying signatures locally depends
on knowing which of Supabase's two signing setups the project uses (legacy
shared secret, asymmetric keys). A verified token is short-lived and cached by its
own hash with the expiry known, so bad cache doesn't outlast token validity.

**Cache bounded, entries evicted by age.** Unbounded growth otherwise maps
1:1 to session volume on a free-tier box (and rotating eviction to
oldest-expiry is the cheapest correct policy available from these entries).

## api/supabase_cookies.py

The cookie format `@supabase/ssr` writes.

| Function | Does |
| --- | --- |
| `SupabaseSession` | access_token + optional refresh_token / expires_at (epoch); `.is_expired` from clock. |
| `_b64url_decode(value)` | Right-padded `-`/`_` alphabet decoder. |
| `_candidate_names(cookies)` | Names containing `auth-token`; chunked names via `_CHUNK_SUFFIX` are collapsed to their root name, plain names go first (plain wins when both exist). |
| `_combine(name, cookies)` | Plain value, or chunks `.0 .1 …` concatenated; stops at the first gap rather than mixing halves. |
| `_decode_value(encoded)` | `base64-` prefix stripped before decoding; a project set to `cookieEncoding: "plain"` is raw JSON. |
| `_parse_session(raw)` | Access-token doc in a cookie plus token: rejects malformed, silently ignores non-session JSON. |
| `extract_session(cookies)` | Walk candidates and return the first resolvable session. |

### Choices made

**Strip before decode.** The `base64-` prefix is text, not base64; decoding
without stripping it returns a plausible-looking error rather than real garbage.

**Stop at the first gap, not a complete chunk set.** A missing middle chunk with
the last chunk present means two different sessions concatenated (a session
swap mid-write is very much possible with a soon-to-expire chunk) — every
incompleteness means silence, which the API answers 401 to anyway.

## api/access.py

Every query filter in the API starts here and filters by `owner_id` directly.

| Function | Does |
| --- | --- |
| `owner_id(principal)` | `str(principal.id)` — the Supabase user id, used on every model. |
| `libraries_for / documents_for / chat_sessions_for` | Ownership filters, optional narrowing to a library. |
| `chunks_for(principal, document)` | Owner-scoped chunks; used for counts and detail views. |
| `searchable_chunks(principal, library)` | Chunks that can be cited: ready document, embedding present, document select_related. |
| `profile_for(principal)` | The local Profile row, or none. |

### Choices made

**Filter before anything else.** The UUIDs in URLs get `.filter(...).first()` —
a foreign id reads as "not found" without revealing existence.

**RLS is the second net.** Migrations 0003 and 0005 enable row level security on
`profiles`, `libraries`, `documents`, `chunks`, `chat_sessions`, `chat_messages`.
The API is the paying (session-pool) Supabase role and would bypass these
another day, but the tables' policies are enforced by Django filters — RLS is
the floor under them, not the gate itself.

## api/library_service.py

Library and document lifecycle outside request handlers.

| Function | Does |
| --- | --- |
| `get_or_create_default_library(principal)` | Guarantees one default library per account: existing wins, creation is transaction-wrapped, and on the unique-partial conflict the winning row is returned. |
| `create_document(principal, library, **fields)` | Ownership re-checks the library, creates the row with `QUEUED` stage. |
| `advance_stage(document, target)` | The transition validation. `FAILED → QUEUED` is the retry transition (clears the reason); terminal stages refuse to leave; `failed` is legal from anywhere; every forward move must be exactly one step. |
| `fail_document(document, reason)` | `FAILED` + the reason (truncated to 2000 — it's user-visible). |
| `document_counts_by_stage(documents)` | Board aggregation, all stages zero-filled. |
| `is_ready_for_chat / ready_documents` | Chat-side predicates. |

### Choices made

**Exactly one step forwards.** Allowing a jump would let a bug skip embedding and
mark a document ready with no vectors in the DB — the failure wouldn't surface
until a user asked, months later.

**Library races resolve by constraint.** The partial unique index
`libraries_one_default_per_owner` makes the second INSERT the loser; its
`IntegrityError` handler re-reads and returns the row the winner created.

## api/serializers.py

Read-only model serializers. `ProfileSerializer` exposes settings fields such as
`max_documents` for display; the server decides their values, so the client
never writes through these. `AskQuestionSerializer` is the one write-validation
path: question (`MAX_QUESTION_CHARS` guard), `session`, `library`,
`new_session`.

## api/profiles.py

| Function | Does |
| --- | --- |
| `get_or_create_profile(principal)` | Creates the Profile row keyed by the Supabase id on first contact; backfills a missing email from a later session that has one. |

Backfilling, not updating: an email present in the Supabase payload is
authoritative, but a row already carrying an email is never touched.

## URL surface

| Route | Class |
| --- | --- |
| `GET /api/v1/health` (+ `/health`) | `HealthView` — liveness, DB check; DEBUG-only pipeline summary |
| `GET /api/v1/me` | `MeView` — profile bootstrap |
| `GET /api/v1/session` | `DemoPrincipalView` — auth debug |
| `GET/POST /api/v1/libraries`, `documents`, `documents/upload`, `documents/{id}` | Library & document CRUD |
| `POST /api/v1/chat/ask`, `GET /api/v1/chat/sessions[/{id}]` | Chat |

Error envelope everywhere: `{"error": {"code": ..., "message": ...}}` —
one JSON shape to parse, one mapping table in the frontend.

## config/settings.py, variable by variable

| Variable | Default | Why it looks like this |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | required | Fail-fast rather than an insecure default. |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Supplied by the UI explicitly. |
| Supabase URL / anon key | required | Needed for identity verification even before any DB use. |
| Database | Supabase PG or a local test PG | Test-suite detection (`pytest` in sys.modules) switches to SQLite — no vectors, no advisory locks, no HNSW — where the RLS phase just can't be exercised; `REVIA_TEST_DB=postgres` opts into the container. `REVIA_TEST_PG_*` wires the docker pgvector one-shot command in the error message. |
| `REST_FRAMEWORK` throttles | 60/min session, 60/h generation, 120/h upload | "session" exists because the cookie is the keyable identity; "generation" because every hit costs real money that otherwise has no meter. |
| `CORS_ALLOWED_ORIGINS` | localhost:3000s | One list feeding cors-headers, `CSRF_TRUSTED_ORIGINS`, and `api.auth`. |
| `CSRF_COOKIE_NAME` | `""` | No Django CSRF cookie can be issued by this service; the origin check is the protection. |
| `SUPABASE_AUTH_CACHE_SECONDS` | 300 | Verified access tokens are short-lived; 5 min is a safe half-life that still absorbs per-request auth costs. |
| `SUPABASE_AUTH_TIMEOUT_SECONDS` | 5 | One authority call per request maximum; wait longer and requests pile up. |
| `GROQ_MODEL`, `GROQ_API_KEY` | `openai/gpt-oss-120b` | Chat model on the free tier. |
| `CLOUDFLARE_*` | – | Account id + API token (Workers AI Edit). |
| `EMBED_MODEL` / `EMBEDDING_DIM` | `BAAI/bge-small-en-v1.5` / 384 | The frozen pair (asserted by `embedding_client`, guarded by `apps.py` check, baked by migration 0002). |
| `EMBEDDING_QUERY_PREFIX` | BGE query instruction | The exact string BGE docs give; the trailing space matters. |
| Storage (`SUPABASE_S3_*`) | bucket `document` | S3-compatible endpoint + keys from the Supabase storage settings. |
| `MAX_UPLOAD_BYTES` | 25 MB | Round number in MB because the message says MB. |
| `ALLOWED_UPLOAD_EXTENSIONS` | pdf/docx/pptx | The three lecture formats chosen on purpose. |
| `PDF_PARTITION_STRATEGY` | `hi_res` (local), `fast` (render.yaml) | Layout detection costs RAM/cycles; production can't afford it. |
| `REVIA_RUN_PIPELINE_IN_PROCESS` | True | The default single-worker web process; the only alternative is an explicit `run_pipeline` command elsewhere. |
| `PIPELINE_BATCH_SIZE` / `IDLE` / `BUSY` | 10 / 5 s / 0.5 s | Poll cadence: tight while there's work, relaxed while idle. |
| `PIPELINE_STALLED_SECONDS` | 900 (15 min) / 300 in DEBUG | Generous against slow Cloudflare calls; DEBUG shortens it to exercise reaping quickly. |
| `CHAT_CONTEXT_WINDOW` / `ANSWER_MAX_TOKENS` | 131072 / 1200 | The window model runs on; the reserve bounds the answer so retrieval gets ~25% of the remainder. |
| `ANSWER_TEMPERATURE` | 0.1 | A citation engine, not a poet. |
| `CHAT_HISTORY_TURNS` / `MAX_TOKENS` | 8 / 3000 | Estimated cheaply; capped rather than truncation cut off. |
| `MAX_QUESTION_CHARS` | 4000 | Kills prompt-thrash DoS while leaving real questions plenty of room. |
| `RETRIEVAL_MAX_DISTANCE` | 0.45 | The measured gap between real matches (0.18–0.34) and unrelated text (0.52+). |
| `LOGGING` | INFO to console | Render log aggregation is the only sink; a single plain formatter. |

## Deployments and operations

**Dockerfile** — python 3.14-slim + uv, dependency layers first (cached while
code changes), the cv2/X11 system libraries unstructured's opencv import needs
even for the "fast" partition path, single gunicorn worker w/ 4 threads. One
worker because (a) the advisory-lock worker wants one process, and (b) 512 MB.

**render.yaml** —Singapore region, free plan, health `/health` (the no-auth
route), `PDF_PARTITION_STRATEGY=fast`, secrets `sync: false` (set in the
dashboard: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CORS_ALLOWED_ORIGINS`, Supabase URLs/keys/DB, `GROQ_API_KEY`,
`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`).

**Embedding economics.** Cloudflare's free tier grants 10,000 neurons/day.
bge-small consumes ≈1,841 neurons per 1 M input tokens, so a day's budget is
≈5.4 M tokens — roughly 85 typical lecture PDFs. On exhaustion code 4006 fires
and the document is marked `failed` with a reason naming the 00:00 UTC reset;
`manage.py reingest` then rebuilds the failed ones. There is no paid tier
dependency — a second account would mean all stored vectors belonged to the
first model anyway.

**Tests at a glance.** `uv run pytest` runs 133 tests on in-memory
SQLite (127 pass, 6 vector-RLS tests skipped without a real Postgres — as
intended). `verify_embeddings` embeds real sample text through the exact
production code path and prints dimensions + norms, exercising
credentials, batching, normalisation and the query prefix end to end.
