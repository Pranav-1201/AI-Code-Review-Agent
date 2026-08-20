import { test, expect } from "@playwright/test";
import { mockBackend } from "./fixtures";

/**
 * The docked sidebar at a split-view width — the acceptance criterion for
 * Phase I in docs/STAFF_AUDIT_2026-08-19.md.
 *
 * Honest scope note: this spec did NOT fail before the BUG-001 fix, and it
 * could not have. That bug only appears at fractional CSS viewport widths
 * (Windows display scaling), and Playwright viewports are whole pixels. The
 * test that gates BUG-001 is src/hooks/use-mobile.test.ts, which models
 * fractional widths directly and was watched failing first.
 *
 * What this spec does add is the integration nothing else covered: that the
 * provider, the CSS and AppSidebar together produce a real docked sidebar at a
 * half-screen width, and that collapsing leaves the icon rail rather than
 * nothing.
 *
 * Runs on the desktop project only — the narrow projects ignore this file, see
 * playwright.config.ts. Their own drawer coverage is in mobile.spec.ts.
 */

test.use({ viewport: { width: 960, height: 800 } });

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

/** The desktop sidebar's fixed panel — the element that is actually on screen. */
function panel(page: import("@playwright/test").Page) {
  return page.locator('[data-sidebar="sidebar"]:not([data-mobile])');
}

test("the sidebar is docked and navigable at a half-screen width", async ({ page }) => {
  await page.goto("/");

  await expect(panel(page)).toBeVisible();
  await expect(page.getByRole("link", { name: "Security Report", exact: true })).toBeVisible();

  // No Radix dialog: at 960px this must be the docked sidebar, not the drawer
  // that belongs to narrow viewports.
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("the trigger collapses the sidebar to the icon rail and back", async ({ page }) => {
  await page.goto("/");

  const trigger = page.getByRole("banner").getByRole("button", { name: /toggle sidebar/i });
  const width = async () => (await panel(page).boundingBox())!.width;

  expect(await width()).toBeGreaterThan(200);

  await trigger.click();
  // 3rem icon rail. Collapsing to zero would leave no navigation at all, which
  // is the state BUG-001 was reported as.
  await expect.poll(width).toBeLessThan(60);
  await expect(panel(page)).toBeVisible();

  await trigger.click();
  await expect.poll(width).toBeGreaterThan(200);
});
