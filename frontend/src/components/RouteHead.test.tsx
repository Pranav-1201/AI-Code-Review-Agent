import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RouteHead } from "./RouteHead";
import { ROUTES, SITE_NAME } from "@/lib/routes";

function renderAt(pathname: string) {
  return render(
    <MemoryRouter
      initialEntries={[pathname]}
      // Match App.tsx, so the suite does not print v7 upgrade warnings that
      // the real router has already opted into.
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <RouteHead />
    </MemoryRouter>,
  );
}

function robots(): string | null {
  return document.head.querySelector('meta[name="robots"]')?.getAttribute("content") ?? null;
}

describe("RouteHead", () => {
  it("titles the landing page with the product name alone", () => {
    renderAt("/");

    // Not "Repository Scanner · AI Code Review". The home page is the one
    // search result where the product name is the whole point.
    expect(document.title).toBe(SITE_NAME);
  });

  it("titles every other route as page then product", () => {
    renderAt("/security");

    expect(document.title).toBe(`Security Report · ${SITE_NAME}`);
  });

  it("gives every route in the table a distinct, non-empty title", () => {
    const titles = new Set<string>();

    for (const route of ROUTES) {
      renderAt(route.path);
      expect(document.title.length).toBeGreaterThan(0);
      titles.add(document.title);
    }

    expect(titles.size).toBe(ROUTES.length);
  });

  it("noindexes an unknown path", () => {
    renderAt("/no-such-page");

    expect(robots()).toBe("noindex");
    expect(document.title).toBe(`Page not found · ${SITE_NAME}`);
  });

  it("noindexes the routes marked non-indexable, and only those", () => {
    for (const route of ROUTES) {
      renderAt(route.path);
      expect(robots()).toBe(route.indexable ? null : "noindex");
    }
  });
});
