# ==========================================================
# File: backend/validation/phase5_validation.py
# Purpose: Chunk 4 (Phase 5 - AI Reasoning & Explainability) harness.
#
# Run:  python backend/validation/phase5_validation.py
# Exit: 0 if every check passes, 1 otherwise.
#
# Verifies the honest deliverables of this chunk:
#   - ChromaDB retired; retrieval is FAISS-only
#   - the Anthropic explanation layer is gated, grounded, and
#     labels its source; junior/senior depth toggle works
#   - the misnamed LLMRefactorEngine is gone (Heuristic now)
#   - feedback loop persists and computes a running precision
# Each check prints the observed values it asserts on. No network:
# the LLM stays gated OFF, so the deterministic path is exercised.
# ==========================================================

from __future__ import annotations

import os
import sys
import tempfile

os.environ.pop("ENABLE_ANTHROPIC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_RESULTS: list = []


def check(item_id: str, description: str):
    def wrap(fn):
        print(f"\n[{item_id}] {description}")
        try:
            detail = fn()
            _RESULTS.append((item_id, True))
            print(f"    PASS  {detail or ''}")
        except AssertionError as e:
            _RESULTS.append((item_id, False))
            print(f"    FAIL  {e}")
        except Exception as e:
            _RESULTS.append((item_id, False))
            print(f"    ERROR {type(e).__name__}: {e}")
        return fn
    return wrap


@check("P5-chromadb-retired", "ChromaDB store gone; report_generator no longer exposes it")
def _chroma():
    import backend.app.services.report_generator as rg
    assert not hasattr(rg, "get_vector_store"), "get_vector_store should be removed"
    assert not hasattr(rg, "ReviewVectorStore"), "ReviewVectorStore should be gone"
    assert not os.path.exists(os.path.join(_REPO_ROOT, "rag", "vector_store.py"))
    return "no get_vector_store / ReviewVectorStore; rag/vector_store.py removed"


@check("P5-faiss-retrieval", "retrieval is FAISS-only and returns a list (graceful fallback)")
def _faiss():
    from backend.app.services.retriever_service import CodeRetriever
    r = CodeRetriever()
    assert isinstance(r.retrieve("nested loops"), list)
    assert r.retrieve("") == []
    return "CodeRetriever.retrieve -> list; empty query -> []"


@check("P5-refactor-renamed", "LLMRefactorEngine misnomer gone; HeuristicRefactorEngine present")
def _rename():
    from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine
    assert HeuristicRefactorEngine is not None
    import importlib
    try:
        importlib.import_module("backend.app.analysis.llm_refactor_engine")
        raise AssertionError("old llm_refactor_engine module still importable")
    except ModuleNotFoundError:
        pass
    return "heuristic_refactor_engine.HeuristicRefactorEngine present; old module gone"


@check("P5-explain-gated", "explanation is gated OFF by default -> deterministic fallback verbatim")
def _gated():
    from backend.app.services import explanation_engine as EE
    assert not EE.anthropic_available()
    res = EE.generate_explanation({"file_name": "x.py"}, deterministic_fallback="DET", depth="senior")
    assert res["source"] == "deterministic" and res["text"] == "DET" and res["model"] is None
    return "gated off -> source=deterministic, text==fallback"


@check("P5-explain-grounded", "prompt is grounded in findings + carries anti-hallucination rules")
def _grounded():
    from backend.app.services import explanation_engine as EE
    ev = {"file_name": "v.py", "security_findings": [
        {"type": "Dangerous Function", "severity": "Critical",
         "description": "eval reachable from request.args", "trust_boundary": "untrusted_input"}]}
    msgs = EE._build_messages(ev, "senior")
    assert "untrusted_input" in msgs["user"], "trust boundary not grounded"
    assert "eval reachable from request.args" in msgs["user"], "finding not grounded"
    assert "Do not invent" in msgs["system"], "anti-hallucination rule missing"
    return "trust boundary + finding grounded; 'do not invent' present"


@check("P5-depth-toggle", "junior/senior depth changes the prompt; invalid depth -> senior")
def _depth():
    from backend.app.services import explanation_engine as EE
    ev = {"file_name": "v.py"}
    jr = EE._build_messages(ev, "junior")["system"]
    sr = EE._build_messages(ev, "senior")["system"]
    inv = EE._build_messages(ev, "wizard")["system"]
    assert "JUNIOR" in jr and "SENIOR" in sr and "SENIOR" in inv
    return "junior != senior; invalid -> senior"


@check("P5-explanation-source", "analyze_code surfaces analysis.explanation_source")
def _source():
    from backend.app.services.llm_service import analyze_code
    out = analyze_code("def f(x):\n    return x+1\n",
                       complexity_metrics=[{"cyclomatic_complexity": 1, "max_loop_depth": 0}])
    src = out["analysis"].get("explanation_source")
    assert src == "deterministic", src
    return f"explanation_source={src}"


@check("P5-feedback-precision", "feedback persists; running precision = up/(up+down)")
def _feedback():
    from backend.database import connection
    connection.DB_PATH = os.path.join(tempfile.mkdtemp(), "phase5.db")
    connection.init_db()
    import importlib
    rr = importlib.reload(importlib.import_module("backend.database.review_repository"))

    assert rr.get_precision_estimate()["precision"] is None, "fresh DB must not fake a score"
    for _ in range(3):
        rr.record_feedback(1, "v.py:1:eval", "up")
    rr.record_feedback(1, "v.py:2:pickle", "down")
    est = rr.get_precision_estimate()
    assert est == {"up": 3, "down": 1, "total": 4, "precision": 0.75}, est
    try:
        rr.record_feedback(1, "x", "meh")
        raise AssertionError("invalid vote should raise")
    except ValueError:
        pass
    return f"precision={est['precision']} (3 up / 1 down); invalid vote rejected"


def main() -> int:
    print("=" * 62)
    print("Phase 5 validation - RAG consolidation, LLM explanation, feedback")
    print("=" * 62)
    passed = sum(1 for _, ok in _RESULTS if ok)
    total = len(_RESULTS)
    print("\n" + "=" * 62)
    print(f"RESULT: {passed}/{total} checks passed")
    for item_id, ok in _RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {item_id}")
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
