"""
Simplified RAG search for Kovačnik V2.
Uses BM25 for keyword matching.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Chunk:
    title: str
    paragraph: str
    url: str | None = None


# Global storage
_CHUNKS: list[Chunk] = []
_BM25_INDEX: dict[str, list[tuple[int, float]]] = {}  # term -> [(doc_idx, tf), ...]
_DOC_LENGTHS: list[int] = []
_AVG_DOC_LEN: float = 0.0


def _tokenize(text: str) -> list[str]:
    """Simple tokenization: lowercase, split on non-alphanumeric."""
    return [t for t in re.split(r'[^a-zA-ZčšžćđČŠŽĆĐ0-9]+', text.lower()) if len(t) >= 2]


def load_knowledge(path: str | Path) -> int:
    """Load knowledge base from JSONL file."""
    global _CHUNKS, _BM25_INDEX, _DOC_LENGTHS, _AVG_DOC_LEN

    path = Path(path)
    if not path.exists():
        return 0

    _CHUNKS = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                _CHUNKS.append(Chunk(
                    title=obj.get('title', ''),
                    paragraph=obj.get('content', '') or obj.get('paragraph', ''),
                    url=obj.get('url'),
                ))
            except json.JSONDecodeError:
                continue

    # Build BM25 index
    _BM25_INDEX = {}
    _DOC_LENGTHS = []

    for idx, chunk in enumerate(_CHUNKS):
        text = f"{chunk.title} {chunk.paragraph}"
        tokens = _tokenize(text)
        _DOC_LENGTHS.append(len(tokens))

        # Count term frequencies
        tf_map: dict[str, int] = {}
        for token in tokens:
            tf_map[token] = tf_map.get(token, 0) + 1

        for term, count in tf_map.items():
            if term not in _BM25_INDEX:
                _BM25_INDEX[term] = []
            _BM25_INDEX[term].append((idx, count))

    _AVG_DOC_LEN = sum(_DOC_LENGTHS) / len(_DOC_LENGTHS) if _DOC_LENGTHS else 1.0

    return len(_CHUNKS)


def search(query: str, top_k: int = 3) -> list[Chunk]:
    """Search knowledge base using BM25."""
    if not _CHUNKS:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # BM25 parameters
    k1 = 1.5
    b = 0.75
    n_docs = len(_CHUNKS)

    scores: dict[int, float] = {}

    for token in query_tokens:
        if token not in _BM25_INDEX:
            continue

        postings = _BM25_INDEX[token]
        df = len(postings)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)

        for doc_idx, tf in postings:
            doc_len = _DOC_LENGTHS[doc_idx]
            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / _AVG_DOC_LEN))
            score = idf * tf_norm
            scores[doc_idx] = scores.get(doc_idx, 0) + score

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [_CHUNKS[idx] for idx, _ in ranked[:top_k]]


def get_context(query: str, top_k: int = 3) -> str:
    """Get context string for LLM from top matching chunks."""
    chunks = search(query, top_k)
    if not chunks:
        return ""

    parts = []
    for chunk in chunks:
        text = chunk.paragraph.strip()
        if chunk.title:
            text = f"[{chunk.title}] {text}"
        parts.append(text)

    return "\n\n".join(parts)
