import faiss
import pickle
from sentence_transformers import SentenceTransformer


class CodeRetriever:
    def __init__(self, index_path="rag/faiss_index/index.faiss",
                 metadata_path="rag/faiss_index/metadata.pkl"):

        self.index = faiss.read_index(index_path)

        with open(metadata_path, "rb") as f:
            self.metadata = pickle.load(f)

        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def retrieve(self, query, top_k=3):

        query_embedding = self.model.encode([query])

        distances, indices = self.index.search(query_embedding, top_k)

        results = []

        for idx in indices[0]:
            results.append(self.metadata[idx])

        return results