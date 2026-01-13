"""
Router V2 - klasifikacija sporočil v standardiziran JSON.
Ne izvaja FSM; samo ugotavlja intent in osnovne entitete.
"""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from typing import Any, Dict, Optional


def _extract_date(text: str) -> Optional[str]:
    match = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b", text)
    if not match:
        return None
    day, month, year = match.groups()
    year = year if len(year) == 4 else f"20{year.zfill(2)}"
    return f"{day.zfill(2)}.{month.zfill(2)}.{year}"


def _extract_time(text: str) -> Optional[str]:
    match = re.search(r"\b(\d{1,2})[:.](\d{2})\b", text)
    if not match:
        return None
    hour, minute = match.groups()
    return f"{hour.zfill(2)}:{minute}"


def _extract_people(text: str) -> Optional[int]:
    nums = re.findall(r"\b(\d{1,2})\b", text)
    if nums:
        try:
            return int(nums[-1])
        except ValueError:
            return None
    return None


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _detect_info_intent(text: str) -> Optional[str]:
    if any(_has_word(text, w) for w in ["zdravo", "živjo", "pozdrav", "dober", "dan", "hey", "hello"]):
        return "pozdrav"
    if any(w in text for w in ["kdo si", "kdo ste", "predstavi se", "kdo si ti"]):
        return "kdo_si"
    if any(w in text for w in ["odpiralni", "kdaj ste odprti", "delovni čas", "odprti", "odprite", "kdaj odprete", "ob kateri uri odprete", "do kdaj ste odprti", "zadnji prihod"]):
        return "odpiralni_cas"
    if any(w in text for w in ["praznik", "prazniki"]):
        return "prazniki"
    if any(w in text for w in ["rezervirati vnaprej", "brez rezervacije", "ali moram rezervirati", "rezervacija vnaprej"]):
        return "rezervacija_vnaprej"
    if "zajtrk" in text and "večerj" not in text:
        return "zajtrk"
    if any(w in text for w in ["večerja", "vecerja", "cena večerje", "cena vecerje", "večerjo"]):
        return "vecerja"
    if any(w in text for w in ["cena sobe", "cenik", "koliko stane noč", "nočitev", "nocitev", "soba za 2", "soba za dve", "za 2 osebi", "za dve osebi", "vključeno v ceno", "v ceno sobe", "kaj je vključeno v ceno"]):
        return "cena_sobe"
    if any(w in text for w in ["koliko sob", "katere sobe", "kakšne sobe", "družinska soba", "družinsko sobo", "balkon", "koliko oseb v sobi", "koliko oseb v sobo", "koliko oseb gre v eno sobo", "kapaciteta sobe", "najboljša soba", "najboljša za družino"]):
        return "sobe"
    if "soba" in text and "družin" in text:
        return "sobe"
    if any(w in text for w in ["klima", "klimatiz"]):
        return "klima"
    if any(w in text for w in ["wifi", "wi-fi", "internet"]):
        return "wifi"
    if any(w in text for w in ["prijava", "odjava", "check in", "check out"]):
        return "prijava_odjava"
    if any(w in text for w in ["parkir", "parking"]):
        return "parking"
    if any(w in text for w in ["katere živali", "kakšne živali", "zivali imate", "živali na kmetiji", "živali na domačiji", "otroci vidijo živali", "lahko otroci vidijo živali"]):
        return "zivali_kmetija"
    if any(w in text for w in ["pes", "psom", "mačk", "ljubljenč", "hišni ljubljenčki", "pripeljem", "s sabo", "dovolite živali", "sprejemate živali"]):
        return "zivali"
    if any(w in text for w in ["telefon", "telefonsko", "številka", "stevilka", "gsm", "mobitel", "mobile", "phone"]):
        return "kontakt"
    if any(w in text for w in ["email", "e-mail", "epošta", "e-pošta"]):
        return "kontakt"
    if any(w in text for w in ["plačilo", "plačam", "placam", "gotovina", "kartic"]):
        return "placilo"
    if any(w in text for w in ["minimal", "min nočit", "najmanj noč", "min noce"]):
        return "min_nocitve"
    if any(w in text for w in ["jedilnik", "menij", "meniju", "menu", "koslo", "kaj ponujate", "kaj strežete", "degustacijski", "degustacija", "koliko hodov", "kosilo", "vikend kosilo", "koliko stane kosilo"]):
        return "jedilnik"
    if any(w in text for w in ["alergij", "alergik", "gluten", "lakto", "vegan", "vegetar", "vegansko"]):
        return "alergije"
    if any(w in text for w in ["nadmorski", "višina"]):
        return "lokacija"
    if any(w in text for w in ["zemlje", "krav", "krave", "kmetij", "kmetijo"]):
        return "kmetija"
    if "gibanica" in text:
        return "gibanica"
    return None


_topics_cache: Optional[list[dict[str, Any]]] = None


def _load_topics() -> list[dict[str, Any]]:
    global _topics_cache
    if _topics_cache is not None:
        return _topics_cache
    topics_path = Path(__file__).resolve().parents[2] / "data" / "knowledge_topics.json"
    try:
        _topics_cache = json.loads(topics_path.read_text(encoding="utf-8"))
    except Exception:
        _topics_cache = []
    return _topics_cache


def _detect_topic_intent(text: str) -> Optional[str]:
    topics = _load_topics()
    if not topics:
        return None
    best_key = None
    best_score = -1
    for topic in topics:
        key = topic.get("key")
        triggers = topic.get("triggers", [])
        priority = int(topic.get("priority", 0))
        for trig in triggers:
            if trig in text:
                score = priority * 100 + len(trig)
                if score > best_score:
                    best_score = score
                    best_key = key
    return best_key


def _detect_product_intent(text: str) -> Optional[str]:
    if any(w in text for w in ["marmelad", "džem", "dzem", "jagod", "malin"]):
        return "marmelada"
    if any(w in text for w in ["liker", "žgan", "zgan", "borovnič", "orehov", "tepk"]):
        return "liker"
    if "gibanica" in text:
        return "gibanica"
    if any(w in text for w in ["bunka", "bunko", "bunke", "salama", "salam", "klobas", "klobasa"]):
        return "bunka"
    if any(w in text for w in ["izdelek", "trgovin", "katalog", "prodajate", "naroč", "naroc"]):
        return "izdelki_splosno"
    return None


def _detect_booking_intent(text: str, has_active_booking: bool) -> str:
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
        "night",
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
        "koslo",
        "kosilo",
        "vecerj",
        "veceja",
        "vecher",
        "dinner",
        "lunch",
    }

    has_booking = any(tok in text for tok in booking_tokens) or any(
        phrase in text
        for phrase in [
            "rezerviram sobo",
            "rezerviral sobo",
            "rezervirala sobo",
            "rezervacija sobe",
            "rezerviram mizo",
            "rezerviral mizo",
            "rezervirala mizo",
            "rezervacija mize",
            "ali lahko rezerviram sobo",
            "ali lahko rezerviram mizo",
        ]
    )
    room_words = {"soba", "sobe", "sobo", "room", "zimmer", "zimmern", "camera"}
    table_words = {"miza", "mize", "mizo", "table", "tisch"}
    has_room = any(_has_word(text, tok) for tok in room_words) or any(
        stem in text for stem in room_tokens if stem not in room_words
    )
    has_table = any(_has_word(text, tok) for tok in table_words) or any(
        stem in text for stem in table_tokens if stem not in table_words
    )

    # Med aktivno rezervacijo: če jasno pove nov tip (soba/miza), začni novo,
    # sicer nadaljuj obstoječi flow.
    if has_active_booking:
        if has_booking and has_room:
            return "BOOKING_ROOM"
        if has_booking and has_table:
            return "BOOKING_TABLE"
        return "BOOKING_CONTINUE"

    # Za sprožitev bookinga zahtevamo namig na rezervacijo (booking_tokens)
    if has_booking and has_room and has_table:
        # če so omenjene oboje, vprašaj pojasnilo kasneje (tukaj izberi none)
        return "GENERAL"
    if has_booking and has_room:
        return "BOOKING_ROOM"
    if has_booking and has_table:
        return "BOOKING_TABLE"
    if has_room and has_booking:
        return "BOOKING_ROOM"
    if has_table and has_booking:
        return "BOOKING_TABLE"
    return "GENERAL"


# --- Logging setup ---
_router_logger = logging.getLogger("router_v2")
if not _router_logger.handlers:
    _router_logger.setLevel(logging.INFO)
    handler = RotatingFileHandler("data/router_debug.log", maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _router_logger.addHandler(handler)

_metrics = {"info_hits": 0, "booking_starts": 0}


def route_message(
    message: str,
    has_active_booking: bool = False,
    booking_step: Optional[str] = None,
) -> Dict[str, Any]:
    text = message.lower()

    intent = _detect_booking_intent(text, has_active_booking)
    topic_key = _detect_topic_intent(text)
    info_key = f"topic:{topic_key}" if topic_key else _detect_info_intent(text)
    product_key = _detect_product_intent(text)

    needs_soft_sell = info_key in {"sobe", "sobe_info", "vecerja", "cena_sobe", "min_nocitve", "kapaciteta_mize"}

    # is_interrupt: med aktivnim bookingom, a sprašuje info/product
    is_interrupt = False
    if intent in {"BOOKING_ROOM", "BOOKING_TABLE", "BOOKING_CONTINUE"}:
        pass
    elif has_active_booking and (info_key or product_key):
        is_interrupt = True
        intent = "INFO" if info_key else "PRODUCT"
    elif has_active_booking and intent == "BOOKING_CONTINUE":
        pass
    elif info_key or product_key:
        intent = "INFO" if info_key else "PRODUCT"

    entities: Dict[str, Any] = {}
    date = _extract_date(text)
    if date:
        entities["date"] = date
    time_val = _extract_time(text)
    if time_val:
        entities["time"] = time_val
    people = _extract_people(text)
    if people:
        entities["people_count"] = people
    if any(room in text for room in ["aljaz", "aljaž"]):
        entities["room_name"] = "ALJAZ"
    elif "julija" in text:
        entities["room_name"] = "JULIJA"
    elif "ana" in text:
        entities["room_name"] = "ANA"

    # Če smo v koraku za telefon in dobimo številko, prisilimo nadaljevanje bookinga
    if booking_step == "awaiting_phone":
        digits_only = re.sub(r"\D+", "", message)
        if len(digits_only) >= 7:
            intent = "BOOKING_CONTINUE"
    confidence = 0.9 if intent in {"INFO", "PRODUCT", "BOOKING_ROOM", "BOOKING_TABLE"} else 0.6

    # metrika
    if intent == "INFO":
        _metrics["info_hits"] += 1
    if intent in {"BOOKING_ROOM", "BOOKING_TABLE"}:
        _metrics["booking_starts"] += 1

    record = {
        "routing": {
            "intent": intent,
            "confidence": confidence,
            "is_interrupt": is_interrupt,
        },
        "context": {
            "info_key": info_key,
            "product_category": product_key,
            "needs_soft_sell": needs_soft_sell,
        },
        "entities": entities,
        "meta": {
            "has_active_booking": has_active_booking,
            "booking_step": booking_step,
        },
    }

    try:
        _router_logger.info(
            json.dumps(
                {
                    "intent": intent,
                    "confidence": confidence,
                    "info_key": info_key,
                    "product_key": product_key,
                    "is_interrupt": is_interrupt,
                    "booking_step": booking_step,
                    "message": message[:200],
                    "metrics": _metrics.copy(),
                },
                ensure_ascii=False,
            )
        )
    except Exception:
        pass

    return record
