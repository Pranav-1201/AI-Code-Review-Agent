/**
 * F1 — both themes must actually be readable.
 *
 * The dark palette was hand-tuned over months of looking at it. The light
 * palette was written in one sitting, which is exactly the situation where
 * "looks fine on my monitor" ships a foreground nobody else can read. This
 * parses index.css and checks the real token pairs against WCAG 2.1.
 *
 * Deliberately reads the stylesheet rather than hardcoding the values: a
 * token edited in index.css without a matching edit here would otherwise be
 * checked against numbers that are no longer on screen.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const css = readFileSync(resolve(__dirname, "../index.css"), "utf-8");

/** Pull the `--token: H S% L%;` declarations out of one selector block. */
function tokensOf(selector: string): Record<string, [number, number, number]> {
  const start = css.indexOf(`  ${selector} {`);
  expect(start, `${selector} block not found in index.css`).toBeGreaterThan(-1);
  const end = css.indexOf("\n  }", start);
  const block = css.slice(start, end);

  const out: Record<string, [number, number, number]> = {};
  const re = /--([\w-]+):\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*;/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(block))) {
    out[m[1]] = [Number(m[2]), Number(m[3]), Number(m[4])];
  }
  return out;
}

function hslToRgb([h, s, l]: [number, number, number]): [number, number, number] {
  const S = s / 100;
  const L = l / 100;
  const c = (1 - Math.abs(2 * L - 1)) * S;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = L - c / 2;
  const [r, g, b] =
    h < 60 ? [c, x, 0] :
    h < 120 ? [x, c, 0] :
    h < 180 ? [0, c, x] :
    h < 240 ? [0, x, c] :
    h < 300 ? [x, 0, c] : [c, 0, x];
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

/** WCAG 2.1 relative luminance. */
function luminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(
  a: [number, number, number],
  b: [number, number, number]
): number {
  const la = luminance(hslToRgb(a));
  const lb = luminance(hslToRgb(b));
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Foreground/background pairs that carry body text — AA is 4.5:1. */
const TEXT_PAIRS: [string, string][] = [
  ["foreground", "background"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["muted-foreground", "muted"],
  ["muted-foreground", "background"],
  ["accent-foreground", "accent"],
  ["destructive-foreground", "destructive"],
  ["sidebar-foreground", "sidebar-background"],
  ["sidebar-accent-foreground", "sidebar-accent"],
  ["warning-foreground", "warning"],
  ["info-foreground", "info"],
  ["success-foreground", "success"],
];

/** Non-text tokens that must still be distinguishable — AA is 3:1. */
const UI_PAIRS: [string, string][] = [
  ["primary", "background"],
  ["primary", "card"],
  ["accent", "card"],
  ["destructive", "card"],
  ["chart-1", "card"],
  ["chart-2", "card"],
  ["chart-3", "card"],
  ["chart-4", "card"],
  ["chart-5", "card"],
];

describe.each([["light", ":root"], ["dark", ".dark"]])(
  "%s theme contrast",
  (_name, selector) => {
    const tokens = tokensOf(selector);

    it.each(TEXT_PAIRS)("%s on %s meets WCAG AA for text", (fg, bg) => {
      expect(tokens[fg], `--${fg} missing from ${selector}`).toBeDefined();
      expect(tokens[bg], `--${bg} missing from ${selector}`).toBeDefined();
      const ratio = contrast(tokens[fg], tokens[bg]);
      expect(
        Number(ratio.toFixed(2)),
        `--${fg} on --${bg} in ${selector} is ${ratio.toFixed(2)}:1, needs 4.5:1`
      ).toBeGreaterThanOrEqual(4.5);
    });

    it.each(UI_PAIRS)("%s on %s meets WCAG AA for UI", (fg, bg) => {
      const ratio = contrast(tokens[fg], tokens[bg]);
      expect(
        Number(ratio.toFixed(2)),
        `--${fg} on --${bg} in ${selector} is ${ratio.toFixed(2)}:1, needs 3:1`
      ).toBeGreaterThanOrEqual(3);
    });

    it("defines a border distinguishable from its background", () => {
      const ratio = contrast(tokens["border"], tokens["background"]);
      expect(
        Number(ratio.toFixed(2)),
        `--border on --background in ${selector} is ${ratio.toFixed(2)}:1`
      ).toBeGreaterThanOrEqual(1.2);
    });
  }
);

describe("theme completeness", () => {
  it("defines the same token set in both themes", () => {
    const light = Object.keys(tokensOf(":root")).sort();
    const dark = Object.keys(tokensOf(".dark")).sort();
    // A token defined in only one theme falls back to the other theme's
    // value, which is exactly how a dark colour ends up on a light page.
    expect(dark).toEqual(light);
  });
});
