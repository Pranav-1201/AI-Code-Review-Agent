import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import AISuggestions from "./AISuggestions";

describe("AISuggestions", () => {
  it("renders the explanation as markdown instead of printing its asterisks", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "backend/app/runner.py",
            explanation: "Reads a config file.\n\n**Suggested improvements (unapplied):** Added docstrings to 2 function(s).",
            explanationSource: "deterministic",
            suggestions: [],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<AISuggestions />);

    expect(screen.getByText("Suggested improvements (unapplied):")).toBeInTheDocument();
    expect(screen.queryByText(/\*\*Suggested improvements/)).not.toBeInTheDocument();
  });

  it("labels whether the prose was written by rules or by the LLM layer", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          { name: "a.py", path: "a.py", explanation: "Parses argv.", explanationSource: "deterministic", suggestions: [] },
        ],
      } as unknown as ScanReport,
    });

    render(<AISuggestions />);

    expect(screen.getByText("Rule-based")).toBeInTheDocument();
  });
});
