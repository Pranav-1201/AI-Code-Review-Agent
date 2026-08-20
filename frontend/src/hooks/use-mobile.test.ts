import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useIsMobile } from "./use-mobile";

/**
 * Regression tests for BUG-001 (docs/bugs/BUG-001-sidebar-split-view.md).
 *
 * The sidebar's layout is decided in two places that must agree exactly:
 *
 *   - CSS: the desktop wrapper is `hidden md:block`, i.e. it is only shown by
 *     `@media (min-width: 768px)`.
 *   - JS:  `useIsMobile()` decides whether to render that desktop wrapper at
 *     all, or the mobile Sheet instead.
 *
 * A viewport width is not always an integer. Windows display scaling (125% is
 * the Windows 11 default on many laptops) makes the CSS width a fraction of a
 * pixel, and `window.innerWidth` reports that fraction ROUNDED. So a real CSS
 * width of 767.6px is reported by JS as 768 and evaluated by CSS as 767.6 —
 * the two disagree, and the sidebar falls into the gap between them.
 *
 * The fake viewport below reproduces that faithfully: media queries see the
 * fractional width, `window.innerWidth` sees the rounded one.
 */

type FakeList = {
  query: string;
  matches: boolean;
  listeners: Set<(event: MediaQueryListEvent) => void>;
};

const originalMatchMedia = window.matchMedia;
const originalInnerWidth = window.innerWidth;

function matchesQuery(query: string, width: number): boolean {
  const max = /^\(max-width:\s*([\d.]+)px\)$/.exec(query);
  if (max) return width <= Number(max[1]);
  const min = /^\(min-width:\s*([\d.]+)px\)$/.exec(query);
  if (min) return width >= Number(min[1]);
  throw new Error(`fake viewport does not understand the query ${query}`);
}

/**
 * Installs a `window.matchMedia` that evaluates min-/max-width queries against
 * a viewport of the given CSS width, and a `window.innerWidth` rounded the way
 * a browser rounds it. Returns a setter that resizes the viewport and fires
 * `change` on exactly those queries whose match state actually flipped — which
 * is the part that matters, because a query that was already false fires
 * nothing when the width moves further away from it.
 */
function installViewport(initialWidth: number) {
  let width = initialWidth;
  const lists: FakeList[] = [];

  const setInnerWidth = (value: number) => {
    Object.defineProperty(window, "innerWidth", {
      value: Math.round(value),
      configurable: true,
      writable: true,
    });
  };
  setInnerWidth(width);

  window.matchMedia = ((query: string) => {
    const list: FakeList = { query, matches: matchesQuery(query, width), listeners: new Set() };
    lists.push(list);
    return {
      get matches() {
        return list.matches;
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) =>
        list.listeners.add(listener),
      removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) =>
        list.listeners.delete(listener),
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  }) as typeof window.matchMedia;

  return function resizeTo(next: number) {
    width = next;
    setInnerWidth(width);
    for (const list of lists) {
      const matches = matchesQuery(list.query, width);
      if (matches === list.matches) continue;
      list.matches = matches;
      const event = { matches, media: list.query } as MediaQueryListEvent;
      for (const listener of list.listeners) listener(event);
    }
  };
}

describe("useIsMobile", () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    Object.defineProperty(window, "innerWidth", {
      value: originalInnerWidth,
      configurable: true,
      writable: true,
    });
  });

  it("agrees with CSS at whole-pixel widths on either side of the breakpoint", () => {
    installViewport(767);
    expect(renderHook(() => useIsMobile()).result.current).toBe(true);

    installViewport(768);
    expect(renderHook(() => useIsMobile()).result.current).toBe(false);
  });

  it("stays mobile at a fractional width that `md:` does not match", () => {
    // 767.6px: `(min-width: 768px)` is false, so the desktop sidebar is hidden
    // by CSS no matter what JS decides. Reporting desktop here renders the
    // desktop wrapper into a `display: none` box — a sidebar that is not on
    // screen and a toggle button that appears to do nothing.
    installViewport(767.6);

    expect(renderHook(() => useIsMobile()).result.current).toBe(true);
  });

  it("returns to desktop after the window is widened back through the gap", () => {
    // Dragging a split-view window wider crosses 767.2px on the way. There,
    // `(max-width: 767px)` stops matching while `(min-width: 768px)` has not
    // started — the one pixel that belongs to neither query. Whatever is
    // decided at that width must not be final: the sidebar has to come back
    // when the window reaches a genuinely desktop width.
    const resizeTo = installViewport(756);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);

    act(() => resizeTo(767.2));
    act(() => resizeTo(776));

    expect(result.current).toBe(false);
  });
});
