# ==========================================================
# File: vector_store.py
# Purpose: Store and retrieve AI code reviews using ChromaDB
# ==========================================================

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions


PERSIST_DIRECTORY = "rag/chroma_db"

MODEL_NAME = "all-MiniLM-L6-v2"


class ReviewVectorStore:
    """
    Vector store for storing and retrieving AI-generated
    code review reports.
    """

    def __init__(self):

        # Persistent ChromaDB client
        self.client = chromadb.Client(
            Settings(
                persist_directory=PERSIST_DIRECTORY,
                anonymized_telemetry=False
            )
        )

        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=MODEL_NAME
        )

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