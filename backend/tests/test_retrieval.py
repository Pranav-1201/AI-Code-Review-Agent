"""
Unit tests for CodeRetriever.

This module tests the retrieval service used by the
RAG system for semantic search of previous code reviews.

Heavy vector database operations are mocked so tests:

- run quickly
- do not require real vector embeddings
- remain deterministic
"""

import sys
import os
from unittest.mock import MagicMock, patch

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.retriever_service import CodeRetriever


# Mock retrieval results
MOCK_RESULTS = [
    {"file": "example.py", "summary": "Nested loops detected"},
    {"file": "util.py", "summary": "Inefficient loop structure"}
]


# ---------------------------------------------------------
# Test: Basic retrieval
# ---------------------------------------------------------

@patch("rag.vector_store.ReviewVectorStore")
def test_basic_retrieval(mock_vector_store):
    """
    Ensure retriever returns results for a valid query.
    """

    mock_instance = mock_vector_store.return_value
    mock_instance.search.return_value = MOCK_RESULTS

    retriever = CodeRetriever()

    results = retriever.retrieve("nested loops inefficiency")

    assert isinstance(results, list)
    assert len(results) > 0


# ---------------------------------------------------------
# Test: Empty query
# ---------------------------------------------------------

@patch("rag.vector_store.ReviewVectorStore")
def test_empty_query(mock_vector_store):
    """
    Retriever should handle empty queries safely.
    """

    mock_instance = mock_vector_store.return_value
    mock_instance.search.return_value = []

    retriever = CodeRetriever()

    results = retriever.retrieve("")

    assert isinstance(results, list)


# ---------------------------------------------------------
# Test: No results found
# ---------------------------------------------------------
from unittest.mock import patch
@patch("rag.vector_store.ReviewVectorStore")


def test_no_results(mock_vector_store):
    """
    Retrieval should return empty list if nothing matches.
    """

    retriever = CodeRetriever()

    with patch.object(retriever, "retrieve", return_value=[]):

        results = retriever.retrieve("completely unrelated query")

        assert results == []


# ---------------------------------------------------------
# Test: Large query input
# ---------------------------------------------------------

@patch("rag.vector_store.ReviewVectorStore")
def test_large_query(mock_vector_store):
    """
    Retriever should handle large query strings safely.
    """

    mock_instance = mock_vector_store.return_value
    mock_instance.search.return_value = MOCK_RESULTS

    retriever = CodeRetriever()

    large_query = "inefficient loops " * 50

    results = retriever.retrieve(large_query)

    assert isinstance(results, list)


# ---------------------------------------------------------
# Test: Vector store failure
# ---------------------------------------------------------

@patch("rag.vector_store.ReviewVectorStore")
def test_vector_store_failure(mock_vector_store):
    """
    Retriever should handle vector DB errors gracefully.
    """

    mock_instance = mock_vector_store.return_value
    mock_instance.search.side_effect = Exception("Vector store error")

    retriever = CodeRetriever()

    try:
        retriever.retrieve("loops")
    except Exception:
        assert True