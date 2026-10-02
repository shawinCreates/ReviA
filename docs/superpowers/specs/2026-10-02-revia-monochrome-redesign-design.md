# ReviA — Achromatic Redesign Design Spec

**Date:** 2026-10-02
**Status:** Approved in chat — pending written review
**Supersedes:** nothing. Succeeds `2026-10-02-revia-redesign-design.md` on the
visual system only; that spec's routes, copy rules and rename matrix still hold
where this one is silent.

## Purpose

Move ReviA's visual system from purple-on-cream to achromatic, and fix four
surfaces that the previous pass left wrong: the landing page's ingestion section
sends visitors into the signed-in product, the chat transcript renders citation
markers as literal text, the sign-in page spends half its width on decoration,
and the copy makes two claims the backend does not support.

The product is unchanged. Routes, flows, data contracts and the API are
untouched.

## Scope

In scope:

- An achromatic colour system (section 1).
- Landing page: ingestion section becomes a static illustration (section 2).
- Chat transcript: message fill and citation rendering (section 3).
- Sign-in and sign-up: single centred column (section 4).
- An accuracy and restraint pass over every user-visible string (section 5).

Out of scope:

- Any route, flow or API change.
- Typography. Orbitron, Geist and JetBrains Mono stay exactly as they are.
- Dark mode. Light-only, locked.
- Password reset. Citation deep links. Both need backend work; see section 6.

## Design read

Redesign pass on a study tool's marketing and product surfaces, for students who
need checkable citations, with a restrained achromatic print language, leaning on
the existing Tailwind v4 token set.

| Dial | Was | Now | Why |
|---|---|---|---|
| `DESIGN_VARIANCE` | 7 | 4 | The brief was minimal. Asymmetry, split headers and staggered reveals are removed or reduced. |
| `MOTION_INTENSITY` | 5 | 3 | Nothing is added. The existing `Reveal` stays because it is already load-bearing for the no-JS path. |
| `VISUAL_DENSITY` | 5 | 5 | Unchanged. Chat is a dense product surface. |

## Decisions (locked)

| Decision | Value |
|---|---|
| Colour | Achromatic. No accent hue. |
| Semantic colour | `danger`, `success`, `warning` keep their hue. They carry state, not decoration. |
| Display type | Unchanged (Orbitron) |
| Body type | Unchanged (Geist) |
| Metadata type | Unchanged (JetBrains Mono) |
| Shape | Unchanged. All-square, one radius scale. |
| Theme | Light-only, locked |
| Landing ingestion section | Static illustration. No card links. No CTA. |
| Citations | Inline superscript markers, one line per source, snippet behind a click. |
| Message style | User message keeps right alignment, loses the solid fill. |
| Auth layout | Single centred column. |
| Copy | Accuracy and restraint. Structure and section order unchanged. |

---

## 1. Tokens

The entire colour change is the `@theme` block in `app/globals.css`. Every
`text-accent`, `bg-accent`, `border-accent`, `border-l-accent` and
`border-t-accent` in the tree keeps its class name and resolves to ink.

| Token | From | To |
|---|---|---|
| `--color-paper` | `#fcfcfa` | `#fafafa` |
| `--color-surface` | `#ffffff` | `#ffffff` (unchanged) |
| `--color-sunk` | `#f4f3ef` | `#f1f1f0` |
| `--color-ink` | `#121212` | `#141414` |
| `--color-ink-soft` | `#2c2c2a` | `#2b2b2b` |
| `--color-muted` | `#5d5d59` | `#5a5a5a` |
| `--color-faint` | `#6f6f6b` | `#6b6b6b` |
| `--color-line` | `#e6e5df` | `#e4e4e3` |
| `--color-line-strong` | `#d4d3cc` | `#cfcfcd` |
| `--color-accent` | `#4b2e83` | `#141414` (same as ink) |
| `--color-accent-soft` | `#efe9f6` | `#f1f1f0` (same as sunk) |
| `--color-success` | `#2f6b43` | unchanged |
| `--color-danger` | `#9f2f2d` | unchanged |
| `--color-warning` | `#8a5a00` | unchanged |

The neutrals lose their warm cast. They are now cool greys, which is what makes
the page read as printed rather than tinted.

Shadows drop the purple tint: `--shadow-whisper` and `--shadow-lift` become
`rgb(20 20 20 / 0.05)` and `rgb(20 20 20 / 0.07)`.

### Contrast

`muted` and `faint` carry 10-13px metadata and are held to 4.5:1 against all
three surfaces, as the current token comment documents. The new values measure
`muted` 6.61 / 6.90 / 6.10 and `faint` 5.11 / 5.33 / 4.72 against
`paper / surface / sunk`. `faint` clears the bar on the darkest surface
(`sunk`), which is where it lands in the chat drop zone. The existing comment
block is updated with these figures rather than deleted.

Where `text-accent` sat on `bg-accent-soft` the pair gets stronger, not weaker:
ink on sunk measures 16.3:1, against 8.75:1 for the old purple pair. `white` on
the solid button measures 18.4:1.

### Three consequences to handle deliberately

These are the places where accent was doing work that a same-valued token cannot
do. Each needs an explicit edit, or the change introduces a silent regression.

1. **`Button` solid hover.** `components/ui.tsx:14` is
   `bg-accent text-white hover:bg-ink`. With accent equal to ink the hover
   becomes a no-op. Change to `hover:bg-ink/85`.
2. **Pricing badges.** `app/page.tsx:364-368` renders `Badge tone="accent"`
   ("Planned") beside `Badge` ("Beta"). Both collapse to `bg-sunk`, differing
   only in text colour. Delete the `Beta` badge, since the section headline
   already says the project is in beta, and render `Planned` as plain
   `text-muted` text.
3. **Focus ring.** `app/globals.css` `:focus-visible` uses
   `var(--color-accent)`, which becomes ink. It already carries
   `outline-offset: 2px`, so the ring sits outside the control on the page
   background and stays visible against a solid ink button. No edit needed, but
   it is checked on the sign-in form's submit button by hand.

No other `accent` usage in the tree changes meaning. The `warm-wash` and
`hairline-grid` utilities stay available; `warm-wash` loses its warm name-only
meaning with the palette and keeps working, since it is a neutral radial
gradient over `--color-line`-derived greys.

---

## 2. Landing page

### The ingestion section becomes static

The problem is not only that `PipelineBoard`'s cards link to `/chat`
(`components/pipeline/board.tsx:127`) and the "See the full board" button links
to `/pipeline` (`app/page.tsx:329`). Both of those send a signed-out visitor
into the signed-in product from a marketing page. It is also that the landing
page mounts a `"use client"` board at all.

New file `components/pipeline/preview.tsx`, a server component:

- Imports `STAGES`, `STAGE_LABELS` and `DEMO_PIPELINE_DOCUMENTS`.
- Renders the same six rails, the same stage glyphs and the same rail blurbs as
  the live board, so the visual language is identical.
- Cards are `<div>` elements. No `Link`, no `useLibrary`, no `use client`, no
  client JavaScript on a marketing page.
- No "in flight / documents" counter and no "Showing the sample library" line.
  Those are live-data affordances and they imply the fixtures are real. The
  section copy carries the framing instead.
- No signup bar.

`app/page.tsx` imports `PipelinePreview` instead of `PipelineBoard`, keeping the
`<div className="mt-12 border-t border-line pt-10 md:mt-14">` wrapper it already
sits in. The preview gets no `Reveal` wrapper, because the board it replaces has
none.

The live `PipelineBoard` is unchanged and stays the whole of `/pipeline`. This
is deliberate duplication: sharing the component is what puts a client hook and
an outbound link on the marketing page.

The "See the full board" `ButtonLink` is deleted from the section. `/pipeline`
stays reachable from the site header nav and the footer, which is where a
product surface belongs in the information architecture.

### Eyebrows: four becomes one

The landing page has seven sections, so one eyebrow is the budget. Surviving:
`Why it holds up` (`app/page.tsx:225`), which labels the explanation rather than
restating the headline beside it.

Deleted: `2026 · beta` (`:134`), `case file · judicial-review` (`:184`),
`question` (`:189`), `Ingestion` (`:324`).

`SectionLabel` survives as a component. It is still the column title for
`Contents` and `Library` in the chat columns and for the footer columns.

### Everything else

Hero, the case-file Q&A preview, how-it-works, the features bento, pricing, the
FAQ and the closing band keep their structure, order and layout. The
`2026 · beta` removal drops the hero to three text elements, which is under the
four-element budget.

---

## 3. Chat transcript

### Citations

The bug: `lib/api.ts:258` rewrites the model's `[1]` markers into `[S1]` inside
`Message.content`, and `components/chat/columns.tsx:214` renders paragraphs as
bare `<p>` text. A visitor reads `[S1]` as literal characters, and the snippet
cards below are visually unrelated to them.

New pure module `lib/markers.ts`:

```ts
export type MarkerRun = { text: string };
export type MarkerRef = { label: string };
export type Segment = MarkerRun | MarkerRef;

export function splitMarkers(text: string): Segment[]
```

Split on `/\[(S\d+(?:,\s*S\d+)*)\]/`. Plain text becomes a `MarkerRun`. A
bracket group becomes one `MarkerRef` per label, so `[S1, S2]` yields two refs.
Anything that does not match the pattern stays inside a `MarkerRun`, which is
what preserves the guarantee `toDisplayText` already provides: a bracketed year
like `[2024]` or an unresolved reference stays as written and renders as text.

Rendering in `MessageBlock`:

- A `MarkerRun` renders as a `<span>`.
- A `MarkerRef` renders as `<sup>` in `font-mono`, `text-ink`, clickable. Clicking
  it expands and highlights the matching source line, and scrolls it into view.
  `aria-label` is `Source ${label}`.
- Paragraph splitting on `\n\n` is unchanged, so a marker never straddles a
  paragraph break.

Sources replace the `flex flex-wrap gap-2` grid of bordered snippet cards
(`columns.tsx:231-247`) with a numbered list:

- One line per source: mono label, filename, then `p. N` or `no page`.
- The snippet sits behind a click on that line, revealed in place.
- Exactly one source open at a time. Opening a second closes the first.
- Clicking an inline marker opens its source. Opening a line by hand does not
  require a marker to exist, since a citation can be returned without an inline
  reference to it.

The `refused` and `uncited` notes stay as they are.

### Messages

The user's solid fill becomes `bg-sunk text-ink`
(`columns.tsx:204`). Right alignment against a left-aligned answer already
carries the role distinction; the black slab was decoration on top of it.

Nothing else in the transcript moves. The header, the pending line, the error
block with its dismiss and retry actions, and the empty-library notice are
unchanged.

### Dead code

`ChatTitleBar` (`components/app-header.tsx:88`) has no references anywhere in
the tree. Delete it.

---

## 4. Sign-in and sign-up

Single centred column at `max-w-[380px]`: wordmark, form, back link. Delete
`app/login/page.tsx:20-39`, which is the whole left panel, and with it the
metadata strip reading `20 documents per library · 25MB per file · PDF, DOCX,
PPTX`. The limits it stated are already in the chat drop zone
(`library-column.tsx:130`) and in the upload rejection copy
(`library-column.tsx:61-66`).

The grid wrapper becomes a plain `flex min-h-dvh items-center justify-center`
with the wordmark above the form.

`components/auth-form.tsx` is unchanged apart from section 5. The auth modal
keeps its current layout, since it is a dialog over the product and already has
the right density.

---

## 5. Copy

Accuracy and restraint. Section order and page structure do not change.

### Claims that are not true today

`backend/api/storage.py` is plain boto3 `put_object` / `get_object` /
`delete_object`. No presigned URL is ever generated, and no URL to a stored file
is ever handed to the browser. Two landing strings describe an implementation
that does not exist:

- `app/page.tsx:44`, "a citation link expires".
- `app/page.tsx:44`, "reached through short-lived signed URLs".

Both strings are in the one `body` on line 44. They are rewritten to what the
code does: objects live in a private bucket, the server reads them during
ingestion, and no address for a stored file is ever issued to the browser.

### Middle-dot runs

Nine occurrences across eight sites. The rule is at most one per line, and for
metadata runs the answer is usually a column or a line break rather than another
separator.

| Location | From | To |
|---|---|---|
| `app/page.tsx:134` | `2026 · beta` | deleted |
| `app/page.tsx:184` | `case file · judicial-review` | deleted |
| `app/page.tsx:207,215` | `S1 · p. 7` | two mono spans in a flex row, hairline-free, `gap` instead of the character |
| `app/login/page.tsx:36` | limits strip | deleted with the panel |
| `app/pipeline/page.tsx:25` | `ingestion · 6 stages` | two stacked lines, `Ingestion` then `6 stages` |
| `library-column.tsx:130` | `PDF, DOCX, PPTX · up to 25 MB` | `PDF, DOCX, PPTX. Up to 25 MB.` as two sentences in one string |
| `columns.tsx:242` | `S1 · filename · p. 7` | the new source line, no separator character |
| `app-header.tsx:93` | `ReviA · sample library` | deleted with `ChatTitleBar` |

### Em-dashes

Zero, anywhere a visitor can read. Comments and docstrings are exempt.

Four fixtures in `lib/mock/data.ts` carry one, and a signed-out visitor reads
them in the chat transcript:

- `Constitutional Law — Week 4 Notes.pdf` (`:22`). The `CITE` map at `:133`
  holds the same string and must change with it, or the citation filename
  stops matching the library filename.
- `Microbiology Lab Report — Draft.docx` (`:81`) becomes a plain hyphen.
- `Sicilian Gardens, 1780–1900.pdf` (`:70`) uses an en-dash in a date range;
  ranges use a hyphen.
- The sample answer at `:153`, "not an appeal against the decision itself —
  the court does not re-run". Restructured around a colon.

`app/layout.tsx:28-29` puts an em-dash in the document title and in every page
title derived from it. Both become a colon and a pipe.

### Everything else

Each remaining user-visible string is re-read for filler, unsupported claims,
passive-aggressive framing and mock-poetic phrasing. Three candidates flagged
during the audit, each to be resolved by rewriting rather than by keeping:

- The how-it-works headline, "Four steps, then it is just answering
  questions", asserts a transition the product does not make.
- The features headline, "Built around the failure modes of a chat tool that
  quotes itself", is a claim about a competitor category dressed as a
  statement about this one.
- The closing headline, "Bring one document you already know", is the clearest
  of the three and likely survives unchanged.

If a rewrite cannot be made plain, the string is replaced with a plain
functional sentence.

---

## 6. Explicitly not doing

- **Password reset.** Needs a reset-request call, a callback route and a
  new page. New routes are out of scope.
- **Citation deep links.** Needs a page-view endpoint and presigned URL
  issuance in the backend. Storage is plain boto3 with no signing helper, so
  this is real backend work, not a link change.
- **Dark mode.** Locked light.
- **Any backend change.**
- **Any test framework.** `scripts/check-*.mts` already covers this pattern.

---

## 7. Files

| File | Change |
|---|---|
| `app/globals.css` | Token values, shadow tint, contrast comment |
| `components/ui.tsx` | `Button` solid hover |
| `app/page.tsx` | Static preview import, four eyebrow deletions, pricing badges, six copy strings, delete the section CTA |
| `components/pipeline/preview.tsx` | New. Server component |
| `app/login/page.tsx` | Delete the left panel, single centred column |
| `components/chat/columns.tsx` | Message fill, marker and source rendering, delete the snippet-card grid |
| `lib/markers.ts` | New. `splitMarkers` |
| `components/app-header.tsx` | Delete `ChatTitleBar` |
| `app-header.tsx` | Delete `ChatTitleBar` |
| `app/layout.tsx` | `<title>` separators |
| `lib/mock/data.ts` | Em-dashes in fixture filenames and the sample answer |
| `scripts/check-markers.mts` | New. Asserts for `splitMarkers` |
| `package.json` | `check:markers` script |
| `app/pipeline/page.tsx` | Eyebrow line break |

Unchanged: `components/pipeline/board.tsx`, `components/auth-form.tsx`,
`components/auth-modal.tsx`, `components/chat/library-column.tsx`,
`components/chrome.tsx`, `components/chat/workspace.tsx`, everything under
`backend/`.

## 8. Verification

```bash
cd frontend
npm run typecheck && npm run lint && npm run build
npm run check:mapping && npm run check:markers
```

`splitMarkers` is a parser, so it gets `scripts/check-markers.mts` following the
existing `check-mapping.mts` pattern: assert-based, no framework. It covers the
single marker, the grouped marker, a bracketed year staying text, an
unresolved label staying text, and a string with no markers.

Manual pass, all four routes, signed in and signed out, desktop and mobile:

- Every CTA meets 4.5:1, or 3:1 at 18px and over.
- `hover:bg-ink/85` is visibly distinct from `bg-ink`.
- The pricing badges no longer read as the same badge.
- Clicking an inline marker expands and highlights its source.
- Clicking a source line twice collapses it.
- The landing ingestion section links nowhere.
- Reveal content is present with JavaScript disabled.
- The page reads the same at 200% zoom.

## 9. Risks

- **Accent equals ink, so any future `accent` usage inherits that.** Recorded
  here so the next person does not add a coloured `text-accent` and expect it
  to read as an accent. If a hue ever comes back, it gets a new token name
  rather than reusing `accent`.
- **Deleting the pipeline CTA removes the only landing-page route into
  `/pipeline`.** Nav and footer still reach it. If that proves too thin in
  practice, the honest fix is a signup CTA, not a link to a page of someone
  else's sample library.
- **`splitMarkers` is the one piece of new logic in the change**, and it sits
  on the path that decides what a citation points at. That is why it gets a
  runnable check rather than a comment.