import { ScanReport, ScanHistoryItem, TestResult } from "./types";

/**
 * Static demo report used by the offline demo mode (ScanContext.loadDemo).
 * It is a fully-formed ScanReport so it drives every page without a backend
 * running. Values are illustrative but internally consistent, and deliberately
 * exercise the trust-boundary and explanation-source badges (Chunk 6 / commit A)
 * so the demo reflects the current UI.
 */
export const mockScanReport: ScanReport = {
  id: "scan-001",
  repoUrl: "https://github.com/example/python-webapp",
  repoName: "python-webapp",
  timestamp: new Date().toISOString(),
  summary: {
    files: 12,
    files_with_issues: 8,
    avg_score: 72.5,
    security_issues: 3,
    totalLines: 4280,
    languages: [
      { name: "Python", percentage: 68, color: "hsl(210, 80%, 55%)" },
      { name: "JavaScript", percentage: 18, color: "hsl(50, 90%, 55%)" },
      { name: "HTML", percentage: 9, color: "hsl(15, 80%, 55%)" },
      { name: "CSS", percentage: 5, color: "hsl(262, 80%, 60%)" },
    ],
    healthScore: 73,
    avg_documentation_coverage: 56,
    avg_cyclomatic_complexity: 11.7,
    production_files: 6,
    test_files: 0,
    maintainability_warnings: [
      { file: "src/auth.py", type: "complexity", message: "High cyclomatic complexity (22) — consider decomposition", severity: "High" },
      { file: "src/main.py", type: "cohesion", message: "process_data mixes validation and transformation concerns", severity: "Medium" },
    ],
  },
  files: [
    {
      name: "main.py",
      path: "src/main.py",
      score: 58,
      language: "python",
      linesOfCode: 245,
      cyclomaticComplexity: 18,
      maxCyclomaticComplexity: 18,
      maxNestingDepth: 2,
      branches: 12,
      fileType: "production",
      documentationCoverage: 35,
      issues: [
        { message: "Nested loops detected — O(n²) complexity", severity: "High", category: "performance", line: 42 },
        { message: "Function `process_data` exceeds 50 lines", severity: "Medium", category: "maintainability", line: 15 },
        { message: "Missing type hints on public function", severity: "Low", category: "style", line: 8 },
      ],
      security: [
        { type: "SQL Injection", severity: "Critical", description: "Raw SQL query built with string interpolation from a request parameter", file: "src/main.py", line: 67, recommendation: "Use parameterized queries", trust_boundary: "untrusted_input" },
      ],
      complexity: "O(n²)",
      explanation: "The main entry point has high cyclomatic complexity due to nested conditional logic and loops. The process_data function handles too many responsibilities, making it hard to test and maintain.",
      explanationSource: "llm",
      suggestions: [
        "Extract inner loop into a separate function",
        "Use list comprehension instead of nested loops",
        "Add type hints to all public functions",
        "Split process_data into smaller, focused functions",
      ],
      improved_code: `def process_data(items: list[dict]) -> list[dict]:
    """Process and validate input data items."""
    validated = [validate_item(item) for item in items]
    return [transform(v) for v in validated if v.is_valid]

def validate_item(item: dict) -> ValidatedItem:
    """Validate a single data item."""
    return ValidatedItem(item)`,
      original_code: `def process_data(items):
    result = []
    for item in items:
        if item:
            for key in item:
                if key in VALID_KEYS:
                    result.append(item[key])
    return result`,
      patch: `--- a/src/main.py
+++ b/src/main.py
@@ -15,10 +15,8 @@
-def process_data(items):
-    result = []
-    for item in items:
-        if item:
-            for key in item:
-                if key in VALID_KEYS:
-                    result.append(item[key])
-    return result
+def process_data(items: list[dict]) -> list[dict]:
+    validated = [validate_item(item) for item in items]
+    return [transform(v) for v in validated if v.is_valid]`,
      // Line 2 and line 7 of `improved_code` above are the two inserted
      // docstrings — counted against that string, not guessed. The demo is the
      // only place this feature is seen without running a scan, so a highlight
      // pointing at the wrong line would be worse than no highlight. The file
      // at the bottom of this list deliberately has no changes, so the demo
      // carries the empty state too.
      refactorChanges: [
        { kind: "docstring", target: "function", name: "process_data", line: 2, lineCount: 1 },
        { kind: "docstring", target: "function", name: "validate_item", line: 7, lineCount: 1 },
      ],
      duplicates: [{ file: "src/utils/helpers.py", similarity: 78 }],
    },
    {
      name: "auth.py",
      path: "src/auth.py",
      score: 45,
      language: "python",
      linesOfCode: 180,
      cyclomaticComplexity: 22,
      maxCyclomaticComplexity: 22,
      maxNestingDepth: 1,
      branches: 15,
      fileType: "production",
      documentationCoverage: 20,
      issues: [
        { message: "Hardcoded secret key detected", severity: "Critical", category: "security", line: 12, trust_boundary: "internal" },
        { message: "Password stored in plaintext", severity: "Critical", category: "security", line: 34 },
        { message: "Missing rate limiting on login endpoint", severity: "High", category: "security", line: 45 },
        { message: "Broad exception handler catches all errors", severity: "Medium", category: "logic", line: 78 },
      ],
      security: [
        { type: "Hardcoded Credentials", severity: "Critical", description: "SECRET_KEY is hardcoded in source", file: "src/auth.py", line: 12, recommendation: "Use environment variables", trust_boundary: "internal" },
        { type: "Plaintext Password", severity: "Critical", description: "Passwords stored without hashing", file: "src/auth.py", line: 34, recommendation: "Use bcrypt or argon2" },
      ],
      complexity: "O(n)",
      explanation: "Critical security vulnerabilities found. The authentication module stores secrets and passwords insecurely, creating significant attack vectors.",
      explanationSource: "llm",
      suggestions: [
        "Move SECRET_KEY to environment variables",
        "Hash passwords with bcrypt before storage",
        "Add rate limiting middleware",
        "Use specific exception types instead of bare except",
      ],
      improved_code: `import os
from passlib.hash import bcrypt

SECRET_KEY = os.environ["SECRET_KEY"]

def hash_password(password: str) -> str:
    return bcrypt.hash(password)`,
      original_code: `SECRET_KEY = "my-super-secret-key-123"

def store_password(password):
    db.save({"password": password})`,
      patch: null,
      duplicates: [],
    },
    {
      name: "database.py",
      path: "src/database.py",
      score: 82,
      language: "python",
      linesOfCode: 120,
      cyclomaticComplexity: 8,
      maxCyclomaticComplexity: 8,
      maxNestingDepth: 0,
      branches: 5,
      fileType: "production",
      documentationCoverage: 65,
      issues: [
        { message: "Connection pool not configured", severity: "Medium", category: "performance", line: 15 },
        { message: "Missing retry logic for transient failures", severity: "Low", category: "logic", line: 30 },
      ],
      security: [],
      complexity: "O(1)",
      explanation: "Database module is well-structured but could benefit from connection pooling and retry logic for production reliability.",
      explanationSource: "deterministic",
      suggestions: ["Configure connection pooling", "Add retry decorator for transient failures"],
      improved_code: `from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(DB_URL, poolclass=QueuePool, pool_size=5)`,
      original_code: `from sqlalchemy import create_engine

engine = create_engine(DB_URL)`,
      patch: null,
      duplicates: [],
    },
    {
      name: "api_routes.py",
      path: "src/api_routes.py",
      score: 71,
      language: "python",
      linesOfCode: 310,
      cyclomaticComplexity: 14,
      maxCyclomaticComplexity: 14,
      maxNestingDepth: 1,
      branches: 9,
      fileType: "production",
      documentationCoverage: 45,
      issues: [
        { message: "Missing input validation on user endpoint", severity: "High", category: "security", line: 25, trust_boundary: "untrusted_input", why_it_matters: "The endpoint forwards request data straight to the database layer, so a malformed or malicious payload reaches persistence unchecked.", how_to_fix: "Validate the request body with a Pydantic model before processing." },
        { message: "Inconsistent error response format", severity: "Medium", category: "style", line: 40 },
        { message: "Dead code: unused import `json`", severity: "Low", category: "maintainability", line: 3 },
      ],
      security: [
        { type: "Input Validation", severity: "High", description: "User input not validated before processing", file: "src/api_routes.py", line: 25, recommendation: "Add Pydantic model validation", trust_boundary: "untrusted_input" },
      ],
      complexity: "O(n)",
      explanation: "API routes lack consistent validation and error handling patterns.",
      explanationSource: "deterministic",
      suggestions: ["Add Pydantic request models", "Standardize error responses", "Remove unused imports"],
      improved_code: `from pydantic import BaseModel

class UserCreate(BaseModel):
    name: str
    email: str`,
      original_code: `@app.post("/users")
def create_user(request):
    data = request.json()
    db.insert(data)`,
      patch: null,
      duplicates: [{ file: "src/admin_routes.py", similarity: 65 }],
    },
    {
      name: "utils.py",
      path: "src/utils/utils.py",
      score: 88,
      language: "python",
      linesOfCode: 95,
      cyclomaticComplexity: 5,
      maxCyclomaticComplexity: 5,
      maxNestingDepth: 0,
      branches: 3,
      fileType: "production",
      documentationCoverage: 80,
      issues: [
        { message: "Unused function `format_legacy_date`", severity: "Low", category: "maintainability", line: 72 },
      ],
      security: [],
      complexity: "O(1)",
      explanation: "Well-written utility module with good documentation coverage. Minor dead code detected.",
      explanationSource: "deterministic",
      suggestions: ["Remove unused `format_legacy_date` function"],
      improved_code: `# Remove lines 72-80 (format_legacy_date)`,
      original_code: `def format_legacy_date(d):
    return d.strftime("%Y-%m-%d")`,
      patch: null,
      duplicates: [],
    },
    {
      name: "models.py",
      path: "src/models.py",
      score: 91,
      language: "python",
      linesOfCode: 150,
      cyclomaticComplexity: 3,
      maxCyclomaticComplexity: 3,
      maxNestingDepth: 0,
      branches: 1,
      fileType: "production",
      documentationCoverage: 90,
      issues: [],
      security: [],
      complexity: "O(1)",
      explanation: "Excellent model definitions with comprehensive docstrings and type annotations.",
      explanationSource: "deterministic",
      suggestions: [],
      improved_code: "",
      original_code: "",
      patch: null,
      duplicates: [],
    },
  ],
  dependencies: [
    { name: "flask", version: "2.0.1", latestVersion: "3.0.2", isOutdated: true, riskLevel: "High", vulnerabilities: [{ id: "CVE-2023-30861", summary: "Cookie disclosed by caching proxy", severity: "High" }], vulnLookup: "checked", constraint: ">=2.0", versionSource: "lockfile" },
    { name: "sqlalchemy", version: "1.4.46", latestVersion: "2.0.25", isOutdated: true, riskLevel: "Medium", vulnerabilities: [], vulnLookup: "checked", constraint: "", versionSource: "pinned" },
    { name: "requests", version: "2.31.0", latestVersion: "2.31.0", isOutdated: false, riskLevel: "Low", vulnerabilities: [], vulnLookup: "checked", constraint: "", versionSource: "pinned" },
    { name: "pydantic", version: "1.10.13", latestVersion: "2.6.1", isOutdated: true, riskLevel: "Low", vulnerabilities: [], vulnLookup: "checked", constraint: "", versionSource: "pinned" },
    { name: "cryptography", version: "3.4.8", latestVersion: "42.0.4", isOutdated: true, riskLevel: "Critical", vulnerabilities: [{ id: "CVE-2023-49083", summary: "NULL dereference when loading PKCS7 certificates", severity: "Critical" }, { id: "CVE-2024-0727", summary: "PKCS12 file can trigger a NULL dereference", severity: "Medium" }], vulnLookup: "checked", constraint: "", versionSource: "pinned" },
    { name: "jinja2", version: "3.1.2", latestVersion: "3.1.3", isOutdated: true, riskLevel: "Medium", vulnerabilities: [{ id: "CVE-2024-22195", summary: "xmlattr filter accepts keys containing spaces", severity: "Medium" }], vulnLookup: "checked", constraint: "", versionSource: "pinned" },
  ],
  insights: {
    top_critical_issues: [
      { message: "SQL injection reachable from untrusted request input", affected_files: ["src/main.py"] },
      { message: "Hardcoded credentials in the authentication module", affected_files: ["src/auth.py"] },
      { message: "User endpoint accepts unvalidated input", affected_files: ["src/api_routes.py"] },
    ],
    most_complex_files: [
      { file_path: "src/auth.py" },
      { file_path: "src/main.py" },
    ],
    most_central_file: "src/database.py",
    most_reused_module: "src/utils/utils.py",
  },
  duplicates: [
    { file1: "src/main.py", file2: "src/utils/helpers.py", similarity: 78, type: "block" },
    { file1: "src/api_routes.py", file2: "src/admin_routes.py", similarity: 65, type: "block" },
  ],
  dependency_graph: {
    nodes: [
      { id: "src/main.py" },
      { id: "src/auth.py" },
      { id: "src/database.py" },
      { id: "src/api_routes.py" },
      { id: "src/utils/utils.py" },
      { id: "src/models.py" },
    ],
    links: [
      { source: "src/main.py", target: "src/api_routes.py" },
      { source: "src/main.py", target: "src/database.py" },
      { source: "src/api_routes.py", target: "src/auth.py" },
      { source: "src/api_routes.py", target: "src/models.py" },
      { source: "src/api_routes.py", target: "src/database.py" },
      { source: "src/auth.py", target: "src/database.py" },
      { source: "src/auth.py", target: "src/utils/utils.py" },
      { source: "src/models.py", target: "src/utils/utils.py" },
    ],
  },
};

export const mockScanHistory: ScanHistoryItem[] = [
  { id: "scan-001", repoName: "python-webapp", repoUrl: "https://github.com/example/python-webapp", timestamp: new Date().toISOString(), healthScore: 73, filesAnalyzed: 12, issuesFound: 14 },
  { id: "scan-002", repoName: "data-pipeline", repoUrl: "https://github.com/example/data-pipeline", timestamp: new Date(Date.now() - 86400000).toISOString(), healthScore: 85, filesAnalyzed: 8, issuesFound: 5 },
  { id: "scan-003", repoName: "ml-service", repoUrl: "https://github.com/example/ml-service", timestamp: new Date(Date.now() - 172800000).toISOString(), healthScore: 62, filesAnalyzed: 22, issuesFound: 31 },
  { id: "scan-004", repoName: "auth-microservice", repoUrl: "https://github.com/example/auth-microservice", timestamp: new Date(Date.now() - 432000000).toISOString(), healthScore: 91, filesAnalyzed: 6, issuesFound: 2 },
];

export const mockTestResults: TestResult[] = [
  { name: "test_complexity", status: "passed", duration: 0.45, module: "analysis" },
  { name: "test_dead_code", status: "passed", duration: 0.32, module: "analysis" },
  { name: "test_llm_refactor", status: "passed", duration: 2.15, module: "services" },
  { name: "test_patch_generator", status: "passed", duration: 0.89, module: "services" },
  { name: "test_quality_score", status: "passed", duration: 0.21, module: "analysis" },
  { name: "test_refactoring", status: "passed", duration: 1.34, module: "services" },
  { name: "test_repo_analysis", status: "passed", duration: 3.42, module: "services" },
  { name: "test_repository_review", status: "passed", duration: 4.21, module: "services" },
  { name: "test_retrieval", status: "passed", duration: 1.56, module: "rag" },
  { name: "test_review_report", status: "passed", duration: 0.78, module: "services" },
  { name: "test_security_integration", status: "passed", duration: 1.12, module: "security" },
  { name: "test_smells", status: "passed", duration: 0.67, module: "analysis" },
];
