import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * F1 — light mode, the remaining half of Phase I.
 *
 * The dark palette lived on `:root`, which meant there was exactly one theme
 * and no way to ask for another. It now lives on `.dark`, and `:root` carries
 * the light palette — the shadcn/Tailwind convention, and the one every
 * component under `components/ui` was already written against.
 *
 * `.dark` on the documentElement rather than a `[data-theme]` attribute
 * because `tailwind.config.ts` already declares `darkMode: ["class"]`.
 * Choosing the attribute would have meant changing that config and breaking
 * every shadcn snippet copied in afterwards.
 */
export type Theme = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "etproject-theme";

const VALID: Theme[] = ["light", "dark", "system"];

interface ThemeContextValue {
  /** What the user asked for, including "system". */
  theme: Theme;
  /** What is actually on screen right now. */
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/** Reading localStorage throws outright in some privacy modes, so every
 *  access is guarded — a browser that refuses storage must still render. */
function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return VALID.includes(stored as Theme) ? (stored as Theme) : "system";
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(resolved: ResolvedTheme) {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  // Lets the browser paint native controls (scrollbars, form widgets) to
  // match, which a class alone does not do.
  root.style.colorScheme = resolved;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark);

  const resolvedTheme: ResolvedTheme =
    theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    applyTheme(resolvedTheme);
  }, [resolvedTheme]);

  // Track the OS preference at all times, but only let it decide the applied
  // theme while `theme` is "system" — which the derivation above handles.
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent | { matches: boolean }) =>
      setSystemDark(event.matches);
    query.addEventListener("change", onChange as EventListener);
    return () => query.removeEventListener("change", onChange as EventListener);
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // A refused write costs persistence, not the toggle.
    }
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme]
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used inside a ThemeProvider");
  }
  return context;
}
