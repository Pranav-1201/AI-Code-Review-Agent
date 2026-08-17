import { test, expect } from "@playwright/test";
import { loadDemo, mockBackend, navigateTo, SIDEBAR_LINKS } from "./fixtures";

// Runs only on the narrow projects; the desktop project excludes this file via
// `testIgnore` in playwright.config.ts.

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

/** Horizontal overflow of the document, in pixels. */
async function overflowPx(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const el = document.documentElement;
    return el.scrollWidth - el.clientWidth;
  });
}

test("no route overflows horizontally", async ({ page }) => {
  // Fifteen routes, each opening and closing the drawer at 375px. That does not
  // fit the 30s default.
  test.setTimeout(180_000);

  // One demo load, then walk the sidebar. Collecting every offender instead of
  // failing at the first one means a single run tells you the whole list.
  await loadDemo(page);

  // Kill transitions. The drawer animation is the slowest part of the walk and
  // the only reason Playwright's stability check ever has to retry; layout
  // width, which is all this test measures, does not depend on it.
  await page.addStyleTag({
    content: `*, *::before, *::after {
      animation-duration: 0s !important;
      animation-delay: 0s !important;
      transition-duration: 0s !important;
      transition-delay: 0s !important;
    }`,
  });

  const offenders: string[] = [];

  for (const path of Object.keys(SIDEBAR_LINKS)) {
    await navigateTo(page, path);

    // Wait out the lazy chunk before measuring; a Suspense fallback has a
    // different layout from the page it stands in for. Keyed to the fallback's
    // own testid rather than role="status", which EmptyState also uses.
    await expect(page.getByTestId("route-fallback")).toHaveCount(0, { timeout: 15_000 });

    // 1px of slack absorbs sub-pixel rounding on fractional viewport scaling.
    const overflow = await overflowPx(page);
    if (overflow > 1) offenders.push(`${path} (+${overflow}px)`);
  }

  expect(offenders, "routes overflowing horizontally").toEqual([]);
});

test("the 404 route does not overflow", async ({ page }) => {
  // Not reachable from the sidebar, and it needs no scan data.
  await page.goto("/does-not-exist");
  await expect(page.getByTestId("route-fallback")).toHaveCount(0, { timeout: 15_000 });

  expect(await overflowPx(page)).toBeLessThanOrEqual(1);
});

test("navigation is reachable at a narrow width", async ({ page }) => {
  await page.goto("/");

  // Scoped to the header: SidebarRail carries the same accessible name, and an
  // unscoped lookup would be a strict-mode violation rather than a real check.
  const trigger = page
    .getByRole("banner")
    .getByRole("button", { name: /toggle sidebar/i });

  await expect(trigger).toBeVisible();

  const navLink = page.getByRole("link", { name: "Security Report", exact: true });

  // useIsMobile switches at width < 768, so 768 itself still gets the docked
  // desktop sidebar and only 375 gets the drawer. Both have to end up with
  // navigation the user can actually reach; how they get there differs.
  if (page.viewportSize()!.width >= 768) {
    await expect(navLink).toBeVisible();
    return;
  }

  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(navLink).toBeVisible();
});
