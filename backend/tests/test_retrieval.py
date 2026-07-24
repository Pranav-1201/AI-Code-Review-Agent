"""
Unit tests for CodeRetriever (FAISS-backed semantic retrieval).

PHASE 5 NOTE: these tests previously decorated every case with
@patch("rag.vector_store.ReviewVectorStore") — the ChromaDB store, which
CodeRetriever never calls. The patches were inert and the tests passed only
via the no-index fallback. ChromaDB has been retired (audit item #7), so the
tests now assert CodeRetriever's real contract instead: it always returns a
list, handles empty/oversized queries safely, and degrades gracefully when
the FAISS index or embedding model is unavailable.
"""

import os
import sys
from unittest.mock import MagicMock

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.retriever_service import CodeRetriever


def test_retrieve_returns_list():
    """A valid query always yields a list (index present or not)."""
    retriever = CodeRetriever()
    results = retriever.retrieve("nested loops inefficiency")
    assert isinstance(results, list)


def test_empty_query_returns_empty_list():
    retriever = CodeRetriever()
    assert retriever.retrieve("") == []


def test_whitespace_query_returns_empty_list():
    retriever = CodeRetriever()
    assert retriever.retrieve("   \n  ") == []


def test_large_query_is_handled():
    """Long queries are truncated internally and must not raise."""
    retriever = CodeRetriever()
    results = retriever.retrieve("inefficient loops " * 500)
    assert isinstance(results, list)


def test_missing_index_falls_back_gracefully():
    """With no FAISS index loaded, retrieval degrades instead of raising."""
    retriever = CodeRetriever()
    retriever.index = None
    results = retriever.retrieve("anything")
    assert isinstance(results, list)


def test_search_failure_is_swallowed():
    """A backend failure returns [] rather than propagating."""
    retriever = CodeRetriever()
    retriever.index = MagicMock()
    retriever.index.search.side_effect = Exception("index corrupted")
    retriever.model = MagicMock()
    retriever.model.encode.return_value = [[0.0, 0.1]]
    assert retriever.retrieve("loops") == []
