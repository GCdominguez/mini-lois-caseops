from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import chromadb
import ollama

BASE_DIR = Path(__file__).resolve().parent
CHROMA_DIR = BASE_DIR / ".chroma"
COLLECTION_NAME = "matter_docs"
DEFAULT_LLM_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
DEFAULT_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name=COLLECTION_NAME)


def embed_text(text: str, model: str = DEFAULT_EMBED_MODEL) -> list[float]:
    response = ollama.embed(model=model, input=text)
    if "embeddings" in response:
        return response["embeddings"][0]
    if "embedding" in response:
        return response["embedding"]
    raise RuntimeError("Unexpected Ollama embedding response shape.")


def retrieve_chunks(
    question: str,
    matter_id: str,
    n_results: int = 5,
    embed_model: str = DEFAULT_EMBED_MODEL,
) -> list[dict[str, Any]]:
    collection = get_collection()
    query_embedding = embed_text(question, model=embed_model)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={"matter_id": matter_id},
        include=["documents", "metadatas", "distances"],
    )

    chunks: list[dict[str, Any]] = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for idx, document in enumerate(documents):
        meta = metadatas[idx] or {}
        chunks.append(
            {
                "source_id": f"S{idx + 1}",
                "text": document,
                "matter_id": meta.get("matter_id"),
                "source_file": meta.get("source_file"),
                "chunk_index": meta.get("chunk_index"),
                "distance": distances[idx] if idx < len(distances) else None,
            }
        )
    return chunks


def build_context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for chunk in chunks:
        parts.append(
            f"[{chunk['source_id']}] source_file={chunk.get('source_file')} "
            f"chunk={chunk.get('chunk_index')}\n{chunk['text']}"
        )
    return "\n\n---\n\n".join(parts)


def answer_question(
    question: str,
    matter: dict[str, Any],
    model: str = DEFAULT_LLM_MODEL,
    embed_model: str = DEFAULT_EMBED_MODEL,
) -> tuple[str, list[dict[str, Any]]]:
    chunks = retrieve_chunks(question, matter["matter_id"], embed_model=embed_model)
    context = build_context(chunks)

    system = """
You are Mini LOIS, a local prototype of a legal operations assistant.
Answer only from the supplied matter context. If the answer is not supported by the context, say what is missing.
Cite sources inline using [S1], [S2], etc. Do not provide legal advice. Keep answers practical and concise.
""".strip()

    user = f"""
Matter metadata:
{matter}

Matter context:
{context}

Question:
{question}
""".strip()

    response = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        options={"temperature": 0.1},
    )
    return response["message"]["content"], chunks
