import * as React from "react";

const MOBILE_BREAKPOINT = 768;

/**
 * True when the viewport is narrower than Tailwind's `md` breakpoint.
 *
 * The query below is deliberately the SAME one Tailwind's `md:` compiles to
 * (`min-width: 768px`), and the answer is read from the query's own match
 * state. Both of those matter — see BUG-001.
 *
 * The earlier version listened to `(max-width: 767px)` and stored
 * `window.innerWidth < 768`, which is two different spellings of one
 * breakpoint. Viewport widths are not always whole pixels — Windows display
 * scaling makes them fractional — and the two spellings disagree in the gap:
 *
 *   - at 767.6px, `min-width: 768px` is false (CSS hides the desktop sidebar)
 *     while `innerWidth` rounds to 768 (JS renders it anyway) — a sidebar
 *     inside a `display: none` box, and a toggle that appears to do nothing;
 *   - at 767.2px, `max-width: 767px` stops matching, so the old listener fired
 *     once and read a rounded 767 — latching "mobile" forever, because that
 *     query never fires again as the window keeps widening.
 *
 * Reading `event.matches` from the same query CSS uses removes both: there is
 * no second spelling to disagree with, and no rounded width to re-read.
 */
export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined);

  React.useEffect(() => {
    const mql = window.matchMedia(`(min-width: ${MOBILE_BREAKPOINT}px)`);
    const onChange = (event: MediaQueryListEvent) => setIsMobile(!event.matches);
    mql.addEventListener("change", onChange);
    setIsMobile(!mql.matches);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return !!isMobile;
}
