import type { FileAnalysis, FileIssue, SecurityVulnerability, Severity } from "./types";

/**
 * One finding, normalized for display.
 *
 * The backend produces two differently-shaped finding objects — security
 * vulnerabilities and file issues — that a reader experiences as the same kind
 * of thing. This is the shape the UI renders, so `FindingCard` never has to
 * know which of the two it was handed.
 *
 * Every field beyond title and severity is optional and absent means absent:
 * consumers render nothing at all rather than an empty label.
 */
export interface FindingView {
  title: string;
  detail?: string;
  severity: Severity;
  category?: string;
  fileName?: string;
  filePath?: string;
  line?: number;
  whyItMatters?: string;
  howToFix?: string;
  confidence?: number;
  trustBoundary?: string;
  /** Numbered source lines around the finding. Absent when unknown. */
  snippet?: string;
}

/**
 * The shape the backend emitted before J2: "Line 42" or
 * "Line 481 indicates: Command Injection". 523 cached scans still contain it
 * and ScanHistory replays them, so it is filtered here rather than rendered.
 * A real snippet is line-numbered as "42: <code>" and never matches this.
 */
const LEGACY_SNIPPET = /^Line \d+( indicates: .+)?$/;

function cleanSnippet(raw?: string): string | undefined {
  if (!raw) return undefined;
  const trimmed = raw.trim();
  if (!trimmed || LEGACY_SNIPPET.test(trimmed)) return undefined;
  return raw;
}

export function fromSecurityVulnerability(v: SecurityVulnerability): FindingView {
  return {
    title: v.type,
    detail: v.description,
    severity: v.severity,
    category: "security",
    fileName: v.file ? v.file.split("/").pop() || v.file : undefined,
    filePath: v.file,
    line: v.line,
    whyItMatters: v.why_it_matters,
    // `recommendation` predates `how_to_fix`; reports in the wild carry either.
    howToFix: v.how_to_fix ?? v.recommendation,
    confidence: v.confidence,
    trustBoundary: v.trust_boundary,
    snippet: cleanSnippet(v.snippet),
  };
}

export function fromFileIssue(i: FileIssue, file: FileAnalysis): FindingView {
  return {
    title: i.message,
    severity: i.severity,
    category: i.category,
    fileName: file.name,
    filePath: file.path,
    line: i.line,
    whyItMatters: i.why_it_matters,
    howToFix: i.how_to_fix,
    confidence: i.confidence,
    trustBoundary: i.trust_boundary,
    snippet: cleanSnippet(i.snippet),
  };
}
