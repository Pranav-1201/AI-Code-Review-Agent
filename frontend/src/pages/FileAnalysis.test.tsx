import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import FileAnalysis from "./FileAnalysis";

/**
 * J3. The page had no test file at all before this. These cover the two code
 * panes specifically: that the tab strip stopped claiming the engine
 * "improved" anything, and that a file with no suggested edits says which two
 * checks ran rather than rendering an unchanged file in silence.
 */

const WITH_EDITS = {
  name: "main.py",
  path: "src/main.py",
  language: "Python",
  score: 72,
  cyclomaticComplexity: 4,
  fileType: "production",
  issues: [],
  security: [],
  suggestions: [],
  explanation: "",
  original_code: 'def hello():\n    print("x")',
  improved_code: 'def hello() -> None:\n    """Hello."""\n    print("x")',
  patch: "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-def hello():\n+def hello() -> None:",
  refactorChanges: [
    { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
    { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
  ],
};

const WITHOUT_EDITS = {
  name: "clean.py",
  path: "src/clean.py",
  language: "Python",
  score: 95,
  cyclomaticComplexity: 1,
  fileType: "production",
  issues: [],
  security: [],
  suggestions: [],
  explanation: "",
  original_code: 'def done() -> None:\n    """Done."""\n    print("x")',
  improved_code: "",
  patch: null,
  refactorChanges: [],
};

function renderWith(files: unknown[]) {
  mockUseScan.mockReturnValue({
    currentReport: { files } as unknown as ScanReport,
  });
  return render(<FileAnalysis />);
}

describe("FileAnalysis code panes", () => {
  it("labels the pane for what the engine actually does", () => {
    renderWith([WITH_EDITS]);

    expect(screen.getByRole("tab", { name: "Suggested edits" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Improved" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Patch" })).not.toBeInTheDocument();
  });

  it("offers the what-changed tab for a file that has edits", () => {
    renderWith([WITH_EDITS]);

    expect(screen.getByRole("tab", { name: "What changed" })).toBeInTheDocument();
  });

  it("explains the empty state for a file with no suggested edits", () => {
    renderWith([WITHOUT_EDITS]);

    // Radix activates a tab on mousedown/focus, never on a synthetic click —
    // fireEvent.click leaves the original tab mounted and the assertion below
    // then fails against the wrong panel.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Suggested edits" }));

    expect(screen.getByText(/Nothing to suggest here/i)).toBeInTheDocument();
    expect(screen.getByText(/not a clean bill of health/i)).toBeInTheDocument();
  });

  it("hides the what-changed tab when there is neither a change list nor a diff", () => {
    renderWith([WITHOUT_EDITS]);

    expect(screen.queryByRole("tab", { name: "What changed" })).not.toBeInTheDocument();
  });
});
