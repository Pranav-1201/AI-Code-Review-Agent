# BUG-001 — sidebar unusable in a half-width browser window

**Status:** OPEN · **Severity:** high (app is unusable in this window size)
**Reported:** 2026-08-19 by Pranav, with a screenshot
**Owner of next step:** whoever starts Phase I
**Investigated by:** Claude Opus 5, session `a55eaf1f` — **not root-caused**

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
