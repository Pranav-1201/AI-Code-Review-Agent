import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WhatChangedPane } from "./WhatChangedPane";
import type { RefactorChange } from "@/lib/types";

const PATCH = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-def hello():\n+def hello() -> None:";

const CHANGES: RefactorChange[] = [
  { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
  { kind: "docstring", target: "function", name: "world", line: 6, lineCount: 1 },
  { kind: "docstring", target: "class", name: "Widget", line: 12, lineCount: 1 },
  { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
];

describe("WhatChangedPane", () => {
  it("counts each kind of edit in prose", () => {
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    expect(screen.getByText(/2 functions and 1 class/i)).toBeInTheDocument();
    expect(screen.getByText(/return hints to 1 function\b/i)).toBeInTheDocument();
  });

  it("names each edited symbol and where it landed", () => {
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    expect(screen.getByText(/Widget/)).toBeInTheDocument();
    expect(screen.getByText(/line 12/i)).toBeInTheDocument();
  });

  it("says the edits are not applied", () => {
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    expect(screen.getByText(/have not been applied/i)).toBeInTheDocument();
  });

  it("keeps the raw diff, collapsed", () => {
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    const trigger = screen.getByRole("button", { name: /raw diff/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/\+def hello\(\) -> None:/)).toBeInTheDocument();
  });

  it("explains a scan recorded before change tracking, and shows its diff", () => {
    render(<WhatChangedPane changes={[]} patch={PATCH} />);

    expect(screen.getByText(/before change tracking/i)).toBeInTheDocument();
    expect(screen.getByText(/\+def hello\(\) -> None:/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /raw diff/i })).not.toBeInTheDocument();
  });

  it("renders nothing when there is neither a change list nor a diff", () => {
    const { container } = render(<WhatChangedPane changes={[]} patch={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
