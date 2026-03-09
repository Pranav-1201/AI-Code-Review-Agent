import os
import faiss
import pickle
from sentence_transformers import SentenceTransformer

# Folder containing code to index
CODE_FOLDER = "rag/data"

# Output files
INDEX_PATH = "rag/faiss_index/index.faiss"
METADATA_PATH = "rag/faiss_index/metadata.pkl"

model = SentenceTransformer("all-MiniLM-L6-v2")

documents = []

# Read all code files
for root, dirs, files in os.walk(CODE_FOLDER):
    for file in files:
        if file.endswith((".py", ".cpp", ".js", ".java")):
            path = os.path.join(root, file)

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()

            documents.append(code)

# Generate embeddings
embeddings = model.encode(documents)

dimension = embeddings.shape[1]

# Build FAISS index
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

# Save index
faiss.write_index(index, INDEX_PATH)

# Save metadata
with open(METADATA_PATH, "wb") as f:
    pickle.dump(documents, f)

print("FAISS index built successfully")