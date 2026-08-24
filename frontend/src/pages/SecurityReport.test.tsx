import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import SecurityReport from "./SecurityReport";

function reportWith(files: Partial<ScanReport["files"][number]>[]): ScanReport {
  return { files } as ScanReport;
}

describe("SecurityReport", () => {
  // setup.ts stubs scrollIntoView once on the prototype for the whole run, so
  // call counts would otherwise accumulate across tests in this file.
  beforeEach(() => {
    vi.mocked(Element.prototype.scrollIntoView).mockClear();
  });

  it("explains why each finding matters and how to fix it", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            {
              type: "Command Injection",
              severity: "Critical",
              description: "subprocess call with a non-constant argv[0]",
              file: "backend/app/runner.py",
              line: 42,
              why_it_matters: "Attackers could run unauthorized utilities on the server.",
              how_to_fix: "Use subprocess.run([...]) with shell=False.",
              confidence: 0.9,
              trust_boundary: "untrusted_input",
            },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    expect(screen.getByText("Command Injection")).toBeInTheDocument();
    expect(screen.getByText("90% Match")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Command Injection/ }));

    expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument();
    expect(screen.getByText(/Use subprocess.run/)).toBeInTheDocument();
  });

  it("scopes the report to production files and accounts for the rest", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "app/runner.py",
            fileType: "production",
            security: [{ type: "Command Injection", severity: "Critical", description: "d", file: "app/runner.py" }],
          },
          {
            name: "test_runner.py",
            path: "tests/test_runner.py",
            fileType: "test",
            security: [
              { type: "Hardcoded Secret", severity: "High", description: "d", file: "tests/test_runner.py" },
              { type: "Weak Hash", severity: "Low", description: "d", file: "tests/test_runner.py" },
            ],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<SecurityReport />);

    expect(screen.getByText(/1 finding in production files/)).toBeInTheDocument();
    // Scoped, not hidden — a reader must be able to reconcile this with the tile.
    expect(screen.getByText(/2 further findings in test\/non-code files/)).toBeInTheDocument();
    expect(screen.queryByText("Hardcoded Secret")).not.toBeInTheDocument();
  });

  it("groups findings by severity and omits groups with nothing in them", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Command Injection", severity: "Critical", description: "d", file: "runner.py", line: 1 },
            { type: "Weak Hash", severity: "Low", description: "d", file: "runner.py", line: 2 },
            { type: "Local Exec", severity: "Info", description: "d", file: "runner.py", line: 3 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    expect(screen.getByRole("heading", { name: /Critical/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Low/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Info/ })).toBeInTheDocument();
    // Nothing is High or Medium here, so neither heading exists.
    expect(screen.queryByRole("heading", { name: /High/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: /Medium/ })).toBeNull();
  });

  it("counts Info findings on a tier, so the tiers sum to the headline", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Local Exec", severity: "Info", description: "d", file: "runner.py", line: 3 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    const tier = screen.getByRole("button", { name: /1 Info/ });
    expect(tier).toBeInTheDocument();
  });

  it("scrolls to a group and moves focus to its heading when the tier is activated", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Command Injection", severity: "Critical", description: "d", file: "runner.py", line: 1 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    fireEvent.click(screen.getByRole("button", { name: /1 Critical/ }));

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    // Scrolling alone leaves a keyboard/screen-reader user where they were —
    // the heading must actually receive focus for the tier to act as navigation.
    expect(screen.getByRole("heading", { name: /Critical/ })).toHaveFocus();
  });

  it("dispatches to the activated tier's own group, not always the first one", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Command Injection", severity: "Critical", description: "d", file: "runner.py", line: 1 },
            { type: "Weak Hash", severity: "Medium", description: "d", file: "runner.py", line: 2 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    // Activate the second tier, not the first — a hardcoded `jumpTo("severity-critical")`
    // would still pass the single-tier test above but fail this one.
    fireEvent.click(screen.getByRole("button", { name: /1 Medium/ }));

    expect(screen.getByRole("heading", { name: /Medium/ })).toHaveFocus();
    expect(screen.getByRole("heading", { name: /Critical/ })).not.toHaveFocus();
  });

  it("renders a zero tier as text, not a control", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Command Injection", severity: "Critical", description: "d", file: "runner.py", line: 1 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    // Four tiers are empty; none of them is a button.
    expect(screen.queryByRole("button", { name: /0 High/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /0 Info/ })).toBeNull();
  });
});
