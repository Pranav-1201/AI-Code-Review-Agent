import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SuggestedEditsPane } from "./SuggestedEditsPane";
import type { RefactorChange } from "@/lib/types";

const ORIGINAL = 'def hello():\n    print("x")';
const IMPROVED = 'def hello() -> None:\n    """Hello."""\n    print("x")';

const CHANGES: RefactorChange[] = [
  { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
  { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
];

describe("SuggestedEditsPane", () => {
  it("names what was checked instead of implying a clean bill of health", () => {
    render(
      <SuggestedEditsPane
        improvedCode={ORIGINAL}
        originalCode={ORIGINAL}
        changes={[]}
        language="python"
      />
    );

    expect(screen.getByText(/Nothing to suggest here/i)).toBeInTheDocument();
    expect(screen.getByText(/no docstring/i)).toBeInTheDocument();
    expect(screen.getByText(/not a clean bill of health/i)).toBeInTheDocument();
  });

  it("treats an empty improved file as nothing to suggest", () => {
    render(
      <SuggestedEditsPane improvedCode="" originalCode={ORIGINAL} changes={[]} language="python" />
    );

    expect(screen.getByText(/Nothing to suggest here/i)).toBeInTheDocument();
  });

  it("shows the full improved file, not just the changed parts", () => {
    const { container } = render(
      <SuggestedEditsPane improvedCode={IMPROVED} originalCode={ORIGINAL} changes={CHANGES} />
    );

    expect(container.textContent).toContain('print("x")');
  });

  it("highlights every line a change claims and nothing else", () => {
    const { container } = render(
      <SuggestedEditsPane improvedCode={IMPROVED} originalCode={ORIGINAL} changes={CHANGES} />
    );

    const marked = Array.from(container.querySelectorAll('[data-changed="true"]'));

    expect(marked).toHaveLength(2);
    expect(marked[0].textContent).toContain("-> None");
    expect(marked[1].textContent).toContain('"""Hello."""');
  });

  it("spans every line of a multi-line change", () => {
    const improved = ["def add(a, b):", '    """', "    Add.", '    """', "    return a + b"].join("\n");
    const changes: RefactorChange[] = [
      { kind: "docstring", target: "function", name: "add", line: 2, lineCount: 3 },
    ];

    const { container } = render(
      <SuggestedEditsPane improvedCode={improved} originalCode="def add(a, b):" changes={changes} />
    );

    expect(container.querySelectorAll('[data-changed="true"]')).toHaveLength(3);
  });

  it("counts the highlighted lines for the reader", () => {
    render(<SuggestedEditsPane improvedCode={IMPROVED} originalCode={ORIGINAL} changes={CHANGES} />);

    expect(screen.getByText(/2 changed lines highlighted/i)).toBeInTheDocument();
  });
  it("does not claim the Python checks ran against a file they cannot parse", () => {
    render(
      <SuggestedEditsPane
        improvedCode=""
        originalCode="export const x = 1;"
        changes={[]}
        language="typescript"
      />
    );

    // The transforms go through ast.parse, so on a non-Python file they return
    // nothing WITHOUT looking — which is not the same as finding no gaps.
    expect(screen.queryByText(/This file has neither gap/i)).not.toBeInTheDocument();
    expect(screen.getByText(/parse Python/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing\s+here was examined/i)).toBeInTheDocument();
  });

  it("still shows the improved code for a scan recorded before change tracking", () => {
    // Pre-J3 scans carry improved_code and a patch but no change records.
    // Claiming "nothing to suggest" would contradict the diff shown beside it,
    // and would silently drop the improved view those scans always had.
    render(
      <SuggestedEditsPane improvedCode={IMPROVED} originalCode={ORIGINAL} changes={[]} language="python" />
    );

    expect(screen.queryByText(/Nothing to suggest here/i)).not.toBeInTheDocument();
    expect(screen.getByText(/before change tracking/i)).toBeInTheDocument();
    expect(screen.getByText(/have not been applied/i)).toBeInTheDocument();
  });

  it("never counts a highlight past the end of the file", () => {
    const changes: RefactorChange[] = [
      { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 500 },
    ];

    const { container } = render(
      <SuggestedEditsPane
        improvedCode={IMPROVED}
        originalCode={ORIGINAL}
        changes={changes}
        language="python"
      />
    );

    // IMPROVED is 3 lines, so a 500-line span can mark at most lines 2 and 3.
    expect(container.querySelectorAll('[data-changed="true"]')).toHaveLength(2);
    expect(screen.getByText(/2 changed lines highlighted/i)).toBeInTheDocument();
  });
});
