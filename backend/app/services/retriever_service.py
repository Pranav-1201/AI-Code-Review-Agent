# ==========================================================
# File: retriever_service.py
# Purpose: Retrieve relevant repository context using FAISS
# ==========================================================

import faiss
import pickle
from pathlib import Path
from typing import List

from sentence_transformers import SentenceTransformer


INDEX_PATH = Path("rag/faiss_index/index.faiss")
METADATA_PATH = Path("rag/faiss_index/metadata.pkl")

MODEL_NAME = "all-MiniLM-L6-v2"


class CodeRetriever:
    """
    Retrieves relevant code/document chunks using
    semantic search over a FAISS vector index.
    """

    def __init__(self):

        if not INDEX_PATH.exists():
            raise FileNotFoundError(f"FAISS index not found: {INDEX_PATH}")

        if not METADATA_PATH.exists():
            raise FileNotFoundError(f"Metadata file not found: {METADATA_PATH}")

        # Load FAISS index
        self.index = faiss.read_index(str(INDEX_PATH))

        # Load metadata
        with open(METADATA_PATH, "rb") as f:
            self.metadata = pickle.load(f)

        # Load embedding model
        self.model = SentenceTransformer(MODEL_NAME)

    # ------------------------------------------------------
    # Retrieve Similar Context
    # ------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:

        if not query.strip():
            return []

        # limit query length (important!)
        query = query[:2000]

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