# ==========================================================
# File: ingest.py
# Purpose: Build FAISS vector index for repository code
# ==========================================================

import os
import faiss
import pickle
from pathlib import Path
from sentence_transformers import SentenceTransformer


CODE_FOLDER = Path("rag/data")
INDEX_DIR = Path("rag/faiss_index")

INDEX_PATH = INDEX_DIR / "index.faiss"
METADATA_PATH = INDEX_DIR / "metadata.pkl"

MODEL_NAME = "all-MiniLM-L6-v2"


def load_documents():

    documents = []

    for root, dirs, files in os.walk(CODE_FOLDER):

        for file in files:

            if file.endswith((".py", ".cpp", ".js", ".java")):

                path = Path(root) / file

                try:
                    code = path.read_text(encoding="utf-8", errors="ignore")

                    documents.append({
                        "file_path": str(path),
                        "content": code
                    })

                except Exception as e:
                    print(f"Failed to read {path}: {e}")

    return documents


def build_index():

    documents = load_documents()

    if not documents:
        raise ValueError("No documents found for indexing")

    texts = [doc["content"] for doc in documents]

    print(f"Embedding {len(texts)} documents")

    model = SentenceTransformer(MODEL_NAME)

    embeddings = model.encode(texts)

    dimension = embeddings.shape[1]

    index = faiss.IndexFlatL2(dimension)

    index.add(embeddings)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(INDEX_PATH))

    with open(METADATA_PATH, "wb") as f:
        pickle.dump(documents, f)

    print("FAISS index built successfully")


if __name__ == "__main__":
    build_index()