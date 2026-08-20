import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FindingCard } from "./FindingCard";
import type { FindingView } from "@/lib/findings";

const full: FindingView = {
  title: "Command Injection",
  detail: "subprocess call with a non-constant argv[0]",
  severity: "Critical",
  category: "security",
  fileName: "runner.py",
  filePath: "backend/app/runner.py",
  line: 42,
  whyItMatters: "Attackers could run unauthorized utilities on the server.",
  howToFix: "Use subprocess.run([...]) with shell=False.",
  confidence: 0.9,
  trustBoundary: "untrusted_input",
};

describe("FindingCard", () => {
  it("shows why a finding matters and how to fix it", () => {
    render(<FindingCard finding={full} />);

    expect(screen.getByText("Command Injection")).toBeInTheDocument();
    expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument();
    expect(screen.getByText(/Use subprocess.run/)).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("Untrusted input")).toBeInTheDocument();
    expect(screen.getByText("90% Match")).toBeInTheDocument();
    expect(screen.getByText("Line 42")).toBeInTheDocument();
  });

  it("renders no label at all for fields the analyzer did not produce", () => {
    const bare: FindingView = { title: "Unused import", severity: "Low" };

    render(<FindingCard finding={bare} />);

    expect(screen.getByText("Unused import")).toBeInTheDocument();
    // The failure this pins: a bare "Context:" or "How to fix" heading with
    // nothing beside it reads as a broken analyzer, not an absent field.
    expect(screen.queryByText(/Context:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/How to fix/)).not.toBeInTheDocument();
    expect(screen.queryByText(/% Match/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Line /)).not.toBeInTheDocument();
  });

  it("renders a zero confidence rather than swallowing it as falsy", () => {
    render(<FindingCard finding={{ title: "Guess", severity: "Info", confidence: 0 }} />);

    expect(screen.getByText("0% Match")).toBeInTheDocument();
  });
});
