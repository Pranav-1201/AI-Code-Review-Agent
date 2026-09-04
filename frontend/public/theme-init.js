/*
 * Applies the saved theme before first paint (F1).
 *
 * Without this the page paints with :root — light — and then React mounts,
 * reads localStorage and swaps to dark, so a dark-theme user gets a white
 * flash on every navigation.
 *
 * A separate file rather than an inline <script> on purpose. The
 * Content-Security-Policy in the Caddyfile is `script-src 'self'` with no
 * 'unsafe-inline', and its comment says that directive must not gain one
 * because it is what actually stops XSS. A same-origin file satisfies
 * 'self' and needs no CSP change at all.
 *
 * Kept deliberately tiny and dependency-free: it runs render-blocking in
 * <head>, so anything slow here is felt on every page load. The logic is
 * duplicated from ThemeContext.tsx, which is the price of running before
 * the bundle exists; ThemeContext re-applies on mount, so a divergence
 * costs a flash rather than a wrong theme.
 */
(function () {
  try {
    var stored = localStorage.getItem("etproject-theme");
    var dark =
      stored === "dark" ||
      ((stored === "system" || stored === null) &&
        window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    if (dark) {
      document.documentElement.classList.add("dark");
    }
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {
    /* Storage refused, or no matchMedia. Fall through to the light default. */
  }
})();
