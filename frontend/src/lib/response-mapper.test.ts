import { describe, it, expect } from "vitest";
import { mapApiResponse, getDisplayName } from "./response-mapper";
import type { FileAnalysis } from "./types";

const REPO = "https://github.com/acme/widget";

describe("mapApiResponse — backend summary averages", () => {
  it("ignores a backend average of 0 and recomputes from production files", () => {
    // `??` alone would accept 0, because 0 is not nullish, and a degenerate
    // backend zero would then mask real production scores.
    const report = mapApiResponse(
      {
        summary: { average_quality_score: 0 },
        file_reports: [
          { file_path: "src/a.py", score: 80, file_type: "production" },
          { file_path: "src/b.py", score: 60, file_type: "production" },
        ],
      },
      REPO
    );

    expect(report.summary.avg_score).toBe(70);
  });

  it("trusts a positive backend average over the local computation", () => {
    const report = mapApiResponse(
      {
        summary: { average_quality_score: 42.5 },
        file_reports: [{ file_path: "src/a.py", score: 80, file_type: "production" }],
      },
      REPO
    );

    expect(report.summary.avg_score).toBe(42.5);
  });
});

describe("mapApiResponse — dependency advisories", () => {
  it("coerces a legacy bare CVE string into a Vulnerability object", () => {
    // Scans persisted before OSV enrichment stored bare id strings, and the
    // history page replays them. A raw string reaching the renderer is thrown
    // by React as an invalid child — this is what crashed the Dependency page.
    const report = mapApiResponse(
      {
        dependencies: [
          { name: "lodash", version: "4.17.20", vulnerabilities: ["CVE-2021-23337"] },
        ],
      },
      REPO
    );

    expect(report.dependencies[0].vulnerabilities).toEqual([
      { id: "CVE-2021-23337", summary: "", severity: "Unknown" },
    ]);
  });

  it("passes through advisory objects unchanged", () => {
    const report = mapApiResponse(
      {
        dependencies: [
          {
            name: "vitest",
            version: "3.2.4",
            vulnerabilities: [
              { id: "GHSA-5xrq-8626-4rwp", summary: "browser mode flaw", severity: "Critical" },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.dependencies[0].vulnerabilities).toEqual([
      { id: "GHSA-5xrq-8626-4rwp", summary: "browser mode flaw", severity: "Critical" },
    ]);
  });

  it("returns an empty list when the backend sends no vulnerabilities field", () => {
    const report = mapApiResponse(
      { dependencies: [{ name: "flask", version: "3.0.0" }] },
      REPO
    );

    expect(report.dependencies[0].vulnerabilities).toEqual([]);
  });
});

describe("mapApiResponse — field-name fallback chains", () => {
  it("prefers file_reports when it is non-empty", () => {
    const report = mapApiResponse(
      {
        file_reports: [{ file_path: "chosen.py" }],
        reports: [{ file_path: "ignored.py" }],
      },
      REPO
    );

    expect(report.files.map((f) => f.name)).toEqual(["chosen.py"]);
  });

  it("falls back to reports when file_reports is an empty array", () => {
    const report = mapApiResponse(
      {
        file_reports: [],
        reports: [{ file_path: "fallback.py" }],
      },
      REPO
    );

    expect(report.files.map((f) => f.name)).toEqual(["fallback.py"]);
  });

  it("prefers repository_summary over summary", () => {
    const report = mapApiResponse(
      {
        repository_summary: { files_analyzed: 7 },
        summary: { files_analyzed: 99 },
      },
      REPO
    );

    expect(report.summary.files).toBe(7);
  });
});

describe("mapApiResponse — severity mapping", () => {
  const issueWithSeverity = (severity: string) =>
    mapApiResponse(
      { file_reports: [{ file_path: "a.py", issues: [{ message: "m", severity }] }] },
      REPO
    ).files[0].issues[0].severity;

  it("maps moderate to Medium", () => {
    expect(issueWithSeverity("moderate")).toBe("Medium");
  });

  it("preserves Info rather than collapsing it to Low", () => {
    // Info is the calmest tier (e.g. a code-exec sink reachable only from
    // local operator input). Collapsing it would overstate exploitability.
    expect(issueWithSeverity("Info")).toBe("Info");
  });

  it("floors an unrecognised severity to Low", () => {
    expect(issueWithSeverity("bananas")).toBe("Low");
  });

  it("maps critical case-insensitively", () => {
    expect(issueWithSeverity("CRITICAL")).toBe("Critical");
  });
});

describe("mapApiResponse — production-only counting", () => {
  it("counts security findings from production files only", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "src/app.py",
            file_type: "production",
            security: [{ type: "sql_injection" }, { type: "weak_crypto" }],
          },
          {
            file_path: "tests/test_app.py",
            file_type: "test",
            security: [{ type: "hardcoded_secret" }, { type: "x" }, { type: "y" }],
          },
        ],
      },
      REPO
    );

    expect(report.summary.security_issues).toBe(2);
  });

  it("uses the backend total when it supplies one", () => {
    const report = mapApiResponse(
      {
        summary: { total_security_issues: 11 },
        file_reports: [
          { file_path: "src/app.py", file_type: "production", security: [{ type: "x" }] },
        ],
      },
      REPO
    );

    expect(report.summary.security_issues).toBe(11);
  });
});

describe("mapApiResponse — path handling", () => {
  it("normalises Windows backslashes to forward slashes", () => {
    const report = mapApiResponse(
      { file_reports: [{ file_path: "src\\pkg\\mod.py" }] },
      REPO
    );

    expect(report.files[0].path).toBe("src/pkg/mod.py");
    expect(report.files[0].name).toBe("mod.py");
  });

  it("derives repoName from the trailing URL segment", () => {
    const report = mapApiResponse({}, "https://github.com/acme/widget");
    expect(report.repoName).toBe("widget");
  });
});

describe("mapApiResponse — noise filtering", () => {
  it("drops the backend's 'no obvious structural issues' placeholder", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "clean.py",
            issues: [
              { message: "No obvious structural issues found." },
              { message: "Real problem here" },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.files[0].issues.map((i) => i.message)).toEqual(["Real problem here"]);
  });
});

describe("mapApiResponse — degenerate input", () => {
  it("maps an empty object without throwing", () => {
    const report = mapApiResponse({}, "");

    expect(report.files).toEqual([]);
    expect(report.dependencies).toEqual([]);
    expect(report.summary.files).toBe(0);
    expect(report.summary.avg_score).toBe(0);
    expect(report.repoName).toBe("repository");
    expect(typeof report.summary.healthScore).toBe("number");
  });
});

describe("getDisplayName", () => {
  const file = (path: string): FileAnalysis =>
    ({ name: path.split("/").pop()!, path } as FileAnalysis);

  it("returns the bare basename when it is unique", () => {
    const files = [file("src/alpha.py"), file("src/beta.py")];
    expect(getDisplayName(files[0], files)).toBe("alpha.py");
  });

  it("qualifies with the parent directory when basenames collide", () => {
    const files = [file("api/models.py"), file("web/models.py")];
    expect(getDisplayName(files[0], files)).toBe("api/models.py");
  });
});

describe("mapApiResponse — refactor changes", () => {
  it("maps the backend's snake_case change records", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "src/main.py",
            refactor_changes: [
              { kind: "docstring", target: "function", name: "hello", line: 2, line_count: 1 },
              { kind: "return_hint", target: "function", name: "hello", line: 1, line_count: 1 },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.files[0].refactorChanges).toEqual([
      { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
      { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
    ]);
  });

  it("drops malformed records at the boundary rather than rendering them", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "src/main.py",
            refactor_changes: [
              { kind: "wat", target: "function", name: "x", line: 1, line_count: 1 },
              { kind: "docstring", target: "module", name: "x", line: 1, line_count: 1 },
              { kind: "docstring", target: "function", name: "x", line: 0, line_count: 1 },
              { kind: "docstring", target: "function", name: "ok", line: 3, line_count: 2 },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.files[0].refactorChanges).toEqual([
      { kind: "docstring", target: "function", name: "ok", line: 3, lineCount: 2 },
    ]);
  });

  it("gives a scan recorded before change tracking an empty list, not undefined", () => {
    const report = mapApiResponse(
      { file_reports: [{ file_path: "src/main.py", patch: "--- a/x" }] },
      REPO
    );

    expect(report.files[0].refactorChanges).toEqual([]);
  });
});
