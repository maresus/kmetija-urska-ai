import shutil
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.rag.knowledge_base import load_knowledge_chunks


def main() -> None:
    chroma_path = BASE_DIR / "data" / "chroma_db"

    if chroma_path.exists():
        shutil.rmtree(chroma_path)

    chroma_path.mkdir(parents=True, exist_ok=True)

    embed_fn = embedding_functions.DefaultEmbeddingFunction()
    client = chromadb.PersistentClient(
        path=str(chroma_path), settings=Settings(anonymized_telemetry=False)
    )

    collection = client.create_collection(
        name="urska_knowledge", embedding_function=embed_fn
    )

    chunks = load_knowledge_chunks()
    if not chunks:
        print("Ni najdenih knowledge chunkov.")
        return

    documents = []
    metadatas = []
    ids = []

    for idx, chunk in enumerate(chunks):
        documents.append(chunk.paragraph)
        metadatas.append({"title": chunk.title, "url": chunk.url})
        ids.append(f"chunk-{idx}")

    collection.add(documents=documents, metadatas=metadatas, ids=ids)
    print(f"Chroma rebuilt: {len(documents)} dokumentov.")


if __name__ == "__main__":
    main()
