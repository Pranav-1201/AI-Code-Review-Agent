import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import SecurityReport from "./SecurityReport";

function reportWith(files: Partial<ScanReport["files"][number]>[]): ScanReport {
  return { files } as ScanReport;
}

describe("SecurityReport", () => {
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
    // These three are computed by the backend today and rendered by no page.
    expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument();
    expect(screen.getByText(/Use subprocess.run/)).toBeInTheDocument();
    expect(screen.getByText("90% Match")).toBeInTheDocument();
  });
});
