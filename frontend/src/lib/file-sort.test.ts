/**
 * Backlog F3 — the per-file table sorted by score only, so every file
 * sharing a score sat in whatever order the backend emitted. On a healthy
 * repository that is most of the table.
 */
import { describe, it, expect } from "vitest";
import { sortFiles } from "./file-sort";

const files = [
  { path: "src/zeta.py", score: 80 },
  { path: "src/alpha.py", score: 80 },
  { path: "src/mid.py", score: 40 },
  { path: "src/file10.py", score: 80 },
  { path: "src/file2.py", score: 80 },
];

const paths = (rows: { path: string }[]) => rows.map((r) => r.path);

describe("sortFiles", () => {
  it("puts the worst score first", () => {
    expect(paths(sortFiles(files, "score"))[0]).toBe("src/mid.py");
  });

  it("breaks a score tie alphabetically instead of leaving it to input order", () => {
    const sorted = paths(sortFiles(files, "score")).slice(1);
    expect(sorted).toEqual([
      "src/alpha.py",
      "src/file2.py",
      "src/file10.py",
      "src/zeta.py",
    ]);
  });

  it("sorts file2 before file10, the way a reader expects", () => {
    const sorted = paths(sortFiles(files, "name"));
    expect(sorted.indexOf("src/file2.py")).toBeLessThan(
      sorted.indexOf("src/file10.py")
    );
  });

  it("sorts by name alone when asked, ignoring score", () => {
    expect(paths(sortFiles(files, "name"))).toEqual([
      "src/alpha.py",
      "src/file2.py",
      "src/file10.py",
      "src/mid.py",
      "src/zeta.py",
    ]);
  });

  it("is stable across repeated calls on the same input", () => {
    const once = paths(sortFiles(files, "score"));
    const twice = paths(sortFiles([...files].reverse(), "score"));
    expect(once).toEqual(twice);
  });

  it("does not mutate its input", () => {
    const original = paths(files);
    sortFiles(files, "name");
    expect(paths(files)).toEqual(original);
  });
});
