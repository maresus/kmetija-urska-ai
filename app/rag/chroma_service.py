"""
ChromaDB Service za iskanje v lokalnih turističnih podatkih.
Uporablja se za turistična vprašanja o okolici.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("[chroma_service] ChromaDB ni nameščen. Poženi: pip install chromadb")

# Pot do ChromaDB baze
BASE_DIR = Path(__file__).resolve().parents[2]
CHROMA_PATH = BASE_DIR / "data" / "chroma_db"

# Turistično relevantne kategorije
TOURIST_CATEGORIES = ["Novice", "Dogodki in priznanja", "O občini"]

# Ključne besede za turistična vprašanja
TOURIST_KEYWORDS = [
    "okolica",
    "izlet",
    "obiščem",
    "obiščemo",
    "znamenitost",
    "turizem",
    "restavracija",
    "gostilna",
    "kmetija",
    "dogodek",
    "prireditev",
    "pohorje",
    "slap",
    "jezero",
    "narava",
    "šport",
    "kolesarjenje",
    "pohodništvo",
    "jahanje",
    "otroci",
    "družina",
    "vikend",
    "areh",
    "kam",
    "kje",
    "kaj početi",
    "kaj delati",
    "v bližini",
    "blizu",
]


def is_chroma_available() -> bool:
    """Preveri ali je ChromaDB na voljo."""
    return CHROMA_AVAILABLE and CHROMA_PATH.exists()


def is_tourist_query(question: str) -> bool:
    """Preveri ali je vprašanje turistično (o okolici)."""
    lowered = question.lower()
    return any(keyword in lowered for keyword in TOURIST_KEYWORDS)


def search_chroma(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Išče v ChromaDB bazi občinskih podatkov.

    Args:
        query: Iskalni niz
        top_k: Število rezultatov

    Returns:
        Lista rezultatov z document, metadata
    """
    if not is_chroma_available():
        return []

    try:
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH), settings=Settings(anonymized_telemetry=False)
        )

        collections = client.list_collections()
        if not collections:
            return []

        collection = client.get_collection(collections[0].name)

        results = collection.query(
            query_texts=[query], n_results=top_k, include=["documents", "metadatas", "distances"]
        )

        formatted: List[Dict[str, Any]] = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0

                category = metadata.get("category", "")
                if category in TOURIST_CATEGORIES or distance < 0.5:
                    formatted.append(
                        {
                            "document": doc,
                            "title": metadata.get("title", ""),
                            "category": category,
                            "source_url": metadata.get("source_url", ""),
                            "distance": distance,
                        }
                    )

        return formatted[:top_k]

    except Exception as e:
        print(f"[chroma_service] Napaka pri iskanju: {e}")
        return []


def format_tourist_info(results: List[Dict[str, Any]]) -> str:
    """Formatira rezultate ChromaDB v berljiv tekst."""
    if not results:
        return ""

    parts = []
    for r in results:
        title = r.get("title", "Brez naslova")
        doc = r.get("document", "")[:500]
        source = r.get("source_url", "")

        part = f"**{title}**\n{doc}"
        if source:
            part += f"\nVir: {source}"
        parts.append(part)

    return "\n\n---\n\n".join(parts)


def answer_tourist_question(question: str) -> Optional[str]:
    """
    Odgovori na turistično vprašanje z uporabo ChromaDB.
    Vrne None če ni relevantnih rezultatov.
    """
    if not is_tourist_query(question):
        return None

    results = search_chroma(question, top_k=3)
    if not results:
        return None

    relevant = [r for r in results if r.get("distance", 1) < 1.0]
    if not relevant:
        return None

    intro = "Na podlagi informacij o okolici:\n\n"
    content = format_tourist_info(relevant)

    return intro + content


def test_chroma() -> None:
    """Testira ChromaDB povezavo."""
    print(f"ChromaDB dostopen: {is_chroma_available()}")
    print(f"Pot: {CHROMA_PATH}")

    if is_chroma_available():
        results = search_chroma("izlet pohorje", top_k=3)
        print(f"Rezultati za 'izlet pohorje': {len(results)}")
        for r in results:
            print(f"  - {r.get('title', 'Brez naslova')[:50]}...")


if __name__ == "__main__":
    test_chroma()
