# ==========================================================
# File: vector_store.py
# Purpose: Store and retrieve AI code reviews using ChromaDB
# ==========================================================

import chromadb
from chromadb.config import Settings
from typing import List

# Use the global embedding model cache
from backend.app.services.retriever_service import get_embedding_model


PERSIST_DIRECTORY = "rag/chroma_db"

MODEL_NAME = "all-MiniLM-L6-v2"


# ==========================================================
# Custom Embedding Function (uses global model cache)
# ==========================================================

class CachedEmbeddingFunction:
    """
    Custom embedding function for ChromaDB that uses the
    globally cached SentenceTransformer model.

    This prevents the model from being loaded multiple times
    across different services.
    """

    def __init__(self):
        self.model = get_embedding_model()

    def __call__(self, texts: List[str]):

        if not texts:
            return []

        if self.model is None:
            return []

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=32,
                normalize_embeddings=True
            )
            return embeddings.tolist()

        except Exception as e:
            print(f"[VectorStore Error] Embedding generation failed: {e}")
            return []


class ReviewVectorStore:
    """
    Vector store for storing and retrieving AI-generated
    code review reports.
    """

    def __init__(self):

        # --------------------------------------------------
        # Persistent ChromaDB client
        # --------------------------------------------------

        self.client = chromadb.Client(
            Settings(
                persist_directory=PERSIST_DIRECTORY,
                anonymized_telemetry=False
            )
        )

        # --------------------------------------------------
        # Use cached embedding model
        # --------------------------------------------------

        embedding_function = CachedEmbeddingFunction()

        self.collection = self.client.get_or_create_collection(
            name="code_reviews",
            embedding_function=embedding_function
        )

    # ------------------------------------------------------
    # Add Review
    # ------------------------------------------------------

    def add_review(self, review_id: int, review_text: str):

        if not review_text.strip():
            return

        self.collection.add(
            documents=[review_text],
            ids=[str(review_id)]
        )

    # ------------------------------------------------------
    # Search Similar Reviews
    # ------------------------------------------------------

    def search_similar_reviews(self, query: str, k: int = 3):

        if not query.strip():
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )

        return results.get("documents", [[]])[0]