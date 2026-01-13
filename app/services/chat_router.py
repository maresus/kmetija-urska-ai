import re
import random
import json
import difflib
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple
import uuid
import threading

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest, ChatResponse
from app.services.product_service import find_products
from app.services.reservation_service import ReservationService
from app.services.email_service import send_guest_confirmation, send_admin_notification, send_custom_message
from app.rag.rag_engine import rag_engine
from app.rag.knowledge_base import (
    CONTACT,
    KNOWLEDGE_CHUNKS,
    generate_llm_answer,
    search_knowledge,
    search_knowledge_scored,
)
from app.core.config import Settings
from app.core.llm_client import get_llm_client
from app.rag.chroma_service import answer_tourist_question, is_tourist_query
from app.services.router_agent import route_message
from app.services.executor_v2 import execute_decision

router = APIRouter(prefix="/chat", tags=["chat"])
USE_ROUTER_V2 = True
USE_FULL_KB_LLM = True
INQUIRY_RECIPIENT = os.getenv("INQUIRY_RECIPIENT", "satlermarko@gmail.com")
SHORT_MODE = os.getenv("SHORT_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}

# ========== CENTRALIZIRANI INFO ODGOVORI (brez LLM!) ==========
INFO_RESPONSES = {
    "pozdrav": """Pozdravljeni pri Turistični kmetiji Urška! 😊

Lahko pomagam z vprašanji o nastanitvi, kulinariki, wellnessu, družini ali spletni trgovini.""",
    "kdo_si": """Sem vaš digitalni pomočnik Turistične kmetije Urška.

Z veseljem odgovorim na vprašanja o nastanitvi, kulinariki, wellnessu ali ponudbi.""",
    "kontakt": """📞 Telefon: 03 759 04 10
📱 Mobitel: 031 249 812
📧 Email: urska@kmetija-urska.si""",
    "lokacija": """📍 Turistična kmetija Urška
Križevec 11 A, 3206 Stranice

Za navigacijo vpišite naslov v Google Maps.""",
    "odpiralni_cas": """Delovni čas in termini so objavljeni na naši spletni strani.
Če mi poveste datum/termin, lahko preverim razpoložljivost.""",
    "prazniki": """Za praznike se urnik lahko prilagodi.
Najbolje je, da nas kontaktirate na urska@kmetija-urska.si ali 03 759 04 10.""",
    "rezervacija_vnaprej": """Rezervacijo priporočamo vnaprej, da vam zagotovimo termin.
Če želite, lahko rezervacijo uredim tukaj.""",
    "sobe": """Opis nastanitev je tukaj: https://www.kmetija-urska.si/namestitev/
Če želite rezervacijo, prosim sporočite datum in število oseb.""",
    "cena_sobe": """Cene in pogoji so v ceniku: https://www.kmetija-urska.si/cenik/""",
    "min_nocitve": """Minimalne nočitve in pogoji so navedeni v ceniku: https://www.kmetija-urska.si/cenik/""",
    "prijava_odjava": """Točen čas prijave/odjave je v opisu nastanitev.
Če mi poveste termin, lahko preverim.""",
    "zajtrk": """Podrobnosti o zajtrku so v ponudbi nastanitve/ceniku.
Če mi poveste termin, preverim še dodatne možnosti.""",
    "vecerja": """Večerja je praviloma možna po dogovoru (zlasti za goste).
Sporočite datum in število oseb, pa preverim.""",
    "klima": """Opremljenost sob (klima ipd.) je v opisu nastanitev na spletni strani.""",
    "wifi": """Wi‑Fi je na voljo v nastanitvah; podrobnosti potrdim ob rezervaciji.""",
    "parking": """Parkiranje je urejeno za goste; podrobnosti potrdimo ob rezervaciji.""",
    "placilo": """Način plačila je naveden v ceniku: https://www.kmetija-urska.si/cenik/""",
    "zivali": """Na kmetiji so tudi živali; podrobnosti najdete na strani Družina.""",
    "zivali_kmetija": """Več o kmetiji in živalih je tukaj: https://www.kmetija-urska.si/druzina/""",
    "kapaciteta_mize": """Kapacitete in možnosti za dogodke uredimo po dogovoru.
Sporočite število oseb in termin.""",
    "alergije": """Posebne prehrane uredimo po dogovoru – prosimo, sporočite ob rezervaciji.""",
    "jedilnik": """Meni je sezonski. Za točen meni povejte termin ali poglejte:
https://www.kmetija-urska.si/kulinarika/""",
    "druzina": """Predstavitev družine je tukaj: https://www.kmetija-urska.si/druzina/""",
    "kmetija": """Več o kmetiji in zgodbi je tukaj: https://www.kmetija-urska.si/druzina/""",
    "izdelki": """Spletna trgovina: https://shop.kmetija-urska.si/trgovina/""",
    "darilni_boni": """Darilni boni so na voljo v spletni trgovini.
Primer: https://shop.kmetija-urska.si/product/darilni-bon-100-eur""",
    "vina": """Vinska ponudba je del kulinarike in cenika.
Za točne informacije mi povejte termin.""",
    "turizem": """Če vas zanima izlet v okolici, mi povejte, ali želite sprehod, naravo ali kulturne znamenitosti.""",
    "kolesa": """Za izposojo koles povprašajte ob rezervaciji (termin in število koles).""",
    "gibanica": """Za sladice in posebna naročila poglejte ponudbo ali nam pišite.""",
}


_TOPIC_RESPONSES: dict[str, str] = {}
_topics_path = Path(__file__).resolve().parents[2] / "data" / "knowledge_topics.json"
if _topics_path.exists():
    try:
        for item in json.loads(_topics_path.read_text(encoding="utf-8")):
            key = item.get("key")
            answer = item.get("answer")
            if key and answer:
                _TOPIC_RESPONSES[key] = answer
    except Exception:
        _TOPIC_RESPONSES = {}

# Varianta odgovorov za bolj človeški ton (rotacija); tukaj uporabljamo iste besedilne vire
INFO_RESPONSES_VARIANTS = {key: [value] for key, value in INFO_RESPONSES.items()}
INFO_RESPONSES_VARIANTS["menu_info"] = [INFO_RESPONSES["jedilnik"]]
INFO_RESPONSES_VARIANTS["menu_full"] = [INFO_RESPONSES["jedilnik"]]
INFO_RESPONSES["menu_info"] = INFO_RESPONSES["jedilnik"]
INFO_RESPONSES["menu_full"] = INFO_RESPONSES["jedilnik"]
INFO_RESPONSES["sobe_info"] = INFO_RESPONSES["sobe"]

BOOKING_RELEVANT_KEYS = {"sobe", "vecerja", "cena_sobe", "min_nocitve", "kapaciteta_mize"}
CRITICAL_INFO_KEYS = {
    "odpiralni_cas",
    "prazniki",
    "rezervacija_vnaprej",
    "zajtrk",
    "vecerja",
    "jedilnik",
    "cena_sobe",
    "min_nocitve",
    "prijava_odjava",
    "placilo",
    "parking",
    "kontakt",
    "sobe",
    "kapaciteta_mize",
}

def _send_reservation_emails_async(payload: dict) -> None:
    def _worker() -> None:
        try:
            send_guest_confirmation(payload)
            send_admin_notification(payload)
        except Exception as exc:
            print(f"[EMAIL] Async send failed: {exc}")
    threading.Thread(target=_worker, daemon=True).start()

FULL_KB_TEXT = ""
try:
    kb_path = Path(__file__).resolve().parents[2] / "knowledge.jsonl"
    if kb_path.exists():
        chunks = []
        for line in kb_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = record.get("url", "")
            title = record.get("title", "")
            content = record.get("content", "")
            if not (url or title or content):
                continue
            chunks.append(
                f"URL: {url}\nNaslov: {title}\nVsebina: {content}\n"
            )
        FULL_KB_TEXT = "\n---\n".join(chunks)
except Exception as exc:
    print(f"[KB] Full KB load failed: {exc}")

def _llm_system_prompt_full_kb(language: str = "si") -> str:
    common = (
        "Ti si asistent Turistične kmetije Urška.\n"
        "Tukaj so VSE informacije o kmetiji:\n"
        f"{FULL_KB_TEXT}\n\n"
        "Ne izmišljuj si podatkov.\n"
        "Odgovarjaj kratko (2–4 stavke), razen če uporabnik izrecno želi podrobnosti.\n"
        "Če nisi prepričan, postavi kratko pojasnitveno vprašanje.\n"
        "Če uporabnik želi TOČEN meni, ga podaš samo, če je v podatkih.\n"
        "Če ni podatka o točnem meniju ali sezoni, to povej in vprašaj za mesec/termin.\n"
        "Če uporabnik želi rezervirati sobo ali mizo, OBVEZNO pokliči funkcijo "
        "`reservation_intent` in nastavi ustrezen action.\n"
    )
    if language == "en":
        return (
            "You are the assistant for Turistična kmetija Urška. Respond in English.\n"
            + common
        )
    if language == "de":
        return (
            "Du bist der Assistent für Turistična kmetija Urška. Antworte auf Deutsch.\n"
            + common
        )
    return (
        common
        + "Odgovarjaj prijazno, naravno in slovensko.\n"
    )

def _llm_route_reservation(message: str) -> dict:
    client = get_llm_client()
    settings = Settings()
    tools = [
        {
            "type": "function",
            "name": "reservation_intent",
            "description": "Ugotovi ali uporabnik želi rezervacijo sobe ali mize. Vrni action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["NONE", "BOOKING_ROOM", "BOOKING_TABLE"],
                    },
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "people_count": {"type": "integer"},
                    "nights": {"type": "integer"},
                },
                "required": ["action"],
            },
        }
    ]
    try:
        response = client.responses.create(
            model=getattr(settings, "openai_model", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": "Ugotovi, ali uporabnik želi rezervacijo sobe ali mize."},
                {"role": "user", "content": message},
            ],
            tools=tools,
            tool_choice={"type": "function", "name": "reservation_intent"},
            temperature=0.2,
            max_output_tokens=120,
        )
    except Exception as exc:
        print(f"[LLM] reservation route error: {exc}")
        return {"action": "NONE"}

    for block in getattr(response, "output", []) or []:
        for content in getattr(block, "content", []) or []:
            content_type = getattr(content, "type", "")
            if content_type not in {"tool_call", "function_call"}:
                continue
            name = getattr(content, "name", "") or getattr(getattr(content, "function", None), "name", "")
            if name != "reservation_intent":
                continue
            args = getattr(content, "arguments", None)
            if args is None and getattr(content, "function", None):
                args = getattr(content.function, "arguments", None)
            args = args or "{}"
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return {"action": "NONE"}
    return {"action": "NONE"}

def _llm_answer_full_kb(message: str, language: str = "si") -> str:
    client = get_llm_client()
    settings = Settings()
    try:
        response = client.responses.create(
            model=getattr(settings, "openai_model", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": _llm_system_prompt_full_kb(language)},
                {"role": "user", "content": message},
            ],
            max_output_tokens=450,
            temperature=getattr(settings, "openai_temperature", 0.8),
            top_p=0.9,
        )
    except Exception as exc:
        print(f"[LLM] answer error: {exc}")
        return "Oprostite, trenutno ne morem odgovoriti. Poskusite znova čez trenutek."
    answer = getattr(response, "output_text", None)
    if not answer:
        outputs = []
        for block in getattr(response, "output", []) or []:
            for content in getattr(block, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    outputs.append(text)
        answer = "\n".join(outputs).strip()
    return answer or "Seveda, z veseljem pomagam. Kaj vas zanima?"


def _stream_text_chunks(text: str, chunk_size: int = 80):
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


def _llm_answer_full_kb_stream(message: str, settings: Settings, language: str = "si"):
    client = get_llm_client()
    try:
        stream = client.responses.create(
            model=getattr(settings, "openai_model", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": _llm_system_prompt_full_kb(language)},
                {"role": "user", "content": message},
            ],
            max_output_tokens=450,
            temperature=getattr(settings, "openai_temperature", 0.8),
            top_p=0.9,
            stream=True,
        )
    except Exception as exc:
        fallback = "Oprostite, trenutno ne morem odgovoriti. Poskusite znova čez trenutek."
        print(f"[LLM] stream error: {exc}")
        for chunk in _stream_text_chunks(fallback):
            yield chunk
        return fallback

    collected: list[str] = []
    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", "")
            if delta:
                collected.append(delta)
                yield delta
        elif event_type == "response.error":
            error_message = getattr(getattr(event, "error", None), "message", "")
            if error_message:
                print(f"[LLM] stream error event: {error_message}")
    final_text = "".join(collected).strip()
    return final_text or "Seveda, z veseljem pomagam. Kaj vas zanima?"

def _llm_answer(question: str, history: list[dict[str, str]]) -> Optional[str]:
    try:
        return generate_llm_answer(question, history=history)
    except Exception as exc:
        print(f"[LLM] Failed to answer: {exc}")
        return None


def get_info_response(key: str, question: str | None = None) -> str:
    if key.startswith("topic:"):
        topic_key = key.split(":", 1)[1]
        if topic_key in _TOPIC_RESPONSES:
            return maybe_shorten_response(_TOPIC_RESPONSES[topic_key])
    if question and USE_FULL_KB_LLM:
        try:
            return generate_llm_answer(question)
        except Exception as exc:
            print(f"[LLM] Failed to answer info: {exc}")
    if key in INFO_RESPONSES_VARIANTS:
        variants = INFO_RESPONSES_VARIANTS[key]
        chosen = min(variants, key=len) if SHORT_MODE else random.choice(variants)
        return maybe_shorten_response(chosen)
    return maybe_shorten_response(INFO_RESPONSES.get(key, "Kako vam lahko pomagam?"))


def maybe_shorten_response(text: str) -> str:
    if not SHORT_MODE:
        return text
    if not text:
        return text
    if len(text) <= 520:
        return text
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 4:
        return "\n".join(lines[:4]) + "\n\nZa več informacij vprašajte naprej."
    clipped = text[:520]
    if ". " in clipped:
        clipped = clipped.rsplit(". ", 1)[0] + "."
    return clipped

# Mini RAG fallback za neznane info/product
def get_mini_rag_answer(question: str) -> Optional[str]:
    chunks = search_knowledge(question, top_k=1)
    if not chunks:
        return None
    chunk = chunks[0]
    snippet = chunk.paragraph.strip()
    if len(snippet) > 500:
        snippet = snippet[:500].rsplit(". ", 1)[0] + "."
    url_line = f"\n\nVeč: {chunk.url}" if chunk.url else ""
    return f"{snippet}{url_line}"

UNKNOWN_RESPONSES = [
    "Tega odgovora nimam pri roki. Pišite na urska@kmetija-urska.si in vam pomagamo.",
    "Nisem prepričana o tem podatku. Prosím, napišite na urska@kmetija-urska.si in bomo preverili.",
    "Trenutno nimam točne informacije. Pošljite nam email na urska@kmetija-urska.si.",
    "Žal nimam odgovora. Najbolje, da nam pišete na urska@kmetija-urska.si.",
    "Tole moram preveriti. Pišite na urska@kmetija-urska.si in vam odgovorimo.",
    "Nimam tega zapisanega. Lahko prosim pošljete vprašanje na urska@kmetija-urska.si?",
    "Za to nimam podatka. Kontaktirajte nas na urska@kmetija-urska.si in bomo pogledali.",
    "Hvala za vprašanje, nimam pa odgovora pri roki. Pišite na urska@kmetija-urska.si.",
    "To vprašanje je specifično, prosim napišite na urska@kmetija-urska.si in skupaj najdemo odgovor.",
    "Tu mi manjka podatek. Email: urska@kmetija-urska.si — z veseljem preverimo.",
]

SEMANTIC_THRESHOLD = 0.75
SEMANTIC_STOPWORDS = {
    "a", "ali", "al", "pa", "in", "na", "za", "se", "so", "je", "smo", "ste",
    "sem", "biti", "bo", "bi", "da", "ne", "ni", "niso", "si", "mi", "ti",
    "vi", "vas", "vam", "nas", "ga", "jo", "jih", "te", "to", "ta", "tisto",
    "kdo", "kaj", "kdaj", "kje", "kako", "kolik", "koliko", "ker", "pač",
    "pri", "od", "do", "v", "iz", "z", "ob", "kot", "naj", "tudi", "lahko",
    "moj", "moja", "moje", "tvoj", "tvoja", "tvoje", "njihov", "njihova",
    "the", "and", "or", "to", "is", "are", "a", "an", "for", "in", "of",
}


def _tokenize_text(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-zČŠŽčšžĐđĆć0-9]+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in SEMANTIC_STOPWORDS}


def _semantic_overlap_ok(question: str, chunk: Any) -> bool:
    q_tokens = _tokenize_text(question)
    if not q_tokens:
        return True
    c_tokens = _tokenize_text(f"{chunk.title or ''} {chunk.paragraph or ''}")
    overlap = q_tokens & c_tokens
    if len(q_tokens) >= 6:
        return len(overlap) >= 2 and (len(overlap) / len(q_tokens)) >= 0.25
    return len(overlap) >= 2 or (len(overlap) / len(q_tokens)) >= 0.5


def _format_semantic_snippet(chunk: Any) -> str:
    snippet = chunk.paragraph.strip()
    if len(snippet) > 500:
        snippet = snippet[:500].rsplit(". ", 1)[0] + "."
    url_line = f"\n\nVeč: {chunk.url}" if chunk.url else ""
    return f"{snippet}{url_line}"


def semantic_info_answer(question: str) -> Optional[str]:
    scored = search_knowledge_scored(question, top_k=1)
    if not scored:
        return None
    score, chunk = scored[0]
    if score < SEMANTIC_THRESHOLD:
        try:
            with open("data/semantic_low_score.log", "a", encoding="utf-8") as handle:
                handle.write(f"{datetime.utcnow().isoformat()} score={score:.2f} q={question}\n")
        except Exception:
            pass
        return None
    if not _semantic_overlap_ok(question, chunk):
        try:
            q_tokens = _tokenize_text(question)
            c_tokens = _tokenize_text(chunk.paragraph or "")
            overlap = q_tokens & c_tokens
            ratio = (len(overlap) / len(q_tokens)) if q_tokens else 0.0
            with open("data/semantic_low_score.log", "a", encoding="utf-8") as handle:
                handle.write(
                    f"{datetime.utcnow().isoformat()} score={score:.2f} overlap={len(overlap)} "
                    f"ratio={ratio:.2f} q={question}\n"
                )
        except Exception:
            pass
        return None
    return _format_semantic_snippet(chunk)
# Fiksni zaključek rezervacije
RESERVATION_PENDING_MESSAGE = """
✅ **Vaše povpraševanje je PREJETO** in čaka na potrditev.

📧 Potrditev boste prejeli po e-pošti.
⏳ Odgovorili vam bomo v najkrajšem možnem času.

⚠️ Preverite tudi **SPAM/VSILJENO POŠTO**.
"""


class ChatRequestWithSession(ChatRequest):
    session_id: Optional[str] = None


last_wine_query: Optional[str] = None
SESSION_TIMEOUT_HOURS = 48
PRODUCT_STEMS = {
    "salam",
    "klobas",
    "sir",
    "izdelek",
    "paket",
    "marmelad",
    "džem",
    "dzem",
    "liker",
    "namaz",
    "bunk",
}
RESERVATION_START_PHRASES = {
    # slovensko - sobe
    "rezervacija sobe",
    "rad bi rezerviral sobo",
    "rad bi rezervirala sobo",
    "želim rezervirati sobo",
    "bi rezerviral sobo",
    "bi rezervirala sobo",
    "rezerviral bi sobo",
    "rezerviraj sobo",
    "rabim sobo",
    "iščem sobo",
    "sobo prosim",
    "prenočitev",
    "nastanitev",
    "nočitev",
    # slovensko - mize
    "rezervacija mize",
    "rad bi rezerviral mizo",
    "rad bi rezervirala mizo",
    "mizo bi",
    "mizo za",
    "mize za",
    "rezerviram mizo",
    "rezervirala bi mizo",
    "rezerviral bi mizo",
    "kosilo",
    "večerja",
    # angleško - sobe
    "book a room",
    "booking",
    "i want to book",
    "i would like to book",
    "i'd like to book",
    "room reservation",
    "i need a room",
    "accommodation",
    "stay for",
    # angleško - mize
    "book a table",
    "table reservation",
    "lunch reservation",
    "dinner reservation",
    # nemško - sobe
    "zimmer reservieren",
    "ich möchte ein zimmer",
    "ich möchte buchen",
    "ich möchte reservieren",
    "ich will buchen",
    "übernachtung",
    "unterkunft",
    "buchen",
    # nemško - mize
    "tisch reservieren",
    "mittagessen",
    "abendessen",
    # italijansko - sobe
    "prenotare una camera",
    "prenotazione",
    "camera",
    "alloggio",
}
INFO_KEYWORDS = {
    "kje",
    "lokacija",
    "naslov",
    "kosilo",
    "vikend kosilo",
    "vikend",
    "hrana",
    "sob",
    "soba",
    "sobe",
    "nočitev",
    "nočitve",
    "zajtrk",
    "večerja",
    "otroci",
    "popust",
}
GREETING_KEYWORDS = {"živjo", "zdravo", "hej", "hello", "dober dan", "pozdravljeni"}
GOODBYE_KEYWORDS = {
    "hvala",
    "najlepša hvala",
    "hvala lepa",
    "adijo",
    "nasvidenje",
    "na svidenje",
    "čao",
    "ciao",
    "bye",
    "goodbye",
    "lp",
    "lep pozdrav",
    "se vidimo",
    "vidimo se",
    "srečno",
    "vse dobro",
    "lahko noč",
}
GREETINGS = [
    "Pozdravljeni! 😊 Kako vam lahko pomagam?",
    "Lepo pozdravljeni! Kako vam lahko pomagam danes?",
    "Dober dan! Vesela sem, da ste nas obiskali. S čim vam lahko pomagam?",
    "Pozdravljeni pri Turistični kmetiji Urška! Kaj vas zanima?",
]
THANKS_RESPONSES = [
    "Ni za kaj! Če boste imeli še kakšno vprašanje, sem tu. 😊",
    "Z veseljem! Lep pozdrav! 😊",
    "Ni problema! Vesela sem, če sem vam lahko pomagala.",
    "Hvala vam! Se vidimo pri nas! 😊",
]
UNKNOWN_RESPONSES = [
    "Ojoj, tega žal ne vem točno. 🤔 Lahko pa povprašam in vam sporočim - mi zaupate vaš email?",
    "Hmm, tega nimam v svojih zapiskih. Če mi pustite email, vam z veseljem poizvem in odgovorim.",
    "Na to vprašanje žal nimam odgovora pri roki. Lahko vam poizvem - mi zaupate vaš elektronski naslov?",
]
PRODUCT_FOLLOWUP_PHRASES = {
    "kaj pa",
    "kaj še",
    "katere",
    "katere pa",
    "kakšne",
    "še kaj",
    "kje naročim",
    "kje lahko naročim",
    "kako naročim",
    "kako lahko naročim",
}
INFO_FOLLOWUP_PHRASES = {
    "še kaj",
    "še kero",
    "še kero drugo",
    "kaj pa še",
    "pa še",
    "še kakšna",
    "še kakšno",
    "še kakšne",
    "še kaj drugega",
}

reservation_service = ReservationService()

# Osnovni podatki o kmetiji
FARM_INFO = {
    "name": "Turistična kmetija Urška",
    "address": "Križevec 11 A, 3206 Stranice",
    "phone": "03 759 04 10",
    "mobile": "031 249 812",
    "email": "urska@kmetija-urska.si",
    "website": "www.kmetija-urska.si",
    "location_description": "Za navigacijo vpišite naslov v Google Maps.",
}

LOCATION_KEYWORDS = {
    "kje",
    "naslov",
    "lokacija",
    "kako pridem",
    "priti",
    "parking",
    "telefon",
    "številka",
    "stevilka",
    "email",
    "kontakt",
    "odprti",
    "odprto",
    "delovni čas",
    "ura",
    "kdaj",
    "wifi",
    "internet",
    "klima",
    "parkirišče",
    "parkirisce",
}

FARM_INFO_KEYWORDS = {
    "kje",
    "naslov",
    "lokacija",
    "kako pridem",
    "priti",
    "parking",
    "telefon",
    "številka",
    "stevilka",
    "email",
    "kontakt",
    "odprti",
    "odprto",
    "delovni čas",
    "ura",
    "kdaj",
    "wifi",
    "internet",
    "klima",
    "nahajate",
    "navodila",
    "pot",
    "avtom",
    "parkirišče",
    "parkirisce",
}

FOOD_GENERAL_KEYWORDS = {"hrana", "jest", "jesti", "ponujate", "kuhate", "jedilnik?"}

HELP_KEYWORDS = {"pomoč", "help", "kaj znaš", "kaj znate", "kaj lahko", "možnosti"}
WEEKLY_KEYWORDS = {
    "teden",
    "tedensk",
    "čez teden",
    "med tednom",
    "sreda",
    "četrtek",
    "petek",
    "degustacij",
    "kulinarično",
    "doživetje",
    "4-hodn",
    "5-hodn",
    "6-hodn",
    "7-hodn",
    "4 hodn",
    "5 hodn",
    "6 hodn",
    "7 hodn",
    "štiri hod",
    "stiri hod",
    "pet hod",
    "šest hod",
    "sest hod",
    "sedem hod",
    "4-hodni meni",
    "5-hodni meni",
    "6-hodni meni",
    "7-hodni meni",
}

PRICE_KEYWORDS = {
    "cena",
    "cene",
    "cenika",
    "cenik",
    "koliko stane",
    "koliko stal",
    "koliko košta",
    "koliko kosta",
    "ceno",
    "cenah",
}

GREETING_RESPONSES = [
    # Uporabljamo GREETINGS za variacije v prijaznih uvodih
] + GREETINGS
GOODBYE_RESPONSES = THANKS_RESPONSES
EXIT_KEYWORDS = {
    "konec",
    "stop",
    "prekini",
    "nehaj",
    "pustimo",
    "pozabi",
    "ne rabim",
    "ni treba",
    "drugič",
    "drugic",
    "cancel",
    "quit",
    "exit",
    "pusti",
}

ROOM_PRICING = {
    "bed_breakfast_price": 72,  # nočitev z zajtrkom (EUR/oseba/noč)
    "half_board_price": 87,  # polpenzion (EUR/oseba/noč)
    "summer_half_board_price": 97,  # razširjeni polpenzion jul/avg
    "min_adults": 1,
    "min_nights_summer": 5,
    "min_nights_other": 1,
    "child_discounts": {},
    "breakfast_included": True,
    "check_in": "po dogovoru",
    "check_out": "po dogovoru",
    "breakfast_time": "po dogovoru",
    "dinner_time": "po dogovoru",
    "closed_days": [],
}

# Vinski seznam za fallback
WINE_LIST = {
    "penece": [],
    "bela": [],
    "rdeca": [],
}

WINE_KEYWORDS = {
    "vino",
    "vina",
    "vin",
    "rdec",
    "rdeca",
    "rdeče",
    "rdece",
    "belo",
    "bela",
    "penin",
    "penina",
    "peneč",
    "muskat",
    "muškat",
    "rizling",
    "sauvignon",
    "frankinja",
    "pinot",
}

SEASONAL_MENUS: list[dict[str, object]] = []
WEEKLY_EXPERIENCES: list[dict[str, object]] = []

def _blank_reservation_state() -> dict[str, Optional[str | int]]:
    return {
        "step": None,
        "type": None,
        "date": None,
        "time": None,
        "nights": None,
        "rooms": None,
        "people": None,
        "adults": None,
        "kids": None,  # število otrok
        "kids_ages": None,  # starosti otrok
        "name": None,
        "phone": None,
        "email": None,
        "location": None,
        "available_locations": None,
        "language": None,
        "dinner_people": None,
        "note": None,
    }


def _blank_inquiry_state() -> dict[str, Optional[str]]:
    return {
        "step": None,
        "details": "",
        "deadline": "",
        "contact_name": "",
        "contact_email": "",
        "contact_phone": "",
        "contact_raw": "",
    }


reservation_states: dict[str, dict[str, Optional[str | int]]] = {}
inquiry_states: dict[str, dict[str, Optional[str]]] = {}


def get_reservation_state(session_id: str) -> dict[str, Optional[str | int]]:
    if session_id not in reservation_states:
        reservation_states[session_id] = _blank_reservation_state()
    return reservation_states[session_id]


def get_inquiry_state(session_id: str) -> dict[str, Optional[str]]:
    if session_id not in inquiry_states:
        inquiry_states[session_id] = _blank_inquiry_state()
    return inquiry_states[session_id]


def reset_inquiry_state(state: dict[str, Optional[str]]) -> None:
    state.update(_blank_inquiry_state())

last_product_query: Optional[str] = None
last_info_query: Optional[str] = None
last_menu_query: bool = False
conversation_history: list[dict[str, str]] = []
last_shown_products: list[str] = []
last_interaction: Optional[datetime] = None
unknown_question_state: dict[str, dict[str, Any]] = {}
chat_session_id: str = str(uuid.uuid4())[:8]
MENU_INTROS = [
    "Hej! Poglej, kaj kuhamo ta vikend:",
    "Z veseljem povem, kaj je na meniju:",
    "Daj, da ti razkrijem naš sezonski meni:",
    "Evo, vikend jedilnik:",
]
menu_intro_index = 0

def answer_wine_question(message: str) -> str:
    """Odgovarja na vprašanja o vinih SAMO iz WINE_LIST, z upoštevanjem followupov."""
    global last_shown_products

    if not any(WINE_LIST.values()):
        return (
            "Vinska ponudba je del kulinarike in je sezonska. "
            "Za točne informacije poglejte kulinariko ali cenik."
        )

    lowered = message.lower()
    is_followup = any(word in lowered for word in ["še", "drug", "kaj pa", "še kaj", "še kater", "še kakšn", "še kakšno"])

    is_red = any(word in lowered for word in ["rdeč", "rdeca", "rdece", "rdeče", "frankinja", "pinot"])
    is_white = any(word in lowered for word in ["bel", "bela", "belo", "rizling", "sauvignon"])
    is_sparkling = any(word in lowered for word in ["peneč", "penina", "penece", "mehurčk", "brut"])
    is_sweet = any(word in lowered for word in ["sladk", "polsladk", "muškat", "muskat"])
    is_dry = any(word in lowered for word in ["suh", "suho", "suha"])

    def format_wines(wines: list, category_name: str, temp: str) -> str:
        # ob followupu skrij že prikazane
        if is_followup:
            wines = [w for w in wines if w["name"] not in last_shown_products]

        if not wines:
            return (
                f"To so vsa naša {category_name} vina. Imamo pa še:\n"
                "🥂 Bela vina (od 14€)\n"
                "🍾 Peneča vina (od 26€)\n"
                "🍯 Polsladka vina (od 17€)\n"
                "🍷 Rdeča vina (od 16€)\n"
                "Kaj vas zanima?"
            )

        lines = [f"Naša {category_name} vina:"]
        for w in wines:
            lines.append(f"• {w['name']} ({w['type']}, {w['price']:.0f}€) – {w['desc']}")
            if w["name"] not in last_shown_products:
                last_shown_products.append(w["name"])

        if len(last_shown_products) > 15:
            last_shown_products[:] = last_shown_products[-15:]

        return "\n".join(lines) + f"\n\nServiramo ohlajeno na {temp}."

    # Rdeča
    if is_red:
        wines = WINE_LIST["rdeca"]
        if is_dry:
            wines = [w for w in wines if "suho" in w["type"]]
        if is_followup:
            remaining = [w for w in wines if w["name"] not in last_shown_products]
            if not remaining:
                return (
                    "To so vsa naša rdeča vina. Imamo pa še:\n"
                    "🥂 Bela vina (od 14€)\n"
                    "🍾 Peneča vina (od 26€)\n"
                    "🍯 Polsladka vina (od 17€)\n"
                    "Kaj vas zanima?"
                )
        return format_wines(wines, "rdeča", "14°C")

    # Peneča
    if is_sparkling:
        return format_wines(WINE_LIST["penece"], "peneča", "6°C")

    # Bela
    if is_white:
        wines = WINE_LIST["bela"]
        if is_dry:
            wines = [w for w in wines if "suho" in w["type"]]
        if is_sweet:
            wines = [w for w in wines if "polsladk" in w["type"]]
        return format_wines(wines[:5], "bela", "8–10°C")

    # Polsladka
    if is_sweet:
        wines = []
        for w in WINE_LIST["bela"]:
            if "polsladk" in w["type"]:
                wines.append(w)
        for w in WINE_LIST["penece"]:
            if "polsladk" in w["type"].lower() or "demi" in w["type"].lower():
                wines.append(w)
        return format_wines(wines, "polsladka", "8°C")

    # Splošno vprašanje
    return (
        "Ponujamo izbor lokalnih vin:\n\n"
        "🍷 **Rdeča** (suha): Modra frankinja (Skuber 16€, Greif 26€), Modri pinot Frešer (23€)\n"
        "🥂 **Bela** (suha): Sauvignon (19€), Laški rizling (18–23€), Renski rizling (22€)\n"
        "🍾 **Peneča**: Doppler Diona brut (30€), Opok27 rose (26€), Muškatna penina (26€)\n"
        "🍯 **Polsladka**: Rumeni muškat (17€), Muškat ottonel (17€)\n\n"
        "Povejte, kaj vas zanima – rdeče, belo, peneče ali polsladko?"
    )


def answer_weekly_menu(message: str) -> str:
    """Odgovarja na vprašanja o tedenski ponudbi (sreda-petek)."""
    lowered = message.lower()
    if not WEEKLY_MENUS:
        return (
            "Degustacijske menije pripravljamo po dogovoru. "
            "Za točne možnosti povejte datum in število oseb ali poglejte kulinariko: "
            "https://www.kmetija-urska.si/kulinarika/"
        )

    requested_courses = None
    if "4" in message or "štiri" in lowered or "stiri" in lowered:
        requested_courses = 4
    elif "5" in message or "pet" in lowered:
        requested_courses = 5
    elif "6" in message or "šest" in lowered or "sest" in lowered:
        requested_courses = 6
    elif "7" in message or "sedem" in lowered:
        requested_courses = 7

    if requested_courses is None:
        lines = [
            "**KULINARIČNA DOŽIVETJA** (sreda–petek, od 13:00, min. 6 oseb)\n",
            "Na voljo imamo degustacijske menije:",
            "",
            f"🍽️ **4-hodni meni**: {WEEKLY_MENUS[4]['price']}€/oseba (vinska spremljava +{WEEKLY_MENUS[4]['wine_pairing']}€ za {WEEKLY_MENUS[4]['wine_glasses']} kozarce)",
            f"🍽️ **5-hodni meni**: {WEEKLY_MENUS[5]['price']}€/oseba (vinska spremljava +{WEEKLY_MENUS[5]['wine_pairing']}€ za {WEEKLY_MENUS[5]['wine_glasses']} kozarcev)",
            f"🍽️ **6-hodni meni**: {WEEKLY_MENUS[6]['price']}€/oseba (vinska spremljava +{WEEKLY_MENUS[6]['wine_pairing']}€ za {WEEKLY_MENUS[6]['wine_glasses']} kozarcev)",
            f"🍽️ **7-hodni meni**: {WEEKLY_MENUS[7]['price']}€/oseba (vinska spremljava +{WEEKLY_MENUS[7]['wine_pairing']}€ za {WEEKLY_MENUS[7]['wine_glasses']} kozarcev)",
            "",
            f"🥗 Posebne zahteve (vege, brez glutena): +{WEEKLY_INFO['special_diet_extra']}€/hod",
            "",
            f"📞 Rezervacije: {WEEKLY_INFO['contact']['phone']} ali {WEEKLY_INFO['contact']['email']}",
            "",
            "Povejte kateri meni vas zanima (4, 5, 6 ali 7-hodni) za podrobnosti!",
        ]
        return "\n".join(lines)

    menu = WEEKLY_MENUS[requested_courses]
    lines = [
        f"**{menu['name']}**",
        f"📅 {WEEKLY_INFO['days'].upper()}, {WEEKLY_INFO['time']}",
        f"👥 Minimum {WEEKLY_INFO['min_people']} oseb",
        "",
    ]

    for i, course in enumerate(menu["courses"], 1):
        wine_text = f" 🍷 _{course['wine']}_" if course["wine"] else ""
        lines.append(f"**{i}.** {course['dish']}{wine_text}")

    lines.extend(
        [
            "",
            f"💰 **Cena: {menu['price']}€/oseba**",
            f"🍷 Vinska spremljava: +{menu['wine_pairing']}€ ({menu['wine_glasses']} kozarcev)",
            f"🥗 Vege/brez glutena: +{WEEKLY_INFO['special_diet_extra']}€/hod",
            "",
            f"📞 Rezervacije: {WEEKLY_INFO['contact']['phone']} ali {WEEKLY_INFO['contact']['email']}",
        ]
    )

    return "\n".join(lines)


def detect_intent(message: str, state: dict[str, Optional[str | int]]) -> str:
    global last_product_query, last_wine_query
    lower_message = message.lower()

    # 1) nadaljevanje rezervacije ima vedno prednost
    if state["step"] is not None:
        if is_menu_query(message):
            return "menu"
        if is_hours_question(message):
            return "farm_info"
        return "reservation"

    # vprašanja o odpiralnem času / zajtrk/večerja
    if is_hours_question(message):
        return "farm_info"

    # koliko sob imate -> info, ne rezervacija
    if re.search(r"koliko\s+soba", lower_message) or re.search(r"koliko\s+sob", lower_message):
        return "room_info"

    # Rezervacija - fuzzy match (tudi s tipkarskimi napakami)
    rezerv_patterns = ["rezerv", "rezev", "rezer", "book", "buking", "bokking", "reserve", "reservation"]
    soba_patterns = ["sobo", "sobe", "soba", "room"]
    miza_patterns = ["mizo", "mize", "miza", "table"]
    has_rezerv = any(p in lower_message for p in rezerv_patterns)
    has_soba = any(p in lower_message for p in soba_patterns)
    has_miza = any(p in lower_message for p in miza_patterns)
    if has_rezerv and (has_soba or has_miza or "nočitev" in lower_message or "nocitev" in lower_message):
        return "reservation"
    if is_reservation_typo(message) and (has_soba or has_miza):
        return "reservation"
    if any(phrase in lower_message for phrase in RESERVATION_START_PHRASES):
        return "reservation"

    # goodbye/hvala
    if is_goodbye(message):
        return "goodbye"

    # jedilnik / meni naj ne sproži rezervacije
    if is_menu_query(message):
        return "menu"

    # SOBE - posebej pred rezervacijo
    sobe_keywords = ["sobe", "soba", "sobo", "nastanitev", "prenočitev", "nočitev nočitve", "rooms", "room", "accommodation"]
    if any(kw in lower_message for kw in sobe_keywords) and "rezerv" not in lower_message and "book" not in lower_message:
        return "room_info"

    # vino intent
    if any(keyword in lower_message for keyword in WINE_KEYWORDS):
        return "wine"

    # vino followup (če je bila prejšnja interakcija o vinih)
    if last_wine_query and any(
        phrase in lower_message for phrase in ["še", "še kakšn", "še kater", "kaj pa", "drug"]
    ):
        return "wine_followup"

    # cene sob
    if any(word in lower_message for word in PRICE_KEYWORDS):
        if any(word in lower_message for word in ["sob", "nočitev", "nocitev", "noč", "spanje", "bivanje"]):
            return "room_pricing"

    # tedenska ponudba (degustacijski meniji) – pred jedilnikom
    if any(word in lower_message for word in WEEKLY_KEYWORDS):
        return "weekly_menu"
    if re.search(r"\b[4-7]\s*-?\s*hodn", lower_message):
        return "weekly_menu"

    # 3) info o kmetiji / kontakt
    if any(keyword in lower_message for keyword in FARM_INFO_KEYWORDS):
        return "farm_info"

    if is_tourist_query(message):
        return "tourist_info"

    # 3) produktna vprašanja (salama, bunka, marmelada, paket, vino …)
    if any(stem in lower_message for stem in PRODUCT_STEMS):
        return "product"

    # 4) kratko nadaljevanje produktnega vprašanja
    if last_product_query and any(
        phrase in lower_message for phrase in PRODUCT_FOLLOWUP_PHRASES
    ):
        return "product_followup"

    # 5) info vprašanja (kje, soba, nočitve …)
    if any(keyword in lower_message for keyword in INFO_KEYWORDS):
        return "info"
    # 6) splošna hrana (ne jedilnik)
    if any(word in lower_message for word in FOOD_GENERAL_KEYWORDS) and not is_menu_query(message):
        return "food_general"
    # 7) pomoč
    if any(word in lower_message for word in HELP_KEYWORDS):
        return "help"
    # 9) tedenska ponudba
    if any(word in lower_message for word in WEEKLY_KEYWORDS):
        return "weekly_menu"
    return "default"


def detect_info_intent(message: str) -> Optional[str]:
    """
    Detecta INFO intent BREZ LLM.
    Vrne ključ iz INFO_RESPONSES ali None če ni info vprašanje.
    """
    text = message.lower().strip()

    # Odpiralni čas
    if any(w in text for w in ["kdaj ste odprti", "odpiralni", "delovni čas", "kdaj odprete"]):
        return "odpiralni_cas"

    # Zajtrk
    if "zajtrk" in text and "večerj" not in text:
        return "zajtrk"

    # Večerja (info, ne rezervacija)
    if any(w in text for w in ["koliko stane večerja", "cena večerje"]):
        return "vecerja"

    # Cena sob / nočitev
    if any(
        w in text
        for w in [
            "cena sobe",
            "cena nočit",
            "cena nocit",
            "koliko stane noč",
            "koliko stane noc",
            "cenik",
            "koliko stane soba",
            "koliko stane nočitev",
        ]
    ):
        return "cena_sobe"

    # Sobe info
    if any(w in text for w in ["koliko sob", "kakšne sobe", "koliko oseb v sobo", "kolko oseb v sobo", "kapaciteta sob"]):
        return "sobe"

    # Klima
    if "klim" in text:
        return "klima"

    # WiFi
    if "wifi" in text or "wi-fi" in text or "internet" in text:
        return "wifi"

    # Prijava/odjava
    if any(w in text for w in ["prijava", "odjava", "check in", "check out"]):
        return "prijava_odjava"

    # Parking
    if "parkir" in text:
        return "parking"

    # Živali
    if any(w in text for w in ["pes", "psa", "psi", "psov", "mačk", "žival", "ljubljenč", "kuža", "kuz", "dog"]):
        return "zivali"

    # Plačilo
    if any(w in text for w in ["plačilo", "kartic", "gotovina"]):
        return "placilo"

    # Kontakt / telefon
    if any(
        w in text
        for w in ["telefon", "telefonsko", "številka", "stevilka", "gsm", "mobitel", "mobile", "phone"]
    ):
        return "kontakt"

    # Min nočitve
    if any(w in text for w in ["minimal", "najmanj noči", "najmanj nočitev", "min nočitev"]):
        return "min_nocitve"

    # Kapaciteta miz
    if any(w in text for w in ["koliko miz", "kapaciteta"]):
        return "kapaciteta_mize"

    # Alergije
    if any(w in text for w in ["alergij", "gluten", "lakto", "vegan"]):
        return "alergije"

    # Vina / vinska karta
    if any(w in text for w in ["vino", "vina", "vinsko", "vinska", "wine", "wein", "vinci"]):
        return "vina"

    # Izleti / turizem
    if any(
        w in text
        for w in [
            "izlet",
            "izleti",
            "znamenitost",
            "naravne",
            "narava",
            "pohod",
            "pohodni",
            "okolici",
            "bližini",
            "pohorje",
            "slap",
            "jezero",
            "vintgar",
            "razgled",
            "bistriški",
            "ščrno jezero",
            "šumik",
        ]
    ):
        return "turizem"

    # Izposoja koles
    if any(w in text for w in ["kolo", "koles", "kolesar", "bike", "e-kolo", "ekolo", "bicikl"]):
        return "kolesa"

    # Slap Skalca
    if "skalca" in text or ("slap" in text and "skalc" in text):
        return "skalca"

    # Darilni boni
    if "darilni bon" in text or ("bon" in text and "daril" in text):
        return "darilni_boni"

    # Vikend ponudba / jedilnik
    if ("vikend" in text or "ponudba" in text) and any(
        w in text for w in ["vikend", "ponudba", "kosilo", "meni", "menu", "jedil"]
    ):
        return "jedilnik"

    # Dodatno: jedilnik / meni
    if any(
        w in text
        for w in [
            "jedilnik",
            "jedilnk",
            "jedilnku",
            "jedlnik",
            "meni",
            "menij",
            "meniju",
            "menu",
            "kaj imate za jest",
            "kaj ponujate",
            "kaj strežete",
            "kaj je za kosilo",
            "kaj je za večerjo",
            "kaj je za vecerjo",
            "koslo",
        ]
    ):
        return "jedilnik"

    if any(w in text for w in ["družin", "druzina", "druzino"]):
        return "druzina"

    if "kmetij" in text or "kmetijo" in text:
        return "kmetija"

    if "gibanica" in text:
        return "gibanica"

    if any(w in text for w in ["izdelk", "trgovin", "katalog", "prodajate"]):
        return "izdelki"

    return None


# Produkti (hitri odgovori brez LLM)
PRODUCT_RESPONSES = {
    "izdelki_splosno": [
        "Izdelki so na voljo v naši spletni trgovini: https://shop.kmetija-urska.si/trgovina/",
        "Naša spletna trgovina: https://shop.kmetija-urska.si/trgovina/",
    ],
    "darilni_bon": [
        "Darilni boni so v trgovini: https://shop.kmetija-urska.si/product/darilni-bon-100-eur",
    ],
}



def detect_product_intent(message: str) -> Optional[str]:
    text = message.lower()
    if "darilni bon" in text:
        return "darilni_bon"
    if any(w in text for w in ["izdelk", "prodaj", "kupiti", "kaj imate", "trgovin", "naroč", "naroc"]):
        return "izdelki_splosno"
    return None


def get_product_response(key: str) -> str:
    if key in PRODUCT_RESPONSES:
        return random.choice(PRODUCT_RESPONSES[key])
    return PRODUCT_RESPONSES["izdelki_splosno"][0]


def get_booking_continuation(step: str, state: dict) -> str:
    """Vrne navodilo za nadaljevanje glede na trenutni korak."""
    continuations = {
        "awaiting_date": "Za kateri **datum** bi rezervirali?",
        "awaiting_nights": "Koliko **nočitev**?",
        "awaiting_people": "Za koliko **oseb**?",
        "awaiting_kids": "Koliko je **otrok** in koliko so stari?",
        "awaiting_kids_info": "Koliko je **otrok** in koliko so stari?",
        "awaiting_kids_ages": "Koliko so stari **otroci**?",
        "awaiting_room_location": "Katero **sobo** želite? (ALJAŽ, JULIJA, ANA)",
        "awaiting_name": "Vaše **ime in priimek**?",
        "awaiting_phone": "Vaša **telefonska številka**?",
        "awaiting_email": "Vaš **e-mail**?",
        "awaiting_dinner": "Želite **večerje**? (Da/Ne)",
        "awaiting_dinner_count": "Za koliko oseb želite **večerje**?",
        "awaiting_note": "Želite še kaj **sporočiti**? (ali 'ne')",
        "awaiting_time": "Ob kateri **uri**?",
        "awaiting_table_date": "Za kateri **datum** bi rezervirali mizo?",
        "awaiting_table_time": "Ob kateri **uri** bi prišli?",
        "awaiting_table_people": "Za koliko **oseb**?",
        "awaiting_table_location": "Katero **jedilnico** želite? (Pri peči / Pri vrtu)",
        "awaiting_table_event_type": "Kakšen je **tip dogodka**?",
        "awaiting_confirmation": "Potrdite rezervacijo? (da/ne)",
    }
    return continuations.get(step or "", "Lahko nadaljujemo z rezervacijo?")


def handle_info_during_booking(message: str, session_state: dict) -> Optional[str]:
    """
    Če je booking aktiven in uporabnik vpraša info ali produkt, odgovorimo + nadaljujemo flow.
    """
    if not session_state or session_state.get("step") is None:
        return None

    info_key = detect_info_intent(message)
    if info_key:
        info_response = get_info_response(info_key, message)
        continuation = get_booking_continuation(session_state.get("step"), session_state)
        return f"{info_response}\n\n---\n\n📝 **Nadaljujemo z rezervacijo:**\n{continuation}"

    product_key = detect_product_intent(message)
    if product_key:
        product_response = get_product_response(product_key)
        if is_bulk_order_request(message):
            product_response = f"{product_response}\n\nZa večja naročila nam pišite na urska@kmetija-urska.si."
        continuation = get_booking_continuation(session_state.get("step"), session_state)
        return f"{product_response}\n\n---\n\n📝 **Nadaljujemo z rezervacijo:**\n{continuation}"

    return None


def is_food_question_without_booking_intent(message: str) -> bool:
    """True če je vprašanje o hrani brez jasne rezervacijske namere."""
    text = message.lower()
    food_words = ["meni", "menu", "hrana", "jed", "kosilo", "večerja", "kaj ponujate", "kaj strežete", "kaj imate za kosilo", "jedilnik"]
    booking_words = ["rezerv", "book", "želim", "rad bi", "radi bi", "za datum", "oseb", "mizo", "rezervacijo"]
    has_food = any(w in text for w in food_words)
    has_booking = any(w in text for w in booking_words)
    return has_food and not has_booking


def is_info_only_question(message: str) -> bool:
    """
    Vrne True če je vprašanje SAMO info (brez booking namere).
    Ta vprašanja ne smejo sprožiti rezervacije.
    """
    text = message.lower()
    info_words = [
        "koliko",
        "kakšn",
        "kakšen",
        "kdo",
        "ali imate",
        "a imate",
        "kaj je",
        "kdaj",
        "kje",
        "kako",
        "cena",
        "stane",
        "vključen",
    ]
    booking_words = [
        "rezervir",
        "book",
        "bi rad",
        "bi radi",
        "želim",
        "želimo",
        "za datum",
        "nocitev",
        "nočitev",
        "oseb",
    ]
    has_info = any(w in text for w in info_words)
    has_booking = any(w in text for w in booking_words)
    return has_info and not has_booking


def is_reservation_typo(message: str) -> bool:
    """Fuzzy zazna tipkarske napake pri 'rezervacija'."""
    words = re.findall(r"[a-zA-ZčšžČŠŽ]+", message.lower())
    targets = ["rezervacija", "rezervirati", "rezerviram", "rezerviraj"]
    for word in words:
        for target in targets:
            if difflib.SequenceMatcher(None, word, target).ratio() >= 0.75:
                return True
    return False


def is_ambiguous_reservation_request(message: str) -> bool:
    lowered = message.lower()
    reserv_words = ["rezerv", "book", "booking", "reserve", "reservation", "zimmer", "buchen"]
    type_words = ["soba", "sobo", "sobe", "room", "miza", "mizo", "table", "nočitev", "nocitev"]
    has_reserv = any(w in lowered for w in reserv_words)
    has_type = any(w in lowered for w in type_words)
    return has_reserv and not has_type


def is_ambiguous_inquiry_request(message: str) -> bool:
    lowered = message.lower()
    if any(w in lowered for w in ["večerj", "vecerj"]):
        return False
    explicit = ["povpraš", "ponudb", "naročil", "naročilo", "naroč", "količin"]
    has_explicit = any(w in lowered for w in explicit)
    has_number = re.search(r"\d", lowered) is not None
    has_product = any(stem in lowered for stem in PRODUCT_STEMS) or any(
        word in lowered for word in ["potica", "potic", "torta", "darilni paket"]
    )
    return has_explicit and not (has_number and has_product)


def is_inquiry_trigger(message: str) -> bool:
    lowered = message.lower()
    if any(w in lowered for w in ["večerj", "vecerj"]):
        return False
    explicit = [
        "povpraš",
        "ponudb",
        "naročil",
        "naročilo",
        "naroč",
        "količin",
        "večja količina",
        "vecja kolicina",
        "teambuilding",
        "poroka",
        "pogrebščina",
        "pogrebscina",
        "pogostitev",
        "catering",
    ]
    if any(t in lowered for t in explicit):
        return True
    has_number = re.search(r"\d", lowered) is not None
    has_product = any(stem in lowered for stem in PRODUCT_STEMS) or any(
        word in lowered for word in ["potica", "potic", "torta", "darilni paket"]
    )
    return has_number and has_product


def is_strong_inquiry_request(message: str) -> bool:
    """Hitro zazna, ali uporabnik eksplicitno želi povpraševanje/naročilo."""
    return is_inquiry_trigger(message)


def is_reservation_related(message: str) -> bool:
    lowered = message.lower()
    reserv_tokens = ["rezerv", "book", "booking", "reserve", "reservation", "zimmer"]
    type_tokens = ["soba", "sobo", "sobe", "room", "miza", "mizo", "table", "nočitev", "nocitev"]
    return any(t in lowered for t in reserv_tokens + type_tokens)


def should_switch_from_reservation(message: str, state: dict[str, Optional[str | int]]) -> bool:
    lowered = message.lower()
    if is_reservation_related(message):
        return False
    if is_affirmative(message) or lowered in {"ne", "no"}:
        return False
    if extract_date(message) or extract_date_range(message) or extract_time(message):
        return False
    if parse_people_count(message).get("total"):
        return False
    if state.get("step") in {"awaiting_phone", "awaiting_email"}:
        return False
    if detect_info_intent(message) or detect_product_intent(message) or is_menu_query(message) or is_hours_question(message):
        return True
    if is_tourist_query(message):
        return True
    return False

def is_product_followup(message: str) -> bool:
    lowered = message.lower()
    if not last_product_query:
        return False
    if any(phrase in lowered for phrase in PRODUCT_FOLLOWUP_PHRASES):
        return True
    return False


def extract_email(text: str) -> str:
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return match.group(0) if match else ""


def extract_phone(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    return digits if len(digits) >= 7 else ""


def is_bulk_order_request(message: str) -> bool:
    """True, če uporabnik omenja večje količine (npr. 20+ kosov/paketov)."""
    nums = re.findall(r"\d+", message)
    if nums and any(int(n) >= 20 for n in nums):
        return True
    bulk_words = ["večja količina", "veliko", "na zalogo", "zalogo", "bulk", "škatl", "karton", "več paketov"]
    return any(w in message.lower() for w in bulk_words)


def _fuzzy_contains(text: str, patterns: set[str]) -> bool:
    return any(pat in text for pat in patterns)


def detect_router_intent(message: str, state: dict[str, Optional[str | int]]) -> str:
    """
    Preprost router za robustno detekcijo rezervacij z fuzzy tipi.
    Vrne: booking_room | booking_table | booking_continue | none
    """
    lower = message.lower()

    if state.get("step") is not None:
        return "booking_continue"

    booking_tokens = {
        "rezerv",
        "rezev",
        "rezer",
        "rezeriv",
        "rezerver",
        "rezerveru",
        "rezr",
        "rezrv",
        "rezrvat",
        "rezerveir",
        "reserv",
        "reservier",
        "book",
        "buking",
        "booking",
        "bukng",
    }
    room_tokens = {
        "soba",
        "sobe",
        "sobo",
        "room",
        "zimmer",
        "zimmern",
        "rum",
        "camer",
        "camera",
        "accom",
        "nocit",
        "nočit",
        "nočitev",
        "nocitev",
    }
    table_tokens = {
        "miza",
        "mize",
        "mizo",
        "miz",
        "table",
        "tabl",
        "tabel",
        "tble",
        "tablle",
        "tafel",
        "tisch",
        "koslo",  # typo kosilo
        "kosilo",
        "vecerj",
        "veceja",
        "vecher",
    }

    has_booking = _fuzzy_contains(lower, booking_tokens)
    has_room = _fuzzy_contains(lower, room_tokens)
    has_table = _fuzzy_contains(lower, table_tokens)

    if has_booking and has_room:
        return "booking_room"
    if has_booking and has_table:
        return "booking_table"
    # fallback: omemba sobe + nočitve tudi brez rezerv besed
    if has_room and ("nocit" in lower or "noč" in lower or "night" in lower):
        return "booking_room"
    # omemba mize + časa/oseb brez booking besed
    if has_table and any(tok in lower for tok in ["oseb", "ob ", ":00"]):
        return "booking_table"

    return "none"


def format_products(query: str) -> str:
    products = find_products(query)
    if not products:
        return "Trenutno nimam podatkov o izdelkih, prosim preverite spletno trgovino ali nas kontaktirajte."

    product_lines = [
        f"- {product.name}: {product.price:.2f} EUR, {product.weight:.2f} kg"
        for product in products
    ]
    header = "Na voljo imamo naslednje izdelke:\n"
    return header + "\n".join(product_lines)


def answer_product_question(message: str) -> str:
    """Odgovarja na vprašanja o izdelkih z linki do spletne trgovine."""
    from app.rag.knowledge_base import KNOWLEDGE_CHUNKS

    lowered = message.lower()

    # Določi kategorijo
    category = None
    if "marmelad" in lowered or "džem" in lowered or "dzem" in lowered:
        category = "marmelad"
    elif (
        "liker" in lowered
        or "žganj" in lowered
        or "zganj" in lowered
        or "žgan" in lowered
        or "zgan" in lowered
        or "žgane" in lowered
        or "zganje" in lowered
        or "tepkovec" in lowered
        or "borovni" in lowered
    ):
        category = "liker"
    elif "bunk" in lowered:
        category = "bunka"
    elif "salam" in lowered or "klobas" in lowered or "mesn" in lowered:
        category = "mesn"
    elif "namaz" in lowered or "pašteta" in lowered or "pasteta" in lowered:
        category = "namaz"
    elif "sirup" in lowered or "sok" in lowered:
        category = "sirup"
    elif "čaj" in lowered or "caj" in lowered:
        category = "caj"
    elif "paket" in lowered or "daril" in lowered:
        category = "paket"

    # Poišči izdelke
    results = []
    for c in KNOWLEDGE_CHUNKS:
        if "/izdelek/" not in c.url:
            continue
        
        url_lower = c.url.lower()
        title_lower = c.title.lower() if c.title else ""
        content_lower = c.paragraph.lower() if c.paragraph else ""
        
        if category:
            if category == "marmelad" and ("marmelad" in url_lower or "marmelad" in title_lower):
                if "paket" in url_lower or "paket" in title_lower:
                    continue
                results.append(c)
            elif category == "liker" and ("liker" in url_lower or "tepkovec" in url_lower):
                results.append(c)
            elif category == "bunka" and "bunka" in url_lower:
                results.append(c)
            elif category == "mesn" and ("salama" in url_lower or "klobas" in url_lower):
                results.append(c)
            elif category == "namaz" and ("namaz" in url_lower or "pastet" in url_lower):
                results.append(c)
            elif category == "sirup" and ("sirup" in url_lower or "sok" in url_lower):
                results.append(c)
            elif category == "caj" and "caj" in url_lower:
                results.append(c)
            elif category == "paket" and "paket" in url_lower:
                results.append(c)
        else:
            # Splošno iskanje po ključnih besedah
            words = [w for w in lowered.split() if len(w) > 3]
            for word in words:
                if word in url_lower or word in title_lower or word in content_lower:
                    results.append(c)
                    break
    
    # Odstrani duplikate in omeji na 5
    seen = set()
    unique = []
    for c in results:
        if c.url not in seen:
            seen.add(c.url)
            unique.append(c)
        if len(unique) >= 5:
            break
    
    if not unique:
        if category == "marmelad":
            return (
                "Imamo več domačih marmelad (npr. božična, jagodna, borovničeva). "
                "Celoten izbor si lahko ogledate v spletni trgovini: https://shop.kmetija-urska.si/trgovina/."
            )
        if category == "liker":
            return "Na voljo je domač borovničev liker (13 €) ter nekaj drugih domačih likerjev. Če želiš seznam, mi povej, ali raje pokličeš."
        return "Trenutno v bazi ne najdem konkretnih izdelkov za to vprašanje. Predlagam, da pobrskaš po spletni trgovini: https://shop.kmetija-urska.si/trgovina/."
    
    # Formatiraj odgovor
    import re
    lines = ["Na voljo imamo:"]
    for c in unique:
        text = c.paragraph.strip() if c.paragraph else ""
        # Izvleci ceno
        price = ""
        price_match = re.match(r'^(\d+[,\.]\d+\s*€)', text)
        if price_match:
            price = price_match.group(1)
            text = text[len(price_match.group(0)):].strip()
        # Skrajšaj opis
        for marker in [" Kategorija:", " V naši ponudbi", " Šifra:"]:
            idx = text.find(marker)
            if idx > 10:
                text = text[:idx]
        if len(text) > 100:
            text = text[:100] + "..."
        
        title = c.title or "Izdelek"
        if price:
            lines.append(f"• **{title}** ({price}) - {text}")
        else:
            lines.append(f"• **{title}** - {text}")
        lines.append(f"  👉 {c.url}")
    
    lines.append("\nČe želite, vam povem še za kakšen izdelek!")
    return "\n".join(lines)


def is_product_query(message: str) -> bool:
    lowered = message.lower()
    return any(stem in lowered for stem in PRODUCT_STEMS)


def is_info_query(message: str) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in INFO_KEYWORDS)


def is_hours_question(message: str) -> bool:
    lowered = message.lower()
    patterns = [
        "odprti",
        "odprt",
        "odpiralni",
        "obratovalni",
        "obratujete",
        "do kdaj",
        "kdaj lahko pridem",
        "kdaj ste",
        "kateri uri",
        "kosilo ob",
        "kosilo do",
        "kosila",
        "zajtrk",
        "breakfast",
        "večerj",
        "vecerj",
        "prijava",
        "odjava",
        "check-in",
        "check out",
        "kosilo",
        "večerja",
        "vecerja",
    ]
    return any(pat in lowered for pat in patterns)


def is_menu_query(message: str) -> bool:
    lowered = message.lower()
    reservation_indicators = ["rezerv", "sobo", "sobe", "mizo", "nočitev", "nočitve", "nocitev"]
    if any(indicator in lowered for indicator in reservation_indicators):
        return False
    weekly_indicators = [
        "teden",
        "tedensk",
        "čez teden",
        "med tednom",
        "sreda",
        "četrtek",
        "petek",
        "hodni",
        "hodn",
        "hodov",
        "degustacij",
        "kulinarično",
        "doživetje",
    ]
    if any(indicator in lowered for indicator in weekly_indicators):
        return False
    menu_keywords = ["jedilnik", "meni", "meniju", "jedo", "kuhate"]
    if any(word in lowered for word in menu_keywords):
        return True
    if "vikend kosilo" in lowered or "vikend kosila" in lowered:
        return True
    if "kosilo" in lowered and "rezerv" not in lowered and "mizo" not in lowered:
        return True
    return False


def parse_month_from_text(message: str) -> Optional[int]:
    lowered = message.lower()
    month_map = {
        "januar": 1,
        "januarja": 1,
        "februar": 2,
        "februarja": 2,
        "marec": 3,
        "marca": 3,
        "april": 4,
        "aprila": 4,
        "maj": 5,
        "maja": 5,
        "junij": 6,
        "junija": 6,
        "julij": 7,
        "julija": 7,
        "avgust": 8,
        "avgusta": 8,
        "september": 9,
        "septembra": 9,
        "oktober": 10,
        "oktobra": 10,
        "november": 11,
        "novembra": 11,
        "december": 12,
        "decembra": 12,
    }
    for key, val in month_map.items():
        if key in lowered:
            return val
    return None


def parse_relative_month(message: str) -> Optional[int]:
    lowered = message.lower()
    today = datetime.now()
    if "jutri" in lowered:
        target = today + timedelta(days=1)
        return target.month
    if "danes" in lowered:
        return today.month
    return None


def next_menu_intro() -> str:
    global menu_intro_index
    intro = MENU_INTROS[menu_intro_index % len(MENU_INTROS)]
    menu_intro_index += 1
    return intro


def answer_farm_info(message: str) -> str:
    lowered = message.lower()

    if any(word in lowered for word in ["zajc", "zajček", "zajcka", "zajčki", "kunec", "zajce"]):
        return "Imamo prijazne zajčke, ki jih lahko obiskovalci božajo. Ob obisku povejte, pa vas usmerimo do njih."

    if any(word in lowered for word in ["ogled", "tour", "voden", "vodenje", "guid", "sprehod po kmetiji"]):
        return "Organiziranih vodenih ogledov pri nas ni. Ob obisku se lahko samostojno sprehodite in vprašate osebje, če želite videti živali."

    if any(word in lowered for word in ["navodila", "pot", "pot do", "pridem", "priti", "pot do vas", "avtom"]):
        return FARM_INFO["directions"]["from_maribor"]

    if any(word in lowered for word in ["kje", "naslov", "lokacija", "nahajate"]):
        return (
            f"Nahajamo se na: {FARM_INFO['address']} ({FARM_INFO['location_description']}). "
            f"Parking: {FARM_INFO['parking']}. Če želite navodila za pot, povejte, od kod prihajate."
        )

    if any(word in lowered for word in ["telefon", "številka", "stevilka", "poklicat", "klicat"]):
        return f"Telefon: {FARM_INFO['phone']}, mobitel: {FARM_INFO['mobile']}. Pišete lahko na {FARM_INFO['email']}."

    if "email" in lowered or "mail" in lowered:
        return f"E-mail: {FARM_INFO['email']}. Splet: {FARM_INFO['website']}."

    if any(word in lowered for word in ["odprt", "kdaj", "delovni", "ura"]):
        return (
            f"Kosila: {FARM_INFO['opening_hours']['restaurant']} | "
            f"Sobe: {FARM_INFO['opening_hours']['rooms']} | "
            f"Trgovina: {FARM_INFO['opening_hours']['shop']} | "
            f"Zaprto: {FARM_INFO['opening_hours']['closed']}"
        )

    if "parking" in lowered or "parkirišče" in lowered or "parkirisce" in lowered or "avto" in lowered:
        return f"{FARM_INFO['parking']}. Naslov za navigacijo: {FARM_INFO['address']}."

    if "wifi" in lowered or "internet" in lowered or "klima" in lowered:
        facilities = ", ".join(FARM_INFO["facilities"])
        return f"Na voljo imamo: {facilities}."

    if any(word in lowered for word in ["počet", "delat", "aktivnost", "izlet"]):
        activities = "; ".join(FARM_INFO["activities"])
        return f"Pri nas in v okolici lahko: {activities}."

    if is_hours_question(message):
        return (
            "Kosila: sobota/nedelja 12:00-20:00 (zadnji prihod 15:00). "
            "Zajtrk: 8:00–9:00 (za goste sob). "
            "Prijava 15:00–20:00, odjava do 11:00. "
            "Večerje za goste po dogovoru (pon/torki kuhinja zaprta)."
        )

    return (
        f"{FARM_INFO['name']} | Naslov: {FARM_INFO['address']} | Tel: {FARM_INFO['phone']} | "
        f"Email: {FARM_INFO['email']} | Splet: {FARM_INFO['website']}"
    )


def answer_food_question(message: str) -> str:
    lowered = message.lower()
    if "alerg" in lowered or "gob" in lowered or "glive" in lowered:
        return (
          "Alergije uredimo brez težav. Ob rezervaciji zapiši alergije (npr. brez gob) ali povej osebju ob prihodu, da lahko prilagodimo jedi. "
          "Želiš, da označim alergije v tvoji rezervaciji?"
        )
    return (
        "Naša kulinarika je sezonska in temelji na domačih sestavinah.\n"
        "Za aktualno ponudbo in cene poglejte kulinariko ali cenik.\n"
        "Posebne zahteve (vege, brez glutena) uredimo ob rezervaciji."
    )


def answer_room_pricing(message: str) -> str:
    """Odgovori na vprašanja o cenah sob."""
    lowered = message.lower()

    if "večerj" in lowered or "penzion" in lowered or "polpenzion" in lowered:
        return (
            f"**Polpenzion**: {ROOM_PRICING['half_board_price']}€/oseba/noč.\n"
            f"Poleti (julij/avgust) je **razširjeni polpenzion** {ROOM_PRICING['summer_half_board_price']}€/oseba/noč.\n"
            f"Večerja je po dogovoru ({ROOM_PRICING['dinner_time']})."
        )

    if "otro" in lowered or "popust" in lowered or "otrok" in lowered:
        return (
            "Popusti za otroke so navedeni v ceniku. "
            "Povejte starost otrok in termin, da lahko preverim natančno."
        )

    return (
        f"**Nočitev z zajtrkom**: {ROOM_PRICING['bed_breakfast_price']}€/oseba/noč\n"
        f"**Polpenzion**: {ROOM_PRICING['half_board_price']}€/oseba/noč\n\n"
        f"**Minimalno bivanje poleti**: {ROOM_PRICING['min_nights_summer']} noči (julij/avgust)\n"
        f"**Prijava/odjava**: {ROOM_PRICING['check_in']} / {ROOM_PRICING['check_out']}\n\n"
        "Za rezervacijo povejte datum in število oseb!"
    )


def get_help_response() -> str:
    return (
        "Pomagam vam lahko z:\n"
        "📅 Rezervacije – sobe ali mize\n"
        "🍽️ Kulinarika – sezonski meni in ponudba\n"
        "🏠 Info o kmetiji – lokacija, kontakt, pogoji\n"
        "🛒 Trgovina – izdelki in darilni boni\n"
        "❓ Vprašanja – karkoli o naši ponudbi\n"
        "Kar vprašajte!"
    )


def is_full_menu_request(message: str) -> bool:
    lowered = message.lower()
    return any(
        phrase in lowered
        for phrase in [
            "celoten meni",
            "celotni meni",
            "poln meni",
            "celoten jedilnik",
            "celotni jedilnik",
            "poln jedilnik",
        ]
    )


def format_current_menu(month_override: Optional[int] = None, force_full: bool = False) -> str:
    if not SEASONAL_MENUS:
        return (
            "Meni je sezonski in ga objavljamo na naši spletni strani.\n"
            "Za točen meni povejte termin ali poglejte:\n"
            "https://www.kmetija-urska.si/kulinarika/"
        )
    now = datetime.now()
    month = month_override or now.month
    current = None
    for menu in SEASONAL_MENUS:
        if month in menu["months"]:
            current = menu
            break
    if not current:
        current = SEASONAL_MENUS[0]
    lines = [
        next_menu_intro(),
        f"{current['label']}",
    ]
    items = [item for item in current["items"] if not item.lower().startswith("cena")]
    if SHORT_MODE and not force_full:
        for item in items[:4]:
            lines.append(f"- {item}")
        lines.append("Cena: 36 EUR odrasli, otroci 4–12 let -50%.")
        lines.append("")
        lines.append("Za celoten sezonski meni recite: \"celoten meni\".")
    else:
        for item in items:
            lines.append(f"- {item}")
        lines.append("Cena: 36 EUR odrasli, otroci 4–12 let -50%.")
        lines.append("")
        lines.append(
            "Jedilnik je sezonski; če želiš meni za drug mesec, samo povej mesec (npr. 'kaj pa novembra'). "
            "Vege ali brez glutena uredimo ob rezervaciji."
        )
    return "\n".join(lines)


def extract_people_count(message: str) -> Optional[int]:
    """
    Ekstrahira skupno število oseb iz sporočila.
    Podpira formate:
      - "2+2" ali "2 + 2"
      - "2 odrasla in 2 otroka"
      - "4 osebe"
    """
    explicit_match = re.search(r"za\s+(\d+)", message, re.IGNORECASE)
    if explicit_match:
        return int(explicit_match.group(1))

    cleaned = re.sub(r"\d{1,2}\.\d{1,2}\.\d{2,4}", " ", message)
    cleaned = re.sub(r"\d{1,2}:\d{2}", " ", cleaned)
    nums = re.findall(r"\d+", cleaned)
    if not nums:
        return None
    # če najdemo več števil, jih seštejemo (uporabno za "2 odrasla in 2 otroka"),
    # a če je naveden skupni "za X oseb", uporabimo zadnjo številko
    if len(nums) > 1:
        tail_people = re.search(r"(\d+)\s*(oseb|osob|people|persons)", cleaned, re.IGNORECASE)
        if tail_people:
            return int(tail_people.group(1))
        if "za" in message.lower():
            return int(nums[-1])
        return sum(int(n) for n in nums)
    return int(nums[0])


def parse_people_count(message: str) -> dict[str, Optional[str | int]]:
    """
    Vrne slovar: {total, adults, kids, ages}
    Podpira formate:
      - "4 osebe"
      - "2+2" ali "2 + 2"
      - "2 odrasla + 2 otroka"
      - "2 odrasla, 2 otroka (3 in 7 let)"
    """
    result: dict[str, Optional[str | int]] = {"total": None, "adults": None, "kids": None, "ages": None}
    ages_match = re.search(r"\(([^)]*let[^)]*)\)", message)
    if ages_match:
        result["ages"] = ages_match.group(1).strip()

    plus_match = re.search(r"(\d+)\s*\+\s*(\d+)", message)
    if plus_match:
        adults = int(plus_match.group(1))
        kids = int(plus_match.group(2))
        result["adults"] = adults
        result["kids"] = kids
        result["total"] = adults + kids
        return result

    adults_match = re.search(r"(\d+)\s*odrasl", message, re.IGNORECASE)
    kids_match = re.search(r"(\d+)\s*otrok", message, re.IGNORECASE)
    if adults_match:
        result["adults"] = int(adults_match.group(1))
    if kids_match:
        result["kids"] = int(kids_match.group(1))
    if result["adults"] is not None or result["kids"] is not None:
        result["total"] = (result["adults"] or 0) + (result["kids"] or 0)
        return result

    total_match = re.search(r"(\d+)\s*oseb", message, re.IGNORECASE)
    if total_match:
        result["total"] = int(total_match.group(1))
        return result

    digits = re.findall(r"\d+", message)
    if len(digits) == 1:
        result["total"] = int(digits[0])
    elif len(digits) == 2:
        adults = int(digits[0])
        kids = int(digits[1])
        result["adults"] = adults
        result["kids"] = kids
        result["total"] = adults + kids

    return result


def parse_kids_response(message: str) -> dict[str, Optional[str | int]]:
    """
    Parsira odgovor na vprašanje o otrocih.
    Podpira formate:
    - "2 otroka, 8 in 6 let"
    - "2...8 in 6"
    - "2, stari 8 in 6"
    - "da, 2 otroka"
    - "2 (8 in 6 let)"
    - "nimam" / "ne" / "brez"
    """
    result: dict[str, Optional[str | int]] = {"kids": None, "ages": None}
    text = message.lower().strip()

    if any(w in text for w in ["ne", "nimam", "brez", "0"]):
        result["kids"] = 0
        result["ages"] = ""
        return result

    numbers = re.findall(r"\d+", message)
    if numbers:
        result["kids"] = int(numbers[0])

    ages_patterns = [
        r"(\d+)\s*(?:in|,|&)\s*(\d+)\s*let",
        r"star[ia]?\s+(\d+)\s*(?:in|,|&)?\s*(\d+)?",
        r"let[^0-9]*(\d+)",
    ]
    for pattern in ages_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            groups = [g for g in match.groups() if g]
            if groups:
                result["ages"] = " in ".join(groups) + " let"
                break

    if not result["ages"] and len(numbers) > 1:
        age_nums = numbers[1:]
        result["ages"] = " in ".join(age_nums) + " let"

    if not result["ages"]:
        dots_match = re.search(r"(\d+)\.+(\d+)", message)
        if dots_match:
            result["kids"] = int(dots_match.group(1))
            rest = message[dots_match.end():]
            rest_nums = re.findall(r"\d+", rest)
            if rest_nums:
                all_ages = [dots_match.group(2)] + rest_nums
                result["ages"] = " in ".join(all_ages) + " let"
            else:
                result["ages"] = dots_match.group(2) + " let"

    return result


def advance_after_room_people(reservation_state: dict[str, Optional[str | int]]) -> str:
    """Premakne flow po tem, ko poznamo število oseb."""
    people_val = int(reservation_state.get("people") or 0)
    reservation_state["rooms"] = max(1, (people_val + 3) // 4)
    available, alternative = reservation_service.check_room_availability(
        reservation_state["date"] or "",
        reservation_state["nights"] or 0,
        people_val,
        reservation_state["rooms"],
    )
    if not available:
        reservation_state["step"] = "awaiting_room_date"
        free_now = reservation_service.available_rooms(
            reservation_state["date"] or "",
            reservation_state["nights"] or 0,
        )
        free_text = ""
        if free_now:
            free_text = f" Trenutno so na ta termin proste: {', '.join(free_now)} (vsaka 2+2)."
        suggestion = (
            f"Najbližji prost termin je {alternative}. Sporočite, ali vam ustreza, ali podajte drug datum."
            if alternative
            else "Prosim izberite drug datum ali manjšo skupino."
        )
        return f"V izbranem terminu nimamo dovolj prostih sob.{free_text} {suggestion}"
    # ponudi izbiro sobe, če je več prostih
    free_rooms = reservation_service.available_rooms(
        reservation_state["date"] or "",
        reservation_state["nights"] or 0,
    )
    needed = reservation_state["rooms"] or 1
    if free_rooms and len(free_rooms) > needed:
        reservation_state["available_locations"] = free_rooms
        reservation_state["step"] = "awaiting_room_location"
        names = ", ".join(free_rooms)
        return f"Proste imamo: {names}. Katero bi želeli (lahko tudi več, npr. 'ALJAZ in ANA')?"
    # auto-assign
    if free_rooms:
        chosen = free_rooms[:needed]
        reservation_state["location"] = ", ".join(chosen)
    else:
        reservation_state["location"] = "Sobe (dodelimo ob potrditvi)"
    reservation_state["step"] = "awaiting_name"
    return "Odlično. Kako se glasi ime in priimek nosilca rezervacije?"


def extract_nights(message: str) -> Optional[int]:
    """Ekstraktira število nočitev iz sporočila."""
    cleaned = re.sub(r"\d{1,2}\.\d{1,2}\.\d{2,4}", " ", message)
    cleaned = re.sub(r"(vikend|weekend|sobota|nedelja)", " ", cleaned, flags=re.IGNORECASE)

    # 1) številka ob besedi noč/nočitev
    match = re.search(r"(\d+)\s*(noč|noc|nočit|nocit|nočitev|noči)", cleaned, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # 2) kratko sporočilo samo s številko
    stripped = cleaned.strip()
    if stripped.isdigit():
        num = int(stripped)
        if 1 <= num <= 30:
            return num

    # 3) prvo število v kratkem sporočilu (<20 znakov)
    if len(message.strip()) < 20:
        nums = re.findall(r"\d+", cleaned)
        if nums:
            num = int(nums[0])
            if 1 <= num <= 30:
                return num

    # 4) števila z besedo (eno, dve, tri, štiri ...)
    word_map = {
        "ena": 1,
        "eno": 1,
        "en": 1,
        "dve": 2,
        "dva": 2,
        "tri": 3,
        "štiri": 4,
        "stiri": 4,
        "pet": 5,
        "šest": 6,
        "sest": 6,
        "sedem": 7,
        "osem": 8,
        "devet": 9,
        "deset": 10,
    }
    for word, num in word_map.items():
        if re.search(rf"\\b{word}\\b", cleaned, re.IGNORECASE):
            return num

    return None


def extract_date(text: str) -> Optional[str]:
    """
    Vrne prvi datum v formatu d.m.yyyy / dd.mm.yyyy ali d/m/yyyy, normaliziran na DD.MM.YYYY.
    Podpira tudi 'danes', 'jutri', 'pojutri'.
    """
    today = datetime.now()
    lowered = text.lower()

    match = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", text)
    if match:
        day, month, year = match.groups()
        return f"{int(day):02d}.{int(month):02d}.{int(year):04d}"

    if "danes" in lowered:
        return today.strftime("%d.%m.%Y")
    if "jutri" in lowered:
        return (today + timedelta(days=1)).strftime("%d.%m.%Y")
    if "pojutri" in lowered:
        return (today + timedelta(days=2)).strftime("%d.%m.%Y")

    return None


def extract_date_from_text(message: str) -> Optional[str]:
    return extract_date(message)


def extract_date_range(text: str) -> Optional[tuple[str, str]]:
    """
    Vrne (start, end) datum v obliki DD.MM.YYYY, če zazna interval (npr. "23. 1. do 26. 1.").
    """
    today = datetime.now()
    match = re.search(
        r"\b(\d{1,2})\s*[./-]\s*(\d{1,2})(?:\s*[./-]\s*(\d{2,4}))?\s*(?:do|–|—|-|to)\s*(\d{1,2})\s*[./-]\s*(\d{1,2})(?:\s*[./-]\s*(\d{2,4}))?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    day1, month1, year1, day2, month2, year2 = match.groups()
    if year2 and not year1:
        year1 = year2
    year1_val = int(year1) if year1 else today.year
    year2_val = int(year2) if year2 else year1_val
    try:
        start_dt = datetime(year1_val, int(month1), int(day1))
        end_dt = datetime(year2_val, int(month2), int(day2))
    except ValueError:
        return None
    if end_dt <= start_dt:
        end_dt = datetime(year2_val + 1, int(month2), int(day2))
    start = start_dt.strftime("%d.%m.%Y")
    end = end_dt.strftime("%d.%m.%Y")
    return (start, end)


def nights_from_range(start: str, end: str) -> Optional[int]:
    try:
        start_dt = datetime.strptime(start, "%d.%m.%Y")
        end_dt = datetime.strptime(end, "%d.%m.%Y")
    except ValueError:
        return None
    nights = (end_dt - start_dt).days
    return nights if nights > 0 else None


def extract_time(text: str) -> Optional[str]:
    """
    Vrne prvi čas v formatu HH:MM (sprejme 13:00, 13.00 ali 1300).
    """
    match = re.search(r"\b(\d{1,2})[:\.]?(\d{2})\b", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def detect_reset_request(message: str) -> bool:
    lowered = message.lower()
    reset_words = [
        "reset",
        "začni znova",
        "zacni znova",
        "od začetka",
        "od zacetka",
        "zmota",
        "zmoto",
        "zmotu",
        "zmotil",
        "zmotila",
        "zgresil",
        "zgrešil",
        "zgrešila",
        "zgresila",
        "napačno",
        "narobe",
        "popravi",
        "nova rezervacija",
    ]
    exit_words = [
        "konec",
        "stop",
        "prekini",
        "nehaj",
        "pustimo",
        "pozabi",
        "ne rabim",
        "ni treba",
        "drugič",
        "drugic",
        "cancel",
        "quit",
        "exit",
        "pusti",
    ]
    return any(word in lowered for word in reset_words + exit_words)


def is_escape_command(message: str) -> bool:
    lowered = message.lower()
    escape_words = {"prekliči", "preklici", "reset", "stop", "prekini"}
    return any(word in lowered for word in escape_words)


def is_switch_topic_command(message: str) -> bool:
    lowered = message.lower()
    switch_words = {
        "zamenjaj temo",
        "menjaj temo",
        "nova tema",
        "spremeni temo",
        "gremo drugam",
        "druga tema",
    }
    return any(phrase in lowered for phrase in switch_words)


def is_affirmative(message: str) -> bool:
    lowered = message.strip().lower()
    return lowered in {
        "da",
        "ja",
        "seveda",
        "potrjujem",
        "potrdim",
        "potrdi",
        "yes",
        "oui",
        "ok",
        "okej",
        "okey",
        "sure",
        "yep",
        "yeah",
    }


def get_last_assistant_message() -> str:
    for msg in reversed(conversation_history):
        if msg.get("role") == "assistant":
            return msg.get("content", "")
    return ""


def last_bot_mentions_reservation(last_bot: str) -> bool:
    text = last_bot.lower()
    return any(token in text for token in ["rezerv", "reserve", "booking", "zimmer", "room", "mizo", "table"])


def reservation_prompt_for_state(state: dict[str, Optional[str | int]]) -> str:
    step = state.get("step")
    res_type = state.get("type")
    if res_type == "table":
        if step == "awaiting_table_date":
            return "Prosim za datum (sobota/nedelja) v obliki DD.MM.YYYY."
        if step == "awaiting_table_time":
            return "Ob kateri uri bi želeli mizo? (12:00–20:00, zadnji prihod na kosilo 15:00)"
        if step == "awaiting_table_people":
            return "Za koliko oseb pripravimo mizo?"
        if step == "awaiting_table_location":
            return "Izberi prostor: Pri peči ali Pri vrtu?"
    else:
        if step == "awaiting_room_date":
            return "Za kateri datum prihoda? (DD.MM.YYYY)"
        if step == "awaiting_nights":
            return "Koliko nočitev načrtujete? (min. 3 v jun/jul/avg, sicer 2)"
        if step == "awaiting_people":
            return "Za koliko oseb bi bilo bivanje (odrasli + otroci)?"
        if step == "awaiting_room_location":
            return "Katero sobo želite (ALJAŽ, JULIJA, ANA)?"
    if step == "awaiting_name":
        return "Prosim ime in priimek nosilca rezervacije."
    if step == "awaiting_phone":
        return "Prosim telefonsko številko."
    if step == "awaiting_email":
        return "Kam naj pošljem povzetek ponudbe? (e-pošta)"
    if step == "awaiting_dinner":
        return "Želite ob bivanju tudi večerje? (Da/Ne)"
    if step == "awaiting_dinner_count":
        return "Za koliko oseb želite večerje?"
    return "Nadaljujeva z rezervacijo – kako vam lahko pomagam?"

def get_greeting_response() -> str:
    return random.choice(GREETINGS)


def get_goodbye_response() -> str:
    return random.choice(THANKS_RESPONSES)


def is_goodbye(message: str) -> bool:
    lowered = message.lower().strip()
    if lowered in GOODBYE_KEYWORDS:
        return True
    if any(keyword in lowered for keyword in ["hvala", "adijo", "nasvidenje", "čao", "ciao", "bye"]):
        return True
    return False


def detect_language(message: str) -> str:
    """Zazna jezik sporočila. Vrne 'si', 'en' ali 'de'."""
    lowered = message.lower()
    
    # Slovenske besede, ki vsebujejo angleške nize (izjeme), odstranimo pred detekcijo
    slovak_exceptions = ["liker", "likerj", " like ", "slike"]
    for exc in slovak_exceptions:
        lowered = lowered.replace(exc, "")

    german_words = [
        "ich",
        "sie",
        "wir",
        "haben",
        "möchte",
        "möchten",
        "können",
        "bitte",
        "zimmer",
        "tisch",
        "reservierung",
        "reservieren",
        "buchen",
        "wann",
        "wie",
        "was",
        "wo",
        "gibt",
        "guten tag",
        "hallo",
        "danke",
        "preis",
        "kosten",
        "essen",
        "trinken",
        "wein",
        "frühstück",
        "abendessen",
        "mittag",
        "nacht",
        "übernachtung",
    ]
    german_count = sum(1 for word in german_words if word in lowered)

    # posebna obravnava angleškega zaimka "I" kot samostojne besede
    english_pronoun = 1 if re.search(r"\bi\b", lowered) else 0

    english_words = [
        " we ",
        "you",
        "have",
        "would",
        " like ",
        "want",
        "can",
        "room",
        "table",
        "reservation",
        "reserve",
        "book",
        "booking",
        "when",
        "how",
        "what",
        "where",
        "there",
        "hello",
        "hi ",
        "thank",
        "price",
        "cost",
        "food",
        "drink",
        "wine",
        "menu",
        "breakfast",
        "dinner",
        "lunch",
        "night",
        "stay",
        "please",
    ]
    english_count = english_pronoun + sum(1 for word in english_words if word in lowered)

    if german_count >= 2:
        return "de"
    if english_count >= 2:
        return "en"
    if german_count == 1 and english_count == 0:
        return "de"
    if english_count == 1 and german_count == 0:
        return "en"

    return "si"


def translate_reply(reply: str, lang: str) -> str:
    """Prevede odgovor v angleščino ali nemščino, če je potrebno."""
    if not reply or lang not in {"en", "de"}:
        return reply
    try:
        prompt = (
            f"Translate this to English, keep it natural and friendly:\n{reply}"
            if lang == "en"
            else f"Translate this to German/Deutsch, keep it natural and friendly:\n{reply}"
        )
        return generate_llm_answer(prompt, history=[])
    except Exception:
        return reply


def maybe_translate(text: str, target_lang: str) -> str:
    """Po potrebi prevede besedilo v angleščino ali nemščino."""
    if target_lang not in {"en", "de"} or not text:
        return text
    try:
        prompt = (
            f"Translate this to English, keep it natural and friendly:\n{text}"
            if target_lang == "en"
            else f"Translate this to German/Deutsch, keep it natural and friendly:\n{text}"
        )
        return generate_llm_answer(prompt, history=[])
    except Exception:
        return text


def translate_response(text: str, target_lang: str) -> str:
    """Prevede besedilo glede na zaznan jezik rezervacije."""
    if target_lang == "si" or target_lang is None:
        return text
    try:
        if target_lang == "en":
            prompt = f"Translate to English, natural and friendly, only translation:\\n{text}"
        elif target_lang == "de":
            prompt = f"Translate to German, natural and friendly, only translation:\\n{text}"
        else:
            return text
        return generate_llm_answer(prompt, history=[])
    except Exception:
        return text


def is_unknown_response(response: str) -> bool:
    """Preveri, ali odgovor nakazuje neznano informacijo."""
    unknown_indicators = [
        "žal ne morem",
        "nimam informacij",
        "ne vem",
        "nisem prepričan",
        "ni na voljo",
        "podatka nimam",
    ]
    response_lower = response.lower()
    return any(ind in response_lower for ind in unknown_indicators)


def get_unknown_response(language: str = "si") -> str:
    """Vrne prijazen odgovor, ko podatkov ni."""
    if language == "si":
        return random.choice(UNKNOWN_RESPONSES)
    responses = {
        "en": "Unfortunately, I cannot answer this question. 😊\n\nIf you share your email address, I will inquire and get back to you.",
        "de": "Leider kann ich diese Frage nicht beantworten. 😊\n\nWenn Sie mir Ihre E-Mail-Adresse mitteilen, werde ich mich erkundigen und Ihnen antworten.",
    }
    return responses.get(language, "Na to vprašanje žal ne morem odgovoriti. 😊")


def is_email(text: str) -> bool:
    """Preveri, ali je besedilo e-poštni naslov."""
    import re as _re

    return bool(_re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", text.strip()))


def validate_reservation_rules(arrival_date_str: str, nights: int) -> Tuple[bool, str, str]:
    cleaned_date = arrival_date_str.strip()
    try:
        datetime.strptime(cleaned_date, "%d.%m.%Y")
    except ValueError:
        return False, "Tega datuma ne razumem. Prosimo uporabite obliko DD.MM.YYYY (npr. 12.7.2025).", "date"

    if nights <= 0:
        return False, "Število nočitev mora biti pozitivno. Poskusite znova.", "nights"

    ok, message = reservation_service.validate_room_rules(cleaned_date, nights)
    if not ok:
        # vsako pravilo za sobe zahteva ponovni vnos datuma/nočitev -> vrnemo tip "date" za reset datuma
        return False, message, "date"

    return True, "", ""


def reset_reservation_state(state: dict[str, Optional[str | int]]) -> None:
    state.clear()
    state.update(_blank_reservation_state())


def start_inquiry_consent(state: dict[str, Optional[str]]) -> str:
    state["step"] = "awaiting_consent"
    return (
        "Žal nimam dovolj informacij. "
        "Lahko zabeležim povpraševanje in ga posredujem ekipi. "
        "Želite to? (da/ne)"
    )


def handle_inquiry_flow(message: str, state: dict[str, Optional[str]], session_id: str) -> Optional[str]:
    text = message.strip()
    lowered = text.lower()
    step = state.get("step")
    if is_escape_command(message) or is_switch_topic_command(message):
        reset_inquiry_state(state)
        return "V redu, prekinil sem povpraševanje. Kako vam lahko še pomagam?"

    if step == "awaiting_consent":
        if lowered in {"da", "ja", "seveda", "lahko", "ok"}:
            state["step"] = "awaiting_details"
            return "Odlično. Prosim opišite, kaj točno želite (količina, izdelek, storitev)."
        if lowered in {"ne", "ne hvala", "ni treba"}:
            reset_inquiry_state(state)
            return "V redu. Če želite, lahko vprašate še kaj drugega."
        return "Želite, da zabeležim povpraševanje? Odgovorite z 'da' ali 'ne'."

    if step == "awaiting_details":
        if text:
            state["details"] = (state.get("details") or "")
            if state["details"]:
                state["details"] += "\n" + text
            else:
                state["details"] = text
        state["step"] = "awaiting_deadline"
        return "Hvala! Do kdaj bi to potrebovali? (datum/rok ali 'ni pomembno')"

    if step == "awaiting_deadline":
        if any(word in lowered for word in ["ni", "ne vem", "kadar koli", "vseeno", "ni pomembno"]):
            state["deadline"] = ""
        else:
            state["deadline"] = text
        state["step"] = "awaiting_contact"
        return "Super. Prosim še kontakt (ime, telefon, email)."

    if step == "awaiting_contact":
        state["contact_raw"] = text
        email = extract_email(text)
        phone = extract_phone(text)
        state["contact_email"] = email or state.get("contact_email") or ""
        state["contact_phone"] = phone or state.get("contact_phone") or ""
        state["contact_name"] = state.get("contact_name") or ""
        if not state["contact_email"]:
            return "Za povratni kontakt prosim dodajte email."

        details = state.get("details") or text
        deadline = state.get("deadline") or ""
        contact_summary = state.get("contact_raw") or ""
        summary = "\n".join(
            [
                "Novo povpraševanje:",
                f"- Podrobnosti: {details}",
                f"- Rok: {deadline or 'ni naveden'}",
                f"- Kontakt: {contact_summary}",
                f"- Session: {session_id}",
            ]
        )
        reservation_service.create_inquiry(
            session_id=session_id,
            details=details,
            deadline=deadline,
            contact_name=state.get("contact_name") or "",
            contact_email=state.get("contact_email") or "",
            contact_phone=state.get("contact_phone") or "",
            contact_raw=contact_summary,
            source="chat",
            status="new",
        )
        send_custom_message(
            INQUIRY_RECIPIENT,
            "Novo povpraševanje – Urška",
            summary,
        )
        reset_inquiry_state(state)
        return "Hvala! Povpraševanje sem zabeležil in ga posredoval. Odgovorimo vam v najkrajšem možnem času."

    return None


def reset_conversation_context(session_id: Optional[str] = None) -> None:
    """Počisti začasne pogovorne podatke in ponastavi sejo."""
    global conversation_history, last_product_query, last_wine_query, last_info_query, last_menu_query
    global last_shown_products, chat_session_id, unknown_question_state, last_interaction
    if session_id:
        state = reservation_states.get(session_id)
        if state is not None:
            reset_reservation_state(state)
            reservation_states.pop(session_id, None)
        unknown_question_state.pop(session_id, None)
    else:
        for state in reservation_states.values():
            reset_reservation_state(state)
        reservation_states.clear()
        unknown_question_state = {}
    conversation_history = []
    last_product_query = None
    last_wine_query = None
    last_info_query = None
    last_menu_query = False
    last_shown_products = []
    chat_session_id = str(uuid.uuid4())[:8]
    last_interaction = None


def generate_confirmation_email(state: dict[str, Optional[str | int]]) -> str:
    subject = "Zadeva: Rezervacija – Turistična kmetija Urška"
    name = state.get("name") or "spoštovani"
    lines = [f"Pozdravljeni {name}!"]

    if state.get("type") == "room":
        try:
            adults = int(state.get("people") or 0)
        except (TypeError, ValueError):
            adults = 0
        try:
            nights_val = int(state.get("nights") or 0)
        except (TypeError, ValueError):
            nights_val = 0
        estimated_price = adults * nights_val * ROOM_PRICING["bed_breakfast_price"] if adults and nights_val else 0
        lines.append(
            f"Prejeli smo povpraševanje za sobo od {state.get('date')} za {state.get('nights')} nočitev "
            f"za {state.get('people')} gostov."
        )
        if estimated_price:
            lines.append(
                f"Okvirna cena bivanja: {estimated_price}€ ({adults} oseb × {state.get('nights')} noči × {ROOM_PRICING['bed_breakfast_price']}€). "
                "Popusti za otroke in večerje se dodajo ob potrditvi."
            )
        lines.append(
            "Zajtrk je vključen v ceno. Prijava od 14:00, odjava do 10:00, zajtrk 8:00–9:00, večerja 18:00 (pon/torki brez večerij)."
        )
        lines.append("Naše sobe so klimatizirane, na voljo je brezplačen Wi‑Fi.")
    else:
        lines.append(
            f"Prejeli smo rezervacijo mize za {state.get('people')} oseb na datum {state.get('date')} ob {state.get('time')}."
        )
        lines.append("Kuhinja ob sobotah in nedeljah deluje med 12:00 in 20:00, zadnji prihod na kosilo je ob 15:00.")

    lines.append("Rezervacijo bomo potrdili po preverjanju razpoložljivosti.")
    lines.append(f"Kontakt domačije: {CONTACT['phone']} | {CONTACT['email']}")
    body = "\n".join(lines)
    return f"{subject}\n\n{body}"


def room_intro_text() -> str:
    return (
        "Sobe: ALJAŽ (2+2), JULIJA (2+2), ANA (2+2). "
        "Minimalno 3 nočitve v juniju/juliju/avgustu, 2 nočitvi v ostalih mesecih. "
        "Prijava 14:00, odjava 10:00, zajtrk 8:00–9:00, večerja 18:00 (pon/torki brez večerij). "
        "Sobe so klimatizirane, Wi‑Fi je brezplačen, zajtrk je vključen."
    )


def table_intro_text() -> str:
    return (
        "Kosila ob sobotah in nedeljah med 12:00 in 20:00, zadnji prihod na kosilo ob 15:00. "
        "Jedilnici: 'Pri peči' (15 oseb) in 'Pri vrtu' (35 oseb)."
    )


def parse_reservation_type(message: str) -> Optional[str]:
    lowered = message.lower()

    def _has_term(term: str) -> bool:
        if " " in term:
            return term in lowered
        return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered) is not None

    # soba - slovensko, angleško, nemško
    room_keywords = [
        # slovensko
        "soba",
        "sobe",
        "sobo",
        "sob",
        "nočitev",
        "prenocitev",
        "noč",
        "prenočiti",
        "prespati",
        # angleško
        "room",
        "rooms",
        "stay",
        "overnight",
        "night",
        "accommodation",
        "sleep",
        # nemško
        "zimmer",
        "übernachtung",
        "übernachten",
        "nacht",
        "schlafen",
        "unterkunft",
    ]
    if any(_has_term(word) for word in room_keywords):
        return "room"

    # miza - slovensko, angleško, nemško
    table_keywords = [
        # slovensko
        "miza",
        "mizo",
        "mize",
        "rezervacija mize",
        "kosilo",
        "večerja",
        "kosilu",
        "mizico",
        "jest",
        "jesti",
        # angleško
        "table",
        "lunch",
        "dinner",
        "meal",
        "eat",
        "dining",
        "restaurant",
        # nemško
        "tisch",
        "mittagessen",
        "abendessen",
        "essen",
        "speisen",
        "restaurant",
    ]
    if any(_has_term(word) for word in table_keywords):
        return "table"
    return None


def _handle_room_reservation_impl(message: str, state: dict[str, Optional[str | int]]) -> str:
    reservation_state = state
    step = reservation_state["step"]

    if step == "awaiting_room_date":
        range_data = extract_date_range(message)
        if range_data:
            reservation_state["date"] = range_data[0]
            nights_candidate = nights_from_range(range_data[0], range_data[1])
            if nights_candidate:
                ok, error_message, _ = validate_reservation_rules(
                    reservation_state["date"] or "", nights_candidate
                )
                if not ok:
                    reservation_state["step"] = "awaiting_room_date"
                    reservation_state["date"] = None
                    reservation_state["nights"] = None
                    return error_message + " Prosim pošlji nov datum in št. nočitev skupaj (npr. 15.7.2025 za 3 nočitve)."
                reservation_state["nights"] = nights_candidate
                reservation_state["step"] = "awaiting_people"
                return (
                    f"Odlično, zabeležila sem {reservation_state['date']} za {reservation_state['nights']} nočitev. "
                    "Za koliko oseb bi bilo bivanje (odrasli + otroci)?"
                )
        date_candidate = extract_date(message)
        nights_candidate = extract_nights(message)
        if not date_candidate:
            reservation_state["date"] = None
            return "Z veseljem uredim sobo. 😊 Sporočite datum prihoda (DD.MM.YYYY) in približno število nočitev?"

        reservation_state["date"] = date_candidate

        # če smo že dobili nočitve v istem stavku, jih validiramo
        if nights_candidate:
            ok, error_message, _ = validate_reservation_rules(
                reservation_state["date"] or "", nights_candidate
            )
            if not ok:
                reservation_state["step"] = "awaiting_room_date"
                reservation_state["date"] = None
                reservation_state["nights"] = None
                return error_message + " Prosim pošlji nov datum in št. nočitev skupaj (npr. 15.7.2025 za 3 nočitve)."
            reservation_state["nights"] = nights_candidate
            reservation_state["step"] = "awaiting_people"
            return (
                f"Odlično, zabeležila sem {reservation_state['date']} za {reservation_state['nights']} nočitev. "
                "Za koliko oseb bi bilo bivanje (odrasli + otroci)?"
            )

        reservation_state["step"] = "awaiting_nights"
        return "Hvala! Koliko nočitev si predstavljate? (poleti min. 3, sicer 2)"

    if step == "awaiting_nights":
        range_data = extract_date_range(message)
        if range_data:
            reservation_state["date"] = range_data[0]
            nights_candidate = nights_from_range(range_data[0], range_data[1])
            if nights_candidate:
                ok, error_message, _ = validate_reservation_rules(
                    reservation_state["date"] or "", nights_candidate
                )
                if not ok:
                    reservation_state["step"] = "awaiting_room_date"
                    reservation_state["date"] = None
                    reservation_state["nights"] = None
                    return error_message + " Prosim pošlji nov datum prihoda (DD.MM.YYYY) in število nočitev."
                reservation_state["nights"] = nights_candidate
                reservation_state["step"] = "awaiting_people"
                return "Super! Za koliko oseb (odrasli + otroci skupaj)? Vsaka soba je 2+2, imamo tri sobe in jih lahko tudi kombiniramo."
        if not reservation_state["date"]:
            reservation_state["step"] = "awaiting_room_date"
            return "Najprej mi, prosim, zaupajte datum prihoda (DD.MM.YYYY), potem še število nočitev."
        nights = None
        match = re.search(r"(\d+)\s*(noč|noc|nočit|nocit|nočitev|noči)", message, re.IGNORECASE)
        if match:
            nights = int(match.group(1))
        else:
            stripped = message.strip()
            if stripped.isdigit():
                nights = int(stripped)
            else:
                nums = re.findall(r"\d+", message)
                if nums and len(message.strip()) < 20:
                    nights = int(nums[0])

        if nights is None:
            return "Koliko nočitev bi si želeli? (npr. '3' ali '3 nočitve')"
        if nights <= 0 or nights > 30:
            return "Število nočitev mora biti med 1 in 30. Koliko nočitev želite?"

        ok, error_message, error_type = validate_reservation_rules(
            reservation_state["date"] or "", nights
        )
        if not ok:
            reservation_state["step"] = "awaiting_room_date"
            reservation_state["date"] = None
            reservation_state["nights"] = None
            return error_message + " Prosim pošlji nov datum prihoda (DD.MM.YYYY) in število nočitev."
        reservation_state["nights"] = nights
        reservation_state["step"] = "awaiting_people"
        return "Super! Za koliko oseb (odrasli + otroci skupaj)? Vsaka soba je 2+2, imamo tri sobe in jih lahko tudi kombiniramo."

    if step == "awaiting_people":
        # če uporabnik popravlja nočitve v tem koraku
        if "nočit" in message.lower() or "nocit" in message.lower() or "noči" in message.lower():
            new_nights = extract_nights(message)
            if new_nights:
                ok, error_message, _ = validate_reservation_rules(
                    reservation_state["date"] or "", new_nights
                )
                if not ok:
                    return error_message + " Koliko nočitev želite?"
                reservation_state["nights"] = new_nights
                # nadaljuj vprašanje za osebe
                return f"Popravljeno na {new_nights} nočitev. Za koliko oseb (odrasli + otroci skupaj)?"
        parsed = parse_people_count(message)
        total = parsed["total"]
        if not total or total <= 0:
            return "Koliko vas bo? (npr. '2 odrasla in 1 otrok' ali '3 osebe')"
        if total > 12:
            return "Na voljo so tri sobe (vsaka 2+2). Za več kot 12 oseb nas prosim kontaktirajte na email."
        reservation_state["people"] = total
        reservation_state["adults"] = parsed["adults"]
        reservation_state["kids"] = parsed["kids"]
        reservation_state["kids_ages"] = parsed["ages"]
        if parsed["kids"] is None and parsed["adults"] is None:
            reservation_state["step"] = "awaiting_kids_info"
            return "Imate otroke? Koliko in koliko so stari?"
        if parsed["kids"] and not parsed["ages"]:
            reservation_state["step"] = "awaiting_kids_ages"
            return "Koliko so stari otroci?"
        return advance_after_room_people(reservation_state)

    if step == "awaiting_kids_info":
        text = message.lower()
        if any(word in text for word in ["ne", "brez", "ni", "nimam"]):
            reservation_state["kids"] = 0
            reservation_state["kids_ages"] = ""
            return advance_after_room_people(reservation_state)
        kids_parsed = parse_kids_response(message)
        if kids_parsed["kids"] is not None:
            reservation_state["kids"] = kids_parsed["kids"]
        if kids_parsed["ages"]:
            reservation_state["kids_ages"] = kids_parsed["ages"]
        if reservation_state.get("kids") and not reservation_state.get("kids_ages"):
            reservation_state["step"] = "awaiting_kids_ages"
            return "Koliko so stari otroci?"
        return advance_after_room_people(reservation_state)

    if step == "awaiting_kids_ages":
        reservation_state["kids_ages"] = message.strip()
        return advance_after_room_people(reservation_state)

    if step == "awaiting_note":
        skip_words = {"ne", "nic", "nič", "nimam", "brez"}
        note_text = "" if any(word in message.lower() for word in skip_words) else message.strip()
        reservation_state["note"] = note_text
        reservation_state["step"] = "awaiting_confirmation"
        chosen_location = reservation_state.get("location") or "Sobe (dodelimo ob potrditvi)"
        dinner_note = (
            f"Večerje: {reservation_state.get('dinner_people')} oseb (25€/oseba)"
            if reservation_state.get("dinner_people")
            else "Večerje: ne"
        )
        lines = [
            "Prosimo, preverite podatke:",
            f"📅 Datum: {reservation_state.get('date')}, {reservation_state.get('nights')} noči",
            f"👥 Osebe: {reservation_state.get('people')}",
            f"🛏️ Soba: {chosen_location}",
            f"👤 Ime: {reservation_state.get('name')}",
            f"📞 Telefon: {reservation_state.get('phone')}",
            f"📧 Email: {reservation_state.get('email')}",
            f"🍽️ {dinner_note}",
        ]
        if note_text:
            lines.append(f"📝 Opombe: {note_text}")
        lines.append("Potrdite rezervacijo? (da/ne)")
        return "\n".join(lines)

    if step == "awaiting_confirmation":
        if message.strip().lower() in {"ne", "no"}:
            reset_reservation_state(state)
            return "V redu, rezervacijo sem preklical. Kako vam lahko pomagam?"
        if is_affirmative(message):
            summary_state = reservation_state.copy()
            dinner_note = ""
            if reservation_state.get("dinner_people"):
                dinner_note = f"Večerje: {reservation_state.get('dinner_people')} oseb (25€/oseba)"
            chosen_location = reservation_state.get("location") or "Sobe (dodelimo ob potrditvi)"
            reservation_service.create_reservation(
                date=reservation_state["date"] or "",
                people=int(reservation_state["people"] or 0),
                reservation_type="room",
                source="chat",
                nights=int(reservation_state["nights"] or 0),
                rooms=int(reservation_state["rooms"] or 0),
                name=str(reservation_state["name"]),
                phone=str(reservation_state["phone"]),
                email=reservation_state["email"],
                location=chosen_location,
                note=(reservation_state.get("note") or "") or dinner_note,
                kids=str(reservation_state.get("kids") or ""),
                kids_small=str(reservation_state.get("kids_ages") or ""),
            )
            email_data = {
                "name": reservation_state.get("name", ""),
                "email": reservation_state.get("email", ""),
                "phone": reservation_state.get("phone", ""),
                "date": reservation_state.get("date", ""),
                "nights": reservation_state.get("nights", 0),
                "rooms": reservation_state.get("rooms", 0),
                "people": reservation_state.get("people", 0),
                "reservation_type": "room",
                "location": chosen_location,
                "note": (reservation_state.get("note") or "") or dinner_note,
                "kids": reservation_state.get("kids", ""),
                "kids_ages": reservation_state.get("kids_ages", ""),
            }
            _send_reservation_emails_async(email_data)
            saved_lang = reservation_state.get("language", "si")
            reset_reservation_state(state)
            lines = [
                "Odlično! 😊 Vaša rezervacija je zabeležena:",
                f"📅 Datum: {summary_state.get('date')}, {summary_state.get('nights')} noči",
                f"👥 Osebe: {summary_state.get('people')}",
                f"🛏️ Soba: {chosen_location}",
            ]
            if dinner_note:
                lines.append(f"🍽️ {dinner_note}")
            if reservation_state.get("note"):
                lines.append(f"📝 Opombe: {reservation_state.get('note')}")
            lines.append(RESERVATION_PENDING_MESSAGE.strip())
            return translate_response("\n".join(lines), saved_lang)
        return "Prosim potrdite z 'da' ali 'ne'."

    if step == "awaiting_room_location":
        options = reservation_state.get("available_locations") or []
        if not options:
            reservation_state["step"] = "awaiting_name"
            return "Nadaljujmo. Prosim še ime in priimek nosilca rezervacije."
        # normalizacija za šumnike
        def normalize(text: str) -> str:
            return (
                text.lower()
                .replace("š", "s")
                .replace("ž", "z")
                .replace("č", "c")
                .replace("ć", "c")
            )

        input_norm = normalize(message)
        selected = []
        any_keywords = {"vseeno", "vseen", "vseeni", "katerakoli", "katerakol", "karkoli", "any"}
        for opt in options:
            opt_norm = normalize(opt)
            if opt_norm in input_norm or input_norm == opt_norm:
                selected.append(opt)
        if input_norm.strip() in any_keywords and not selected:
            selected = options[:]
        if not selected:
            return "Prosim izberite med: " + ", ".join(options)
        needed = reservation_state.get("rooms") or 1
        if len(selected) < needed:
            # če je uporabnik izbral premalo, dopolnimo
            for opt in options:
                if opt not in selected and len(selected) < needed:
                    selected.append(opt)
        reservation_state["location"] = ", ".join(selected[:needed])
        reservation_state["step"] = "awaiting_name"
        return f"Zabeleženo: {reservation_state['location']}. Prosim še ime in priimek nosilca rezervacije."

    if step == "awaiting_name":
        full_name = message.strip()
        if len(full_name.split()) < 2:
            return "Prosim napišite ime in priimek (npr. 'Ana Novak')."
        reservation_state["name"] = full_name
        reservation_state["step"] = "awaiting_phone"
        return "Hvala! Zdaj prosim še telefonsko številko."

    if step == "awaiting_phone":
        phone = message.strip()
        digits = re.sub(r"\D+", "", phone)
        if len(digits) < 7:
            return "Zaznal sem premalo številk. Prosimo vpišite veljavno telefonsko številko."
        reservation_state["phone"] = phone
        reservation_state["step"] = "awaiting_email"
        return "Kam naj pošljem povzetek ponudbe? (e-poštni naslov)"

    if step == "awaiting_email":
        email = message.strip()
        if "@" not in email or "." not in email:
            return "Prosim vpišite veljaven e-poštni naslov (npr. info@primer.si)."
        reservation_state["email"] = email
        reservation_state["step"] = "awaiting_dinner"
        return (
            "Želite ob bivanju tudi večerje? (25€/oseba, vključuje juho, glavno jed in sladico)\n"
            "Odgovorite Da ali Ne."
        )

    if step == "awaiting_dinner":
        answer = message.strip().lower()
        positive = {
            "da",
            "ja",
            "seveda",
            "zelim",
            "želim",
            "hocem",
            "hočem",
            "polpenzion",
            "pol penzion",
            "pol-penzion",
        }
        negative = {"ne", "no", "nocem", "nočem", "brez"}

        def dinner_warning() -> Optional[str]:
            arrival = reservation_service._parse_date(reservation_state.get("date") or "")
            nights = int(reservation_state.get("nights") or 1)
            if not arrival:
                return None
            for offset in range(max(1, nights)):
                day = (arrival + timedelta(days=offset)).weekday()
                if day in {0, 1}:
                    return "Opozorilo: večerje ob ponedeljkih in torkih ne strežemo."
            return None

        warn = dinner_warning()
        if any(word in answer for word in positive):
            reservation_state["step"] = "awaiting_dinner_count"
            follow = "Za koliko oseb želite večerje?"
            if warn:
                follow = warn + " " + follow
            return follow
        if any(word in answer for word in negative):
            reservation_state["dinner_people"] = 0
            reservation_state["step"] = "awaiting_note"
            return "Želite še kaj sporočiti? (posebne želje, alergije, praznovanje...)"
        return "Prosim odgovorite z Da ali Ne glede na večerje."

    if step == "awaiting_dinner_count":
        digits = re.findall(r"\d+", message)
        if not digits:
            return "Prosim povejte za koliko oseb želite večerje (število)."
        count = int(digits[0])
        reservation_state["dinner_people"] = count
        reservation_state["step"] = "awaiting_note"
        return "Želite še kaj sporočiti? (posebne želje, alergije, praznovanje...)"

    return "Nadaljujmo z rezervacijo sobe. Za kateri datum jo želite?"


def handle_room_reservation(message: str, state: dict[str, Optional[str | int]]) -> str:
    response = _handle_room_reservation_impl(message, state)
    lang = state.get("language", "si")
    return translate_response(response, lang)


def _handle_table_reservation_impl(message: str, state: dict[str, Optional[str | int]]) -> str:
    reservation_state = state
    step = reservation_state["step"]

    def proceed_after_table_people() -> str:
        people = int(reservation_state.get("people") or 0)
        available, location, suggestions = reservation_service.check_table_availability(
            reservation_state["date"] or "",
            reservation_state["time"] or "",
            people,
        )
        if not available:
            reservation_state["step"] = "awaiting_table_time"
            alt = (
                "Predlagani prosti termini: " + "; ".join(suggestions)
                if suggestions
                else "Prosim izberite drugo uro ali enega od naslednjih vikendov."
            )
            return f"Izbran termin je zaseden. {alt}"
        # če imamo lokacijo že izbranega prostora
        if location:
            reservation_state["location"] = location
            reservation_state["step"] = "awaiting_name"
            return f"Lokacija: {location}. Odlično. Prosim še ime in priimek nosilca rezervacije."

        # če ni vnaprej dodelil, ponudimo izbiro med razpoložljivimi
        # če so na voljo oba prostora, vprašamo za izbiro
        possible = []
        occupancy = reservation_service._table_room_occupancy()
        norm_time = reservation_service._parse_time(reservation_state["time"] or "")
        for room in ["Jedilnica Pri peči", "Jedilnica Pri vrtu"]:
            used = occupancy.get((reservation_state["date"], norm_time, room), 0)
            cap = 15 if "peč" in room.lower() else 35
            if used + people <= cap:
                possible.append(room)
        if len(possible) <= 1:
            reservation_state["location"] = possible[0] if possible else "Jedilnica (dodelimo ob prihodu)"
            reservation_state["step"] = "awaiting_name"
            return "Odlično. Prosim še ime in priimek nosilca rezervacije."
        reservation_state["available_locations"] = possible
        reservation_state["step"] = "awaiting_table_location"
        return "Imamo prosto v: " + " ali ".join(possible) + ". Kje bi želeli sedeti?"

    if step == "awaiting_table_date":
        proposed = extract_date(message) or ""
        if not proposed:
            return "Za kateri datum (sobota/nedelja)? (DD.MM.YYYY)"
        ok, error_message = reservation_service.validate_table_rules(proposed, "12:00")
        if not ok:
            reservation_state["date"] = None
            return error_message + " Bi poslali datum sobote ali nedelje v obliki DD.MM.YYYY?"
        reservation_state["date"] = proposed
        reservation_state["step"] = "awaiting_table_time"
        return "Ob kateri uri bi želeli mizo? (12:00–20:00, zadnji prihod na kosilo 15:00)"

    if step == "awaiting_table_time":
        desired_time = extract_time(message) or message.strip()
        ok, error_message = reservation_service.validate_table_rules(
            reservation_state["date"] or "", desired_time
        )
        if not ok:
            reservation_state["step"] = "awaiting_table_date"
            reservation_state["date"] = None
            reservation_state["time"] = None
            return error_message + " Poskusiva z novim datumom (sobota/nedelja, DD.MM.YYYY)."
        reservation_state["time"] = reservation_service._parse_time(desired_time)
        reservation_state["step"] = "awaiting_table_people"
        return "Za koliko oseb pripravimo mizo?"

    if step == "awaiting_kids_info":
        text = message.lower()
        if any(word in text for word in ["ne", "brez", "ni", "nimam"]):
            reservation_state["kids"] = 0
            reservation_state["kids_ages"] = ""
            return proceed_after_table_people()
        kids_parsed = parse_kids_response(message)
        if kids_parsed["kids"] is not None:
            reservation_state["kids"] = kids_parsed["kids"]
        if kids_parsed["ages"]:
            reservation_state["kids_ages"] = kids_parsed["ages"]
        if reservation_state.get("kids") and not reservation_state.get("kids_ages"):
            reservation_state["step"] = "awaiting_kids_ages"
            return "Koliko so stari otroci?"
        return proceed_after_table_people()

    if step == "awaiting_kids_ages":
        reservation_state["kids_ages"] = message.strip()
        return proceed_after_table_people()

    if step == "awaiting_note":
        skip_words = {"ne", "nic", "nič", "nimam", "brez"}
        note_text = "" if any(word in message.lower() for word in skip_words) else message.strip()
        reservation_state["note"] = note_text
        reservation_state["step"] = "awaiting_confirmation"
        lines = [
            "Prosimo, preverite podatke:",
            f"📅 Datum: {reservation_state.get('date')} ob {reservation_state.get('time')}",
            f"👥 Osebe: {reservation_state.get('people')}",
            f"🍽️ Jedilnica: {reservation_state.get('location')}",
            f"👤 Ime: {reservation_state.get('name')}",
            f"📞 Telefon: {reservation_state.get('phone')}",
            f"📧 Email: {reservation_state.get('email')}",
        ]
        if note_text:
            lines.append(f"📝 Opombe: {note_text}")
        lines.append("Potrdite rezervacijo? (da/ne)")
        return "\n".join(lines)

    if step == "awaiting_confirmation":
        if message.strip().lower() in {"ne", "no"}:
            reset_reservation_state(state)
            return "V redu, rezervacijo sem preklical. Kako vam lahko pomagam?"
        if is_affirmative(message):
            summary_state = reservation_state.copy()
            reservation_service.create_reservation(
                date=reservation_state["date"] or "",
                people=int(reservation_state["people"] or 0),
                reservation_type="table",
                source="chat",
                time=reservation_state["time"],
                location=reservation_state["location"],
                name=str(reservation_state["name"]),
                phone=str(reservation_state["phone"]),
                email=reservation_state["email"],
                note=reservation_state.get("note") or "",
                kids=str(reservation_state.get("kids") or ""),
                kids_small=str(reservation_state.get("kids_ages") or ""),
                event_type=reservation_state.get("event_type"),
            )
            email_data = {
                "name": reservation_state.get("name", ""),
                "email": reservation_state.get("email", ""),
                "phone": reservation_state.get("phone", ""),
                "date": reservation_state.get("date", ""),
                "time": reservation_state.get("time", ""),
                "people": reservation_state.get("people", 0),
                "reservation_type": "table",
                "location": reservation_state.get("location", ""),
                "note": reservation_state.get("note") or "",
                "kids": reservation_state.get("people_kids", ""),
                "kids_ages": reservation_state.get("kids_ages", ""),
            }
            _send_reservation_emails_async(email_data)
            reset_reservation_state(state)
            final_response = (
                "Super! 😊 Vaša rezervacija mize je zabeležena:\n"
                f"📅 Datum: {summary_state.get('date')} ob {summary_state.get('time')}\n"
                f"👥 Osebe: {summary_state.get('people')}\n"
                f"🍽️ Jedilnica: {summary_state.get('location')}\n"
                f"{'📝 Opombe: ' + (summary_state.get('note') or '') if summary_state.get('note') else ''}\n\n"
                f"{RESERVATION_PENDING_MESSAGE.strip()}"
            )
            return final_response
        return "Prosim potrdite z 'da' ali 'ne'."

    if step == "awaiting_table_people":
        parsed = parse_people_count(message)
        people = parsed["total"]
        if people is None or people <= 0:
            return "Prosim sporočite število oseb (npr. '6 oseb')."
        if people > 35:
            return "Za večje skupine nad 35 oseb nas prosim kontaktirajte za dogovor o razporeditvi."
        reservation_state["people"] = people
        reservation_state["adults"] = parsed["adults"]
        reservation_state["kids"] = parsed["kids"]
        reservation_state["kids_ages"] = parsed["ages"]
        if parsed["kids"] is None and parsed["adults"] is None:
            reservation_state["step"] = "awaiting_kids_info"
            return "Imate otroke? Koliko in koliko so stari?"
        if parsed["kids"] and not parsed["ages"]:
            reservation_state["step"] = "awaiting_kids_ages"
            return "Koliko so stari otroci?"
        return proceed_after_table_people()

    if step == "awaiting_table_location":
        choice = message.strip().lower()
        options = reservation_state.get("available_locations") or []
        selected = None
        for opt in options:
            if opt.lower() in choice or opt.lower().split()[-1] in choice:
                selected = opt
                break
        if not selected:
            return "Prosim izberite med: " + " ali ".join(options)
        reservation_state["location"] = selected
        reservation_state["step"] = "awaiting_name"
        return f"Zabeleženo: {selected}. Prosim še ime in priimek nosilca rezervacije."

    if step == "awaiting_name":
        full_name = message.strip()
        if len(full_name.split()) < 2:
            return "Prosim napišite ime in priimek (npr. 'Ana Novak')."
        reservation_state["name"] = full_name
        reservation_state["step"] = "awaiting_phone"
        return "Hvala! Zdaj prosim še telefonsko številko."

    if step == "awaiting_phone":
        phone = message.strip()
        digits = re.sub(r"\D+", "", phone)
        if len(digits) < 7:
            return "Zaznal sem premalo številk. Prosimo vpišite veljavno telefonsko številko."
        reservation_state["phone"] = phone
        reservation_state["step"] = "awaiting_email"
        return "Kam naj pošljem povzetek ponudbe? (e-poštni naslov)"

    if step == "awaiting_email":
        email = message.strip()
        if "@" not in email or "." not in email:
            return "Prosim vpišite veljaven e-poštni naslov (npr. info@primer.si)."
        reservation_state["email"] = email
        reservation_state["step"] = "awaiting_note"
        return "Želite še kaj sporočiti? (posebne želje, alergije, praznovanje...)"

    return "Nadaljujmo z rezervacijo mize. Kateri datum vas zanima?"


def handle_table_reservation(message: str, state: dict[str, Optional[str | int]]) -> str:
    response = _handle_table_reservation_impl(message, state)
    lang = state.get("language", "si")
    return translate_response(response, lang)


def handle_reservation_flow(message: str, state: dict[str, Optional[str | int]]) -> str:
    reservation_state = state
    if reservation_state["language"] is None:
        reservation_state["language"] = detect_language(message)

    def _tr(text: str) -> str:
        return translate_response(text, reservation_state.get("language", "si"))

    # možnost popolnega izhoda iz rezervacije
    if any(word in message.lower() for word in EXIT_KEYWORDS):
        reset_reservation_state(state)
        return _tr("V redu, rezervacijo sem preklical. Kako vam lahko pomagam?")

    if detect_reset_request(message):
        reset_reservation_state(state)
        return _tr("Ni problema, začniva znova. Želite rezervirati sobo ali mizo za kosilo?")

    # če smo v enem toku, pa uporabnik omeni drug tip, preklopimo
    lowered = message.lower()
    if reservation_state["step"] and reservation_state.get("type") == "room" and "miza" in lowered:
        reset_reservation_state(state)
        reservation_state["type"] = "table"
        reservation_state["step"] = "awaiting_table_date"
        return _tr(
            f"Preklopim na rezervacijo mize. Za kateri datum (sobota/nedelja)? (DD.MM.YYYY)\n{table_intro_text()}"
        )
    if reservation_state["step"] and reservation_state.get("type") == "table" and "soba" in lowered:
        reset_reservation_state(state)
        reservation_state["type"] = "room"
        reservation_state["step"] = "awaiting_room_date"
        return _tr(
            f"Preklopim na rezervacijo sobe. Za kateri datum prihoda? (DD.MM.YYYY)\n{room_intro_text()}"
        )

    if reservation_state["step"] is None:
        # Če je tip že nastavljen (npr. iz routerja), ga upoštevaj.
        detected = reservation_state.get("type") or parse_reservation_type(message)
        if detected == "room":
            reservation_state["type"] = "room"
            # poskusimo prebrati datum in nočitve iz prvega stavka
            prefilled_date = extract_date_from_text(message)
            range_data = extract_date_range(message)
            if range_data:
                prefilled_date = range_data[0]
            prefilled_nights = None
            if "nočit" in message.lower() or "nocit" in message.lower() or "noči" in message.lower():
                prefilled_nights = extract_nights(message)
            if range_data and not prefilled_nights:
                prefilled_nights = nights_from_range(range_data[0], range_data[1])
            prefilled_people = parse_people_count(message)
            if prefilled_people.get("total"):
                reservation_state["people"] = prefilled_people["total"]
                reservation_state["adults"] = prefilled_people["adults"]
                reservation_state["kids"] = prefilled_people["kids"]
                reservation_state["kids_ages"] = prefilled_people["ages"]
            if prefilled_date:
                reservation_state["date"] = prefilled_date
            reply_prefix = "Super, z veseljem uredim rezervacijo sobe. 😊"
            # če imamo nočitve, jih validiramo
            if prefilled_nights:
                ok, error_message, _ = validate_reservation_rules(
                    reservation_state["date"] or "", prefilled_nights
                )
                if not ok:
                    reservation_state["step"] = "awaiting_room_date"
                    reservation_state["date"] = None
                    reservation_state["nights"] = None
                    return _tr(
                        f"{error_message} Na voljo imamo najmanj 2 nočitvi (oz. 3 v poletnih mesecih). "
                        "Mi pošljete nov datum prihoda (DD.MM.YYYY) in število nočitev?"
                    )
                reservation_state["nights"] = prefilled_nights
            # določi naslednji korak glede na manjkajoče podatke
            if not reservation_state["date"]:
                reservation_state["step"] = "awaiting_room_date"
                return _tr(
                    f"{reply_prefix} Za kateri datum prihoda? (DD.MM.YYYY)\n{room_intro_text()}"
                )
            if not reservation_state["nights"]:
                reservation_state["step"] = "awaiting_nights"
                return _tr(
                    f"{reply_prefix} Koliko nočitev načrtujete? (min. 3 v jun/jul/avg, sicer 2)"
                )
            if reservation_state.get("people"):
                if reservation_state.get("kids") is None and reservation_state.get("adults") is None:
                    reservation_state["step"] = "awaiting_kids_info"
                    return _tr("Imate otroke? Koliko in koliko so stari?")
                if reservation_state.get("kids") and not reservation_state.get("kids_ages"):
                    reservation_state["step"] = "awaiting_kids_ages"
                    return _tr("Koliko so stari otroci?")
                reply = advance_after_room_people(reservation_state)
                return _tr(reply)
            reservation_state["step"] = "awaiting_people"
            return _tr(
                f"{reply_prefix} Zabeleženo imam {reservation_state['date']} za "
                f"{reservation_state['nights']} nočitev. Za koliko oseb bi to bilo?"
            )
        if detected == "table":
            reservation_state["type"] = "table"
            reservation_state["step"] = "awaiting_table_date"
            return _tr(
                f"Odlično, mizo rezerviramo z veseljem. Za kateri datum (sobota/nedelja)? (DD.MM.YYYY)\n{table_intro_text()}"
            )
        reservation_state["step"] = "awaiting_type"
        return _tr("Kako vam lahko pomagam – rezervacija sobe ali mize za kosilo?")

    if reservation_state["step"] == "awaiting_type":
        choice = parse_reservation_type(message)
        if not choice:
            return _tr(
                "Mi zaupate, ali rezervirate sobo ali mizo za kosilo? "
                f"{room_intro_text()} / {table_intro_text()}"
            )
        reservation_state["type"] = choice
        if choice == "room":
            reservation_state["step"] = "awaiting_room_date"
            return _tr(
                f"Odlično, sobo uredimo. Za kateri datum prihoda razmišljate? (DD.MM.YYYY)\n{room_intro_text()}"
            )
        reservation_state["step"] = "awaiting_table_date"
        return _tr(
            f"Super, uredim mizo. Za kateri datum (sobota/nedelja)? (DD.MM.YYYY)\n{table_intro_text()}"
        )

    if reservation_state["type"] == "room":
        return handle_room_reservation(message, state)
    return handle_table_reservation(message, state)


def is_greeting(message: str) -> bool:
    lowered = message.lower()
    return any(greeting in lowered for greeting in GREETING_KEYWORDS)


def append_today_hint(message: str, reply: str) -> str:
    lowered = message.lower()
    if "danes" in lowered:
        today = datetime.now().strftime("%A, %d.%m.%Y")
        reply = f"{reply}\n\nZa orientacijo: danes je {today}."
    return reply


def ensure_single_greeting(message: str, reply: str) -> str:
    greetings = ("pozdrav", "živjo", "zdravo", "hej", "hello")
    if reply.lstrip().lower().startswith(greetings):
        return reply
    return f"Pozdravljeni! {reply}"


def build_effective_query(message: str) -> str:
    global last_info_query
    normalized = message.strip().lower()
    short_follow = (
        len(normalized) < 12
        or normalized in INFO_FOLLOWUP_PHRASES
        or normalized.rstrip("?") in INFO_FOLLOWUP_PHRASES
    )
    if short_follow:
        if last_product_query:
            return f"{last_product_query} {message}"
        if last_info_query:
            return f"{last_info_query} {message}"
    return message


@router.post("", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequestWithSession) -> ChatResponse:
    global last_product_query, last_wine_query, last_info_query, last_menu_query, conversation_history, last_interaction, chat_session_id
    now = datetime.now()
    session_id = payload.session_id or "default"
    if last_interaction and now - last_interaction > timedelta(hours=SESSION_TIMEOUT_HOURS):
        reset_conversation_context(session_id)
    last_interaction = now
    state = get_reservation_state(session_id)
    inquiry_state = get_inquiry_state(session_id)
    needs_followup = False

    if is_switch_topic_command(payload.message):
        reset_reservation_state(state)
        reset_inquiry_state(inquiry_state)
        reply = "Seveda — zamenjamo temo. Kako vam lahko pomagam?"
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "switch_topic", followup_flag=False)

    if state.get("step") is None and is_affirmative(payload.message):
        last_bot = get_last_assistant_message().lower()
        if last_bot_mentions_reservation(last_bot):
            if any(token in last_bot for token in ["mizo", "miza", "table"]):
                state["type"] = "table"
            elif any(token in last_bot for token in ["sobo", "soba", "preno", "room", "zimmer"]):
                state["type"] = "room"
            else:
                state["type"] = None
            reply = handle_reservation_flow(payload.message, state)
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "reservation_confirmed", followup_flag=False)

    if state.get("step") is None:
        last_bot = get_last_assistant_message().lower()
        has_room_context = any(token in last_bot for token in ["sobo", "soba", "preno", "room", "zimmer"])
        has_table_context = any(token in last_bot for token in ["mizo", "miza", "table"])
        date_hit = extract_date(payload.message) or extract_date_range(payload.message)
        people_hit = parse_people_count(payload.message).get("total")
        if date_hit and people_hit and (has_room_context or has_table_context):
            state["type"] = "room" if has_room_context else "table"
            reply = handle_reservation_flow(payload.message, state)
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "reservation_context_start", followup_flag=False)

    # zabeležimo user vprašanje v zgodovino (omejimo na zadnjih 6 parov)
    conversation_history.append({"role": "user", "content": payload.message})
    if len(conversation_history) > 12:
        conversation_history = conversation_history[-12:]

    detected_lang = detect_language(payload.message)

    def finalize(reply_text: str, intent_value: str, followup_flag: bool = False) -> ChatResponse:
        nonlocal needs_followup
        global conversation_history
        final_reply = reply_text
        flag = followup_flag or needs_followup or is_unknown_response(final_reply)
        if flag:
            final_reply = get_unknown_response(detected_lang)
        conv_id = reservation_service.log_conversation(
            session_id=session_id,
            user_message=payload.message,
            bot_response=final_reply,
            intent=intent_value,
            needs_followup=flag,
        )
        if flag:
            unknown_question_state[session_id] = {"question": payload.message, "conv_id": conv_id}
        conversation_history.append({"role": "assistant", "content": final_reply})
        if len(conversation_history) > 12:
            conversation_history = conversation_history[-12:]
        return ChatResponse(reply=final_reply)

    # inquiry flow
    if state.get("step") is None and inquiry_state.get("step"):
        inquiry_reply = handle_inquiry_flow(payload.message, inquiry_state, session_id)
        if inquiry_reply:
            inquiry_reply = maybe_translate(inquiry_reply, detected_lang)
            return finalize(inquiry_reply, "inquiry", followup_flag=False)

    if state.get("step") is None and is_inquiry_trigger(payload.message):
        if is_strong_inquiry_request(payload.message):
            inquiry_state["details"] = payload.message.strip()
            inquiry_state["step"] = "awaiting_deadline"
            reply = "Super, zabeležim povpraševanje. Do kdaj bi to potrebovali? (datum/rok ali 'ni pomembno')"
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "inquiry_start", followup_flag=False)
        info_key = detect_info_intent(payload.message)
        if info_key:
            info_reply = get_info_response(info_key, message)
            consent = start_inquiry_consent(inquiry_state)
            reply = f"{info_reply}\n\n---\n\n{consent}"
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "inquiry_offer", followup_flag=False)
        inquiry_reply = start_inquiry_consent(inquiry_state)
        inquiry_reply = maybe_translate(inquiry_reply, detected_lang)
        return finalize(inquiry_reply, "inquiry_offer", followup_flag=False)

    # če je prejšnji odgovor bil "ne vem" in uporabnik pošlje email
    if session_id in unknown_question_state and is_email(payload.message):
        state = unknown_question_state.pop(session_id)
        email_value = payload.message.strip()
        conv_id = state.get("conv_id")
        if conv_id:
            reservation_service.update_followup_email(conv_id, email_value)
        reply = "Hvala! 📧 Vaš elektronski naslov sem si zabeležil. Odgovoril vam bom v najkrajšem možnem času."
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "followup_email", followup_flag=False)

    # V2 router/exec (opcijsko)
    if USE_FULL_KB_LLM:
        if state.get("step") is not None:
            if should_switch_from_reservation(payload.message, state):
                reset_reservation_state(state)
                reply = _llm_answer_full_kb(payload.message, detected_lang)
                return finalize(reply, "switch_from_reservation", followup_flag=False)
            lowered_message = payload.message.lower()
            if is_inquiry_trigger(payload.message) and is_strong_inquiry_request(payload.message):
                reset_reservation_state(state)
                inquiry_state["details"] = payload.message.strip()
                inquiry_state["step"] = "awaiting_deadline"
                reply = "Super, zabeležim povpraševanje. Do kdaj bi to potrebovali? (datum/rok ali 'ni pomembno')"
                reply = maybe_translate(reply, detected_lang)
                return finalize(reply, "inquiry_start", followup_flag=False)
            question_like = (
                "?" in payload.message
                or is_info_only_question(payload.message)
                or is_info_query(payload.message)
                or any(word in lowered_message for word in ["gospodar", "družin", "lastnik", "kmetij"])
            )
            if question_like:
                llm_reply = _llm_answer_full_kb(payload.message, detected_lang)
                continuation = get_booking_continuation(state.get("step"), state)
                llm_reply = f"{llm_reply}\n\n---\n\n📝 **Nadaljujemo z rezervacijo:**\n{continuation}"
                llm_reply = maybe_translate(llm_reply, detected_lang)
                return finalize(llm_reply, "info_during_reservation", followup_flag=False)
            reply = handle_reservation_flow(payload.message, state)
            return finalize(reply, "reservation", followup_flag=False)
        if is_ambiguous_reservation_request(payload.message):
            reply = "Želite rezervirati **sobo** ali **mizo**?"
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "clarify_reservation", followup_flag=False)
        if is_ambiguous_inquiry_request(payload.message):
            reply = (
                "Ali želite, da zabeležim **povpraševanje/naročilo**? "
                "Če da, prosim napišite **količino** in **rok**."
            )
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "clarify_inquiry", followup_flag=False)
        try:
            intent_result = _llm_route_reservation(payload.message)
        except Exception as exc:
            print(f"[LLM] routing failed: {exc}")
            intent_result = {"action": "NONE"}
        action = (intent_result or {}).get("action") or "NONE"
        if action in {"BOOKING_ROOM", "BOOKING_TABLE"}:
            reset_reservation_state(state)
            state["type"] = "room" if action == "BOOKING_ROOM" else "table"
            reply = handle_reservation_flow(payload.message, state)
            return finalize(reply, action.lower(), followup_flag=False)
        info_key = detect_info_intent(payload.message)
        if info_key:
            info_reply = get_info_response(info_key, message)
            info_reply = maybe_translate(info_reply, detected_lang)
            return finalize(info_reply, "info_llm", followup_flag=False)
        # fallback: če LLM ne vrne action, uporabi osnovno heuristiko
        if any(token in payload.message.lower() for token in ["rezerv", "book", "booking", "reserve", "reservation", "zimmer"]) or is_reservation_typo(payload.message):
            if "mizo" in payload.message.lower() or "table" in payload.message.lower():
                reset_reservation_state(state)
                state["type"] = "table"
                reply = handle_reservation_flow(payload.message, state)
                return finalize(reply, "booking_table_fallback", followup_flag=False)
            if "sobo" in payload.message.lower() or "room" in payload.message.lower() or "nočitev" in payload.message.lower():
                reset_reservation_state(state)
                state["type"] = "room"
                reply = handle_reservation_flow(payload.message, state)
                return finalize(reply, "booking_room_fallback", followup_flag=False)
        llm_reply = _llm_answer_full_kb(payload.message, detected_lang)
        return finalize(llm_reply, "info_llm", followup_flag=False)

    if USE_ROUTER_V2:
        decision = route_message(
            payload.message,
            has_active_booking=state.get("step") is not None,
            booking_step=state.get("step"),
        )
        routing_info = decision.get("routing", {})
        print(f"[ROUTER_V2] intent={routing_info.get('intent')} conf={routing_info.get('confidence')} info={decision.get('context', {}).get('info_key')} product={decision.get('context', {}).get('product_category')} interrupt={routing_info.get('is_interrupt')}")
        info_key = decision.get("context", {}).get("info_key") or ""
        is_critical_info = info_key in CRITICAL_INFO_KEYS

        def _translate(txt: str) -> str:
            return maybe_translate(txt, detected_lang)

        def _info_resp(key: Optional[str], soft_sell: bool) -> str:
            reply_local = get_info_response(key or "", message)
            if soft_sell and (key or "") in BOOKING_RELEVANT_KEYS:
                reply_local = f"{reply_local}\n\nŽelite, da pripravim **ponudbo**?"
            return reply_local

        def _product_resp(key: str) -> str:
            reply_local = get_product_response(key)
            if is_bulk_order_request(payload.message):
                reply_local = f"{reply_local}\n\nZa večja naročila nam pišite na urska@kmetija-urska.si, da uskladimo količine in prevzem."
            return reply_local

        def _continuation(step_val: Optional[str], st: dict) -> str:
            return get_booking_continuation(step_val, st)

        # INFO brez kritičnih podatkov -> LLM/RAG odgovor (z možnostjo nadaljevanja rezervacije)
        if routing_info.get("intent") == "INFO" and not is_critical_info:
            llm_reply = _llm_answer(payload.message, conversation_history)
            if llm_reply:
                if routing_info.get("is_interrupt") and state.get("step"):
                    cont = _continuation(state.get("step"), state)
                    llm_reply = f"{llm_reply}\n\n---\n\n📝 **Nadaljujemo z rezervacijo:**\n{cont}"
                llm_reply = maybe_translate(llm_reply, detected_lang)
                if state.get("step") is None and is_unknown_response(llm_reply) and inquiry_state.get("step") is None:
                    inquiry_reply = start_inquiry_consent(inquiry_state)
                    inquiry_reply = maybe_translate(inquiry_reply, detected_lang)
                    return finalize(inquiry_reply, "inquiry_offer", followup_flag=False)
                return finalize(llm_reply, "info_llm", followup_flag=False)

        reply_v2 = execute_decision(
            decision=decision,
            message=payload.message,
            state=state,
            translate_fn=_translate,
            info_responder=_info_resp,
            product_responder=_product_resp,
            reservation_flow_fn=handle_reservation_flow,
            reset_fn=reset_reservation_state,
            continuation_fn=_continuation,
            general_handler=None,
        )
        if reply_v2:
            return finalize(reply_v2, decision.get("routing", {}).get("intent", "v2"), followup_flag=False)
        # Če nič ne ujame, poskusi LLM/RAG odgovor
        llm_reply = _llm_answer(payload.message, conversation_history)
        if llm_reply:
            llm_reply = maybe_translate(llm_reply, detected_lang)
            return finalize(llm_reply, "general_llm", followup_flag=False)
        # Če nič ne ujame, poskusi turistični RAG
        if state.get("step") is None:
            tourist_reply = answer_tourist_question(payload.message)
            if tourist_reply:
                tourist_reply = maybe_translate(tourist_reply, detected_lang)
                return finalize(tourist_reply, "tourist_info", followup_flag=False)
            # Nato semantični INFO odgovor iz knowledge baze
            semantic_reply = semantic_info_answer(payload.message)
            if semantic_reply:
                semantic_reply = maybe_translate(semantic_reply, detected_lang)
                return finalize(semantic_reply, "info_semantic", followup_flag=False)
            # Če še vedno nič, priznaj neznano in ponudi email
            if state.get("step") is None:
                inquiry_reply = start_inquiry_consent(inquiry_state)
                inquiry_reply = maybe_translate(inquiry_reply, detected_lang)
                return finalize(inquiry_reply, "info_unknown", followup_flag=False)
            reply = random.choice(UNKNOWN_RESPONSES)
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "info_unknown", followup_flag=False)
    # Info ali produkt med aktivno rezervacijo: odgovor + nadaljevanje
    info_during = handle_info_during_booking(payload.message, state)
    if info_during:
        reply = maybe_translate(info_during, detected_lang)
        return finalize(reply, "info_during_reservation", followup_flag=False)

    # === ROUTER: Info intent detection ===
    info_key = detect_info_intent(payload.message)
    if info_key:
        reply = get_info_response(info_key, message)
        if info_key in BOOKING_RELEVANT_KEYS:
            reply = f"{reply}\n\nŽelite, da pripravim **ponudbo**?"
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "info_static", followup_flag=False)
    # === KONEC ROUTER ===

    # Produktni intent brez LLM (samo če ni aktivne rezervacije)
    if state["step"] is None:
        product_key = detect_product_intent(payload.message)
        if product_key:
            reply = get_product_response(product_key)
            if is_bulk_order_request(payload.message):
                reply = f"{reply}\n\nZa večja naročila nam pišite na urska@kmetija-urska.si, da uskladimo količine in prevzem."
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "product_static", followup_flag=False)

    # Guard: info-only vprašanja naj ne sprožijo rezervacije
    if state["step"] is None and is_info_only_question(payload.message):
        reply = random.choice(UNKNOWN_RESPONSES)
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "info_only", followup_flag=False)

    # Fuzzy router za rezervacije (robustno na tipkarske napake)
    router_intent = detect_router_intent(payload.message, state)
    if router_intent == "booking_room" and state["step"] is None:
        reset_reservation_state(state)
        state["type"] = "room"
        reply = handle_reservation_flow(payload.message, state)
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "reservation_router_room", followup_flag=False)
    if router_intent == "booking_table" and state["step"] is None:
        reset_reservation_state(state)
        state["type"] = "table"
        reply = handle_reservation_flow(payload.message, state)
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "reservation_router_table", followup_flag=False)

    # Hrana/meni brez jasne rezervacijske namere
    if is_food_question_without_booking_intent(payload.message):
        reply = get_info_response("menu_info", message)
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "food_info", followup_flag=False)

    # aktivna rezervacija ima prednost, vendar omogoča izhod ali druga vprašanja
    if state["step"] is not None:
        if is_inquiry_trigger(payload.message) and is_strong_inquiry_request(payload.message):
            reset_reservation_state(state)
            inquiry_state["details"] = payload.message.strip()
            inquiry_state["step"] = "awaiting_deadline"
            reply = "Super, zabeležim povpraševanje. Do kdaj bi to potrebovali? (datum/rok ali 'ni pomembno')"
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "inquiry_start", followup_flag=False)
        if is_escape_command(payload.message):
            reset_reservation_state(state)
            reply = "OK, prekinil sem rezervacijo."
            reply = maybe_translate(reply, detected_lang)
            return finalize(reply, "reservation_cancel", followup_flag=False)
        if payload.message.strip().lower() == "nadaljuj":
            prompt = reservation_prompt_for_state(state)
            reply = maybe_translate(prompt, detected_lang)
            return finalize(reply, "reservation_continue", followup_flag=False)
        lowered_message = payload.message.lower()
        question_like = (
            "?" in payload.message
            or is_info_only_question(payload.message)
            or is_info_query(payload.message)
            or any(word in lowered_message for word in ["gospodar", "družin", "lastnik", "kmetij"])
        )
        if question_like:
            if USE_FULL_KB_LLM:
                llm_reply = _llm_answer_full_kb(payload.message, detected_lang)
            else:
                llm_reply = _llm_answer(payload.message, conversation_history)
            if llm_reply:
                continuation = get_booking_continuation(state.get("step"), state)
                llm_reply = f"{llm_reply}\n\n---\n\n📝 **Nadaljujemo z rezervacijo:**\n{continuation}"
                llm_reply = maybe_translate(llm_reply, detected_lang)
                return finalize(llm_reply, "info_during_reservation", followup_flag=False)
        if is_product_query(payload.message):
            reply = answer_product_question(payload.message)
            last_product_query = payload.message
            last_wine_query = None
            last_info_query = None
            last_menu_query = False
            reply = maybe_translate(reply, detected_lang)
            reply = f"{reply}\n\nČe želiš nadaljevati rezervacijo, napiši 'nadaljuj'."
            return finalize(reply, "product_during_reservation", followup_flag=False)
        if is_info_query(payload.message):
            reply = answer_farm_info(payload.message)
            last_product_query = None
            last_wine_query = None
            last_info_query = payload.message
            last_menu_query = False
            reply = maybe_translate(reply, detected_lang)
            reply = f"{reply}\n\nČe želiš nadaljevati rezervacijo, napiši 'nadaljuj'."
            return finalize(reply, "info_during_reservation", followup_flag=False)

        reply = handle_reservation_flow(payload.message, state)
        last_product_query = None
        last_wine_query = None
        last_info_query = None
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "reservation")

    intent = detect_intent(payload.message, state)

    if intent == "goodbye":
        reply = get_goodbye_response()
        last_product_query = None
        last_wine_query = None
        last_info_query = None
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "goodbye")

    if intent == "reservation":
        reply = handle_reservation_flow(payload.message, state)
        last_product_query = None
        last_wine_query = None
        last_info_query = None
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "reservation")

    # tedenska ponudba naj ima prednost pred vikend jedilnikom
    if intent == "weekly_menu":
        reply = answer_weekly_menu(payload.message)
        last_product_query = None
        last_wine_query = None
        last_info_query = payload.message
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "weekly_menu")

    if intent == "room_info":
        reply = """Seveda! 😊 Imamo tri prijetne družinske sobe:

🛏️ **Soba ALJAŽ** - soba z balkonom (2+2 osebi)
🛏️ **Soba JULIJA** - družinska soba z balkonom (2 odrasla + 2 otroka)  
🛏️ **Soba ANA** - družinska soba z dvema spalnicama (2 odrasla + 2 otroka)

**Cena**: 50€/osebo/noč z zajtrkom
**Večerja**: dodatnih 25€/osebo

Sobe so klimatizirane, Wi-Fi je brezplačen. Prijava ob 14:00, odjava ob 10:00.

Bi želeli rezervirati? Povejte mi datum in število oseb! 🗓️"""
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "room_info")

    if intent == "room_pricing":
        reply = answer_room_pricing(payload.message)
        last_product_query = None
        last_wine_query = None
        last_info_query = payload.message
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "room_pricing")

    if intent == "tourist_info":
        tourist_reply = answer_tourist_question(payload.message)
        if tourist_reply:
            detected_lang = detect_language(payload.message)
            if detected_lang == "en":
                reply = generate_llm_answer(
                    f"Translate this to English, keep it natural and friendly:\n{tourist_reply}",
                    history=[],
                )
            elif detected_lang == "de":
                reply = generate_llm_answer(
                    f"Translate this to German/Deutsch, keep it natural and friendly:\n{tourist_reply}",
                    history=[],
                )
            else:
                reply = tourist_reply
            last_product_query = None
            last_wine_query = None
            last_info_query = payload.message
            last_menu_query = False
            return finalize(reply, "tourist_info")

    month_hint = parse_month_from_text(payload.message) or parse_relative_month(payload.message)
    if is_menu_query(payload.message):
        reply = format_current_menu(month_override=month_hint, force_full=is_full_menu_request(payload.message))
        last_product_query = None
        last_wine_query = None
        last_info_query = None
        last_menu_query = True
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "menu")
    if month_hint is not None and intent == "default":
        reply = format_current_menu(month_override=month_hint, force_full=is_full_menu_request(payload.message))
        last_product_query = None
        last_wine_query = None
        last_info_query = None
        last_menu_query = True
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "menu")

    if intent == "product":
        reply = answer_product_question(payload.message)
        last_product_query = payload.message
        last_wine_query = None
        last_info_query = None
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "product")

    if intent == "product_followup":
        reply = answer_product_question(payload.message)
        last_product_query = payload.message
        last_wine_query = None
        last_info_query = None
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "product_followup")

    if intent == "farm_info":
        reply = answer_farm_info(payload.message)
        last_product_query = None
        last_wine_query = None
        last_info_query = payload.message
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "farm_info")

    if intent == "food_general":
        reply = answer_food_question(payload.message)
        last_product_query = None
        last_wine_query = None
        last_info_query = payload.message
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "food_general")

    if intent == "help":
        reply = get_help_response()
        last_product_query = None
        last_wine_query = None
        last_info_query = payload.message
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "help")

    if intent == "wine":
        reply = answer_wine_question(payload.message)
        last_product_query = None
        last_wine_query = payload.message
        last_info_query = None
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "wine")

    if intent == "wine_followup":
        combined = f"{last_wine_query} {payload.message}" if last_wine_query else payload.message
        reply = answer_wine_question(combined)
        last_wine_query = combined
        last_product_query = None
        last_info_query = None
        last_menu_query = False
        reply = maybe_translate(reply, detected_lang)
        return finalize(reply, "wine_followup")

    try:
        effective_query = build_effective_query(payload.message)
        detected_lang = detect_language(payload.message)

        if detected_lang == "en":
            lang_hint = "\n\n[IMPORTANT: The user is writing in English. Respond in English.]"
            effective_query = effective_query + lang_hint
        elif detected_lang == "de":
            lang_hint = "\n\n[IMPORTANT: The user is writing in German. Respond in German/Deutsch.]"
            effective_query = effective_query + lang_hint

        reply = generate_llm_answer(effective_query, history=conversation_history)
        last_info_query = effective_query
    except Exception:
        reply = (
            "Trenutno imam tehnične težave pri dostopu do podatkov. "
            "Za natančne informacije prosim preverite www.kmetija-urska.si."
        )
        last_info_query = None
    last_product_query = None
    last_wine_query = None
    last_menu_query = False

    if intent == "default" and is_greeting(payload.message):
        reply = get_greeting_response()
    else:
        reply = append_today_hint(payload.message, reply)

    reply = maybe_translate(reply, detected_lang)
    return finalize(reply, intent)
WEEKLY_MENUS: dict[int, dict[str, object]] = {}

WEEKLY_INFO = {
    "days": "",
    "time": "",
    "min_people": 0,
    "contact": {"phone": "03 759 04 10", "email": "urska@kmetija-urska.si"},
    "special_diet_extra": 0,
}


@router.post("/stream")
def chat_stream(payload: ChatRequestWithSession):
    global conversation_history, last_interaction
    now = datetime.now()
    session_id = payload.session_id or "default"
    if last_interaction and now - last_interaction > timedelta(hours=SESSION_TIMEOUT_HOURS):
        reset_conversation_context(session_id)
    last_interaction = now
    state = get_reservation_state(session_id)
    inquiry_state = get_inquiry_state(session_id)

    def stream_and_log(reply_chunks):
        collected: list[str] = []
        for chunk in reply_chunks:
            collected.append(chunk)
            yield chunk
        final_reply = "".join(collected).strip() or "Seveda, z veseljem pomagam. Kaj vas zanima?"
        reservation_service.log_conversation(
            session_id=session_id,
            user_message=payload.message,
            bot_response=final_reply,
            intent="stream",
            needs_followup=False,
        )
        conversation_history.append({"role": "assistant", "content": final_reply})
        if len(conversation_history) > 12:
            conversation_history[:] = conversation_history[-12:]

    # Če je rezervacija aktivna ali gre za rezervacijo, uporabimo obstoječo pot (brez pravega streama)
    if state.get("step") is not None or detect_intent(payload.message, state) == "reservation":
        response = chat_endpoint(payload)
        return StreamingResponse(
            _stream_text_chunks(response.reply),
            media_type="text/plain",
        )

    # inquiry flow mora prednostno delovati tudi v stream načinu
    if inquiry_state.get("step") or is_inquiry_trigger(payload.message):
        response = chat_endpoint(payload)
        return StreamingResponse(
            _stream_text_chunks(response.reply),
            media_type="text/plain",
        )

    if is_ambiguous_reservation_request(payload.message) or is_ambiguous_inquiry_request(payload.message):
        response = chat_endpoint(payload)
        return StreamingResponse(
            _stream_text_chunks(response.reply),
            media_type="text/plain",
        )

    if USE_FULL_KB_LLM:
        settings = Settings()
        conversation_history.append({"role": "user", "content": payload.message})
        if len(conversation_history) > 12:
            conversation_history = conversation_history[-12:]
        return StreamingResponse(
            stream_and_log(_llm_answer_full_kb_stream(payload.message, settings, detect_language(payload.message))),
            media_type="text/plain",
        )

    response = chat_endpoint(payload)
    return StreamingResponse(
        _stream_text_chunks(response.reply),
        media_type="text/plain",
    )
