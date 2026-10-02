# ReviA Redesign & Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the application to ReviA everywhere, and apply a bold futuristic-editorial visual identity across all four routes without changing flows or routes.

**Architecture:** Backend rename is a mechanical find-and-replace of `EndNote`/`endnote`/`ENDNOTE_` identifiers. Frontend redesign replaces the design tokens in `app/globals.css`, swaps fonts in `app/layout.tsx`, rewrites the shared primitives, then recomposes each route's JSX against those tokens. No data contracts change.

**Tech Stack:** Next.js 16 (app router), React 19, TypeScript, Tailwind v4 (`@theme` tokens), Django 6.1 + DRF backend, Supabase auth. Fonts via `next/font/google`.

**Spec:** `docs/superpowers/specs/2026-10-02-revia-redesign-design.md`

## Global Constraints

- Brand string: `ReviA` (exact casing). Single source of truth is `APP_NAME` in `frontend/lib/config.ts`.
- Theme is light-only. No `dark:` variants, no theme toggle, no `prefers-color-scheme` branching.
- Single accent: royal purple `#4b2e83`. Semantic colours are status-only (`success #2f6b43`, `danger #9f2f2d`, `warning #8a5a00`).
- Shape: every radius is `0`; all borders are hairlines (`--color-line` / `--color-line-strong`).
- Fonts (all via `next/font/google`, variable, `display: "swap"`): `Orbitron` (display), `Geist` (UI/body), `JetBrains_Mono` (metadata). No serif, no Inter.
- Routes and flows are frozen: `/`, `/chat`, `/pipeline`, `/login`. Do not add, remove, or rename routes.
- No new runtime dependencies. `next.config.ts` may only gain an `images.remotePatterns` entry for `picsum.photos`.
- Copy: sentence case headers; no clichés ("Elevate", "Seamless", "Unleash", "Next-Gen", "Delve", "Tapestry"); no exclamation marks; no em dashes as design flourish; no invented precise stats.
- The string `EndNote` must not appear in user-visible copy or code identifiers after Task 1 (the spec/plan docs under `docs/superpowers/` are exempt).
- Every interactive element keeps a visible `:focus-visible` ring and works keyboard-only.
- Every motion effect degrades to static under `@media (prefers-reduced-motion: reduce)`.
- Verification commands: `cd frontend && npm run typecheck && npm run lint && npm run build`; `uv run ruff check backend && uv run python backend/manage.py check && uv run pytest`.

## Review Focus

Failure modes the spec implies but no unit test pins; reviewers should name each in their report where relevant:

1. **Colour contrast** - dark ink on a thin purple accent fill, and muted grey metadata on paper, must stay WCAG AA. A palette refresh is the most likely place to ship unreadable text.
2. **Reduced motion** - every reveal/transition must become static under `prefers-reduced-motion: reduce`; screenshots at rest cannot show a violation.
3. **Keyboard focus** - square controls and recoloured borders must not remove the visible focus ring or the skip path through nav/forms/composer.
4. **Copy residue** - the string `EndNote` and any AI-cliché phrasing surviving in JSX strings/alt text after the rename.
5. **Mobile collapse** - asymmetric desktop grids (hero, bento, split panels) must collapse to single column below 768px without horizontal overflow.

---

### Task 1: Full internal rename EndNote → ReviA

**Files:**
- Modify: `frontend/lib/config.ts` (line 1 `APP_NAME`)
- Modify: `frontend/package.json` (line 2 `name`)
- Modify: `frontend/package-lock.json` (lines 2 and 8 `name`)
- Modify: `frontend/scripts/check-live-data.mts` (line 117 console label)
- Modify: `frontend/components/chrome.tsx` (line 101 disclaimer)
- Modify: `backend/api/apps.py` (line 93 `verbose_name`)
- Modify: `backend/api/ingestion.py` (line 48 `WORKER_LOCK_KEY` + comment)
- Modify: `backend/api/pipeline_worker.py` (line 69 thread `name`)
- Modify: `backend/api/management/commands/run_pipeline.py` (line 62 env var in message)
- Modify: `backend/config/settings.py` (`ENDNOTE_*` → `REVIA_*`, docstring)
- Modify: `backend/.env.example` (`ENDNOTE_*`, `endnote-test-pg`, `endnote` password)
- Modify: `pyproject.toml` (lines 2 and 4)
- Modify: `uv.lock` (line 216 root package name; regenerate if possible)
- Modify: `README.md` (title, all `ENDNOTE_*`, `endnote` DB/docker names, and remove plaintext credentials at the end)

**Interfaces:**
- Produces: `APP_NAME = "ReviA"` in `frontend/lib/config.ts` (consumed by every later task), and `REVIA_*` env-var names the backend reads (consumed by runtime config only).
- The worker advisory-lock key changes value; the old and new worker processes could overlap for one pass during a live deploy. Acceptable for this project.

- [ ] **Step 1: Apply the rename in frontend branding and packaging**

In `frontend/lib/config.ts` set `export const APP_NAME = "ReviA";`. In `frontend/package.json` set `"name": "revia-frontend"`. In `frontend/package-lock.json` replace both `"endnote-frontend"` occurrences with `"revia-frontend"`. In `frontend/scripts/check-live-data.mts` change the `ENDNOTE:` label at line 117 to `REVIA:`. In `frontend/components/chrome.tsx` delete the footer paragraph at lines 100-102 ("Unrelated to EndNote from Clarivate...").

- [ ] **Step 2: Apply the rename in the backend**

`backend/api/apps.py`: `verbose_name = "ReviA API"`. `backend/api/ingestion.py`: set `WORKER_LOCK_KEY = 0x52657669410000` and change the trailing comment to `# b"ReviA!"` (keep the constant's role comment). Compute the value for real with `python -c "print(hex(int.from_bytes(b'ReviA!', 'big')))"` and use that exact value rather than the placeholder above. `backend/api/pipeline_worker.py`: `name="revia-pipeline"`. `backend/api/management/commands/run_pipeline.py`: the message at line 62 must read `REVIA_RUN_PIPELINE_IN_PROCESS`. `backend/config/settings.py`: rename every `ENDNOTE_*` env lookup to `REVIA_*` (`REVIA_ENV_FILE`, `REVIA_TEST_PG_HOST`, `REVIA_TEST_PG_NAME`, `REVIA_TEST_PG_USER`, `REVIA_TEST_PG_PASSWORD`, `REVIA_TEST_PG_PORT`, `REVIA_TEST_DB`, `REVIA_TEST_DB_NAME`, `REVIA_TEST_PG_TEST_NAME`, `REVIA_RUN_PIPELINE_IN_PROCESS`), rename the hardcoded `endnote-test-pg` container name and `endnote` password in the error example (around lines 149-150) to `revia-test-pg`/`revia`, and update the module docstring to "ReviA backend". `backend/.env.example`: rename all `ENDNOTE_*` to `REVIA_*`, and rename the example docker/container/password strings `endnote-test-pg` → `revia-test-pg`, `endnote` password → `revia`.

- [ ] **Step 3: Rename packaging and docs**

`pyproject.toml`: `name = "revia"` and description `"ReviA backend: document ingestion, retrieval, and cited chat over Supabase."`. `uv.lock`: update the root package name at line 216 to `revia`; then run `uv lock` to regenerate cleanly if the network allows, otherwise leave the manual edit. `README.md`: retitle `# ReviA`; replace every `ENDNOTE_*` with `REVIA_*`, `endnote`/`endnote_test` database names with `revia`/`revia_test`, and docker container names `endnote-test-pg`/`endnote_test` with `revia-test-pg`/`revia_test`. Remove the trailing plaintext credentials block (the `user1` / `user2` email-and-password lines at the end of the file).

- [ ] **Step 4: Verify no EndNote residue and the backend still loads**

Run:
```bash
git grep -in endnote -- . ':(exclude)docs/superpowers' | head
```
Expected: no output.

Run:
```bash
uv run python backend/manage.py check && uv run ruff check backend && uv run pytest
```
Expected: system check passes, ruff clean, tests pass.

Run:
```bash
cd frontend && npm run typecheck
```
Expected: typecheck passes.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename EndNote to ReviA throughout"
```

---

### Task 2: Design tokens and fonts

**Files:**
- Modify: `frontend/app/globals.css` (replace the `@theme` block and base layer)
- Modify: `frontend/app/layout.tsx` (replace the two fonts with three)
- Modify: `frontend/next.config.ts` (add `images.remotePatterns`)
- Create: `docs/revia-image-slots.md`

**Interfaces:**
- Produces: the CSS custom properties every later task uses (`--color-paper`, `--color-surface`, `--color-sunk`, `--color-ink`, `--color-ink-soft`, `--color-muted`, `--color-faint`, `--color-line`, `--color-line-strong`, `--color-accent`, `--color-accent-soft`, `--color-success`, `--color-danger`, `--color-warning`), the font variables `--font-display`, `--font-sans`, `--font-mono`, and the utilities `reveal`, `reveal-in`, `hairline-grid`, `warm-wash`.
- Produces: `docs/revia-image-slots.md` listing the placeholder image slots to replace.

- [ ] **Step 1: Replace the token block in `frontend/app/globals.css`**

Replace the existing `@theme { ... }` block with exactly:

```css
@theme {
  --color-paper: #fcfcfa;
  --color-surface: #ffffff;
  --color-sunk: #f4f3ef;
  --color-ink: #121212;
  --color-ink-soft: #2c2c2a;
  --color-muted: #6c6c68;
  --color-faint: #9d9c96;
  --color-line: #e6e5df;
  --color-line-strong: #d4d3cc;

  --color-accent: #4b2e83;
  --color-accent-soft: #efe9f6;
  --color-success: #2f6b43;
  --color-danger: #9f2f2d;
  --color-warning: #8a5a00;

  --font-display: var(--font-orbitron), ui-sans-serif, system-ui, sans-serif;
  --font-sans: var(--font-geist), ui-sans-serif, system-ui, sans-serif;
  --font-mono: var(--font-jetbrains), ui-monospace, SFMono-Regular, Menlo, monospace;

  --text-display: 3.25rem;
  --text-display--line-height: 1.04;
  --text-display--letter-spacing: -0.02em;
  --text-title: 2rem;
  --text-title--line-height: 1.12;
  --text-title--letter-spacing: -0.01em;
  --text-lede: 1.25rem;
  --text-lede--line-height: 1.6;

  --radius-card: 0px;
  --radius-control: 0px;

  --shadow-whisper: 0 2px 10px rgb(75 46 131 / 0.05);
  --shadow-lift: 0 10px 30px rgb(75 46 131 / 0.07);

  --ease-out-quiet: cubic-bezier(0.16, 1, 0.3, 1);
}
```

Update the base layer: `body` uses `background-color: var(--color-paper)`, `color: var(--color-ink)`, `font-family: var(--font-sans)`. `::selection` uses `background: var(--color-accent-soft)` and `color: var(--color-accent)`. `:focus-visible` uses `outline: 2px solid var(--color-accent)`. Keep `h1,h2,h3` weight 500 and `text-wrap: balance`. Keep the four `@utility` blocks unchanged. Also replace every `bg-canvas` class in `frontend/app` and `frontend/components` with `bg-paper` (six files use it: `app/page.tsx`, `app/chat/page.tsx`, `components/app-header.tsx`, `components/chat/columns.tsx`, `components/chrome.tsx`, `components/pipeline/board.tsx`). Remove the old `--color-pale-*` tokens entirely. The now-migrated `::selection` rule was their only consumer inside `globals.css`; a few components still use `text-pale-blue-ink` (landing and chat) and lose that styling until Tasks 4-5 restyle them, which is expected and checked in Task 8.

- [ ] **Step 2: Swap fonts in `frontend/app/layout.tsx`**

Replace `Space_Grotesk` and `Space_Mono` imports with `Orbitron`, `Geist`, and `JetBrains_Mono` from `next/font/google`. Instantiate:
- `orbitron = Orbitron({ subsets: ["latin"], variable: "--font-orbitron", display: "swap" })`
- `geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" })`
- `jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" })`

Set the `<html>` className to `${orbitron.variable} ${geist.variable} ${jetbrains.variable}`. Keep `lang="en"`, `data-scroll-behavior="smooth"`, and the `<noscript>` reveal override. Keep the metadata description, but it must not mention EndNote (it does not).

- [ ] **Step 3: Allow placeholder images in `frontend/next.config.ts`**

Set:
```ts
const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [{ protocol: "https", hostname: "picsum.photos" }],
  },
};
```

- [ ] **Step 4: Create `docs/revia-image-slots.md`**

Write a short file listing every placeholder image slot introduced in Tasks 4-7 with its intended subject and aspect ratio, and a note that all `picsum.photos` URLs are placeholders to be replaced with real assets. Start with the landing hero (16:9, "a desk with printed lecture notes and a laptop") and the landing editorial supporting image (4:5). Later tasks append their slots.

- [ ] **Step 5: Verify the build**

Run:
```bash
cd frontend && npm run typecheck && npm run build
```
Expected: build succeeds and `app/globals.css` contains no `--color-pale-*` token. Component-level `text-pale-*` classes are removed by Tasks 4-5 and checked in Task 8; Tailwind silently drops unresolved class names, so they do not fail this build.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/globals.css frontend/app/layout.tsx frontend/next.config.ts docs/revia-image-slots.md
git commit -m "feat: ReviA design tokens and futuristic type system"
```

---

### Task 3: Primitives, icons and chrome

**Files:**
- Modify: `frontend/components/ui.tsx`
- Modify: `frontend/components/icons.tsx`
- Modify: `frontend/components/chrome.tsx`
- Modify: `frontend/components/app-header.tsx`
- Create: `frontend/app/icon.svg`

**Interfaces:**
- Consumes: the tokens and font variables from Task 2.
- Produces: `Button`, `ButtonLink`, `Badge`, `Card`, `SectionLabel`, `Kbd` with the same exported names and prop shapes as today (so Tasks 4-7 can use them unchanged), plus a new exported `ReviaMark` icon. `Badge` `tone` prop changes to accept only `"neutral" | "accent" | "success" | "warning" | "danger"`.

- [ ] **Step 1: Restyle `frontend/components/ui.tsx`**

Keep all exported names and prop types. Change `CONTROL` to `rounded-none`, transition `duration-200`, and active `scale-[0.98]`. `VARIANTS`: `solid` = `bg-accent text-white hover:bg-ink`; `outline` = `border border-line-strong bg-surface text-ink hover:border-ink`; `ghost` = `text-muted hover:bg-sunk hover:text-ink`; `quiet` = `bg-sunk text-ink hover:bg-line`. `Badge`: square (`rounded-none`), `text-[10px] uppercase tracking-[0.08em]`, tones `neutral` = `bg-sunk text-muted`, `accent` = `bg-accent-soft text-accent`, `success` = `bg-success/10 text-success`, `warning` = `bg-warning/10 text-warning`, `danger` = `bg-danger/10 text-danger`. `Card`: `rounded-none border border-line bg-surface`. `SectionLabel`: keep as the small uppercase label but use `text-faint` and `tracking-[0.16em]`. `Kbd`: `rounded-none border border-line bg-sunk font-mono`.

- [ ] **Step 2: Update icons and add the ReviA mark**

Keep every existing icon export and the shared `base` (strokeWidth 1.6). Add `export function ReviaMark({ className, size = 20 }: IconProps)` drawing a simple geometric monogram: an outlined square with a single diagonal stroke forming a stylised "R" (a square, one vertical stroke, one diagonal leg). It must be a single simple mark, not a detailed illustration.

- [ ] **Step 3: Rework `frontend/components/chrome.tsx`**

`Wordmark`: render `ReviaMark` followed by `APP_NAME` in the display font — wrap the text in a span with `font-[family-name:var(--font-display)]`, uppercase, `tracking-[0.02em]`. `SiteHeader`: keep single-line nav and the `h-16` sticky hairline bar; nav links (`How it works`, `Features`, `Pricing`, `Pipeline`) restyled with `text-muted hover:text-ink`; keep the `children ??` default CTAs (`Sign in` ghost, `Try ReviA` solid). `SiteFooter`: simplify to the wordmark, a one-line description, and two link groups (Product, Account); delete the EndNote disclaimer line; keep `©`-free and no clichés.

- [ ] **Step 4: Rework `frontend/components/app-header.tsx`**

Keep `AppHeader`, `AccountSlot`, and `ChatTitleBar` exports and behaviour. Restyle only: hairline bar, display-font wordmark via `Wordmark`, mono metadata in `ChatTitleBar` (`text-faint`). The `ChatTitleBar` right label stays `{APP_NAME} &middot; sample library`.

- [ ] **Step 5: Add `frontend/app/icon.svg`**

Create a square SVG favicon (viewBox 0 0 64 64) using `#4b2e83` on `#fcfcfa` with the same stylised "R" mark. Keep it a simple geometric mark.

- [ ] **Step 6: Verify**

Run:
```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```
Expected: all pass. (The `text-pale-*` residue in landing/chat is removed by Tasks 4-5 and verified in Task 8, not here.)

- [ ] **Step 7: Commit**

```bash
git add frontend/components/ui.tsx frontend/components/icons.tsx frontend/components/chrome.tsx frontend/components/app-header.tsx frontend/app/icon.svg
git commit -m "feat: ReviA primitives, mark and chrome"
```

---

### Task 4: Landing page recompose

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `docs/revia-image-slots.md` (append slots used)

**Interfaces:**
- Consumes: `ButtonLink`, `Badge`, `Card`, `SectionLabel`, `Kbd`, `Reveal`, `SiteHeader`, `SiteFooter`, `PipelineBoard`, and the icons from Tasks 2-3.
- Produces: no new exports; the page's copy data arrays (`FEATURES`, `STEPS`, `FAQ`, `PLANS`) stay in the file.

- [ ] **Step 1: Recompose the page (visual only; keep section content)**

Rebuild `Home` so that:
- Hero is left-aligned, `text-display` in the display font, max two lines, with a right-side `next/image` (picsum seed `revia-hero`, 16:9, `priority`). Hero has at most four text elements: a mono dateline (e.g. `2026 · beta`) replacing the `Now in beta` badge, the H1 (`APP_TAGLINE`), a lede paragraph (≤ 20 words), and two CTAs (`Try ReviA` solid, `Create an account` outline). No trust strip, no tagline under the CTAs.
- The existing case-file Q&A block is kept but framed square with a purple accent citation label.
- "How it works" uses an asymmetric numbered layout (not a row of four equal cards) with section numbers in the display font.
- Features use an asymmetric bento grid with at least two cells carrying a real visual (image, accent-tinted fill, or hairline pattern), not all white cards.
- Pipeline, pricing (two plans), FAQ (two-column list, not an accordion tower) and closing CTA sections are restyled; the closing CTA headline uses the display font.
- At most two `SectionLabel` eyebrows on the whole page.
- No section repeats the same layout family twice; no more than two consecutive image+text split sections.

- [ ] **Step 2: Verify mobile collapse**

Every multi-column grid must declare a single-column fallback below `md`. Run the build and open `/` at 375px wide: no horizontal scroll, hero CTAs visible without scrolling.

Run:
```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx docs/revia-image-slots.md
git commit -m "feat: recompose ReviA landing page"
```

---

### Task 5: Chat surfaces

**Files:**
- Modify: `frontend/components/chat/columns.tsx`
- Modify: `frontend/components/chat/library-column.tsx`
- Modify: `frontend/components/chat/workspace.tsx`
- Modify: `frontend/app/chat/page.tsx`

**Interfaces:**
- Consumes: primitives and tokens from Tasks 2-3; `ASK_REASON` and `UPLOAD_REASON` stay exported with their current text.
- Produces: unchanged `ChatWorkspace` props and unchanged hook usage; all existing behaviour (submit, `/` shortcut, auth modal, upload validation, delete, polling) is preserved.

- [ ] **Step 1: Restyle `HistoryColumn`**

Header label becomes `Contents` (kept as `SectionLabel`). Session rows become square hairline entries with mono message counts; active row uses an accent left border. Keep the `New conversation` button (square, outline).

- [ ] **Step 2: Restyle `ChatColumn` and `MessageBlock`**

Header keeps the derived `title`, the sample-library badge (now `Badge tone="warning"`), and mono source count. User messages: square, `bg-ink text-white`. Assistant messages: body in `Geist` with relaxed leading; citation cards become square hairline footnotes with the label in `font-mono text-accent`. Pending/error/blocked states restyled with the new semantic tones. Composer: square textarea, hairline border, accent focus border, `Send` button solid accent.

- [ ] **Step 3: Restyle `LibraryColumn`**

Header `Library` (SectionLabel) + mono file count. Dropzone: square dashed hairline, accent border on drag. Document rows: square hairline, mono size/page metadata, stage `Badge` using the new tones (`accent` for parsing/chunking, `warning` for embedding, `success` for ready, `danger` for failed, `neutral` for queued), error text in `danger`. Keep the upload validation messages verbatim.

- [ ] **Step 4: `workspace.tsx` and `chat/page.tsx`**

No behaviour change. Only adjust wrapper classes so the three columns read as square hairline panels on `--color-paper`. Keep the `h-dvh` chat shell and the `Suspense` fallback.

- [ ] **Step 5: Verify**

Run:
```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```
Expected: pass. Then check `/chat` signed-out: sample transcript renders, asking opens the auth modal; at 375px the columns stack without overflow.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/chat frontend/app/chat/page.tsx
git commit -m "feat: restyle ReviA chat surfaces"
```

---

### Task 6: Pipeline surfaces

**Files:**
- Modify: `frontend/components/pipeline/board.tsx`
- Modify: `frontend/app/pipeline/page.tsx`

**Interfaces:**
- Consumes: tokens/primitives from Tasks 2-3; `STAGES`, `STAGE_LABELS`, `documentsByStage`.
- Produces: unchanged `PipelineBoard` props (`signedIn`, `initialDocuments`) and unchanged route behaviour.

- [ ] **Step 1: Restyle the board**

Six stage columns become square hairline rails. Column headers use mono stage counts and a small status glyph (`success` check for ready, `danger` alert for failed, hairline dot otherwise). Document cards are square hairline entries with mono metadata; failed cards get a `danger` error block. The summary line (`N in flight`, `M documents`) uses mono numerals. Keep the signed-out sample-library note and its `Create an account` button.

- [ ] **Step 2: Restyle the page shell**

`app/pipeline/page.tsx`: replace the `SectionLabel`-style eyebrow with a mono dateline if kept, use the display font for the `h1`, and keep the `Back to chat` link. Keep metadata title.

- [ ] **Step 3: Verify**

Run:
```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```
Expected: pass. Check `/pipeline` signed-out shows the sample board; at 768px the six columns wrap to 2 columns, at 375px to 1.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/pipeline/board.tsx frontend/app/pipeline/page.tsx
git commit -m "feat: restyle ReviA pipeline surfaces"
```

---

### Task 7: Auth surfaces

**Files:**
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/components/auth-form.tsx`
- Modify: `frontend/components/auth-modal.tsx`

**Interfaces:**
- Consumes: tokens/primitives from Tasks 2-3; `AuthForm` props (`mode`, `next`, `onSuccess`, `compact`) and `AuthModal` props (`open`, `onClose`, `next`, `reason`) unchanged.
- Produces: unchanged behaviour (Supabase sign-in/sign-up, notice/error display, Escape-to-close, body scroll lock).

- [ ] **Step 1: Restyle `login/page.tsx`**

Keep the two-panel split. Left panel: paper/surface with the `hairline-grid` utility and a display-font statement headline plus one supporting paragraph and a mono limits line. Right panel: centered form. Keep the `Wordmark`, the `Suspense`, and the back-home link.

- [ ] **Step 2: Restyle `auth-form.tsx`**

Square inputs with hairline borders and accent focus. Labels above inputs, errors below (keep the existing `Alert`/`Check` inline messages and their colours mapped to `danger`/`success`). Submit button solid accent, `ArrowRight` retained. Keep the mode switch and the privacy line, but remove the brand-name sentence if it reads awkwardly with `ReviA`; it must not contain a cliché.

- [ ] **Step 3: Restyle `auth-modal.tsx`**

Square dialog, hairline border, purple-tinted `shadow-lift`, clip-corner styling allowed but corners stay square. Keep the escape handler, overlay click, scroll lock and the `Keep looking around instead` ghost button.

- [ ] **Step 4: Verify**

Run:
```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```
Expected: pass. Check `/login?mode=signup`, the chat auth modal, and keyboard-only Escape/close.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/login/page.tsx frontend/components/auth-form.tsx frontend/components/auth-modal.tsx
git commit -m "feat: restyle ReviA auth surfaces"
```

---

### Task 8: Cross-cutting state, motion and copy audit

**Files:**
- Modify: any file from Tasks 3-7 that fails the checklist below

**Interfaces:**
- Consumes: everything produced by Tasks 1-7.
- Produces: no new interfaces; a verified final state.

- [ ] **Step 1: Reduced-motion audit**

Ensure the `Reveal` utility and every hover/transition either sits behind `@media (prefers-reduced-motion: no-preference)` or is disabled under `@media (prefers-reduced-motion: reduce)`. At minimum, add a global reduced-motion override in `globals.css` that disables `reveal` transforms and transitions. Verify by building and toggling the OS setting.

- [ ] **Step 2: Focus and contrast audit**

Tab through `/`, `/login`, `/chat`, `/pipeline` with the keyboard. Every control shows the accent focus ring. Check `muted`/`faint` text on `paper` and `accent` text on `accent-soft` against WCAG AA (4.5:1 body, 3:1 large). Adjust `muted`/`faint` darker if they fail.

- [ ] **Step 3: Copy self-audit**

Re-read every visible string on all four routes and flag/rewrite: any `EndNote` residue, clichés, broken grammar, unclear referents, fake-precise stats, or em dashes used as flourish. Also verify alt text on every image.

- [ ] **Step 4: Final verification**

Run:
```bash
git grep -in endnote -- . ':(exclude)docs/superpowers' | head
cd frontend && npm run typecheck && npm run lint && npm run build
cd .. && uv run ruff check backend && uv run python backend/manage.py check && uv run pytest
```
Expected: grep empty; all frontend and backend checks pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: ReviA state, motion and copy polish"
```
