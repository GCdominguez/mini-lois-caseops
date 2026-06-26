from __future__ import annotations

import hashlib
from pathlib import Path

import chromadb

from rag import CHROMA_DIR, COLLECTION_NAME, DEFAULT_EMBED_MODEL, embed_text

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "data" / "docs"


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    clean = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not clean:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + chunk_size, len(clean))
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def matter_id_from_filename(path: Path) -> str:
    return path.name.split("_")[0]


def reset_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    return client.get_or_create_collection(name=COLLECTION_NAME)


def main() -> None:
    collection = reset_collection()
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, object]] = []
    embeddings: list[list[float]] = []

    for path in sorted(DOCS_DIR.glob("*.txt")):
        matter_id = matter_id_from_filename(path)
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        for index, chunk in enumerate(chunks):
            stable_id = hashlib.sha1(f"{path.name}:{index}".encode("utf-8")).hexdigest()
            ids.append(stable_id)
            docs.append(chunk)
            metas.append(
                {
                    "matter_id": matter_id,
                    "source_file": path.name,
                    "chunk_index": index,
                }
            )
            embeddings.append(embed_text(chunk, model=DEFAULT_EMBED_MODEL))

    if not ids:
        raise RuntimeError(f"No .txt files found in {DOCS_DIR}")

    collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
    print(f"Ingested {len(ids)} chunks into Chroma collection '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
