import { useLocation } from "react-router-dom";

import { useDocumentHead } from "@/hooks/useDocumentHead";
import { ROUTES, SITE_NAME, routeFor } from "@/lib/routes";

/**
 * Applies the current route's metadata to the document head.
 *
 * Rendered once, inside <BrowserRouter>. The alternative — a useDocumentHead
 * call in each of the 15 pages — would mean 15 files to touch and 15 chances
 * to forget one, while the metadata already lives centrally in routes.ts.
 */

/**
 * Absolute origin for canonical URLs, e.g. "https://example.com".
 *
 * Empty by default and deliberately so, mirroring Phase F's SITE_ADDRESS: the
 * site has no domain yet, and every consumer of this value is written to omit
 * itself rather than emit a placeholder.
 */
const SITE_URL = (import.meta.env.VITE_SITE_URL ?? "").replace(/\/+$/, "");

const SEARCH_CONSOLE_TOKEN = import.meta.env.VITE_SEARCH_CONSOLE_TOKEN ?? "";

/** Shown for any path not in ROUTES — i.e. the "*" route. */
const NOT_FOUND: { title: string; description: string } = {
  title: "Page not found",
  description: "The page you are looking for does not exist.",
};

export function RouteHead() {
  const { pathname } = useLocation();
  const route = routeFor(pathname);

  const title = route
    ? // The landing page is titled with the product name alone. "Repository
      // Scanner · AI Code Review" reads worse in a search result than the
      // product name does, and the home page is the one result where the
      // product name is the whole point.
      route.path === "/"
      ? SITE_NAME
      : `${route.title} · ${SITE_NAME}`
    : `${NOT_FOUND.title} · ${SITE_NAME}`;

  useDocumentHead({
    title,
    description: route ? route.description : NOT_FOUND.description,
    canonical: SITE_URL ? `${SITE_URL}${pathname}` : undefined,
    // An unknown path is never indexable, whatever it is. It already returns a
    // real 404 from Caddy; this covers the client-side navigation case, where
    // no HTTP status is involved at all.
    noindex: route ? !route.indexable : true,
    verification: SEARCH_CONSOLE_TOKEN || undefined,
  });

  return null;
}

/** Exported for tests: the routes whose metadata this component can apply. */
export const HEAD_ROUTES = ROUTES;
