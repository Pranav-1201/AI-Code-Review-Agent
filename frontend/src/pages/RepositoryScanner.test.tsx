/**
 * F10 — the scanner must say which languages it analyses before a user
 * spends a clone finding out. B6 gives them the answer afterwards; this is
 * the half that gives it beforehand.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import RepositoryScanner from "./RepositoryScanner";
import { SUPPORTED_LANGUAGES } from "@/lib/languages";

vi.mock("@/context/ScanContext", () => ({
  useScan: () => ({
    triggerScan: vi.fn(),
    loadDemo: vi.fn(),
    isScanning: false,
    scanError: null,
    scanStatus: null,
  }),
}));

function renderScanner() {
  return render(
    <MemoryRouter>
      <RepositoryScanner />
    </MemoryRouter>
  );
}

describe("RepositoryScanner — stating the analysis boundary", () => {
  it("names every supported language on the page", () => {
    renderScanner();
    for (const language of SUPPORTED_LANGUAGES) {
      expect(
        screen.getByText(language, { exact: true })
      ).toBeInTheDocument();
    }
  });

  it("says other languages are skipped rather than implying full coverage", () => {
    renderScanner();
    expect(
      screen.getByText(/other languages are skipped/i)
    ).toBeInTheDocument();
  });
});
