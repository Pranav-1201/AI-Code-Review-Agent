// Registers the jest-dom matchers (toBeInTheDocument, toHaveTextContent, ...)
// on vitest's expect. Referenced from vite.config.ts `test.setupFiles`.
import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom implements none of these, and Radix primitives (Collapsible, Select,
// Dialog, ...) reach for them internally. Without stubs, mounting those
// components throws "not implemented" rather than the assertion failure a
// test is actually trying to produce.
Element.prototype.scrollIntoView = vi.fn();

window.matchMedia =
  window.matchMedia ||
  function matchMedia(query: string) {
    return {
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList;
  };

class ResizeObserverStub {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
window.ResizeObserver = window.ResizeObserver || (ResizeObserverStub as unknown as typeof ResizeObserver);
