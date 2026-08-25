import { test, expect } from "@playwright/test";
import { loadDemo, mockBackend, navigateTo } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

/**
 * F16. The tiles and the finding cards are new interactive elements, and a
 * control that only works with a mouse is not a control. These drive both
 * from the keyboard alone.
 *
 * navigateTo() only guarantees the URL has changed, not that the destination
 * page has finished rendering — SecurityReport is lazy-loaded, and for a
 * moment after the URL updates the previous route's DOM (e.g. ScanResults'
 * own collapsible "All File Scores" section) is still what's on screen. A
 * selector built before the heading below is confirmed can lock onto that
 * leftover content instead of this page's. Waiting for the page's own
 * heading first is what makes everything queried after it trustworthy.
 */

test("a finding card expands from the keyboard", async ({ page }) => {
  await loadDemo(page);
  await navigateTo(page, "/security");
  await expect(page.getByRole("heading", { name: "Security Vulnerability Report" })).toBeVisible();

  const main = page.getByRole("main");

  // `{ expanded: false }` finds the first collapsed card, but it is a LIVE
  // filter, not a snapshot: once the click flips aria-expanded to "true" the
  // same locator stops matching that button and silently re-resolves to the
  // next still-collapsed one instead. Asserting through a locator built this
  // way never fails — it just keeps checking a different, genuinely-closed
  // button on every retry. Reading the button's name once and re-finding it
  // by that stable name is what keeps the assertion pointed at the button we
  // actually activated.
  const collapsed = main.getByRole("button", { expanded: false }).first();
  await expect(collapsed).toBeVisible();
  const name = await collapsed.evaluate((el) => el.textContent?.trim());
  const trigger = main.getByRole("button", { name: name!, exact: true });

  await expect(trigger).toHaveAttribute("aria-expanded", "false");

  await trigger.focus();
  await page.keyboard.press("Enter");

  await expect(trigger).toHaveAttribute("aria-expanded", "true");
});

test("a severity tier moves focus to its group heading", async ({ page }) => {
  await loadDemo(page);
  await navigateTo(page, "/security");
  await expect(page.getByRole("heading", { name: "Security Vulnerability Report" })).toBeVisible();

  // Whichever tier the demo data actually populates. Matching on the aria-label
  // shape rather than a hardcoded severity keeps this from breaking when the
  // demo report changes.
  const tier = page.getByRole("button", { name: /jump to findings/ }).first();
  await expect(tier).toBeVisible();

  const label = await tier.getAttribute("aria-label");
  const severity = label!.split(" ")[1];

  const heading = page.getByRole("heading", { name: new RegExp(`^${severity} — `) });
  await expect(heading).not.toBeFocused();

  await tier.focus();
  await page.keyboard.press("Enter");

  await expect(heading).toBeFocused();
});

/**
 * J3. The panes are the product's explanation surface; a unit test proves the
 * component renders, only the real app proves the demo reaches it. This also
 * pins that the two renamed tabs are what a user actually sees — "Improved"
 * and "Patch" both claimed more than the engine does.
 */
test("the suggested-edits pane is reachable and the raw diff survives", async ({ page }) => {
  await loadDemo(page);
  await navigateTo(page, "/file-analysis");
  await expect(page.getByRole("heading", { name: "File Level Analysis" })).toBeVisible();

  await expect(page.getByRole("tab", { name: "Suggested edits" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Improved" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Patch" })).toHaveCount(0);

  await page.getByRole("tab", { name: "What changed" }).click();

  await expect(page.getByText(/Added placeholder docstrings to/)).toBeVisible();
  await expect(page.getByRole("button", { name: /raw diff/i })).toBeVisible();
});
