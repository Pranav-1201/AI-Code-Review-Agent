# ==========================================================
# File: rag_ingest.py
# Purpose: Build FAISS vector index for RAG retrieval
# ==========================================================

import os
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS


# ----------------------------------------------------------
# Paths
# ----------------------------------------------------------

DATA_PATH = Path("rag/data/guidelines.txt")
INDEX_PATH = Path("rag/faiss_index")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ----------------------------------------------------------
# Build FAISS Index
# ----------------------------------------------------------

def build_faiss_index():
    """
    Builds a FAISS vector index from guideline documents.
    """

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Data file not found: {DATA_PATH}")

    # ------------------------------------------------------
    # Load text data
    # ------------------------------------------------------

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    print(f"Loaded guideline file ({len(text)} characters)")

    # ------------------------------------------------------
    # Split text into chunks
    # ------------------------------------------------------

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=80
    )

    docs = splitter.create_documents([text])

    print(f"Created {len(docs)} chunks")

    # ------------------------------------------------------
    # Load embedding model
    # ------------------------------------------------------

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    # ------------------------------------------------------
    # Create FAISS index
    # ------------------------------------------------------

    vectorstore = FAISS.from_documents(docs, embeddings)

    INDEX_PATH.mkdir(parents=True, exist_ok=True)

    vectorstore.save_local(str(INDEX_PATH))

    print("FAISS index built successfully")
    print(f"Index saved at: {INDEX_PATH}")


# ----------------------------------------------------------
# CLI Entry Point
# ----------------------------------------------------------

if __name__ == "__main__":
    build_faiss_index()