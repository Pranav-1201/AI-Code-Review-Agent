import type { FileAnalysis } from "./types";

export type FileSortMode = "score" | "name";

export const FILE_SORT_MODES: { value: FileSortMode; label: string }[] = [
  { value: "score", label: "Worst score first" },
  { value: "name", label: "Name (A–Z)" },
];

/**
 * Order the per-file table (backlog F3).
 *
 * Both modes break ties on path, so the table does not reshuffle between two
 * renders of the same scan. The previous sort was score-ascending only, which
 * left every file sharing a score — and on a healthy repository that is most
 * of them — in whatever order the backend happened to emit.
 *
 * Path comparison uses localeCompare with numeric collation so `file2.py`
 * sorts before `file10.py`, which is what a reader scanning a list expects.
 */
export function sortFiles<T extends Pick<FileAnalysis, "path" | "score">>(
  files: T[],
  mode: FileSortMode
): T[] {
  const byPath = (a: T, b: T) =>
    a.path.localeCompare(b.path, undefined, {
      numeric: true,
      sensitivity: "base",
    });

  return [...files].sort((a, b) => {
    if (mode === "name") return byPath(a, b);
    return a.score - b.score || byPath(a, b);
  });
}
