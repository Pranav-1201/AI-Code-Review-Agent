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

    security_issues = detect_security_issues(code)

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
            language=file_data.get("language", "python")
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
        "lines": lines,
        "issues": formatted_issues,
        "security_risks": merged_security,
        "report": report,
        "refactor_summary": refactor_result.get("explanation", ""),
        "refactor_suggestion": refactor_result.get("improved_code", ""),
        "suggestions": refactor_result.get("suggestions", []),
        "explanation": refactor_result.get("explanation", ""),
        "content": code,
        "documentation_coverage": doc_coverage
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
        # Run file analysis
        # --------------------------------------------------

        for file_data in repo_data:
            result = analyze_single_file(file_data, self.refactor_engine)
            results.append(result)

        # --------------------------------------------------
        # Aggregate results
        # --------------------------------------------------

        all_issues = []

        for result in results:

            print(f"Processed file: {result['file_path']}")

            file_reports.append({
                "file_path": result["file_path"],
                "file_name": result.get("file_name", ""),

                "score": result.get("score", 0),
                "language": result.get("language", "unknown"),

                "lines": result.get("lines", 0),
                "lines_of_code": result.get("lines", 0),

                "complexity": result.get("complexity", "O(1)"),
                "cyclomatic_complexity": result.get("cyclomatic_complexity", 0),

                "issues": result.get("issues", []),

                "security_risks": result.get("security_risks", []),

                "suggestions": result.get("suggestions", []),
                "explanation": result.get("explanation", ""),

                "improved_code": result.get("refactor_suggestion"),
                "refactor_summary": result.get("refactor_summary"),

                "content": result.get("content", ""),
                "original_code": result.get("content", ""),

                "documentation_coverage": result.get("documentation_coverage", 0),
                "time_complexity": result.get("complexity", "O(1)")
            })

            total_score += result["score"]

            # Count files with real issues (exclude security from count,
            # and filter placeholder messages)
            real_issues = [
                i for i in result.get("issues", [])
                if i.get("type") != "security"
                and "no obvious structural issues" not in str(i.get("message", "")).lower()
            ]

            if real_issues:
                issue_files += 1

            security_issues += len(result.get("security_risks", []))

            # Only add real issues to all_issues
            for issue in result.get("issues", []):
                msg = issue.get("message", "") if isinstance(issue, dict) else str(issue)
                if "no obvious structural issues" not in msg.lower():
                    all_issues.append(issue)

        file_count = len(results)

        avg_score = round(total_score / file_count, 2) if file_count else 0

        summary = {
            "files_analyzed": file_count,
            "files_with_issues": issue_files,
            "average_quality_score": avg_score,
            "total_security_issues": security_issues,
            "lines_of_code": sum(r["lines"] for r in results)
        }

        visualizations = {
            "quality_scores": [r["score"] for r in results],
            "complexity": [r.get("cyclomatic_complexity", 0) for r in results],
            "lines": [r["lines"] for r in results]
        }

        # --------------------------------------------------
        # Map duplicates to file-level for frontend
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

        # Attach duplicates to file reports
        for report in file_reports:
            fname = report.get("file_name", "")
            fpath = report.get("file_path", "")
            report["duplicates"] = duplicate_map.get(fname, []) or duplicate_map.get(fpath, [])

        # --------------------------------------------------
        # Final repository report
        # --------------------------------------------------

        return {
            "repository_summary": summary,
            "file_reports": file_reports,
            "issues": all_issues,
            "dependencies": dependencies,
            "dependency_graph": dependency_graph,
            "duplicates": duplicates,
            "visualizations": visualizations
        }