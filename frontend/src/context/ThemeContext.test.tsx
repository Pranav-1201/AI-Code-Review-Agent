/**
 * F1 — light mode. The remaining half of Phase I.
 *
 * The dark palette lived on `:root`, so there was exactly one theme and no
 * way to ask for another. These tests pin the three behaviours that make a
 * theme toggle trustworthy: it remembers the choice, it follows the OS when
 * asked to, and it stops following the OS once the user has chosen.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { ThemeProvider, useTheme, THEME_STORAGE_KEY } from "./ThemeContext";

let mediaListeners: ((e: { matches: boolean }) => void)[] = [];
let prefersDark = false;

function installMatchMedia() {
  mediaListeners = [];
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("dark") ? prefersDark : false,
      media: query,
      addEventListener: (_: string, fn: (e: { matches: boolean }) => void) =>
        mediaListeners.push(fn),
      removeEventListener: (_: string, fn: (e: { matches: boolean }) => void) => {
        mediaListeners = mediaListeners.filter((l) => l !== fn);
      },
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }))
  );
}

function Probe() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setTheme("light")}>light</button>
      <button onClick={() => setTheme("dark")}>dark</button>
      <button onClick={() => setTheme("system")}>system</button>
    </div>
  );
}

const isDarkClassOn = () => document.documentElement.classList.contains("dark");

beforeEach(() => {
  prefersDark = false;
  installMatchMedia();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ThemeProvider", () => {
  it("defaults to following the operating system", () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByTestId("theme")).toHaveTextContent("system");
  });

  it("resolves to dark when the OS prefers dark", () => {
    prefersDark = true;
    installMatchMedia();
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(isDarkClassOn()).toBe(true);
  });

  it("resolves to light when the OS prefers light", () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
    expect(isDarkClassOn()).toBe(false);
  });

  it("applies an explicit choice over the OS preference", () => {
    prefersDark = true;
    installMatchMedia();
    render(<ThemeProvider><Probe /></ThemeProvider>);
    fireEvent.click(screen.getByRole("button", { name: "light" }));
    expect(isDarkClassOn()).toBe(false);
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
  });

  it("persists the choice so a reload does not undo it", () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    fireEvent.click(screen.getByRole("button", { name: "dark" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("restores a stored choice on mount", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    expect(isDarkClassOn()).toBe(true);
  });

  it("follows a live OS change while set to system", () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(isDarkClassOn()).toBe(false);
    act(() => {
      mediaListeners.forEach((fn) => fn({ matches: true }));
    });
    expect(isDarkClassOn()).toBe(true);
  });

  it("ignores a live OS change once the user has chosen", () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    fireEvent.click(screen.getByRole("button", { name: "light" }));
    act(() => {
      mediaListeners.forEach((fn) => fn({ matches: true }));
    });
    expect(isDarkClassOn()).toBe(false);
  });

  it("survives localStorage being unavailable", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError: storage disabled");
    });
    expect(() =>
      render(<ThemeProvider><Probe /></ThemeProvider>)
    ).not.toThrow();
    getItem.mockRestore();
  });

  it("ignores a corrupted stored value rather than applying it", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "chartreuse");
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByTestId("theme")).toHaveTextContent("system");
  });
});
