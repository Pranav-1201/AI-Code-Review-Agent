import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { ROUTES } from "./routes";

/**
 * Caddy cannot import TypeScript, so the Caddyfile holds a hand-written mirror
 * of the route list. A mirror nobody checks is a mirror that rots: adding a
 * route to routes.ts and forgetting the Caddyfile would ship a page that 404s
 * in production while working perfectly in `npm run dev`, because the dev
 * server has no Caddy in front of it.
 *
 * These tests are the check. They read the real file from the repository root
 * rather than a fixture, so they cannot pass against a stale copy.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

function readRepoFile(relativePath: string): string {
  return readFileSync(path.join(REPO_ROOT, relativePath), "utf8");
}

/**
 * Pull the argument list out of the Caddyfile's `@spa path ...` matcher.
 *
 * The matcher spans several lines joined by trailing backslashes, so the
 * continuations are folded before the paths are split out.
 */
function spaPathsFromCaddyfile(caddyfile: string): string[] {
  const unwrapped = caddyfile.replace(/\\\r?\n\s*/g, " ");
  const match = unwrapped.match(/^\s*@spa\s+path\s+(.*)$/m);

  if (!match) {
    throw new Error(
      "No `@spa path ...` matcher found in the Caddyfile. The SPA route list " +
        "must live there so unknown paths can return a real 404.",
    );
  }

  return match[1].trim().split(/\s+/).filter(Boolean);
}

describe("Caddyfile / routes.ts agreement", () => {
  it("serves the SPA for exactly the paths routes.ts declares", () => {
    const caddyPaths = spaPathsFromCaddyfile(readRepoFile("Caddyfile"));
    const appPaths = ROUTES.map((route) => route.path);

    // Sorted so the failure output is a readable diff rather than an ordering
    // argument — the Caddyfile groups paths for line length, routes.ts orders
    // them for the sidebar, and neither order is wrong.
    expect([...caddyPaths].sort()).toEqual([...appPaths].sort());
  });

  it("lists each path exactly once in the Caddyfile", () => {
    const caddyPaths = spaPathsFromCaddyfile(readRepoFile("Caddyfile"));

    expect(caddyPaths).toHaveLength(new Set(caddyPaths).size);
  });
});

describe("routes.ts portability", () => {
  it("imports nothing, so vite.config.ts can load it in Node", () => {
    const source = readRepoFile("frontend/src/lib/routes.ts");

    // Strip block and line comments first: the file's own header explains this
    // rule using the word `import`, and matching that text would fail the test
    // for documenting itself.
    const withoutComments = source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");

    expect(withoutComments).not.toMatch(/^\s*import\s/m);
    expect(withoutComments).not.toMatch(/\bimport\s*\(/);
    expect(withoutComments).not.toMatch(/\bimport\.meta\b/);
  });

  it("declares a unique, absolute path for every route", () => {
    const paths = ROUTES.map((route) => route.path);

    expect(paths).toHaveLength(new Set(paths).size);
    for (const routePath of paths) {
      expect(routePath.startsWith("/")).toBe(true);
    }
  });

  it("gives every route a title and a description", () => {
    for (const route of ROUTES) {
      expect(route.title.length).toBeGreaterThan(0);
      expect(route.description.length).toBeGreaterThan(0);
    }
  });
});
