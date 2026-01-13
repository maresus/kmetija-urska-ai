from __future__ import annotations

import re
from typing import List, Set

from app.rag.knowledge_base import KNOWLEDGE_CHUNKS, KnowledgeChunk

STOPWORDS = {
    "in",
    "ali",
    "ter",
    "za",
    "na",
    "se",
    "je",
    "smo",
    "so",
    "sem",
    "pri",
    "ki",
    "kje",
    "kaj",
    "kako",
    "koliko",
    "kdo",
    "od",
    "do",
    "the",
    "and",
    "of",
    "for",
    "with",
    "a",
    "an",
    "to",
}


def _tokenize(text: str) -> Set[str]:
    lowered = text.lower()
    cleaned = re.sub(r"[^\w]+", " ", lowered)
    return {token for token in cleaned.split() if len(token) >= 3}


def _score_chunk(question_tokens: Set[str], chunk: KnowledgeChunk) -> float:
    paragraph_tokens = _tokenize(chunk.paragraph) - STOPWORDS
    title_tokens = _tokenize(chunk.title) - STOPWORDS
    if not paragraph_tokens:
        return 0.0
    overlap_paragraph = len(question_tokens & paragraph_tokens)
    overlap_title = len(question_tokens & title_tokens)
    return overlap_paragraph + 0.5 * overlap_title


def answer_from_knowledge(question: str, top_k: int = 3) -> str:
    if not KNOWLEDGE_CHUNKS:
        return (
            "Trenutno nimam dostopa do podatkov s spletne strani Urška. "
            "Poskusite kasneje ali preverite www.kmetija-urska.si."
        )

    question_tokens = _tokenize(question) - STOPWORDS
    if not question_tokens:
        return (
            "Na podlagi dosedanjih podatkov težko razumem vprašanje. "
            "Poskusite vprašati npr. 'Kaj ponujate za vikend kosila?' ali 'Koliko nočitev najmanj moram rezervirati julija?'"
        )

    scored: List[tuple[float, KnowledgeChunk]] = []
    for chunk in KNOWLEDGE_CHUNKS:
        score = _score_chunk(question_tokens, chunk)
        if score > 0:
            scored.append((score, chunk))

    if not scored:
        return (
            "Trenutno v podatkih ne najdem jasnega odgovora na to vprašanje. "
            "Predlagam, da nas kontaktirate preko urska@kmetija-urska.si ali preverite www.kmetija-urska.si."
        )

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_chunks = [chunk for _, chunk in scored[:top_k]]

    unique_urls: list[KnowledgeChunk] = []
    seen = set()
    for chunk in top_chunks:
        if chunk.url not in seen:
            unique_urls.append(chunk)
            seen.add(chunk.url)

    paragraph_text = "\n\n".join(chunk.paragraph for chunk in top_chunks)

    sources_lines = ["Več informacij:"]
    for chunk in unique_urls:
        label = chunk.title or "Vir"
        sources_lines.append(f"• {label} – {chunk.url}")

    return (
        "Na podlagi informacij iz naše spletne strani lahko povzamem takole:\n\n"
        f"{paragraph_text}\n\n"
        + "\n".join(sources_lines)
    )
