# ReviA Image Slots

All `picsum.photos` URLs used in the redesign are placeholders and must be replaced with real assets.

## Landing (app/page.tsx)
- **Hero image** (16:9, 1200×675) — subject: "a desk with printed lecture notes and a laptop"
- **Editorial supporting image** (4:5, 1024×1280) — subject: "stack of open notebooks and reading glasses"

### Task 4 slots in use (app/page.tsx)

| Slot | URL | Aspect | Alt text | Placement |
|---|---|---|---|---|
| Hero | `https://picsum.photos/seed/revia-hero/1200/675` | 16:9 | "Printed lecture notes spread open on a desk beside a laptop" | Hero right column, `priority`, hairline frame on `bg-sunk` |
| Editorial | `https://picsum.photos/seed/revia-notes/1024/1280` | 4:5 (rendered cropped, `max-h-[440px]`, `object-cover`) | "A stack of open notebooks and reading glasses left on a table" | Features bento, "Says it does not know" cell |

Both slots are rendered through `next/image` with `picsum.photos` already allowed
in `frontend/next.config.ts` `remotePatterns`. Replacing them means swapping the
two constants at the top of `app/page.tsx`; keep the 16:9 and 4:5 ratios or the
frames will crop differently.

## Chat (app/chat/page.tsx)
- No new placeholder images introduced in Task 2.

## Components
- No new placeholder images introduced in Task 2.

_Note:_ Tasks 5–7 will append additional image slots as they are introduced.
