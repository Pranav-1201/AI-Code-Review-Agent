import { describe, expect, it } from "vitest";

import { fromFileIssue, fromSecurityVulnerability } from "./findings";
import type { FileAnalysis, FileIssue, SecurityVulnerability } from "./types";

const vuln: SecurityVulnerability = {
  type: "Command Injection",
  severity: "Critical",
  description: "subprocess call with a non-constant argv[0]",
  file: "backend/app/runner.py",
  line: 42,
  recommendation: "Pass a list, not a shell string.",
  why_it_matters: "Running external commands with untrusted input can let attackers run unauthorized utilities on the server.",
  how_to_fix: "Use subprocess.run([...]) with shell=False.",
  confidence: 0.9,
  trust_boundary: "untrusted_input",
};

const issue: FileIssue = {
  message: "Function exceeds the complexity budget",
  severity: "Medium",
  category: "maintainability",
  line: 7,
  why_it_matters: "Complex functions are harder to test and change safely.",
  how_to_fix: "Extract the branching into helper functions.",
  confidence: 0.5,
};

const file = { name: "runner.py", path: "backend/app/runner.py" } as FileAnalysis;

describe("fromSecurityVulnerability", () => {
  it("carries the explanation fields the pages need", () => {
    const view = fromSecurityVulnerability(vuln);

    expect(view.title).toBe("Command Injection");
    expect(view.detail).toBe("subprocess call with a non-constant argv[0]");
    expect(view.severity).toBe("Critical");
    expect(view.category).toBe("security");
    expect(view.whyItMatters).toBe(vuln.why_it_matters);
    expect(view.confidence).toBe(0.9);
    expect(view.trustBoundary).toBe("untrusted_input");
  });

  it("prefers how_to_fix over the older recommendation field", () => {
    expect(fromSecurityVulnerability(vuln).howToFix).toBe("Use subprocess.run([...]) with shell=False.");
  });

  it("falls back to recommendation when how_to_fix is absent", () => {
    const { how_to_fix, ...withoutFix } = vuln;

    expect(fromSecurityVulnerability(withoutFix).howToFix).toBe("Pass a list, not a shell string.");
  });

  it("leaves absent fields undefined rather than inventing empty strings", () => {
    const bare: SecurityVulnerability = {
      type: "Weak Hash",
      severity: "Low",
      description: "md5 used for a digest",
      file: "util.py",
    };
    const view = fromSecurityVulnerability(bare);

    expect(view.whyItMatters).toBeUndefined();
    expect(view.howToFix).toBeUndefined();
    expect(view.confidence).toBeUndefined();
    expect(view.trustBoundary).toBeUndefined();
    expect(view.line).toBeUndefined();
  });

  it("shortens the file path to a basename for display but keeps the full path", () => {
    const view = fromSecurityVulnerability(vuln);

    expect(view.fileName).toBe("runner.py");
    expect(view.filePath).toBe("backend/app/runner.py");
  });
});

describe("fromFileIssue", () => {
  it("uses the message as the title and the issue's own category", () => {
    const view = fromFileIssue(issue, file);

    expect(view.title).toBe("Function exceeds the complexity budget");
    expect(view.detail).toBeUndefined();
    expect(view.category).toBe("maintainability");
    expect(view.fileName).toBe("runner.py");
    expect(view.filePath).toBe("backend/app/runner.py");
    expect(view.whyItMatters).toBe(issue.why_it_matters);
    expect(view.howToFix).toBe("Extract the branching into helper functions.");
  });

  it("leaves absent fields undefined", () => {
    const bare: FileIssue = { message: "Unused import", severity: "Low", category: "style" };
    const view = fromFileIssue(bare, file);

    expect(view.whyItMatters).toBeUndefined();
    expect(view.howToFix).toBeUndefined();
    expect(view.confidence).toBeUndefined();
    expect(view.line).toBeUndefined();
  });
});
