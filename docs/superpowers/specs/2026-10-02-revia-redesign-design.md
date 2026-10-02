# ReviA — Redesign & Rename Design Spec

**Date:** 2026-10-02
**Status:** Approved (chat) — pending written review

## Purpose

Rename the application from **EndNote** to **ReviA** throughout, and give the
frontend a bold, futuristic-editorial visual identity (working name:
"Futurist Reading Room"). The product is unchanged: a citation-backed study
tool. Routes, flows and data contracts are unchanged.

## Scope

In scope:
- Full internal rename `EndNote → ReviA` (brand, code, env vars, packaging, docs).
- A new design system (type, color, shape, motion) applied to every screen.
- Interaction-state polish (hover/active/focus/loading/empty/error) on every screen.
- Page composition rework on all four routes.

Out of scope:
- Any change to flows, navigation, or routes (`/`, `/chat`, `/pipeline`, `/login`).
- Any change to the API contract, auth, ingestion, retrieval or database.
- Dark mode (explicitly rejected: light-only, locked).
- New features.

## Decisions (locked)

| Decision | Value |
|---|---|
| Rename depth | Full internal rename |
| Redesign depth | Bold overhaul, same flows |
| UX depth | Visual + interaction polish |
| Theme | Light-only, locked (no dark tokens, no toggle) |
| Accent | Royal purple `#4B2E83` (single accent) |
| Display type | Open-source futuristic (Orbitron) |
| UI/body type | Geist sans |
| Metadata type | JetBrains Mono |
| Dials | DESIGN_VARIANCE 7 / MOTION_INTENSITY 5 / VISUAL_DENSITY 5 |

Rationale for rejecting the originally-linked demo fonts (Corpta by Pandeka
Foundry, Deltha by Vultype): both are personal-use-only, explicitly forbid
commercial/web/application embedding, and ship reduced glyph sets. ReviA ships
with SIL Open Font License faces instead, self-hostable and commercial-safe.

## Design system

### Typography
| Role | Face | Weights | Use |
|---|---|---|---|
| Display | Orbitron | 500, 700 | Wordmark, hero H1, page/CTA headlines, large numerals |
| UI + body | Geist | 400, 500, 600 | Nav, buttons, body, forms, section titles, list rows |
| Metadata | JetBrains Mono | 400, 500 | Citation labels, page numbers, stages, file sizes, dateline |

Display is used with intent, not everywhere: repeated section titles are Geist.
No serif. Fonts loaded via `next/font/google` with `display: "swap"`.

### Color (light, locked)
| Token | Value | Use |
|---|---|---|
| `--color-paper` | `#fcfcfa` | Page background |
| `--color-surface` | `#ffffff` | Raised panels |
| `--color-sunk` | `#f4f3ef` | Inset/quiet fill |
| `--color-ink` | `#121212` | Primary text |
| `--color-ink-soft` | `#2c2c2a` | Body prose |
| `--color-muted` | `#6c6c68` | Secondary text |
| `--color-faint` | `#9d9c96` | Tertiary/metadata |
| `--color-line` | `#e6e5df` | Hairlines |
| `--color-line-strong` | `#d4d3cc` | Emphasised hairlines |
| `--color-accent` | `#4b2e83` | Single accent: links, citations, primary CTA |
| `--color-accent-soft` | `#efe9f6` | Accent-tinted fill |
| `--color-success` | `#2f6b43` | Ready stage (semantic only) |
| `--color-danger` | `#9f2f2d` | Failed stage / errors (semantic only) |
| `--color-warning` | `#8a5a00` | Embedding/in-flight warning (semantic only) |

No pure `#000000`/`#ffffff` as text/background pairs beyond the listed tokens.
Shadows are purple-tinted, e.g. `0 2px 10px rgb(75 46 131 / 0.05)`.
`::selection` uses `--color-accent-soft` with `--color-accent` text.

### Shape
All-sharp. `--radius-card: 0`, `--radius-control: 0`. One consistent scale:
every card, button, input, badge and panel is square with a hairline border.
No mixed radii.

### Motion (intensity 5)
- Reuse the existing `Reveal` component for section entry.
- Hover: underline/colour shift on links; `-translate-y-px` + border shift on buttons.
- Active: `scale-[0.98]`.
- Focus: visible 2px accent outline, `outline-offset: 2px`.
- All non-essential motion disabled under `prefers-reduced-motion: reduce`.
- No marquees, no scroll-hijacking, no custom cursors, no infinite decorative loops.

### Imagery
No image-generation tool is available. Use `next/image` with seeded
`https://picsum.photos/seed/revia-*/W/H` placeholders for the landing hero and
one supporting editorial image, with `remotePatterns` added to `next.config.ts`.
Track replacements in `docs/revia-image-slots.md` (the plan creates it). The
existing landing Q&A preview stays: it is a real component preview rendering
real citation data, not a fake screenshot.

## Page composition

Each page keeps its current routes and behaviour.

- **Chrome** — sharp sticky hairline header; ReviA wordmark + simple monogram
  mark; single-line desktop nav; simplified footer; the
  "Unrelated to EndNote from Clarivate" line is deleted. `app/icon.svg` favicon.
- **Landing `/`** — left-aligned Orbitron hero (max 2 lines) with a right-side
  image, ≤4 hero text elements, mono dateline instead of a pill badge; case-file
  Q&A section with purple marginal citations; asymmetric numbered "how it works";
  features as an asymmetric bento grid (no row of three equal cards); pipeline
  spread; two-plan pricing; FAQ as a two-column list; Orbitron closing CTA. Each
  section uses a distinct layout family; at most 2 eyebrows on the page.
- **Chat `/chat`** — keep the three columns. History becomes a *Contents* index;
  transcript becomes a reading column with citation cards set as marginal
  footnotes; library becomes an *Evidence* ledger with mono stage tags. Full
  hover/focus/empty/loading/error treatment.
- **Pipeline `/pipeline`** — keep six stage columns as sharp hairline rails with
  mono metadata; clearer in-flight and failed states.
- **Login + modal/form** — sharp two-panel split; Orbitron statement; square
  inputs; helpers above input, error below.

## Copy rules
- Sentence case for headers; no AI clichés ("Elevate", "Seamless", "Unleash",
  "Next-Gen", "Delve", "Tapestry"); no exclamation marks; no fake-precise
  numbers that the product does not claim; no em dashes used as design flourish.
- The word "EndNote" does not appear in user-visible copy or code identifiers.
- `APP_NAME` is the single source of truth for the brand string.

## Rename matrix (contract)
| Surface | From | To |
|---|---|---|
| `frontend/lib/config.ts` `APP_NAME` | `EndNote` | `ReviA` |
| `frontend/package.json` name | `endnote-frontend` | `revia-frontend` |
| `frontend/package-lock.json` name (x2) | `endnote-frontend` | `revia-frontend` |
| `frontend/scripts/check-live-data.mts` label | `ENDNOTE` | `REVIA` |
| `frontend/components/chrome.tsx` disclaimer | present | deleted |
| `backend/api/apps.py` `verbose_name` | `EndNote API` | `ReviA API` |
| `backend/api/ingestion.py` `WORKER_LOCK_KEY` | `0x456E644E6F746521` (`b"EndNote!"`) | value of `b"ReviA!"`, comment updated |
| `backend/api/pipeline_worker.py` thread name | `endnote-pipeline` | `revia-pipeline` |
| `backend/api/management/commands/run_pipeline.py` message | `ENDNOTE_RUN_PIPELINE_IN_PROCESS` | `REVIA_RUN_PIPELINE_IN_PROCESS` |
| `backend/config/settings.py` env vars + docstring | `ENDNOTE_*` / `EndNote backend` | `REVIA_*` / `ReviA backend` |
| `backend/.env.example` | `ENDNOTE_*`, `endnote-test-pg`, `endnote` | `REVIA_*`, `revia-test-pg`, `revia` |
| `pyproject.toml` name/description | `endnote` | `revia` |
| `uv.lock` root package name | `endnote` | `revia` |
| `README.md` | `EndNote`, `ENDNOTE_*`, `endnote*` DB/docker names | `ReviA`, `REVIA_*`, `revia*` |

`ENDNOTE_ENV_FILE` is read from the environment to locate `.env`; the renamed
variable is `REVIA_ENV_FILE`. `backend/.env` contains no `ENDNOTE_*` keys
(verified), so no secret file needs editing.

## Security note (in-scope)
`README.md` currently contains plaintext login credentials near the end. These
are removed as part of the rename task.

## Verification
- `cd frontend && npm run typecheck && npm run lint && npm run build`.
- `uv run ruff check backend && uv run python backend/manage.py check && uv run pytest`.
- `grep -ri endnote` over tracked files returns nothing (git history excluded).
- Manual pass on all four routes, signed-in and signed-out, desktop and mobile,
  keyboard-only, and with reduced motion enabled.
