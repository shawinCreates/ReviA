# Achromatic Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move ReviA from purple-on-cream to an achromatic colour system, and fix the landing ingestion section, the chat citation rendering, the sign-in page and the copy.

**Architecture:** The colour change is a single `@theme` block edit in `app/globals.css`: `--color-accent` becomes the same value as `--color-ink`, so every existing `text-accent` / `bg-accent` / `border-l-accent` in the tree keeps its class name and resolves to ink. The landing ingestion section stops mounting the live `"use client"` `PipelineBoard` and gets a static server-rendered `PipelinePreview` with no links and no client JavaScript. The one piece of new logic is `splitMarkers`, a pure parser in `lib/markers.ts` that turns the `[S1]` markers already baked into `Message.content` into renderable segments.

**Tech Stack:** Next.js 16 app router, React 19, TypeScript, Tailwind v4, `next/font/google`. No new dependencies. No backend changes.

**Spec:** `docs/superpowers/specs/2026-10-02-revia-monochrome-redesign-design.md`

## Global Constraints

- No new dependencies. Nothing is installed.
- No backend changes. No route changes. No new routes.
- Light theme only. No `dark:` variants are added anywhere.
- Typography is unchanged: Orbitron display, Geist body, JetBrains Mono metadata.
- Shape is unchanged: all-square, one radius scale.
- `--color-accent: #141414` and `--color-accent-soft: #f1f1f0`. Accent equals ink; the token name survives so existing classes keep working.
- `--color-success`, `--color-danger` and `--color-warning` keep their current values. They are the only hues left on the page.
- Zero em-dashes (`—`) and zero en-dashes (`–`) in any user-visible string. Comments and docstrings are exempt. Use a plain hyphen for ranges and compound words.
- At most one `·` per line in a user-visible string. Metadata runs use a column or a line break instead.
- Metadata and secondary text holds 4.5:1 against paper, surface and sunk. The pinned values clear it; do not lighten `faint`.
- No new motion. The existing `Reveal` component is the only entry animation and it stays as it is.

## Review Focus

Five things the spec implies that no automated check covers. Each is verified by hand in the task listed.

1. **An answer with citations but no inline marker.** The model can cite without writing an inline reference. Every source line must still be expandable by hand, with no marker required. Task 3.
2. **An inline marker whose citation was dropped.** `toDisplayText` validates markers, so this should not happen, but if it does the marker must render as inert text rather than a button that expands nothing. Task 3.
3. **A long unbreakable filename in a source line.** It must wrap inside the line and not widen the reading column. Needs `min-w-0 break-words`. Task 3.
4. **A signed-out visitor on the landing page.** The ingestion section must render server-side with no client boundary and no outbound link. Task 4.
5. **Keyboard operation of a source line.** Expansion is a real `<button>`, so Enter and Space work and focus is visible. Task 3.

---

### Task 1: Achromatic tokens and what they collapse

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/components/ui.tsx:14`
- Modify: `frontend/app/page.tsx:360-368`

**Interfaces:**
- Consumes: nothing.
- Produces: the achromatic value of `--color-accent` / `--color-accent-soft`, relied on by every later task that keeps an `accent` class.

- [ ] **Step 1: Replace the token values in `app/globals.css`**

Edit the `@theme` block so it reads:

```
  --color-paper: #fafafa;
  --color-surface: #ffffff;
  --color-sunk: #f1f1f0;
  --color-ink: #141414;
  --color-ink-soft: #2b2b2b;
  --color-muted: #5a5a5a;
  --color-faint: #6b6b6b;
  --color-line: #e4e4e3;
  --color-line-strong: #cfcfcd;

  --color-accent: #141414;
  --color-accent-soft: #f1f1f0;
  --color-success: #2f6b43;
  --color-danger: #9f2f2d;
  --color-warning: #8a5a00;
```

Leave the three semantic colours exactly as written above. Replace
`--shadow-whisper` and `--shadow-lift` with `rgb(20 20 20 / 0.05)` and
`rgb(20 20 20 / 0.07)` respectively, dropping the purple tint.

- [ ] **Step 2: Rewrite the contrast comment above the token values**

The existing comment documents the old purple figures. Replace it with the
measured values for the new palette, which are `muted` at 6.61 / 6.90 / 6.10
and `faint` at 5.11 / 5.33 / 4.72 against paper, surface and sunk. State that
`faint` clears 4.5:1 on all three and that `sunk` is the darkest background any
`faint` text lands on, which is the chat drop zone. Keep the comment's existing
tone: it explains why the values are what they are, so a future change does not
lighten `faint` without knowing what it fails.

- [ ] **Step 3: Fix the solid button hover in `components/ui.tsx`**

The `solid` variant is `bg-accent text-white hover:bg-ink`. Accent now equals
ink, so the hover is a no-op. Change it to:

```
  solid: "bg-accent text-white hover:bg-accent/85",
```

- [ ] **Step 4: Collapse the pricing badges in `app/page.tsx`**

`Badge tone="accent"` and the default `Badge` both resolve to `bg-sunk` now, so
the two pricing badges render identically. Replace the `plan.highlight ?` block
at `app/page.tsx:363-368` with plain text: `Planned` as
`text-[13px] text-ink` when `plan.highlight`, and nothing at all otherwise, since
the section headline already states that the project is in beta. Remove `Badge`
from the `@/components/ui` import on line 16, then confirm no other `Badge`
reference remains in the file.

- [ ] **Step 5: Verify the build**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`

Expected: all three pass. A `Badge` unused-import error at this point means
Step 4 missed a reference.

- [ ] **Step 6: Confirm the three known consequences by hand**

Run the dev server (`npm run dev`) and open `/`, `/login`, `/chat` and
`/pipeline`. Check that the primary button hover is visibly distinct from its
resting state, the two pricing badges no longer look the same, and the focus
ring is visible on the sign-in submit button.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/globals.css frontend/components/ui.tsx frontend/app/page.tsx
git commit -m "feat: achromatic colour system

Accent becomes ink, so every existing accent class resolves to the
primary ink and the page carries no accent hue. Fixes the two things
that collapse when the token changes value: the solid button hover,
which was a no-op, and the pricing badges, which became identical."
```

---

### Task 2: `splitMarkers`

**Files:**
- Create: `frontend/lib/markers.ts`
- Create: `frontend/scripts/check-markers.mts`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `Segment` and `splitMarkers(text: string): Segment[]` from `@/lib/markers`, consumed by Task 3. `Segment` is a discriminated union on `kind`:
  - `{ kind: "text"; value: string }`
  - `{ kind: "marker"; label: string }` where `label` is the bare label with brackets stripped, for example `"S1"`.

- [ ] **Step 1: Write the failing check in `scripts/check-markers.mts`**

Follow the shape of `scripts/check-mapping.mts`: a module docstring saying it
guards the citation-marker parser, a `check(name, condition, detail?)` helper
that prints PASS or FAIL and increments a counter, and a final
`process.exit(failed === 0 ? 0 : 1)`.

Import `splitMarkers` from `"../lib/markers.js"`. Note the `.js` extension: it is
what the existing check scripts use for the same reason.

Add a helper for readability, then these checks:

```
splitMarkers("No markers here.")
  deep-equals [{ kind: "text", value: "No markers here." }]

splitMarkers("Checked [S1].")
  deep-equals [{ kind: "text", value: "Checked " },
               { kind: "marker", label: "S1" },
               { kind: "text", value: "." }]

splitMarkers("Both [S1, S2] agree.")
  deep-equals [{ kind: "text", value: "Both " },
               { kind: "marker", label: "S1" },
               { kind: "text", value: ", " },
               { kind: "marker", label: "S2" },
               { kind: "text", value: " agree." }]

splitMarkers("Published in [2024] here.")
  deep-equals [{ kind: "text", value: "Published in [2024] here." }]

splitMarkers("See [7] for detail.")
  deep-equals [{ kind: "text", value: "See [7] for detail." }]

splitMarkers("[S1] leads.")
  deep-equals [{ kind: "marker", label: "S1" },
               { kind: "text", value: " leads." }]

splitMarkers("")
  deep-equals []
```

The `[2024]` and `[7]` cases are the load-bearing ones. `lib/api.ts` only
relabels a bracketed number into `[S1]` when that number resolved to a real
citation, so anything still carrying square brackets at render time did not
resolve. Rendering it as a marker would point at a source that does not exist,
which is the single failure this product exists to prevent.

- [ ] **Step 2: Add the npm script to `package.json`**

Add next to `check:mapping`:

```
    "check:markers": "tsx scripts/check-markers.mts",
```

- [ ] **Step 3: Run the check to verify it fails**

Run: `cd frontend && npm run check:markers`

Expected: FAIL to resolve `../lib/markers.js`.

- [ ] **Step 4: Implement `splitMarkers` in `lib/markers.ts`**

Export the `Segment` union exactly as pinned in Interfaces. Declare the pattern
as `const GROUP = /\[(S\d+(?:,\s*S\d+)*)\]/g;` and export
`splitMarkers(text: string): Segment[]`.

The tests determine everything else. One pass with the global pattern: append the
text before each match as a single `text` segment, then one `marker` segment per
comma-separated label with the brackets stripped. Skip a zero-length text
segment rather than emitting `""`, which is what makes the empty-string case
return `[]` and what keeps adjacent markers from producing an empty run between
them.

Do not trim or collapse the surrounding text. A marker sitting directly against
a full stop must stay directly against it, or the punctuation detaches from the
sentence.

Add a docstring stating that markers are already validated against real
citations by `toDisplayText` in `lib/api.ts`, and that anything this function
does not match is a model-authored bracket that must render as text.

- [ ] **Step 5: Run the check to verify it passes**

Run: `cd frontend && npm run check:markers`

Expected: every check prints PASS and the script exits 0.

- [ ] **Step 6: Confirm nothing else regressed**

Run: `cd frontend && npm run check:mapping && npm run typecheck && npm run lint`

Expected: all pass. `check:mapping` is included because `splitMarkers` parses
the output of `toDisplayText`, and that check is what pins the output format.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/markers.ts frontend/scripts/check-markers.mts frontend/package.json
git commit -m "feat: citation marker parser

Splits an answer into text and marker segments so the transcript can
render an inline marker instead of the literal [S1] characters. A
bracket that did not resolve to a citation stays text, which is the
guarantee toDisplayText already provides."
```

---

### Task 3: Chat transcript

**Files:**
- Modify: `frontend/components/chat/columns.tsx:200-249`

**Interfaces:**
- Consumes: `splitMarkers` and `Segment` from `@/lib/markers` (Task 2).
- Produces: nothing for later tasks.

- [ ] **Step 1: Add the marker and source state to `MessageBlock`**

`MessageBlock` is rendered per message and is already keyed by `message.id`, so
the open-source state belongs to it and to no higher component. Add:

```ts
const [openSource, setOpenSource] = useState<string | null>(null);
```

`MessageBlock` is defined below `ChatColumn` in a `"use client"` module, so
`useState` is available. Add it to the existing `react` import.

Opening a source closes whichever one was open, which is the "exactly one open"
rule:

```ts
function toggleSource(label: string) {
  setOpenSource((current) => (current === label ? null : label));
}
```

- [ ] **Step 2: Render the answer body through `splitMarkers`**

Replace the paragraph loop at `columns.tsx:213-217`. Keep splitting on `"\n\n"`
and keep `max-w-[68ch]`; a marker must never straddle a paragraph break. Inside
each paragraph, map `splitMarkers(paragraph)` to a keyed fragment:

- `kind === "text"` renders its `value` in a `<span>`.
- `kind === "marker"` renders a `<sup>` holding `label` in `font-mono text-ink`.

A marker is only interactive when `message.citations` contains a citation whose
`label` equals it. When it does not, render the `<sup>` as plain text with no
button and no `aria-label`, because a button that expands nothing is a control
that lies about what it does. This cannot normally happen, since `toDisplayText`
relabels only numbers that resolved to a real citation, but the guarantee is
worth making total at the point of rendering.

When the marker is interactive, it is a `<button>` inside a `<sup>`, with
`aria-label={`Source ${label}`}`. Its click handler is `toggleSource(label)`
followed by scrolling the source into view:

```ts
document
  .getElementById(`source-${message.id}-${label}`)
  ?.scrollIntoView({ block: "nearest", behavior: "auto" });
```

Pass `behavior: "auto"` on purpose. `scroll-behavior: smooth` is already set in
`globals.css` and already neutralised under `prefers-reduced-motion`, and `auto`
defers to it. Passing `"smooth"` here would bypass that and animate for a
reduced-motion visitor.

Give each `<sup>` a stable key of `marker-${index}` and each text fragment
`text-${index}`, since adjacent fragments of the same kind can repeat.

- [ ] **Step 3: Replace the snippet-card grid with a source list**

Delete the `message.citations.length > 0 ?` block at `columns.tsx:231-247`, which
is a `flex flex-wrap gap-2` grid of bordered cards. Replace it with a list
rendering one line per citation:

- The line is a `<button>`, full width, with `id={`source-${message.id}-${citation.label}`}`.
- Its visible content is the label in `font-mono`, then the filename, then the
  page as `p. {page}` or `no page` when `page` is 0. Use a flex row with `gap`
  so there is no separator character between them.
- The filename span carries `min-w-0 break-words` so a long unbreakable name
  wraps inside the line instead of widening the column. This is Review Focus 3.
- When `openSource === citation.label`, the snippet renders below the line as
  plain `text-[12px] text-muted` body text with no border and no fill.
- The button carries `aria-expanded`.

The `refused` and `uncited` notes above this block stay exactly as they are.

- [ ] **Step 4: Change the user message fill**

`columns.tsx:204` is `bg-ink px-4 py-2.5 text-[14px] leading-relaxed text-white`.
Change to `bg-sunk px-4 py-2.5 text-[14px] leading-relaxed text-ink`. Alignment
already distinguishes the two roles; the solid slab was decoration on top of it.

- [ ] **Step 5: Verify the build and both checks**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build && npm run check:markers && npm run check:mapping`

Expected: all pass.

- [ ] **Step 6: Verify the five Review Focus cases by hand**

Run `npm run dev` and open `/chat` signed out, so the sample transcript from
`lib/mock/data.ts` is what renders. That fixture has both a single `[S1]` and a
grouped `[S1, S2]` marker, plus a citation whose snippet is present.

1. Inline markers render as superscripts, not `[S1]` text.
2. Clicking a marker opens and scrolls to its source line.
3. Every source line opens by hand, with no marker required.
4. The longest fixture filename wraps without widening the column.
5. Tab to a source line and press Enter, then Space. Each toggles it, and the
   focus ring is visible.

For the inert-marker rule, temporarily edit the fixture at
`lib/mock/data.ts:153` so its answer cites `[S3]` while its `citations` array
holds only `S1`. Expected: `S3` renders as a `<sup>` that is not focusable and
opens nothing. Revert the fixture afterwards.

Then sign in, ask a question against a real library, and confirm the same
behaviour on a live answer. Confirm opening a second source closes the first.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/chat/columns.tsx
git commit -m "feat: citation markers and one-line sources in the transcript

An answer's markers were rendering as the literal characters [S1], with
the snippet cards below unrelated to them. Markers are now superscripts
that open their source, and sources are one line each with the snippet
behind a click."
```

---

### Task 4: Static pipeline preview on the landing page

**Files:**
- Create: `frontend/components/pipeline/preview.tsx`
- Modify: `frontend/lib/config.ts`
- Modify: `frontend/components/pipeline/board.tsx:13-20`
- Modify: `frontend/app/page.tsx:321-344`

**Interfaces:**
- Consumes: nothing from earlier tasks. `PipelineBoard` keeps its current props and behaviour for `/pipeline`.
- Produces: `PipelinePreview(): JSX.Element`, no props, a server component, exported from `@/components/pipeline/preview`. And `STAGE_BLURBS: Record<Stage, string>` exported from `@/lib/config`, which the preview and the live board both read.

- [ ] **Step 1: Move the rail blurbs into `lib/config.ts`**

`BLURB` currently lives inside `components/pipeline/board.tsx`, which is a
`"use client"` module. Importing it from a server component would drag the
client boundary across, so it moves next to `STAGE_LABELS`, which is already
there.

Add to `lib/config.ts`, after `STAGE_LABELS`:

```ts
export const STAGE_BLURBS: Record<Stage, string> = {
  queued: "Accepted and waiting for a worker",
  parsing: "Reading text and page structure",
  chunking: "Slicing pages into retrievable chunks",
  embedding: "Writing vectors and the search index",
  ready: "Searchable, and answering questions",
  failed: "Stopped, with the reason given",
};
```

In `board.tsx`, delete the local `BLURB` const and replace its one use at
`board.tsx:87` with `STAGE_BLURBS[stage]`. Add `STAGE_BLURBS` to that file's
`@/lib/config` import.

- [ ] **Step 2: Create `components/pipeline/preview.tsx`**

A server component. No `"use client"`, no hooks, no `next/link`. It renders the
same six rails as the live board so the visual language matches:

- A `grid grid-cols-1 border-l border-t border-line sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6`, then for each of `STAGES` a `section` with `flex min-h-[220px] flex-col border-b border-r border-line bg-paper`, exactly as `board.tsx:66-99` does.
- The rail header holds the stage glyph, `STAGE_LABELS[stage]` as an `<h2>`, the entry count in `font-mono`, then `STAGE_BLURBS[stage]` beneath it.
- Group the fixture with `documentsByStage` from `@/lib/mock/data`, which is already exported and is a pure function.
- Cards are `<div>` elements, not links. Copy the filename-and-error markup from `board.tsx:124-148` and change the `Link` to a `div`, dropping `hover:` and `active:` classes and the `transition-colors`.
- The stage glyph is `Check` for `ready`, `Alert` for `failed`, and a `1.5`-size `bg-line-strong` dot otherwise, matching `board.tsx:118-122`.

Deliberately absent: the "N in flight / N documents" counter, the "Showing the
sample library" line, and the sign-up bar. Those are live-data affordances and on
a fixture they imply the fixture is real.

Add a docstring naming the reason this is a separate component rather than a prop
on `PipelineBoard`: sharing the component is what put a client hook and an
outbound link on a marketing page.

- [ ] **Step 3: Swap the landing page over and delete the section CTA**

In `app/page.tsx`, change the import at line 14 from `PipelineBoard` to
`PipelinePreview`, and change the render `<PipelineBoard />` to
`<PipelinePreview />`, keeping the `<div className="mt-12 border-t border-line
pt-10 md:mt-14">` wrapper it already sits in. Add no `Reveal` wrapper, because
the board it replaces has none.

Delete the `ButtonLink` whose `href` is `/pipeline` and whose label is
`See the full board`. Locate it by those two strings, not by line number: the
same dispatch makes both edits in this file, so deleting one shifts the other.
`/pipeline` stays reachable from the site header nav and the footer.

- [ ] **Step 4: Verify the build and confirm the section links nowhere**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`

Expected: all pass. If `PipelineBoard` is reported as unused in `app/page.tsx`,
it is still imported by `app/pipeline/page.tsx` and must stay exported.

Then run `npm run dev`, open `/`, and click every part of the ingestion section.
Expected: nothing is focusable and nothing navigates. Open `/pipeline` from the
nav and confirm the live board still works, including its card links to `/chat`
and its sign-up bar signed out.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/config.ts frontend/components/pipeline/board.tsx frontend/components/pipeline/preview.tsx frontend/app/page.tsx
git commit -m "feat: static pipeline preview on the landing page

The landing page mounted the live board, so every rail card linked to
/chat and 'See the full board' linked to /pipeline. A signed-out visitor
could only click through into the signed-in product. The section now
renders a server component with no links and no client JavaScript, and
the live board is unchanged for /pipeline."
```

---

### Task 5: Sign-in and sign-up

**Files:**
- Modify: `frontend/app/login/page.tsx:18-59`

**Interfaces:**
- Consumes: nothing. Produces: nothing for later tasks.

- [ ] **Step 1: Delete the left panel**

Remove `app/login/page.tsx:20-39` in full: the `hidden overflow-hidden border-r
border-line bg-surface lg:block` div, its `warm-wash` and `hairline-grid`
children, the statement headline, the paragraph, and the metadata strip reading
`20 documents per library · 25MB per file · PDF, DOCX, PPTX`.

The limits it stated are already stated in the chat drop zone
(`components/chat/library-column.tsx:130`) and in the upload rejection copy at
`library-column.tsx:61-66`, so nothing is lost by deleting it.

- [ ] **Step 2: Replace the grid wrapper with a centred column**

The `grid min-h-dvh lg:grid-cols-2` root becomes a
`flex min-h-dvh items-center justify-center px-6 py-16`. Its surviving child, the
`w-full max-w-[380px]` div, keeps its contents unchanged: the `lg:hidden`
wordmark becomes unconditional now that there is no panel to sit beside, and the
`Suspense`-wrapped `AuthForm` and the back link stay exactly as they are.

- [ ] **Step 3: Verify the build and the form still submits**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`

Expected: all pass.

Then run `npm run dev`, open `/login` and `/login?mode=signup` at 375px and at
1280px, and sign in with a real account. Expected: one centred column at both
widths, the form submits and lands on `/chat`, and the mode toggle between sign
in and sign up still works.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/login/page.tsx
git commit -m "feat: single-column sign-in page

The left panel was decoration carrying the only real content on the
page, a limits strip that the chat drop zone and the upload rejection
copy already state."
```

---

### Task 6: Copy accuracy and restraint

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/pipeline/page.tsx:24-26`
- Modify: `frontend/components/chat/library-column.tsx:130`
- Modify: `frontend/components/app-header.tsx:88-97`
- Modify: `frontend/app/layout.tsx:27-30`
- Modify: `frontend/lib/mock/data.ts:22,70,81,133,153`

**Interfaces:**
- Consumes: nothing. Produces: nothing for later tasks.

- [ ] **Step 1: Correct the two claims the backend does not support**

`backend/api/storage.py` is plain boto3 `put_object`, `get_object` and
`delete_object`. No presigned URL is generated anywhere, and no address for a
stored file reaches the browser.

Replace the `body` string of the "Your files stay private" card in
`app/page.tsx` with:

```
"Files sit in a private bucket. The server reads them to build the index and never hands the browser an address for one, so a citation can point at text but never at your file."
```

Leave the `title` as it is. That string is the only place in the tree that
claims signed URLs.

- [ ] **Step 2: Replace the three flagged headlines**

These are exact replacements. Do not paraphrase them.

- `Four steps, then it is just answering questions.` becomes `How a question becomes an answer.`
- `Built around the failure modes of a chat tool that quotes itself.` becomes `Where a cited answer can still go wrong.`
- Leave `Bring one document you already know.` unchanged.

- [ ] **Step 3: Cut the case-file labels and the two remaining section labels**

Locate each target by its current text, not by line number: Tasks 1 and 4 already
rewrote parts of `app/page.tsx`, so its line numbers no longer match this plan.

The citation headers read `S1 · p. 7` and `S2 · p. 9`. Render each as a flex row
holding two `font-mono` spans, label then page, separated by `gap` instead of the
character.

Replace the string `case file · judicial-review` with `sample library`. Keep the
mono uppercase tracking. This is not decoration: it is the disclosure that the
block above it is fixture content, and it is the reason it is acceptable for a
card header to carry a small-caps mono label.

Delete the `question` label element entirely. The block beneath it is obviously
the question.

Delete the hero eyebrow `<p>` which reads `2026 · beta`. It is a version label,
and removing it leaves the hero with three text elements.

Delete the `<SectionLabel>Ingestion</SectionLabel>` element. The headline beneath
it already says what the section is. `SectionLabel` stays imported, because the
`Why it holds up` section label still uses it.

- [ ] **Step 4: Fix the remaining separator runs**

- `app/pipeline/page.tsx:25`, currently `ingestion · {STAGES.length} stages`: render as two stacked lines, `Ingestion` then `{STAGES.length} stages`, inside the existing `<p>`.
- `components/chat/library-column.tsx:130`, currently `PDF, DOCX, PPTX · up to {megabytes(MAX_UPLOAD_BYTES)}`: replace with `PDF, DOCX, PPTX. Up to {megabytes(MAX_UPLOAD_BYTES)}.`

- [ ] **Step 5: Delete the dead `ChatTitleBar`**

`components/app-header.tsx:88-97` defines `ChatTitleBar` and nothing in the tree
references it. Delete the function and the `APP_NAME` import it was the only
consumer of.

- [ ] **Step 6: Remove the em-dashes from user-visible strings**

- `app/layout.tsx:28`, the default title, currently `` `${APP_NAME} — ${APP_TAGLINE}` ``: becomes `` `${APP_NAME}: ${APP_TAGLINE}` ``. Line 29, the template, currently `` `%s — ${APP_NAME}` ``: becomes `` `%s | ${APP_NAME}` ``.
- `lib/mock/data.ts:22`, `Constitutional Law — Week 4 Notes.pdf`: becomes `Constitutional Law - Week 4 Notes.pdf`. The `CITE` map at line 133 holds the same string and must change with it, or the citation filename stops matching the library filename. Change both.
- `lib/mock/data.ts:81`, `Microbiology Lab Report — Draft.docx`: plain hyphen.
- `lib/mock/data.ts:70`, `Sicilian Gardens, 1780–1900.pdf`: the en-dash in the range becomes a hyphen.
- `lib/mock/data.ts:153`, the sample answer: `not an appeal against the decision itself — the court does not re-run` becomes `not an appeal against the decision itself: the court does not re-run`.

Leave comments and docstrings alone. They are not user-visible.

- [ ] **Step 7: Read every remaining user-visible string once more**

Read the whole of `app/page.tsx`, `app/login/page.tsx`,
`components/chat/columns.tsx`, `components/chat/library-column.tsx`,
`components/pipeline/board.tsx`, `components/chrome.tsx` and
`lib/mock/data.ts` looking for grammar that does not parse, referents with no
antecedent, filler verbs, and claims the code does not support. Rewrite what is
wrong in plain language. If a rewrite cannot be made plain, replace the string
with a plain functional sentence.

- [ ] **Step 8: Verify the build and sweep for leftovers**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`

Expected: all pass.

Then:

```bash
grep -rn "—\|–" frontend/app frontend/components frontend/lib --include=*.tsx --include=*.ts | grep -v "^\s*//" | grep -v "\*"
grep -rn "middot" frontend/app frontend/components frontend/lib --include=*.tsx
```

Expected: the first returns nothing but comments and docstrings. The second
returns nothing. Fix anything it reports and re-run.

- [ ] **Step 9: Read the landing page aloud, top to bottom**

Run `npm run dev` and read `/` as a visitor would. Every claim must be something
you could defend by pointing at the code. Pay attention to the case-file block:
it is fixture content, and the only thing telling a reader so is the
`sample library` label from Step 3.

- [ ] **Step 10: Commit**

```bash
git add frontend/app/page.tsx frontend/app/pipeline/page.tsx frontend/app/layout.tsx frontend/components/chat/library-column.tsx frontend/components/app-header.tsx frontend/lib/mock/data.ts
git commit -m "fix: copy accuracy and restraint

Removes two claims the backend does not support, the signed-URL and
expiring-citation strings, in favour of what the storage adapter
actually does. Strips the separator runs, cuts the section labels to
one per three sections, and drops every em-dash from a user-visible
string. Deletes ChatTitleBar, which nothing references."
```

---

## Final verification

Run after all six tasks:

```bash
cd frontend
npm run typecheck && npm run lint && npm run build
npm run check:mapping && npm run check:markers
```

Manual pass, all four routes, signed in and signed out, at 375px and 1280px:

- Every CTA meets 4.5:1, or 3:1 at 18px and over.
- The solid button hover is visibly distinct from its resting state.
- The landing ingestion section has nothing focusable in it and links nowhere.
- Reveal content is present with JavaScript disabled.
- The page reads correctly at 200% zoom.
- A reader who has never seen the product cannot find a claim on any page that
  the code does not support.