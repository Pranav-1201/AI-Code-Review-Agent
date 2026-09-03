/**
 * F14 — the report surfaces two different scores and never says how they
 * relate. `health_score` (53 on this repository) is a weighted composite;
 * `average_quality_score` (90.56) is one of its four inputs. Both are
 * correct, and side by side without explanation they read as a bug.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import HealthScore from "./HealthScore";
import type { ScanReport } from "@/lib/types";

const report = {
  id: "s1",
  repoUrl: "https://github.com/acme/widget",
  repoName: "widget",
  timestamp: new Date().toISOString(),
  files: [],
  dependencies: [],
  summary: {
    files: 10,
    files_with_issues: 2,
    avg_score: 90.56,
    security_issues: 0,
    totalLines: 1000,
    languages: [],
    healthScore: 53,
    avg_documentation_coverage: 12,
    avg_cyclomatic_complexity: 9,
    production_files: 8,
    test_files: 2,
  },
} as unknown as ScanReport;

vi.mock("@/context/ScanContext", () => ({
  useScan: () => ({ currentReport: report }),
}));

describe("HealthScore — explaining the composite", () => {
  it("states that the overall score is a weighted blend of the four below", () => {
    render(<HealthScore />);
    expect(
      screen.getByText(/weighted blend of the four dimensions below/i)
    ).toBeInTheDocument();
  });

  it("shows each dimension's weight, so 91 maintainability and 53 overall reconcile", () => {
    render(<HealthScore />);
    expect(screen.getByText("35% of overall")).toBeInTheDocument(); // Maintainability
    expect(screen.getByText("25% of overall")).toBeInTheDocument(); // Security
    expect(screen.getAllByText("20% of overall")).toHaveLength(2);  // Docs, Simplicity
  });

  it("calls the complexity dimension Simplicity, not Performance", () => {
    // The score is 100 - min(avgCC * 3, 80). That measures complexity, not
    // performance, and the backend already names it simplicity_score.
    render(<HealthScore />);
    expect(screen.getByText("Simplicity")).toBeInTheDocument();
    expect(screen.queryByText("Performance")).not.toBeInTheDocument();
  });
});
