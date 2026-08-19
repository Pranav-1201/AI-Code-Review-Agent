import { useEffect } from "react";

/**
 * Head management for a static SPA.
 *
 * react-helmet-async exists to solve this problem *during server-side
 * rendering*, where tags must be collected out of band and serialised into an
 * HTML string. Nothing here is server-rendered: Caddy serves a static
 * index.html and React mounts into it. There is no render pass to collect
 * from, so the library's actual value does not apply and this is a dependency
 * the project does not need to carry.
 */

export type DocumentHead = {
  /** Written to document.title verbatim. */
  title: string;
  description: string;
  /** Absolute URL. Omitted entirely when the site has no domain yet. */
  canonical?: string;
  /** True emits <meta name="robots" content="noindex">. */
  noindex?: boolean;
  /** Search Console verification token, when one is configured. */
  verification?: string;
};

/**
 * Create-or-update a tag, identified by a stable selector.
 *
 * Tags are never removed, only rewritten. Removing and re-adding on every
 * navigation would leave the head briefly inconsistent, and a crawler or a
 * share-preview fetch that sampled that moment would see a page with no
 * description at all.
 */
function upsert(
  selector: string,
  create: () => HTMLElement,
  apply: (element: HTMLElement) => void,
): void {
  let element = document.head.querySelector<HTMLElement>(selector);

  if (!element) {
    element = create();
    document.head.appendChild(element);
  }

  apply(element);
}

function setMeta(attribute: "name" | "property", key: string, content: string): void {
  upsert(
    `meta[${attribute}="${key}"]`,
    () => {
      const meta = document.createElement("meta");
      meta.setAttribute(attribute, key);
      return meta;
    },
    (meta) => meta.setAttribute("content", content),
  );
}

/** Remove a tag if it exists. Used for the conditional ones. */
function remove(selector: string): void {
  document.head.querySelector(selector)?.remove();
}

export function useDocumentHead(head: DocumentHead): void {
  const { title, description, canonical, noindex, verification } = head;

  useEffect(() => {
    document.title = title;

    setMeta("name", "description", description);
    setMeta("property", "og:title", title);
    setMeta("property", "og:description", description);

    if (canonical) {
      upsert(
        'link[rel="canonical"]',
        () => {
          const link = document.createElement("link");
          link.setAttribute("rel", "canonical");
          return link;
        },
        (link) => link.setAttribute("href", canonical),
      );
      setMeta("property", "og:url", canonical);
    } else {
      // No domain configured. An absent canonical is honest; one pointing at a
      // placeholder origin would actively tell crawlers the wrong thing.
      remove('link[rel="canonical"]');
      remove('meta[property="og:url"]');
    }

    if (noindex) {
      setMeta("name", "robots", "noindex");
    } else {
      remove('meta[name="robots"]');
    }

    if (verification) {
      setMeta("name", "google-site-verification", verification);
    }
  }, [title, description, canonical, noindex, verification]);
}
