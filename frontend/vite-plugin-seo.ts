import { appendFileSync, copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

import { ROUTES } from "./src/lib/routes";

/**
 * Build-time SEO artifacts: 404.html, sitemap.xml, and the robots.txt pointer.
 *
 * This plugin imports src/lib/routes.ts directly, in Node — which is the whole
 * reason that file is forbidden from importing anything itself. A React import
 * there would turn this line into a build failure.
 */

export type SeoPluginOptions = {
  /**
   * Absolute public origin, e.g. "https://example.com".
   *
   * Empty is the default and the normal state until a domain exists. Empty
   * means no sitemap and no robots.txt pointer at all, rather than either one
   * built around a placeholder origin — a sitemap full of wrong URLs is worse
   * than no sitemap, because a crawler will act on it.
   */
  siteUrl?: string;
};

function sitemapXml(siteUrl: string): string {
  const urls = ROUTES.filter((route) => route.indexable)
    .map((route) => `  <url><loc>${siteUrl}${route.path}</loc></url>`)
    .join("\n");

  // No <lastmod>, <changefreq> or <priority>. lastmod would have to be either
  // the build timestamp (which lies — the page did not change) or maintained by
  // hand (which rots), and Google ignores the other two outright.
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`;
}

export function seoPlugin(options: SeoPluginOptions = {}): Plugin {
  const siteUrl = (options.siteUrl ?? "").replace(/\/+$/, "");

  return {
    name: "etproject:seo",
    apply: "build",

    closeBundle() {
      const outDir = path.resolve(__dirname, "dist");
      const indexHtml = path.join(outDir, "index.html");

      if (!existsSync(indexHtml)) {
        throw new Error(
          `Expected ${indexHtml} after the build; cannot generate 404.html without it.`,
        );
      }

      // 404.html is a byte-copy of the shell, so the 404 page IS the app:
      // React Router matches "*" and renders the existing NotFound component.
      // Caddy serves this file with the original status via handle_errors.
      copyFileSync(indexHtml, path.join(outDir, "404.html"));

      if (!siteUrl) return;

      writeFileSync(path.join(outDir, "sitemap.xml"), sitemapXml(siteUrl), "utf8");

      const robots = path.join(outDir, "robots.txt");
      if (existsSync(robots) && !readFileSync(robots, "utf8").includes("Sitemap:")) {
        appendFileSync(robots, `\nSitemap: ${siteUrl}/sitemap.xml\n`, "utf8");
      }
    },
  };
}
