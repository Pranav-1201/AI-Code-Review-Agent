import chromadb
from chromadb.utils import embedding_functions

class ReviewVectorStore:

    def __init__(self):
        self.client = chromadb.Client()

        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        self.collection = self.client.get_or_create_collection(
            name="code_reviews",
            embedding_function=embedding_function
        )

    def add_review(self, review_id, review_text):
        self.collection.add(
            documents=[review_text],
            ids=[str(review_id)]
        )

    def search_similar_reviews(self, query, k=3):
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )

        return results["documents"][0]