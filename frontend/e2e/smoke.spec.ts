import { test, expect } from "@playwright/test";
import { loadDemo, mockBackend, navigateTo } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test("the landing route renders", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Repository Scanner" })).toBeVisible();
});

test("a scan runs and lands on the results route", async ({ page }) => {
  await page.goto("/");

  await page.getByPlaceholder("https://github.com/username/repository").fill(
    "https://github.com/acme/widget"
  );
  await page.getByRole("button", { name: "Scan" }).click();

  await expect(page).toHaveURL(/\/results$/, { timeout: 30_000 });
});

test("lazily-loaded routes resolve", async ({ page }) => {
  // Each of these lives in its own chunk after the code-splitting change.
  // Asserting the page's own heading is what proves the chunk arrived and
  // rendered; asserting the error boundary is absent proves it did not arrive
  // as a failed import.
  const routes = [
    { path: "/security", heading: "Security Vulnerability Report" },
    { path: "/dependencies", heading: "Dependency Analysis" },
    { path: "/visualizations", heading: "Visualization Dashboard" },
  ];

  // These pages early-return an empty state when no scan is loaded, and an
  // empty state renders no heading — so without data the assertion below could
  // not tell a missing chunk from a page with nothing to show.
  await loadDemo(page);

  for (const { path, heading } of routes) {
    await navigateTo(page, path);
    await expect(page.getByTestId("route-fallback")).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
});
