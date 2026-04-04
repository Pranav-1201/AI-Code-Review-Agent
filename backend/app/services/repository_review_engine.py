# ==========================================================
# File: repository_review_engine.py
# Purpose: Orchestrates repository-level AI code review
# ==========================================================

from typing import Dict, List

from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.llm_service import analyze_code
from backend.app.services.report_generator import generate_review_report
from backend.app.analysis.llm_refactor_engine import LLMRefactorEngine
from backend.app.analysis.dependency_analyzer import analyze_dependencies
from backend.app.analysis.dependency_graph import build_dependency_graph
from backend.app.analysis.duplicate_detector import detect_duplicates
from backend.app.services.security_analyzer import detect_security_issues


# ----------------------------------------------------------
# Single File Analysis Worker
# ----------------------------------------------------------

def analyze_single_file(file_data: Dict, refactor_engine: LLMRefactorEngine) -> Dict:

    code = file_data["content"]
    file_name = file_data["file_name"]
    file_path = file_data.get("file_path", file_name)
    file_is_test = file_data.get("is_test", False)

    # SINGLE security analysis call per file — with full context:
    # - is_test_file: skips assert, downgrades subprocess
    # - file_path: framework-aware eval/exec/compile severity
    security_issues = detect_security_issues(
        code,
        is_test_file=file_is_test,
        file_path=file_path
    )

    functions = file_data.get("functions", [])
    imports = file_data.get("imports", [])
    complexity_metrics = file_data.get("complexity_metrics", [])
    smells = file_data.get("code_smells", [])

    max_depth = 0
    for fn in complexity_metrics:
        max_depth = max(max_depth, fn.get("max_loop_depth", 0))

    complexity = {
        "max_loop_depth": max_depth
    }

    # ------------------------------------------------------
    # Safe AI analysis execution
    # ------------------------------------------------------

    try:

        analysis_result = analyze_code(
            code,
            functions=functions,
            imports=imports,
            complexity_metrics=complexity_metrics,
            language=file_data.get("language", "python"),
            security_issues=security_issues,
            is_test_file=file_is_test
        )

        analysis_section = analysis_result.get("analysis", {})

        refactor_result = refactor_engine.generate_refactor(
            code,
            analysis_result,
            complexity,
            smells
        )

    except Exception as e:

        print(f"Analysis failed for {file_name}: {e}")

        analysis_result = {
            "code_quality_score": 0,
            "analysis": {
                "issues": [{
                    "type": "analysis_error",
                    "severity": "high",
                    "message": str(e)
                }],
                "security_risks": []
            }
        }

        analysis_section = analysis_result["analysis"]

        refactor_result = {
            "improved_code": "",
            "explanation": "",
            "suggestions": [],
            "patch": None
        }

    score = analysis_result.get("code_quality_score", 0)
    issues = analysis_section.get("issues", [])
    ai_security = analysis_section.get("security_risks", [])

    # --------------------------------------------------
    # Merge security issues (AI + static analyzer)
    # Deduplicate by description
    # --------------------------------------------------

    seen_descriptions = set()
    merged_security = []

    for sec in (ai_security + security_issues):
        if isinstance(sec, dict):
            desc = sec.get("description", "")
            if desc not in seen_descriptions:
                seen_descriptions.add(desc)
                merged_security.append(sec)
        elif isinstance(sec, str):
            # Legacy format: plain string
            if sec not in seen_descriptions:
                seen_descriptions.add(sec)
                merged_security.append({
                    "type": "Vulnerability",
                    "severity": "High",
                    "description": sec,
                    "recommendation": "",
                    "file": file_path,
                    "line": 0
                })

    # --------------------------------------------------
    # Format issues with proper categories
    # --------------------------------------------------

    formatted_issues = []

    for issue in issues:
        # Skip non-informational placeholder messages
        msg = issue.get("message", "") if isinstance(issue, dict) else str(issue)
        if "no obvious structural issues" in msg.lower():
            continue

        if isinstance(issue, dict):
            formatted_issues.append({
                "file": file_path,
                "type": issue.get("type", "code_issue"),
                "severity": issue.get("severity", "medium"),
                "message": issue.get("message", "")
            })
        else:
            formatted_issues.append({
                "file": file_path,
                "type": "code_issue",
                "severity": "medium",
                "message": str(issue)
            })

    # Add security issues as issues too (for issue explorer)
    for sec in merged_security:
        formatted_issues.append({
            "file": file_path,
            "type": "security",
            "severity": sec.get("severity", "High").lower(),
            "message": sec.get("description", str(sec))
        })

    lines = len(code.splitlines())
    language = file_data.get("language", "unknown")

    # Get metrics from repo analyzer
    file_cyclomatic = file_data.get("cyclomatic_complexity", 0)
    file_time_complexity = file_data.get("time_complexity", "O(1)")
    doc_coverage = file_data.get("documentation_coverage", 0)

    report = generate_review_report(
        file_name=file_name,
        analysis_result=analysis_result,
        refactor_result=refactor_result,
        complexity_metrics=complexity_metrics,
        smell_metrics=smells
    )

    return {
        "file_path": file_path,
        "file_name": file_name,
        "language": language,
        "score": score,
        "complexity": file_time_complexity,
        "cyclomatic_complexity": file_cyclomatic,
        "max_cyclomatic_complexity": file_data.get("max_cyclomatic_complexity", 0),
        "lines": lines,
        "issues": formatted_issues,
        "security_risks": merged_security,
        "report": report,
        "refactor_summary": refactor_result.get("explanation", ""),
        "refactor_suggestion": refactor_result.get("improved_code", ""),
        "patch": refactor_result.get("patch", None),
        "suggestions": refactor_result.get("suggestions", []),
        "explanation": refactor_result.get("explanation", ""),
        "content": code,
        "documentation_coverage": doc_coverage,
        "is_test": file_is_test,
        "file_type": file_data.get("file_type", "production"),
    }


# ==========================================================
# Repository Review Engine
# ==========================================================

class RepositoryReviewEngine:

    def __init__(self):
        self.refactor_engine = LLMRefactorEngine()

    def review_repository(self, repo_path: str, repo_data) -> Dict:

        # --------------------------------------------------
        # Repo-level analysis
        # --------------------------------------------------

        dependencies = analyze_dependencies(repo_path)
        dependency_graph = build_dependency_graph(repo_data)
        duplicates = detect_duplicates(repo_data)

        file_reports: List[Dict] = []
        results = []

        total_score = 0
        issue_files = 0
        security_issues = 0

        # --------------------------------------------------
        # Run file analysis (only on code files)
        # --------------------------------------------------

        for file_data in repo_data:

            # Non-code files: add minimal report without AI analysis
            if not file_data.get("is_code", True):
                file_reports.append({
                    "file_path": file_data["file_path"],
                    "file_name": file_data["file_name"],
                    "score": 100,
                    "language": file_data.get("language", "unknown"),
                    "lines": file_data.get("lines", 0),
                    "lines_of_code": file_data.get("lines", 0),
                    "complexity": "N/A",
                    "cyclomatic_complexity": 0,
                    "max_cyclomatic_complexity": 0,
                    "issues": [],
                    "security_risks": [],
                    "suggestions": [],
                    "explanation": "",
                    "improved_code": "",
                    "refactor_summary": "",
                    "content": file_data.get("content", ""),
                    "original_code": file_data.get("content", ""),
                    "documentation_coverage": 0,
                    "is_test": False,
                    "file_type": "non_code",
                })
                continue

            result = analyze_single_file(file_data, self.refactor_engine)
            results.append(result)

        # --------------------------------------------------
        # Aggregate results
        # --------------------------------------------------

        all_issues = []

        # Separate production and test results for scoring
        prod_results = []
        test_results = []

        for result in results:

            # Normalize path
            fpath = result["file_path"].replace("\\", "/")
            result["file_path"] = fpath

            print(f"Processed file: {fpath}")

            file_report = {
                "file_path": fpath,
                "file_name": result.get("file_name", ""),

                "score": result.get("score", 0),
                "language": result.get("language", "unknown"),

                "lines": result.get("lines", 0),
                "lines_of_code": result.get("lines", 0),

                "complexity": result.get("complexity", "O(1)"),
                "cyclomatic_complexity": result.get("cyclomatic_complexity", 0),
                "max_cyclomatic_complexity": result.get("max_cyclomatic_complexity", 0),

                "issues": result.get("issues", []),

                "security_risks": result.get("security_risks", []),

                "suggestions": result.get("suggestions", []),
                "explanation": result.get("explanation", ""),

                "improved_code": result.get("refactor_suggestion"),
                "refactor_summary": result.get("refactor_summary"),
                "patch": result.get("patch"),

                "content": result.get("content", ""),
                "original_code": result.get("content", ""),

                "documentation_coverage": result.get("documentation_coverage", 0),
                "time_complexity": result.get("complexity", "O(1)"),

                "is_test": result.get("is_test", False),
                "file_type": result.get("file_type", "production"),
            }

            file_reports.append(file_report)

            # Classify into production vs test for scoring
            if result.get("is_test", False):
                test_results.append(result)
            else:
                prod_results.append(result)

            # Count files with real issues (all code files)
            real_issues = [
                i for i in result.get("issues", [])
                if i.get("type") != "security"
                and "no obvious structural issues" not in str(i.get("message", "")).lower()
            ]

            if real_issues:
                issue_files += 1

            # Security issues: count only from production files
            if not result.get("is_test", False):
                security_issues += len(result.get("security_risks", []))

            for issue in result.get("issues", []):
                msg = issue.get("message", "") if isinstance(issue, dict) else str(issue)
                if "no obvious structural issues" not in msg.lower():
                    all_issues.append(issue)

        # --------------------------------------------------
        # Compute averages from PRODUCTION files only
        # Test files and non-code files must not distort metrics
        # --------------------------------------------------

        prod_count = len(prod_results)
        total_file_count = len(file_reports)
        code_file_count = len(results)

        if prod_count > 0:
            avg_score = round(
                sum(r["score"] for r in prod_results) / prod_count, 2
            )
            avg_doc = round(
                sum(r.get("documentation_coverage", 0) for r in prod_results) / prod_count, 1
            )
            avg_cyclomatic = round(
                sum(r.get("cyclomatic_complexity", 0) for r in prod_results) / prod_count, 1
            )
        else:
            avg_score = 0
            avg_doc = 0
            avg_cyclomatic = 0

        # --------------------------------------------------
        # Compute health_score on the BACKEND
        # using production files only
        # --------------------------------------------------

        quality_score = avg_score
        sec_score = 100 if security_issues == 0 else max(0, round(100 - (security_issues ** 0.7) * 10))
        doc_score = avg_doc
        simplicity_score = max(0, round(100 - min(avg_cyclomatic * 3, 80)))

        health_score = round(
            0.35 * quality_score +
            0.25 * sec_score +
            0.20 * doc_score +
            0.20 * simplicity_score
        )

        # --------------------------------------------------
        # Group repeated issues by message pattern
        # --------------------------------------------------

        grouped_issues = []
        issue_groups: Dict[str, Dict] = {}

        for issue in all_issues:
            msg = issue.get("message", "") if isinstance(issue, dict) else str(issue)
            # Normalize message for grouping (remove numbers, file-specific parts)
            key = msg.lower().strip()

            if key in issue_groups:
                issue_groups[key]["count"] += 1
                file = issue.get("file", "")
                if file and file not in issue_groups[key]["affected_files"]:
                    issue_groups[key]["affected_files"].append(file)
            else:
                issue_groups[key] = {
                    **issue,
                    "count": 1,
                    "affected_files": [issue.get("file", "")]
                }

        grouped_issues = list(issue_groups.values())

        # --------------------------------------------------
        # Maintainability warnings
        # Detect long files and complex functions in prod code
        # --------------------------------------------------

        maintainability_warnings = []

        for r in prod_results:
            lines = r.get("lines", 0)
            fpath = r.get("file_path", "")
            cc = r.get("cyclomatic_complexity", 0)
            max_cc = r.get("max_cyclomatic_complexity", 0)

            if lines > 300:
                maintainability_warnings.append({
                    "file": fpath,
                    "type": "long_file",
                    "message": f"File is {lines} lines long — consider splitting into smaller modules",
                    "severity": "medium"
                })

            if max_cc > 10:
                maintainability_warnings.append({
                    "file": fpath,
                    "type": "complex_function",
                    "message": f"Contains function(s) with cyclomatic complexity {max_cc} — consider refactoring",
                    "severity": "medium" if max_cc <= 20 else "high"
                })

        summary = {
            "files_analyzed": total_file_count,
            "code_files": code_file_count,
            "production_files": prod_count,
            "test_files": len(test_results),
            "files_with_issues": issue_files,
            "average_quality_score": avg_score,
            "total_security_issues": security_issues,
            "lines_of_code": sum(r["lines"] for r in results),
            "avg_documentation_coverage": avg_doc,
            "avg_cyclomatic_complexity": avg_cyclomatic,
            "health_score": health_score,
            "maintainability_warnings": maintainability_warnings,
        }

        visualizations = {
            "quality_scores": [r["score"] for r in results],
            "complexity": [r.get("cyclomatic_complexity", 0) for r in results],
            "lines": [r["lines"] for r in results]
        }

        # --------------------------------------------------
        # Map duplicates to file-level
        # --------------------------------------------------

        duplicate_map = {}
        for dup in duplicates:
            f1 = dup.get("file1", "")
            f2 = dup.get("file2", "")
            sim = dup.get("similarity", 100)

            if f1 not in duplicate_map:
                duplicate_map[f1] = []
            duplicate_map[f1].append({"file": f2, "similarity": sim})

            if f2 not in duplicate_map:
                duplicate_map[f2] = []
            duplicate_map[f2].append({"file": f1, "similarity": sim})

        for report in file_reports:
            fname = report.get("file_name", "")
            fpath = report.get("file_path", "")
            report["duplicates"] = duplicate_map.get(fpath, []) or duplicate_map.get(fname, [])

        # --------------------------------------------------
        # Final repository report
        # --------------------------------------------------

        return {
            "repository_summary": summary,
            "file_reports": file_reports,
            "issues": grouped_issues,
            "dependencies": dependencies,
            "dependency_graph": dependency_graph,
            "duplicates": duplicates,
            "visualizations": visualizations
        }