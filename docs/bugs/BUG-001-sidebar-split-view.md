# BUG-001 — sidebar unusable in a half-width browser window

**Status:** **RESOLVED** 2026-08-20 (`8ce9a3e`) · **Severity:** high (app was
unusable in this window size)
**Reported:** 2026-08-19 by Pranav, with a screenshot
**Investigated by:** Claude Opus 5, session `a55eaf1f` — not root-caused
**Root-caused and fixed by:** Claude Opus 5, session `848e92a5`

**Read the Resolution section at the bottom first.** Everything between here
and it is the investigation as it stood while the bug was open, kept because
the two falsified hypotheses are still worth not repeating.

---

## Symptom

With Chrome open in split view beside another app — a window roughly 960px wide
— the sidebar toggle button does nothing, and no sidebar is visible at all.

From the screenshot: the header renders correctly (toggle icon, the pulsing dot,
`SYSTEM ONLINE`), the page content renders correctly, and there is no sidebar
and no icon rail anywhere on screen.

---

## Why it matters

Split-screen is an ordinary way to use a browser. In that layout the app has no
navigation at all — every page except the current one becomes unreachable.

---

## What has been ruled out

Both of these were investigated and **falsified**. Do not spend time on them
again.

### Hypothesis 1 — Tailwind `md` disagrees with `MOBILE_BREAKPOINT` ❌

**The theory:** `useIsMobile()` hardcodes `MOBILE_BREAKPOINT = 768`, while the
desktop sidebar root is `hidden md:block`. If Tailwind's `md` were larger than
768 there would be a dead zone where the mobile Sheet does not render (viewport
is "not mobile") *and* the desktop sidebar is still `hidden`. At 960px that
would produce exactly this symptom.

**Why it is wrong:** `tailwind.config.ts` does contain a `screens` block, but it
is nested **inside `container`** and only sets `2xl: 1400px` for container
max-widths. Tailwind's actual breakpoints are untouched, so `md` is 768px —
identical to the hook. There is no dead zone.

```
theme: { container: { screens: { "2xl": "1400px" } } }   ← scoped to container
```

### Hypothesis 2 — `SidebarRail` at `z-20` covers the trigger ❌

**The theory:** `ui/sidebar.tsx:263` renders `SidebarRail` at `z-20`, above the
header's `z-10`. If it sat over the trigger, clicks would land on the rail.

**Why it is wrong:** `AppSidebar` never renders a `SidebarRail`. Confirmed by
grep — the component is defined in `ui/sidebar.tsx` but not used.

---

## What is known to be true

- `AppSidebar` renders `<Sidebar collapsible="icon">` (`AppSidebar.tsx:86`), so
  on desktop a collapse should leave a **3rem icon rail** with visible icons —
  never nothing. The screenshot shows nothing, which does not match either state.
- `AppSidebar` does render icons when collapsed (`AppSidebar.tsx:93, :120` gate
  only the text on `!collapsed`), so an empty rail is not explained by the
  component's own logic.
- `SidebarTrigger` (`ui/sidebar.tsx:230`) calls `toggleSidebar()` unconditionally
  in `onClick`. Nothing gates it by viewport.
- The desktop wrapper is `hidden md:block` (`ui/sidebar.tsx:182`); the fixed
  panel is `fixed inset-y-0 z-10 ... md:flex` (`:201`).
- Below 768px the sidebar is a Sheet, and it *does* close on navigation — that
  was a real bug fixed in Phase D and is not this one.

---

## Next step — reproduce before fixing

Static reading has produced two dead ends. Stop reading and reproduce.

1. Run the app (`start.bat`), open `http://localhost:8080`.
2. Set the viewport to **940–960px** wide specifically — not 800, not 1200. Use
   devtools device toolbar or a real half-screen window.
3. Inspect the desktop wrapper element and record:
   - `data-state` (`expanded` / `collapsed`)
   - `data-collapsible` (`icon` / empty)
   - the computed width of the gap div and the fixed div
   - whether the fixed div is on-screen or translated out
4. Click the trigger and record whether `data-state` changes at all.

**That last check splits the problem cleanly:**
- `data-state` changes but nothing moves → a CSS/width problem
- `data-state` does not change → a state/provider problem

Only then form a third hypothesis.

---

## Suggested regression test once fixed

A Playwright test at viewport 960×800 that asserts the sidebar is visible,
clicks the trigger, and asserts the state actually changed. The existing
Playwright setup already covers mobile drawer behaviour and can host it.

---

## Related

- Phase I in `docs/STAFF_AUDIT_2026-08-19.md` (idea **F2**)
- `docs/FLOW.md` Path 3 for the component tree

---

## Resolution — 2026-08-20, session `848e92a5`

### Root cause

One breakpoint, written two different ways, with a gap between them.

`useIsMobile()` listened to `(max-width: 767px)` but stored
`window.innerWidth < 768`. Those are only equivalent when the viewport is a
whole number of CSS pixels. It often is not — Windows display scaling (125% is
the default on many laptops) makes the CSS width fractional, and a browser
reports `window.innerWidth` **rounded**. CSS sees 767.6; JS sees 768.

Neither of the two falsified hypotheses was close, and neither needed to be:
the breakpoint values were never the problem. `md` really is 768 and the hook
really is 768. The defect is that one of them is evaluated against a fraction
and the other against a rounded integer.

### Reproduced, then measured

Headless Chromium at whole-pixel widths could not reproduce it — the sidebar
was correct at every width from 320 to 1440, on all 15 routes, through every
resize path. **That is why static reading and ordinary Playwright both missed
it.** It reproduces in a headed Chrome at `devicePixelRatio` 1.25, walking the
real window across the breakpoint. Two distinct failures, both from the cause
above:

| CSS width | `max-width:767px` | `min-width:768px` | `innerWidth` | Result |
|---|---|---|---|---|
| 767.6 | false | **false** | 768 (rounded up) | JS says desktop, CSS hides it — the wrapper renders inside a `display: none` box. No sidebar, no rail, and the trigger only flips `data-state`. **The screenshot.** |
| 767.2 | false | false | 767 (rounded down) | The hook's only listener fires here and reads 767, latching `isMobile = true`. `max-width:767px` never fires again as the window widens, so the desktop sidebar never comes back. |

The second one is the nastier half. Measured on the way back up: the wrapper
was absent from CSS width 776 through 887, and clicking the trigger at 887px
opened the *mobile drawer*. Only a reload restored the sidebar. So the bug
outlives the window size that caused it — which is why Pranav saw no sidebar
at a width where the sidebar demonstrably works.

Note the band `767 < w < 768` matches **neither** query. That one pixel
belonging to nobody is where both failures live.

### Fix

`frontend/src/hooks/use-mobile.tsx` now listens to `(min-width: 768px)` — byte
for byte what Tailwind's `md:` compiles to — and reads its answer from
`event.matches` rather than re-reading a rounded `window.innerWidth`. There is
no second spelling left to disagree with, and no rounding involved.

### Verified

- `src/hooks/use-mobile.test.ts` — 3 tests. The two fractional-width cases were
  **watched failing against the old hook first** (`expected true, got false`
  and `expected false, got true`); the whole-pixel control passed both before
  and after, which is what makes it a control.
- The headed browser walk above, re-run against the rebuilt app: the wrapper is
  now correctly *absent* at CSS 767.x (drawer mode, agreeing with CSS) and
  returns at 776 and stays. Toggling at 887px moves the docked sidebar.
- `npm run test` 42/42 · `npm run typecheck` (`tsc -b`) exit 0 ·
  `npx playwright test` 17/17.

### What this cost, and the lesson worth keeping

Two sessions of static reading produced two dead ends, and a whole-pixel
browser sweep produced a third. **A layout bug that only exists at fractional
viewport widths is invisible to every tool that only offers integers** —
jsdom, Playwright viewports, and devtools' device toolbar all do. Reaching it
needed a real window, a non-integer `devicePixelRatio`, and a sweep across the
boundary one pixel at a time.

Generalise it: any breakpoint expressed once in CSS and once in JS is this bug
waiting to happen. Grep for a second `MOBILE_BREAKPOINT`-style constant before
adding one.
