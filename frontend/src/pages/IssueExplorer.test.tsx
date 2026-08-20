import { render, screen, fireEvent } from "@testing-library/react";
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

  it("searches by file name, filtering out issues from other files", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "backend/handlers/runner_service.py",
            fileType: "production",
            security: [],
            issues: [{ message: "Issue in runner", severity: "Medium", category: "maintainability", line: 1 }],
          },
          {
            name: "auth.py",
            path: "backend/handlers/auth_service.py",
            fileType: "production",
            security: [],
            issues: [{ message: "Issue in auth", severity: "Medium", category: "maintainability", line: 1 }],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<IssueExplorer />);

    expect(screen.getByText("Issue in runner")).toBeInTheDocument();
    expect(screen.getByText("Issue in auth")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search issues..."), { target: { value: "auth.py" } });

    expect(screen.getByText("Issue in auth")).toBeInTheDocument();
    expect(screen.queryByText("Issue in runner")).not.toBeInTheDocument();
  });

  it("filters by a non-default severity, hiding issues of other severities", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "backend/app/runner.py",
            fileType: "production",
            security: [],
            issues: [
              { message: "High severity issue", severity: "High", category: "security", line: 1 },
              { message: "Low severity issue", severity: "Low", category: "style", line: 2 },
            ],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<IssueExplorer />);

    expect(screen.getByText("High severity issue")).toBeInTheDocument();
    expect(screen.getByText("Low severity issue")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("combobox")[0]);
    fireEvent.click(screen.getByRole("option", { name: "High" }));

    expect(screen.getByText("High severity issue")).toBeInTheDocument();
    expect(screen.queryByText("Low severity issue")).not.toBeInTheDocument();
  });
});
