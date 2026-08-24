import { fireEvent, render, screen } from "@testing-library/react";
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
  snippet: "41:     cmd = request.args.get(\"cmd\")\n42:     subprocess.run(cmd, shell=True)",
  confidence: 0.9,
  trustBoundary: "untrusted_input",
};

describe("FindingCard", () => {
  it("is collapsed by default, showing identity but not the explanation", () => {
    render(<FindingCard finding={full} />);

    // Visible while collapsed: what it is, how bad, and where.
    expect(screen.getByText("Command Injection")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("runner.py")).toBeInTheDocument();
    expect(screen.getByText("Line 42")).toBeInTheDocument();
    expect(screen.getByText("Untrusted input")).toBeInTheDocument();
    expect(screen.getByText("90% Match")).toBeInTheDocument();

    // Hidden until asked for.
    expect(screen.queryByText(/Attackers could run unauthorized utilities/)).toBeNull();
    expect(screen.queryByText(/Use subprocess.run/)).toBeNull();
  });

  it("exposes an expand control that reports its state", () => {
    render(<FindingCard finding={full} />);

    const trigger = screen.getByRole("button", { name: /Command Injection/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("reveals the explanation and the snippet when expanded", () => {
    render(<FindingCard finding={full} />);

    fireEvent.click(screen.getByRole("button", { name: /Command Injection/ }));

    expect(screen.getByRole("button", { name: /Command Injection/ }))
      .toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument();
    expect(screen.getByText(/Use subprocess.run/)).toBeInTheDocument();
    expect(screen.getByText(/subprocess.run\(cmd, shell=True\)/)).toBeInTheDocument();
  });

  it("renders no expand control when there is nothing to expand", () => {
    render(<FindingCard finding={{ title: "Dead import", severity: "Low" }} />);

    expect(screen.getByText("Dead import")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows a confidence of 0 rather than hiding it", () => {
    render(<FindingCard finding={{ ...full, confidence: 0 }} />);

    expect(screen.getByText("0% Match")).toBeInTheDocument();
  });
});
