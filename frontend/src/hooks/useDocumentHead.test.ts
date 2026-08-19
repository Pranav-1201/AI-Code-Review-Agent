import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useDocumentHead } from "./useDocumentHead";

/**
 * The conditional tags are the ones worth testing. Title and description are
 * always written; canonical, og:url and robots are each present only in one
 * configuration, and getting that backwards is silent — a canonical pointing
 * at the wrong origin looks fine in a browser and misdirects every crawler.
 */

function head(selector: string): HTMLElement | null {
  return document.head.querySelector<HTMLElement>(selector);
}

function content(selector: string): string | undefined {
  return head(selector)?.getAttribute("content") ?? undefined;
}

describe("useDocumentHead", () => {
  beforeEach(() => {
    document.head.innerHTML = "";
    document.title = "";
  });

  it("writes the title and description", () => {
    renderHook(() =>
      useDocumentHead({ title: "Security Report · AI Code Review", description: "Findings." }),
    );

    expect(document.title).toBe("Security Report · AI Code Review");
    expect(content('meta[name="description"]')).toBe("Findings.");
    expect(content('meta[property="og:title"]')).toBe("Security Report · AI Code Review");
    expect(content('meta[property="og:description"]')).toBe("Findings.");
  });

  it("omits canonical and og:url when no site URL is configured", () => {
    renderHook(() => useDocumentHead({ title: "T", description: "D" }));

    expect(head('link[rel="canonical"]')).toBeNull();
    expect(head('meta[property="og:url"]')).toBeNull();
  });

  it("emits canonical and og:url when a site URL is configured", () => {
    renderHook(() =>
      useDocumentHead({ title: "T", description: "D", canonical: "https://example.com/security" }),
    );

    expect(head('link[rel="canonical"]')?.getAttribute("href")).toBe(
      "https://example.com/security",
    );
    expect(content('meta[property="og:url"]')).toBe("https://example.com/security");
  });

  it("emits noindex only when asked", () => {
    const { rerender } = renderHook(
      (props: { noindex: boolean }) =>
        useDocumentHead({ title: "T", description: "D", noindex: props.noindex }),
      { initialProps: { noindex: true } },
    );

    expect(content('meta[name="robots"]')).toBe("noindex");

    // Navigating from a noindex route to an indexable one must actually clear
    // the tag. Leaving it behind would quietly de-index the rest of the site
    // for any crawler that arrived via a client-side navigation.
    rerender({ noindex: false });
    expect(head('meta[name="robots"]')).toBeNull();
  });

  it("drops the canonical again when navigating to a route without one", () => {
    const { rerender } = renderHook(
      (props: { canonical?: string }) =>
        useDocumentHead({ title: "T", description: "D", canonical: props.canonical }),
      { initialProps: { canonical: "https://example.com/a" } as { canonical?: string } },
    );

    expect(head('link[rel="canonical"]')).not.toBeNull();

    rerender({ canonical: undefined });
    expect(head('link[rel="canonical"]')).toBeNull();
  });

  it("updates tags in place rather than accumulating duplicates", () => {
    const { rerender } = renderHook(
      (props: { description: string }) =>
        useDocumentHead({ title: "T", description: props.description }),
      { initialProps: { description: "First" } },
    );

    rerender({ description: "Second" });

    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1);
    expect(content('meta[name="description"]')).toBe("Second");
  });

  it("emits the Search Console token only when one is configured", () => {
    renderHook(() => useDocumentHead({ title: "T", description: "D" }));
    expect(head('meta[name="google-site-verification"]')).toBeNull();

    renderHook(() => useDocumentHead({ title: "T", description: "D", verification: "abc123" }));
    expect(content('meta[name="google-site-verification"]')).toBe("abc123");
  });
});
