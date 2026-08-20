import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import IssueExplorer from "./IssueExplorer";

describe("IssueExplorer", () => {
  it("gives each issue its context and remediation, not just a message", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "backend/app/runner.py",
            fileType: "production",
            security: [],
            issues: [
              {
                message: "Function exceeds the complexity budget",
                severity: "Medium",
                category: "maintainability",
                line: 7,
                why_it_matters: "Complex functions are harder to test and change safely.",
                how_to_fix: "Extract the branching into helper functions.",
              },
            ],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<IssueExplorer />);

    expect(screen.getByText("Function exceeds the complexity budget")).toBeInTheDocument();
    expect(screen.getByText(/Complex functions are harder to test/)).toBeInTheDocument();
    expect(screen.getByText(/Extract the branching/)).toBeInTheDocument();
  });
});
