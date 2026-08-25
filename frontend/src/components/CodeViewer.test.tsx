import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CodeViewer } from "./CodeViewer";

const CODE = ["def hello():", '    """Hello."""', '    print("x")'].join("\n");

describe("CodeViewer", () => {
  it("numbers every line from 1", () => {
    render(<CodeViewer code={CODE} />);

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("marks exactly the lines it is given, and no others", () => {
    const { container } = render(
      <CodeViewer code={CODE} highlightedLines={new Set([2])} />
    );

    const marked = container.querySelectorAll('[data-changed="true"]');

    expect(marked).toHaveLength(1);
    expect(marked[0].textContent).toContain('"""Hello."""');
  });

  it("does not rely on colour alone to say a line changed", () => {
    render(<CodeViewer code={CODE} highlightedLines={new Set([2])} />);

    // One announced marker per changed line, for anyone not seeing the tint.
    expect(screen.getAllByText("Changed line.")).toHaveLength(1);
  });

  it("colours a unified diff by its leading character", () => {
    const { container } = render(
      <CodeViewer code={"@@ -1 +1 @@\n-old\n+new"} isPatch />
    );

    expect(container.textContent).toContain("+new");
    expect(container.querySelectorAll('[data-changed="true"]')).toHaveLength(0);
  });

  it("says so when there is nothing to show", () => {
    render(<CodeViewer code="" />);

    expect(screen.getByText("Not available")).toBeInTheDocument();
  });
});
