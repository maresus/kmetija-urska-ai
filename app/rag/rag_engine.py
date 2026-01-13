import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class KnowledgeItem:
    url: str
    title: str
    content: str


class RAGEngine:
    def __init__(self, knowledge_path: Path | None = None) -> None:
        if knowledge_path is None:
            knowledge_path = Path(__file__).with_name("knowledge.jsonl")

        self.items: List[KnowledgeItem] = []
        if knowledge_path.exists():
            with knowledge_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    url = data.get("url", "")
                    title = data.get("title", "")
                    content = data.get("content", "") or ""
                    if not (url or title or content):
                        continue
                    self.items.append(KnowledgeItem(url=url, title=title, content=content))

    def _score(self, question: str, text: str) -> int:
        q = question.lower()
        t = text.lower()
        words = [w for w in q.replace("?", " ").replace(",", " ").split() if len(w) >= 3]
        if not words:
            return 0
        score = 0
        for w in words:
            if w in t:
                score += 1
        return score

    def search(self, question: str, top_k: int = 3) -> List[KnowledgeItem]:
        scored: list[tuple[int, KnowledgeItem]] = []
        for item in self.items:
            text = f"{item.title} {item.content}"
            score = self._score(question, text)
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for score, item in scored[:top_k]]

    def answer(self, question: str) -> str:
        results = self.search(question, top_k=3)
        if not results:
            return (
                "Na to vprašanje trenutno nimam natančnega odgovora na podlagi podatkov, "
                "ki jih imam. Predlagam, da nas kontaktirate na urska@kmetija-urska.si ali po telefonu."
            )

        best = results[0]
        content = best.content.strip()
        if not content:
            return (
                "Na to vprašanje trenutno nimam natančnega odgovora na podlagi podatkov, "
                "ki jih imam. Predlagam, da nas kontaktirate na urska@kmetija-urska.si ali po telefonu."
            )

        max_len = 800
        if len(content) > max_len:
            snippet = content[:max_len]
            last_dot = snippet.rfind(".")
            if last_dot > 200:
                snippet = snippet[: last_dot + 1]
        else:
            snippet = content

        reply = (
            "Na podlagi informacij iz naše spletne strani lahko povzamem takole:\n\n"
            f"{snippet}\n\n"
            f"Več informacij: {best.url}"
        )
        return reply


rag_engine = RAGEngine()
