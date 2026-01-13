from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

from app.core.llm_client import get_llm_client

BASE_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_PATH = BASE_DIR / "knowledge.jsonl"


@dataclass
class KnowledgeChunk:
    url: str
    title: str
    paragraph: str


IMPORTANT_TERMS = (
    "jahanje",
    "jahamo",
    "ponij",
    "bunka",
    "marmelad",
    "salama",
    "klobasa",
    "liker",
)


def _split_into_paragraphs(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for raw in normalized.split("\n"):
        chunk = raw.strip()
        if not chunk:
            continue
        lowered = chunk.lower()
        # kratke vrstice obdržimo, če imajo pomembne izraze (jahanje, bunka, salama …)
        if len(chunk) < 40 and not any(term in lowered for term in IMPORTANT_TERMS):
            continue
        paragraphs.append(chunk)
    return paragraphs


def load_knowledge_chunks() -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    if not KNOWLEDGE_PATH.exists():
        print(f"[knowledge_base] Datoteka {KNOWLEDGE_PATH} ne obstaja. Vračam prazen seznam.")
        return chunks

    with KNOWLEDGE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = record.get("url", "") or ""
            title = record.get("title", "") or ""
            content = record.get("content", "") or ""
            if not (url or title or content):
                continue
            for paragraph in _split_into_paragraphs(content):
                chunks.append(KnowledgeChunk(url=url, title=title, paragraph=paragraph))

    print(f"[knowledge_base] Naloženih {len(chunks)} odstavkov")
    return chunks


KNOWLEDGE_CHUNKS: List[KnowledgeChunk] = load_knowledge_chunks()

CONTACT = {
    "phone": "03 759 04 10, 031 249 812",
    "email": "urska@kmetija-urska.si",
}


def _tokenize(text: str) -> Set[str]:
    lowered = text.lower()
    cleaned = re.sub(r"[^\w]+", " ", lowered)
    return {token for token in cleaned.split() if len(token) >= 3}


def _score_chunk(tokens: Set[str], chunk: KnowledgeChunk) -> float:
    paragraph_tokens = _tokenize(chunk.paragraph)
    if not paragraph_tokens:
        return 0.0
    title_tokens = _tokenize(chunk.title)
    overlap_para = len(tokens & paragraph_tokens)
    overlap_title = len(tokens & title_tokens)
    return overlap_para + 0.5 * overlap_title


def _score_chunk_ratio(tokens: Set[str], chunk: KnowledgeChunk, base_len: int) -> float:
    if not tokens or base_len <= 0:
        return 0.0
    paragraph_tokens = _tokenize(chunk.paragraph)
    if not paragraph_tokens:
        return 0.0
    title_tokens = _tokenize(chunk.title)
    overlap_para = len(tokens & paragraph_tokens)
    overlap_title = len(tokens & title_tokens)
    raw = overlap_para + 0.5 * overlap_title
    return raw / max(1.0, float(base_len))


def _expand_query_tokens(query: str, tokens: Set[str]) -> Set[str]:
    lowered = query.lower()
    expanded = set(tokens)
    if "konj" in lowered or "konja" in lowered:
        expanded.update({"poni", "ponij", "ponija", "jahanje"})
    if "jah" in lowered:
        expanded.update({"jahanje", "poni", "ponij", "ponija"})
    return expanded


def search_knowledge_scored(query: str, top_k: int = 3) -> list[tuple[float, KnowledgeChunk]]:
    base_tokens = _tokenize(query)
    tokens = _expand_query_tokens(query, base_tokens)
    base_len = len(base_tokens)
    if not tokens:
        return []
    lowered = query.lower()
    candidates = None
    for patterns in KEYWORD_RULES.values():
        if any(term in lowered for term in patterns):
            candidates = []
            for chunk in KNOWLEDGE_CHUNKS:
                chunk_text = f"{chunk.title.lower()} {chunk.paragraph.lower()} {chunk.url.lower()}"
                if any(term in chunk_text for term in patterns):
                    candidates.append(chunk)
            break
    # Če je vprašanje o jahanju/poniju, preferiraj specifične odstavke
    if any(term in lowered for term in ["jahanje", "jahati", "jahamo", "poni", "ponij", "konj", "konja"]):
        filtered = []
        source = candidates if candidates is not None else KNOWLEDGE_CHUNKS
        for chunk in source:
            chunk_text = f"{chunk.title.lower()} {chunk.paragraph.lower()} {chunk.url.lower()}"
            if "ponij" in chunk_text or "jahanje" in chunk_text:
                filtered.append(chunk)
        if filtered:
            candidates = filtered
    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk in (candidates if candidates is not None else KNOWLEDGE_CHUNKS):
        score = _score_chunk_ratio(tokens, chunk, base_len)
        if score > 0:
            scored.append((score, chunk))
    if any(term in lowered for term in ["jahanje", "jahati", "jahamo", "poni", "ponij", "konj", "konja"]):
        boosted: list[tuple[float, KnowledgeChunk]] = []
        for score, chunk in scored:
            chunk_text = f"{chunk.title.lower()} {chunk.url.lower()}"
            if "ponij" in chunk_text or "jahanje" in chunk_text:
                score += 1.0
            boosted.append((score, chunk))
        scored = boosted
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:top_k]


def search_knowledge(query: str, top_k: int = 5) -> list[KnowledgeChunk]:
    tokens = _tokenize(query)
    if not tokens:
        return []
    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk in KNOWLEDGE_CHUNKS:
        score = _score_chunk(tokens, chunk)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


KEYWORD_RULES = {
    "salama": ["salama", "salamo", "salame", "klobasa", "klobaso", "mesni izdelki", "klobase"],
    "bunka": ["bunka", "bunko", "bunke", "pohorska bunka"],
    "marmelada": ["marmelada", "marmelado", "marmelade", "marmeldo", "džem", "namaz", "marmelad"],
    "liker": ["liker", "likerje", "žganje", "žganja", "tepkovec"],
    "jahanje": ["jahanje", "jahati", "jahamo", "poni", "ponij", "ponija", "ponijem"],
    "nočitev": ["nočitev", "nočitve", "noči"],
    "kosilo": ["vikend kosilo", "degustacijski", "degustacijo", "kosilo"],
}


def _collect_focus_terms(question: str) -> list[str]:
    lowered = question.lower()
    focus: list[str] = []
    for patterns in KEYWORD_RULES.values():
        if any(term in lowered for term in patterns):
            focus.extend(patterns)
    if not focus:
        focus.extend(IMPORTANT_TERMS)
    return list({term for term in focus if len(term) >= 3})


def _trim_content(content: str, focus_terms: list[str]) -> str:
    if len(content) <= 700:
        return content
    content_lower = content.lower()
    for term in focus_terms:
        idx = content_lower.find(term)
        if idx != -1:
            start = max(0, idx - 200)
            end = min(len(content), idx + 500)
            snippet = content[start:end]
            start_dot = snippet.find(". ")
            if start > 0 and start_dot != -1:
                snippet = snippet[start_dot + 1 :]
            return snippet.strip()
    snippet = content[:700]
    last_dot = snippet.rfind(".")
    if last_dot > 200:
        snippet = snippet[: last_dot + 1]
    return snippet


def _build_context_snippet(question: str, paragraphs: List[KnowledgeChunk]) -> str:
    focus_terms = _collect_focus_terms(question)
    parts: list[str] = []
    for chunk in paragraphs:
        lines: list[str] = []
        if chunk.title:
            lines.append(f"Naslov: {chunk.title}")
        if chunk.url:
            lines.append(f"URL: {chunk.url}")
        content = _trim_content(chunk.paragraph.strip(), focus_terms)
        lines.append(f"Vsebina: {content}")
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def _keyword_chunks(question: str, limit: int = 6) -> list[KnowledgeChunk]:
    lowered = question.lower()
    selected: list[KnowledgeChunk] = []
    seen = set()
    for keyword, patterns in KEYWORD_RULES.items():
        if any(term in lowered for term in patterns):
            for chunk in KNOWLEDGE_CHUNKS:
                chunk_text = f"{chunk.title.lower()} {chunk.paragraph.lower()} {chunk.url.lower()}"
                if any(term in chunk_text for term in patterns):
                    key = (chunk.url, chunk.paragraph[:80])
                    if key not in seen:
                        selected.append(chunk)
                        seen.add(key)
                        if len(selected) >= limit:
                            return selected
            if len(selected) >= limit:
                break
    return selected


def _gather_relevant_chunks(question: str, base_top_k: int = 6) -> list[KnowledgeChunk]:
    lowered = question.lower()
    is_bunka = any(word in lowered for word in ["bunka", "bunko", "bunke"])
    is_salama = any(
        word in lowered for word in ["salama", "salamo", "salame", "klobasa", "klobase", "klobaso"]
    )
    is_marmelada = any(word in lowered for word in ["marmelad", "marmelado", "marmelade", "marmeldo", "džem"])
    is_jahanje = any(
        word in lowered for word in ["jahanje", "jahati", "jahamo", "poni", "ponij", "ponija", "ponijem"]
    )

    # mesnine (bunka / salama)
    if is_bunka or is_salama:
        chunks = [
            chunk
            for chunk in KNOWLEDGE_CHUNKS
            if "/izdelek/" in chunk.url.lower()
            and (
                "bunka" in chunk.title.lower()
                or "bunka" in chunk.paragraph.lower()
                or "salama" in chunk.title.lower()
                or "salama" in chunk.paragraph.lower()
                or "mesni izdelki" in chunk.paragraph.lower()
            )
        ]
        return chunks[:4]

    # marmelade
    if is_marmelada:
        chunks = [
            chunk
            for chunk in KNOWLEDGE_CHUNKS
            if "/marmelada" in chunk.url.lower()
            or "marmelad" in chunk.title.lower()
            or "kategorija: marmelade" in chunk.paragraph.lower()
        ]
        return chunks[:4]

    # jahanje / poni – če ni v bazi, dodamo ročni fallback
    if is_jahanje:
        chunks = [
            chunk
            for chunk in KNOWLEDGE_CHUNKS
            if "jahanje" in chunk.paragraph.lower() or "ponij" in chunk.paragraph.lower()
        ]
        if chunks:
            return chunks[:4]
        return [
            KnowledgeChunk(
                url="https://www.kmetija-urska.si/cenik/",
                title="Aktivnosti na Turistični kmetiji Urška",
                paragraph="Za aktivnosti in cene poglejte uradni cenik Turistične kmetije Urška.",
            )
        ]

    keyword_chunks = _keyword_chunks(question, limit=4)
    base_chunks = search_knowledge(question, top_k=base_top_k)

    combined: list[KnowledgeChunk] = []
    seen = set()
    for chunk in keyword_chunks + base_chunks:
        key = (chunk.url, chunk.paragraph[:80])
        if key in seen:
            continue
        combined.append(chunk)
        seen.add(key)
        if len(combined) >= base_top_k + len(keyword_chunks):
            break
    return combined


def _filter_chunks_by_category(question: str, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
    lowered = question.lower()

    # mesnine: bunka / salama / klobasa
    if any(word in lowered for word in ["bunka", "bunko", "salama", "klobasa", "mesni"]):
        filtered = [
            c
            for c in chunks
            if "mesni izdelki" in c.paragraph.lower()
            or "kategorija: mesni" in c.paragraph.lower()
            or "bunka" in c.paragraph.lower()
            or "salama" in c.paragraph.lower()
        ]
        if filtered:
            return filtered[:4]
        fallback = [
            c
            for c in KNOWLEDGE_CHUNKS
            if "mesni izdelki" in c.paragraph.lower()
            or "bunka" in c.paragraph.lower()
            or "salama" in c.paragraph.lower()
        ]
        return fallback[:3]

    # marmelade
    if any(word in lowered for word in ["marmelad", "džem"]):
        filtered = [c for c in chunks if "/marmelada" in c.url.lower()]
        if filtered:
            return filtered
        for chunk in KNOWLEDGE_CHUNKS:
            if "/marmelada" in chunk.url.lower():
                return [chunk]
        return chunks

    # likerji / žganje
    if any(word in lowered for word in ["liker", "žganj", "žganje"]):
        filtered = [
            c
            for c in chunks
            if any(token in c.url.lower() for token in ["liker", "žganje", "tepkovec"])
        ]
        if filtered:
            return filtered
        for chunk in KNOWLEDGE_CHUNKS:
            if any(token in chunk.url.lower() for token in ["liker", "žganje", "tepkovec"]):
                return [chunk]
        return chunks

    return chunks


SYSTEM_PROMPT = """
Ti si prijazna gostiteljica na Turistični kmetiji Urška. Pomagaš gostom z informacijami o kmetiji, sobah, kulinariki, wellnessu in okolici.

TVOJA OSEBNOST:
- Si topla, prijazna in pristna - kot da se pogovarjaš z gostom v jedilnici
- Govoriš naravno, kot pravi človek - ne kot robot ali uraden asistent
- Včasih dodaš osebno noto ("Pri nas je to zelo priljubljeno", "To jed imam sama zelo rada")
- Občasno uporabiš emoji, ampak zmerno (1-2 na odgovor max)
- Goste VEDNO vikaš (vi, vam, vaš)

POGOVOR:
- Odgovarjaš kratko in jedrnato (2-4 stavki), razen če gost vpraša za več podrobnosti
- Postavljaš vprašanja nazaj, da bolje razumeš potrebe ("Za koliko oseb bi bila rezervacija?", "Imate raje sladko ali suho vino?")
- Če nekaj ne veš, to iskreno poveš in ponudiš alternativo
- NE ponavljaj istih fraz - bodi kreativen/a z uvodnimi stavki

REZERVACIJE SOB:
- Sobe so odprte od SREDE do NEDELJE
- Ob ponedeljkih in torkih so ZAPRTE
- Zimski premor: 30.12.2025 - 28.2.2026 (sobe zaprte)
- Božični premor: 22.12.2025 - 26.12.2025 (sobe zaprte)
- Minimalno 2 nočitvi (3 v poletni sezoni jun/jul/avg)
- Cena: 50€/osebo/noč z zajtrkom
- Večerja: dodatnih 25€/osebo
- Za datume IZVEN obdobij zaprtja samozavestno ponudi rezervacijo!

REZERVACIJE MIZ:
- Vikend kosila: sobota in nedelja 12:00-20:00
- Zadnji prihod na kosilo: 15:00
- Vedno potrebna rezervacija vnaprej

PRIMERI DOBRIH ODGOVOROV:

Gost: "Imate proste sobe?"
Ti: "Seveda, z veseljem preverim! 😊 Za kateri datum in koliko oseb bi želeli rezervirati?"

Gost: "23.4.2026"
Ti: "Super, april je čudovit čas pri nas - narava se ravno prebuja! Za 23.4.2026 imamo sobe na voljo. Koliko vas bo in za koliko noči bi želeli ostati?"

Gost: "Kaj ponujate za jesti?"
Ti: "Ob vikendih pripravljamo domača kosila iz lokalnih sestavin - od goveje juhe z jetrnimi cmočki do pohorskega piskra in naše slovite gibanice. 😋 Vas zanima jedilnik za ta vikend?"

Gost: "Hvala"
Ti: "Ni za kaj! Če boste imeli še kakšno vprašanje, sem tu. Lep pozdrav s Pohorja! 🏔️"

ČESA NE DELAŠ:
- Ne izmišljuješ si informacij, ki jih nimaš
- Ne govoriš preveč uradno ali robotsko
- Ne ponavljaš "Več informacij na kmetija-urska.si" pri vsakem odgovoru
- Ne daješ predolgih odgovorov brez potrebe
- Ne zaključuješ vedno z istim stavkom
"""


def generate_llm_answer(question: str, top_k: int = 6, history: list[dict[str, str]] | None = None) -> str:
    try:
        paragraphs = _gather_relevant_chunks(question, base_top_k=top_k)
        paragraphs = _filter_chunks_by_category(question, paragraphs)
    except Exception:
        paragraphs = []

    if not paragraphs:
        context_text = (
            "Nimam specifičnih podatkov o tem vprašanju, ampak lahko pomagam z drugimi informacijami o kmetiji."
        )
    else:
        context_text = _build_context_snippet(question, paragraphs)

    client = get_llm_client()
    convo: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "developer", "content": f"Kontekst iz baze znanja Urška:\n{context_text}"},
    ]
    if history:
        # vzamemo zadnjih nekaj sporočil, da ohranimo kratko zgodovino
        convo.extend(history[-6:])
    convo.append({"role": "user", "content": f"Vprašanje gosta: {question}"})

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=convo,
        max_output_tokens=400,
        temperature=0.7,
        top_p=0.9,
    )

    answer = getattr(response, "output_text", None)
    if not answer:
        outputs = []
        for block in getattr(response, "output", []) or []:
            for content in getattr(block, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    outputs.append(text)
        answer = "\n".join(outputs).strip()

    return answer or (
        "Trenutno v podatkih ne najdem jasnega odgovora. Prosimo, preverite www.kmetija-urska.si."
    )
