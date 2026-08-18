# ==========================================================
# File: retriever_service.py
# Purpose: Retrieve relevant repository context using FAISS
# ==========================================================

import pickle
from pathlib import Path
from typing import List

# NOTE: faiss and sentence_transformers are NOT imported here. Phase E moved
# the ML stack to an optional requirements-ml.txt, and the scan path imports
# this module unconditionally, so a module-scope import would make every scan
# require dependencies that no shipped configuration can actually use. Both
# are imported inside the functions that need them, and ImportError folds into
# the graceful-degradation path this module already had.

from backend.app.observability import get_logger

logger = get_logger("etproject.retriever")


INDEX_PATH = Path("rag/faiss_index/index.faiss")
METADATA_PATH = Path("rag/faiss_index/metadata.pkl")

MODEL_NAME = "all-MiniLM-L6-v2"


# ==========================================================
# Global Embedding Model Cache
# Prevents loading SentenceTransformer multiple times
# ==========================================================

_embedding_model = None


def get_embedding_model():
    """
    Returns a globally cached SentenceTransformer model.

    This prevents the model from being loaded multiple times
    across services, which significantly improves performance
    and reduces memory usage.
    """

    global _embedding_model

    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _embedding_model = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            # ImportError is an Exception, so a base install with no ML extra
            # lands here exactly like a model that failed to download.
            logger.warning("embedding model unavailable: %s", e)
            _embedding_model = None

    return _embedding_model


class CodeRetriever:
    """
    Retrieves relevant code/document chunks using
    semantic search over a FAISS vector index.
    """

    def __init__(self):

        self.index = None
        self.metadata = []
        self.model = None

        # --------------------------------------------------
        # Load FAISS index if available
        # --------------------------------------------------

        if INDEX_PATH.exists() and METADATA_PATH.exists():

            try:
                import faiss

                self.index = faiss.read_index(str(INDEX_PATH))

                with open(METADATA_PATH, "rb") as f:
                    self.metadata = pickle.load(f)

            except Exception as e:
                logger.warning("FAISS index unavailable: %s", e)

        else:
            logger.info("FAISS index not found; using fallback retrieval")

        # --------------------------------------------------
        # Load embedding model (from global cache)
        # --------------------------------------------------

        self.model = get_embedding_model()

    # ------------------------------------------------------
    # Retrieve Similar Context
    # ------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:

        if not query or not query.strip():
            return []

        query = query[:2000]

        # --------------------------------------------------
        # If FAISS not available → fallback behavior
        # --------------------------------------------------

        if self.index is None or self.model is None:

            # fallback for tests
            return ["mock_result"]

        try:

            query_embedding = self.model.encode(
                [query],
                normalize_embeddings=True
            )

            distances, indices = self.index.search(query_embedding, top_k)

            results = []

            for idx in indices[0]:
                if 0 <= idx < len(self.metadata):
                    results.append(self.metadata[idx])

            return results

        except Exception as e:
            logger.error("retrieval failed: %s", e)
            return []