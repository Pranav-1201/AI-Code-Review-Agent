# ==========================================================
# File: llm_service.py
# Purpose: Core AI code analysis service combining
#          RAG retrieval + transformer inference +
#          deterministic heuristics.
# ==========================================================

import os
import ast
from typing import Dict, List, Any

from backend.app.services.retriever_service import CodeRetriever
from backend.app.services.security_analyzer import detect_security_issues
from backend.app.services.quality_scorer import compute_quality_score


# ----------------------------------------------------------
# Phase 0 — CodeBERT gated behind environment flag
# ----------------------------------------------------------
# CodeBERT is NOT fine-tuned for issue classification.
# Until a labeled training dataset is built and fine-tuning
# is completed (Phase 5), the model outputs are random noise.
# Set ENABLE_CODEBERT=true in .env ONLY when a fine-tuned
# checkpoint is available. Default is deterministic mode.
# ----------------------------------------------------------

ENABLE_CODEBERT = os.getenv("ENABLE_CODEBERT", "false").lower() == "true"

MODEL_NAME = "microsoft/codebert-base"


# ----------------------------------------------------------
# Global cached objects (loaded once)
# ----------------------------------------------------------

_tokenizer = None
_model = None
_retriever = None


# ----------------------------------------------------------
# Model Loader (safe lazy loading)
# Only executes when ENABLE_CODEBERT=true
# ----------------------------------------------------------

def load_model():
    global _tokenizer, _model

    if not ENABLE_CODEBERT:
        # Skip entirely — deterministic mode is active
        return

    # Import only when needed — avoids torch/transformers
    # overhead when running in deterministic mode
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    from backend.app.config import HF_TOKEN

    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            token=HF_TOKEN
        )

    if _model is None:
        _model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_NAME,
            num_labels=2,
            token=HF_TOKEN
        )


# ----------------------------------------------------------
# Retriever Loader
# ----------------------------------------------------------

def get_retriever():
    global _retriever

    if _retriever is None:
        _retriever = CodeRetriever()

    return _retriever


# ----------------------------------------------------------
# Deterministic Issue Probability  (Phase 0 replacement)
# ----------------------------------------------------------
# Replaces CodeBERT inference until fine-tuning is complete.
# Derived entirely from static analysis signals already
# computed by ComplexityAnalyzer and SecurityAnalyzer —
# making the score 100% reproducible and meaningful.
#
# Score interpretation:
#   0.0  — clean file, no signals
#   0.3  — moderate complexity or minor issues
#   0.7+ — high complexity + critical security issues
# ----------------------------------------------------------

def _compute_deterministic_probability(
    cc: int,
    depth: int,
    sec_issues: list,
    line_count: int
) -> float:
    """
    Compute a deterministic issue probability (0.0–1.0) from
    static analysis signals. Used in place of CodeBERT until
    a fine-tuned model is available (Phase 5).

    Parameters
    ----------
    cc : int
        Cyclomatic complexity of the file.
    depth : int
        Maximum loop nesting depth.
    sec_issues : list
        List of detected security issues (dicts with 'severity').
    line_count : int
        Total lines in the file.

    Returns
    -------
    float
        Probability in [0.0, 1.0]. Higher = more likely the
        file has quality/security issues.
    """

    score = 0.0

    # --------------------------------------------------
    # Complexity contribution
    # --------------------------------------------------
    if cc > 10:
        score += 0.30
    elif cc > 5:
        score += 0.10

    # --------------------------------------------------
    # Loop depth contribution
    # --------------------------------------------------
    if depth >= 3:
        score += 0.30
    elif depth == 2:
        score += 0.15

    # --------------------------------------------------
    # Critical security issue contribution
    # Only Critical-severity issues drive a strong signal
    # --------------------------------------------------
    crit_count = sum(
        1 for s in sec_issues
        if isinstance(s, dict) and s.get("severity", "").lower() == "critical"
    )
    score += min(crit_count * 0.20, 0.40)

    # --------------------------------------------------
    # Long file contribution (minor signal)
    # --------------------------------------------------
    if line_count > 500:
        score += 0.10

    return min(score, 1.0)


# ----------------------------------------------------------
# Heuristic Analysis
# ----------------------------------------------------------

def _heuristic_analysis(code: str, complexity: dict = None, filename: str = "", file_role: str = 'utility'): # PHASE 1: Added file_role
    """
    Perform heuristic code analysis for structural issues.
    Complexity is provided by the caller (from ComplexityAnalyzer),
    NOT re-calculated here — single source of truth.
    """
    if complexity is None:
        complexity = {}

    # Use TOTAL line count (matching wc -l), not stripped
    line_count = len(code.splitlines())
    lines = [l.strip() for l in code.split("\n") if l.strip()]

    issues = []

    # --------------------------------------------------
    # Generate performance issue from complexity param
    # --------------------------------------------------

    depth = complexity.get("max_loop_depth", 0)

    if depth >= 3:
        issues.append({
            "type": "performance",
            "severity": "high",
            "message": f"Deeply nested loops detected (depth {depth}) — high time complexity."
        })
    elif depth == 2:
        issues.append({
            "type": "performance",
            "severity": "medium",
            "message": "Nested loop detected (depth 2) — possible performance bottleneck."
        })

    # --------------------------------------------------
    # Cyclomatic branching check (only when nesting exists)
    # --------------------------------------------------

    condition_count = sum(1 for l in lines if l.lstrip().startswith(("if ", "elif ")))
    cc = complexity.get("cyclomatic_complexity", 1)

    if condition_count > 10 and cc > 5:
        issues.append({
            "type": "maintainability",
            "severity": "medium",
            "message": (
                f"High cyclomatic complexity ({cc}): high branching "
                f"({condition_count} conditions) combined with deep nesting."
            )
        })

    # Detect long files
    if line_count > 300:
        issues.append({
            "type": "maintainability",
            "severity": "medium",
            "message": f"File is {line_count} lines long — consider splitting into smaller modules"
        })
    elif line_count > 150:
        issues.append({
            "type": "style",
            "severity": "low",
            "message": f"File is {line_count} lines — approaching recommended module size limit"
        })

    # --------------------------------------------------
    # Detect missing if __name__ guard
    # Skip for __main__.py — it IS the entry point by
    # definition, the guard is meaningless there.
    # Skip for library modules (no script execution patterns)
    # --------------------------------------------------

    basename = filename.replace("\\", "/").split("/")[-1].lower() if filename else ""
    is_main_module = basename == "__main__.py"

    if not is_main_module:
        has_main_guard = any("__name__" in l and "__main__" in l for l in lines)

        script_execution_patterns = (
            ".run(", "main(", "sys.exit(", "app.run(",
            "cli(", "click.command", "argparse"
        )
        has_script_execution = any(
            any(pat in l for pat in script_execution_patterns)
            for l in lines
            if l and not l.startswith(("def ", "class ", "#", "@", " ", "\t"))
        )

        if has_script_execution and not has_main_guard:
            # PHASE 1: suppress top-level call heuristic for library contexts
            _LIBRARY_PATH_SEGMENTS = {'src', 'lib', 'library', 'libraries', 'vendor', 'pkg'}
            is_library_path = bool(
                _LIBRARY_PATH_SEGMENTS & set(filename.replace('\\', '/').split('/'))
            )
            is_library_role = file_role in ('utility', 'data_model', 'orchestrator')

            if is_library_path or is_library_role:
                pass  # skip top-level call heuristic entirely
            else:
                issues.append({
                    "type": "style",
                    "severity": "low",
                    "message": "Top-level function calls detected without if __name__ == '__main__' guard"
                })

    return issues


# ----------------------------------------------------------
# Generate File-Specific Explanation
# ----------------------------------------------------------

def _generate_explanation(
    code: str,
    issues: List[Dict],
    security_issues: List[Dict],
    complexity: Dict[str, Any],
    quality_score: int,
    functions: List[str],
    imports: List[str],
    language: str,
    doc_coverage: float = 0.0,
    undocumented_count: int = 0,
    file_name: str = ""
) -> str:
    """
    Generate a meaningful, file-specific explanation
    using a deterministic hybrid extraction engine.
    """

    total_lines = len(code.splitlines())
    cc = complexity.get("cyclomatic_complexity", 1)
    depth = complexity.get("max_loop_depth", 0)
    branches = complexity.get("branches", 0)

    # 1. Purpose Summary
    purpose = f"This `{language}` file"
    if file_name:
        purpose += f" (`{file_name}`)"
    if "test" in file_name.lower():
        purpose += " contains test suites to verify functionality."
    elif "example" in file_name.lower():
        purpose += " provides usage examples and documentation."
    elif total_lines > 200:
        purpose += " acts as a core module, managing significant system logic."
    else:
        purpose += " provides focused utility or component logic."

    # 2. Key Responsibilities
    responsibilities = []
    if functions:
        fn_list = ", ".join(f"`{f}`" for f in functions[:5])
        suffix = f", plus {len(functions) - 5} more." if len(functions) > 5 else "."
        responsibilities.append(f"Defines {len(functions)} core function(s): {fn_list}{suffix}")
    if imports:
        responsibilities.append(
            f"Integrates with {len(imports)} dependencies, including: {', '.join(imports[:3])}."
        )

    # 3. Design Observations
    design = []
    if doc_coverage < 100.0 and undocumented_count > 0:
        design.append(
            f"**Documentation:** Coverage is at {doc_coverage:.1f}% "
            f"({undocumented_count} functions/classes lack docstrings)."
        )

    if cc > 10:
        design.append(f"**Complexity:** High cyclomatic complexity ({cc}) indicates dense branching logic.")
    elif cc > 5:
        design.append(f"**Complexity:** Moderate complexity ({cc}) with {branches} branches.")
    else:
        design.append(f"**Complexity:** Logic is straightforward with minimal branching ({cc}).")

    if total_lines > 300:
        design.append(f"**Size:** File length ({total_lines} lines) may impact maintainability.")

    # 4. Risk Analysis
    risks = []
    if security_issues:
        sev_counts = {}
        for s in security_issues:
            sev = s.get("severity", "Medium") if isinstance(s, dict) else "High"
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        sev_str = ", ".join(f"{v} {k}" for k, v in sorted(sev_counts.items()))
        risks.append(f"⚠️ **Security Risks:** Detected {len(security_issues)} issue(s) ({sev_str}).")

    real_issues = [i for i in issues if isinstance(i, dict)]
    if real_issues:
        risks.append(
            f"🛠 **Code Quality:** Static analysis found {len(real_issues)} "
            f"structural/style area(s) for improvement."
        )

    if not risks:
        risks.append("✅ **Health:** No critical security or structural risks detected.")

    # Assemble Markdown
    md = f"### Purpose Summary\n{purpose}\n\n"
    if responsibilities:
        md += "### Key Responsibilities\n" + "\n".join(f"- {r}" for r in responsibilities) + "\n\n"
    if design:
        md += "### Design Observations\n" + "\n".join(f"- {d}" for d in design) + "\n\n"
    md += "### Risk Analysis\n" + "\n".join(f"- {r}" for r in risks)

    return md


# ----------------------------------------------------------
# Generate File-Specific Suggestions
# ----------------------------------------------------------

def _generate_suggestions(
    complexity: Dict[str, Any],
    security_issues: List[Dict],
    issues: List[Dict],
    functions: List[str],
    imports: List[str],
    code: str
) -> List[str]:
    """
    Generate actionable, file-specific suggestions
    based on actual analysis signals.
    """

    suggestions = []

    # Complexity suggestions
    depth = complexity.get("max_loop_depth", 0)
    if depth >= 2:
        suggestions.append(
            "Consider reducing nested loops using sets, hash maps, or "
            "vectorized operations for better performance."
        )

    # Security suggestions
    if security_issues:
        sec_types = set()
        for s in security_issues:
            if isinstance(s, dict):
                sec_types.add(s.get("type", "security"))
        if "Hardcoded Credential" in sec_types:
            suggestions.append(
                "Move hardcoded credentials to environment variables or a secrets manager."
            )
        if "SQL Injection" in sec_types:
            suggestions.append(
                "Use parameterized queries or an ORM instead of string concatenation for SQL."
            )
        if "Command Injection" in sec_types:
            suggestions.append(
                "Use subprocess with list arguments instead of shell commands."
            )

    # Long file suggestion
    lines = len([l for l in code.split("\n") if l.strip()])
    if lines > 200:
        suggestions.append(
            f"This file has {lines} lines. Consider splitting it into "
            "smaller, focused modules."
        )

    # Many functions suggestion
    if len(functions) > 15:
        suggestions.append(
            f"This file defines {len(functions)} functions. Consider grouping "
            "related functions into separate modules or classes."
        )

    # Many imports suggestion
    if len(imports) > 10:
        suggestions.append(
            f"This file has {len(imports)} imports — review for unused imports "
            "and consider lazy loading."
        )

    # Fallback if nothing specific
    if not suggestions:
        if complexity.get("time_complexity") == "O(1)":
            suggestions.append("Code structure appears efficient for typical input sizes.")
        else:
            suggestions.append(
                "Code complexity is manageable. Consider adding docstrings "
                "for better documentation."
            )

    return suggestions


# ----------------------------------------------------------
# Main Code Analysis Function
# ----------------------------------------------------------

def analyze_code(
    code: str,
    functions: List[str] = None,
    imports: List[str] = None,
    complexity_metrics: List[Dict] = None,
    language: str = "unknown",
    security_issues: List[Dict] = None,
    is_test_file: bool = False,
    **kwargs # PHASE 1: Accept extra args from file_result dict
) -> Dict:
    """
    Main code analysis function combining AI inference,
    heuristic analysis, and security scanning.

    Parameters
    ----------
    security_issues : List[Dict], optional
        Pre-computed security issues from the caller.
        If provided, detect_security_issues() is NOT called
        (eliminates duplicate analysis).
    is_test_file : bool
        If True and security_issues is None, passes context
        to detect_security_issues for filtering.
    """

    # Only load model if CodeBERT is explicitly enabled
    load_model()

    functions = functions or []
    imports = imports or []

    # ------------------------------------------------------
    # STEP 1: Retrieve repository context (RAG)
    # Context is preserved for future Phase 5 LLM integration
    # ------------------------------------------------------

    try:
        context_chunks = get_retriever().retrieve(code)
    except Exception:
        context_chunks = []

    # ------------------------------------------------------
    # STEP 2: Security analysis
    # Use pre-computed issues from caller when available
    # to avoid duplicate analysis (single source of truth)
    # ------------------------------------------------------

    if security_issues is None:
        security_issues = detect_security_issues(code, is_test_file=is_test_file)

    # ------------------------------------------------------
    # STEP 3: Complexity from AST analyzer
    # ------------------------------------------------------

    comp_data = {
        "cyclomatic_complexity": 1,
        "max_loop_depth": 0,
        "branches": sum(fn.get("branches", 0) for fn in complexity_metrics) if complexity_metrics else 0
    }

    if complexity_metrics:
        comp_data["max_loop_depth"] = max(
            fn.get("max_loop_depth", 0) for fn in complexity_metrics
        )
        comp_data["cyclomatic_complexity"] = max(
            fn.get("cyclomatic_complexity", 1) for fn in complexity_metrics
        )

    # ------------------------------------------------------
    # STEP 4: Issue probability
    # --
    # CODEBERT MODE (ENABLE_CODEBERT=true):
    #   Uses the transformer model for inference.
    #   Only enable once a fine-tuned checkpoint exists.
    # --
    # DETERMINISTIC MODE (default):
    #   Derives probability from static analysis signals.
    #   100% reproducible — same code always scores the same.
    # ------------------------------------------------------

    line_count = len(code.splitlines())

    if ENABLE_CODEBERT and _tokenizer is not None and _model is not None:
        import torch

        context_text = "\n".join(context_chunks[:3])  # limit context size

        prompt = f"""
Repository Context:
{context_text}

Code:
{code}
"""
        inputs = _tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=512
        )

        with torch.no_grad():
            outputs = _model(**inputs)

        probs = torch.softmax(outputs.logits, dim=1).tolist()[0]
        issue_probability = probs[1]

    else:
        # Deterministic fallback — derived from real signals
        issue_probability = _compute_deterministic_probability(
            cc=comp_data["cyclomatic_complexity"],
            depth=comp_data["max_loop_depth"],
            sec_issues=security_issues,
            line_count=line_count
        )
        probs = [round(1.0 - issue_probability, 3), round(issue_probability, 3)]

    # ------------------------------------------------------
    # STEP 5: Heuristic issue detection
    # Single source of truth: complexity comes from the
    # ComplexityAnalyzer (step 3 above). _heuristic_analysis
    # generates issue messages FROM that complexity, not its
    # own competing calculation.
    # ------------------------------------------------------

    # Extract filename for __main__.py guard suppression
    _filename = ""
    if complexity_metrics and len(complexity_metrics) > 0:
        _filename = complexity_metrics[0].get("_filename", "")

    # Defect C: role is now passed explicitly by repository_review_engine.
    # Keep the legacy _file_role key as a fallback for any other caller.
    file_role = kwargs.get("file_role", kwargs.get("_file_role", "utility"))
    
    heuristic_issues = _heuristic_analysis(code, complexity=comp_data, filename=_filename, file_role=file_role)
    issues = list(heuristic_issues)

    score_result = compute_quality_score(
        issue_probability,
        comp_data,
        security_issues,
        is_test_file=is_test_file
    )
    quality_score = score_result if isinstance(score_result, int) else score_result[0]
    breakdown = score_result[1] if isinstance(score_result, tuple) else {}

    # ------------------------------------------------------
    # STEP 6: Generate file-specific explanation
    # ------------------------------------------------------

    # Extract doc coverage if passed via complexity_metrics metadata
    _doc_coverage = 0.0
    if complexity_metrics and len(complexity_metrics) > 0:
        _doc_coverage = complexity_metrics[0].get("_doc_coverage", 0.0)

    explanation = _generate_explanation(
        code=code,
        issues=issues,
        security_issues=security_issues,
        complexity=comp_data,
        quality_score=quality_score,
        functions=functions,
        imports=imports,
        language=language,
        doc_coverage=_doc_coverage,
        file_name=_filename
    )

    suggestions = _generate_suggestions(
        complexity=comp_data,
        security_issues=security_issues,
        issues=issues,
        functions=functions,
        imports=imports,
        code=code
    )

    # ------------------------------------------------------
    # STEP 7: Structured result
    # ------------------------------------------------------

    return {
        "language": language,
        "confidence_scores": {
            "issue_likely":   round(probs[1], 3),
            "issue_unlikely": round(probs[0], 3)
        },
        "code_quality_score": quality_score,
        "breakdown": breakdown,
        "analysis": {
            "issues":          issues,
            "security_risks":  security_issues,
            "time_complexity": "O(1)",   # kept for backward-compatible parsing
            "complexity":      comp_data,
            "explanation":     explanation,
            "suggestions":     suggestions
        },
        "retrieved_context": context_chunks
    }