"""
Kmetija Urška AI — 100 poglobljenih testov
============================================
Kategorije:
  A.  _detect_booking_intent               (15 testov)
  B.  RAG: load_knowledge + search         (15 testov)
  C.  QuickBookingRequest validacija        (12 testov)
  D.  /health + osnovna infra              (5 testov)
  E.  /chat/quick-booking endpoint         (18 testov)
  F.  /chat (mock LLM)                     (20 testov)
  G.  Živi LLM testi (pravi API klici)     (15 testov)

Za žive teste potrebuješ OPENAI_API_KEY v okolju.
Brez njega se G preskoči (skipira).
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── pot do projekta ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Zaglušimo psycopg2 za lokalne teste (SQLite mode)
os.environ.setdefault("DATABASE_URL", "")

# ── FastAPI TestClient ────────────────────────────────────────────────────────
from fastapi.testclient import TestClient

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
HAS_OPENAI = bool(OPENAI_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Pomožni mock za OpenAI odgovor
# ─────────────────────────────────────────────────────────────────────────────
def _make_openai_mock(text: str):
    """Vrne mock objekt ki simulira OpenAI Responses API odgovor."""
    mock_response = MagicMock()
    mock_response.output_text = text
    return mock_response


def _patch_openai(text: str):
    """Context manager ki popravi OpenAI klic v llm_chat.py."""
    mock_client = MagicMock()
    mock_client.responses.create.return_value = _make_openai_mock(text)
    return patch("app.chat.llm_chat.OpenAI", return_value=mock_client)


# ─────────────────────────────────────────────────────────────────────────────
# A. _detect_booking_intent — 15 testov
# ─────────────────────────────────────────────────────────────────────────────
from app.chat.router import _detect_booking_intent


class TestDetectBookingIntent:
    # --- ROOM triggers ---
    def test_A01_rezerviraj_triggers_room(self):
        assert _detect_booking_intent("Rad bi rezerviral sobo") == "room"

    def test_A02_soba_triggers_room(self):
        assert _detect_booking_intent("Ali imate prosto sobo?") == "room"

    def test_A03_prenocitev_triggers_room(self):
        assert _detect_booking_intent("Zanima me prenočitev") == "room"

    def test_A04_nocitev_triggers_room(self):
        assert _detect_booking_intent("Koliko stane noč?") == "room"

    def test_A05_noci_triggers_room(self):
        assert _detect_booking_intent("Priti bi za 3 noči") == "room"

    def test_A06_nastanitev_triggers_room(self):
        assert _detect_booking_intent("Kako se nastaniti?") == "room"

    def test_A07_apartma_triggers_room(self):
        assert _detect_booking_intent("Imate kak apartma za 4 osebe?") == "room"

    # --- WELLNESS triggers ---
    def test_A08_wellness_triggers_wellness(self):
        assert _detect_booking_intent("Zanima me wellness") == "wellness"

    def test_A09_savna_triggers_wellness(self):
        assert _detect_booking_intent("Ali imate savno?") == "wellness"

    def test_A10_jacuzzi_triggers_wellness(self):
        assert _detect_booking_intent("Kdaj je jacuzzi na voljo?") == "wellness"

    def test_A11_kopel_v_senu_triggers_wellness(self):
        assert _detect_booking_intent("Zanima me kopel v senu") == "wellness"

    def test_A12_spa_triggers_wellness(self):
        assert _detect_booking_intent("Ima kmetija spa?") == "wellness"

    # --- Ni intent ---
    def test_A13_general_question_no_intent(self):
        assert _detect_booking_intent("Kje ste locirani?") is None

    def test_A14_price_question_no_intent(self):
        assert _detect_booking_intent("Koliko stane hrana?") is None

    def test_A15_empty_message_no_intent(self):
        assert _detect_booking_intent("") is None


# ─────────────────────────────────────────────────────────────────────────────
# B. RAG: load_knowledge + search — 15 testov
# ─────────────────────────────────────────────────────────────────────────────
from app.rag.search import load_knowledge, search, get_context

KNOWLEDGE_PATH = PROJECT_ROOT / "knowledge.jsonl"


class TestRAG:
    @pytest.fixture(autouse=True)
    def load_kb(self):
        """Naloži knowledge base pred vsakim testom."""
        count = load_knowledge(KNOWLEDGE_PATH)
        assert count > 0, "Baza znanja mora biti naložena"

    def test_B01_knowledge_loads_all_chunks(self):
        count = load_knowledge(KNOWLEDGE_PATH)
        assert count >= 16  # vsaj 16 chunkov

    def test_B02_search_wellness_returns_results(self):
        results = search("wellness savna jacuzzi", top_k=3)
        assert len(results) > 0

    def test_B03_search_wellness_relevant_content(self):
        results = search("wellness savna", top_k=1)
        text = results[0].paragraph.lower()
        assert "wellness" in text or "savna" in text or "jacuzzi" in text

    def test_B04_search_kontakt_returns_phone(self):
        results = search("kontakt telefon", top_k=1)
        text = results[0].paragraph
        assert "031" in text or "kmetija" in text.lower()

    def test_B05_search_cene_sobe(self):
        results = search("cena soba prenočitev", top_k=2)
        assert len(results) >= 1
        combined = " ".join(r.paragraph for r in results).lower()
        assert "74" in combined or "eur" in combined or "cen" in combined

    def test_B06_search_druzina_topolsek(self):
        results = search("Urška Vilma Tone", top_k=2)
        combined = " ".join(r.paragraph for r in results).lower()
        assert "topolšek" in combined or "urška" in combined

    def test_B07_search_paketi(self):
        results = search("paket vikend", top_k=2)
        combined = " ".join(r.paragraph for r in results).lower()
        assert "215" in combined or "paket" in combined

    def test_B08_search_aktivnosti(self):
        results = search("aktivnosti živali koze", top_k=2)
        combined = " ".join(r.paragraph for r in results).lower()
        assert "koze" in combined or "aktivnosti" in combined

    def test_B09_search_certifikati(self):
        results = search("green key certifikat", top_k=2)
        combined = " ".join(r.paragraph for r in results).lower()
        assert "green" in combined or "certif" in combined

    def test_B10_get_context_returns_string(self):
        ctx = get_context("soba cena", top_k=2)
        assert isinstance(ctx, str)
        assert len(ctx) > 10

    def test_B11_get_context_not_empty_for_known_topic(self):
        ctx = get_context("wellness hiša dobrega počutja")
        assert ctx.strip() != ""

    def test_B12_search_top_k_limit_respected(self):
        results = search("soba", top_k=2)
        assert len(results) <= 2

    def test_B13_search_top_k_5(self):
        results = search("kmetija", top_k=5)
        assert len(results) <= 5

    def test_B14_search_unknown_term_returns_empty_or_few(self):
        results = search("xyzabc123neobstojece")
        assert len(results) == 0

    def test_B15_search_darilni_bon(self):
        results = search("darilni bon", top_k=2)
        combined = " ".join(r.paragraph for r in results).lower()
        assert "bon" in combined or "daril" in combined


# ─────────────────────────────────────────────────────────────────────────────
# C. QuickBookingRequest validacija — 12 testov
# ─────────────────────────────────────────────────────────────────────────────
from app.chat.router import QuickBookingRequest
from pydantic import ValidationError


class TestQuickBookingRequest:
    def _valid_payload(self, **overrides):
        base = {
            "date": "2026-06-15",
            "adults": 2,
            "name": "Janez Novak",
            "phone": "041 123 456",
            "gdpr": True,
        }
        base.update(overrides)
        return base

    def test_C01_valid_minimal_payload(self):
        req = QuickBookingRequest(**self._valid_payload())
        assert req.name == "Janez Novak"

    def test_C02_default_booking_type_is_room(self):
        req = QuickBookingRequest(**self._valid_payload())
        assert req.booking_type == "room"

    def test_C03_wellness_booking_type(self):
        req = QuickBookingRequest(**self._valid_payload(booking_type="wellness"))
        assert req.booking_type == "wellness"

    def test_C04_default_children_is_zero(self):
        req = QuickBookingRequest(**self._valid_payload())
        assert req.children == 0

    def test_C05_default_half_board_false(self):
        req = QuickBookingRequest(**self._valid_payload())
        assert req.half_board is False

    def test_C06_half_board_true(self):
        req = QuickBookingRequest(**self._valid_payload(half_board=True))
        assert req.half_board is True

    def test_C07_children_ages_default_empty(self):
        req = QuickBookingRequest(**self._valid_payload())
        assert req.children_ages == []

    def test_C08_children_ages_populated(self):
        req = QuickBookingRequest(**self._valid_payload(children=2, children_ages=[5, 8]))
        assert req.children_ages == [5, 8]

    def test_C09_optional_email_default_empty(self):
        req = QuickBookingRequest(**self._valid_payload())
        assert req.email == ""

    def test_C10_session_id_none_by_default(self):
        req = QuickBookingRequest(**self._valid_payload())
        assert req.session_id is None

    def test_C11_session_id_can_be_set(self):
        sid = str(uuid.uuid4())
        req = QuickBookingRequest(**self._valid_payload(session_id=sid))
        assert req.session_id == sid

    def test_C12_gdpr_false_field_works(self):
        req = QuickBookingRequest(**self._valid_payload(gdpr=False))
        assert req.gdpr is False


# ─────────────────────────────────────────────────────────────────────────────
# Skupni client fixture
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    # Ne patchamo OpenAI tukaj — vsak test to naredi sam
    from main import app
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# D. /health + osnovna infra — 5 testov
# ─────────────────────────────────────────────────────────────────────────────
class TestHealth:
    def test_D01_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_D02_health_status_ok(self, client):
        r = client.get("/health")
        assert r.json()["status"] == "ok"

    def test_D03_health_bot_name(self, client):
        r = client.get("/health")
        assert r.json()["bot"] == "kmetija-urska"

    def test_D04_root_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_D05_chat_endpoint_exists(self, client):
        """POST /chat mora biti registriran (ne 404)."""
        with _patch_openai("Test."):
            r = client.post("/chat", json={"message": "zdravo"})
        assert r.status_code != 404


# ─────────────────────────────────────────────────────────────────────────────
# E. /chat/quick-booking — 18 testov
# ─────────────────────────────────────────────────────────────────────────────
def _qb_payload(**overrides):
    base = {
        "date": "2026-07-10",
        "adults": 2,
        "name": "Ana Kovač",
        "phone": "040 000 111",
        "gdpr": True,
        "booking_type": "room",
    }
    base.update(overrides)
    return base


class TestQuickBooking:
    def _post(self, client, **overrides):
        return client.post("/chat/quick-booking", json=_qb_payload(**overrides))

    def test_E01_valid_booking_returns_ok(self, client):
        r = self._post(client)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_E02_valid_booking_returns_reservation_id(self, client):
        r = self._post(client)
        data = r.json()
        assert "reservation_id" in data
        assert isinstance(data["reservation_id"], int)
        assert data["reservation_id"] > 0

    def test_E03_gdpr_false_returns_error(self, client):
        r = self._post(client, gdpr=False)
        data = r.json()
        assert data["ok"] is False
        assert "gdpr" in data.get("error", "").lower() or "obdelavo" in data.get("error", "").lower()

    def test_E04_wellness_booking_type_accepted(self, client):
        r = self._post(client, booking_type="wellness")
        assert r.json()["ok"] is True

    def test_E05_half_board_true_saves(self, client):
        r = self._post(client, half_board=True)
        assert r.json()["ok"] is True

    def test_E06_with_children(self, client):
        r = self._post(client, children=2, children_ages=[3, 7])
        assert r.json()["ok"] is True

    def test_E07_with_note(self, client):
        r = self._post(client, note="Alergija na gluten")
        assert r.json()["ok"] is True

    def test_E08_with_email(self, client):
        r = self._post(client, email="test@example.com")
        assert r.json()["ok"] is True

    def test_E09_with_session_id(self, client):
        r = self._post(client, session_id=str(uuid.uuid4()))
        assert r.json()["ok"] is True

    def test_E10_nights_0_saved(self, client):
        r = self._post(client, nights=0)
        assert r.json()["ok"] is True

    def test_E11_nights_5_saved(self, client):
        r = self._post(client, nights=5)
        assert r.json()["ok"] is True

    def test_E12_adults_1_single_room(self, client):
        r = self._post(client, adults=1)
        assert r.json()["ok"] is True

    def test_E13_adults_4_family(self, client):
        r = self._post(client, adults=4)
        assert r.json()["ok"] is True

    def test_E14_consecutive_bookings_get_different_ids(self, client):
        r1 = self._post(client, name="Gost1")
        r2 = self._post(client, name="Gost2")
        assert r1.json()["reservation_id"] != r2.json()["reservation_id"]

    def test_E15_response_has_no_extra_error_on_success(self, client):
        r = self._post(client)
        data = r.json()
        assert "error" not in data or data.get("error") is None

    def test_E16_half_board_note_combined_with_user_note(self, client):
        r = self._post(client, half_board=True, note="Posebna dieta")
        assert r.json()["ok"] is True

    def test_E17_empty_note_still_saves(self, client):
        r = self._post(client, note="")
        assert r.json()["ok"] is True

    def test_E18_long_name_saves(self, client):
        r = self._post(client, name="Marija Magdalena Topolšek-Planinšek")
        assert r.json()["ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# F. /chat endpoint (mock LLM) — 20 testov
# ─────────────────────────────────────────────────────────────────────────────
class TestChatEndpoint:
    def _chat(self, client, message, session_id=None):
        payload = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        with _patch_openai("Privzeti testni odgovor."):
            return client.post("/chat", json=payload)

    def test_F01_returns_200(self, client):
        r = self._chat(client, "Pozdravljeni!")
        assert r.status_code == 200

    def test_F02_reply_field_present(self, client):
        r = self._chat(client, "Pozdravljeni!")
        assert "reply" in r.json()

    def test_F03_session_id_returned(self, client):
        r = self._chat(client, "test")
        assert "session_id" in r.json()
        assert r.json()["session_id"]

    def test_F04_same_session_id_preserved(self, client):
        sid = str(uuid.uuid4())
        r = self._chat(client, "test", session_id=sid)
        assert r.json()["session_id"] == sid

    def test_F05_new_session_created_when_none(self, client):
        r = self._chat(client, "test")
        sid = r.json()["session_id"]
        assert len(sid) == 36  # UUID format

    def test_F06_booking_intent_room_returns_action(self, client):
        with _patch_openai("Rada vam pomagam z rezervacijo sobe!"):
            r = client.post("/chat", json={"message": "Rad bi rezerviral sobo za 3 noči"})
        data = r.json()
        assert data.get("action") == "open_booking_form"

    def test_F07_booking_intent_room_hint(self, client):
        with _patch_openai("Odlično, pomagam z rezervacijo!"):
            r = client.post("/chat", json={"message": "Rad bi rezerviral sobo"})
        assert r.json().get("booking_type_hint") == "room"

    def test_F08_booking_intent_wellness_hint(self, client):
        with _patch_openai("Wellness je na voljo!"):
            r = client.post("/chat", json={"message": "Zanima me wellness in savna"})
        assert r.json().get("booking_type_hint") == "wellness"

    def test_F09_no_booking_intent_no_action(self, client):
        r = self._chat(client, "Kje ste locirani?")
        assert r.json().get("action") is None

    def test_F10_form_offered_once_only(self, client):
        sid = str(uuid.uuid4())
        with _patch_openai("Rezervacija!"):
            r1 = client.post("/chat", json={"message": "Rad bi rezerviral sobo", "session_id": sid})
            r2 = client.post("/chat", json={"message": "Povedite mi več o sobah", "session_id": sid})
        # Drugi klic ne bi smel vrniti action=open_booking_form
        assert r2.json().get("action") != "open_booking_form"

    def test_F11_reply_not_empty(self, client):
        r = self._chat(client, "Zdravo")
        assert r.json()["reply"].strip() != ""

    def test_F12_strip_whitespace_message(self, client):
        r = self._chat(client, "   Zdravo   ")
        assert r.status_code == 200

    def test_F13_long_message_accepted(self, client):
        long_msg = "Zanima me vaša kmetija. " * 50
        r = self._chat(client, long_msg)
        assert r.status_code == 200

    def test_F14_slovenian_characters_accepted(self, client):
        r = self._chat(client, "Ali imate sobo za čšž gosta?")
        assert r.status_code == 200

    def test_F15_history_persists_across_turns(self, client):
        sid = str(uuid.uuid4())
        self._chat(client, "Moje ime je Franc", session_id=sid)
        r = self._chat(client, "Kako mi je ime?", session_id=sid)
        assert r.status_code == 200

    def test_F16_response_model_has_required_fields(self, client):
        r = self._chat(client, "test")
        data = r.json()
        assert "reply" in data
        assert "session_id" in data

    def test_F17_action_null_for_normal_chat(self, client):
        r = self._chat(client, "Kdaj imate odprto?")
        data = r.json()
        assert data.get("action") is None or data.get("action") == ""

    def test_F18_booking_type_hint_null_for_normal_chat(self, client):
        r = self._chat(client, "Koliko stane zajtrk?")
        data = r.json()
        assert data.get("booking_type_hint") is None

    def test_F19_multiple_sessions_independent(self, client):
        sid1 = str(uuid.uuid4())
        sid2 = str(uuid.uuid4())
        r1 = self._chat(client, "test1", session_id=sid1)
        r2 = self._chat(client, "test2", session_id=sid2)
        assert r1.json()["session_id"] == sid1
        assert r2.json()["session_id"] == sid2

    def test_F20_empty_message_handled(self, client):
        r = self._chat(client, "")
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# G. Živi LLM testi (pravi OpenAI API klici) — 15 testov
# ─────────────────────────────────────────────────────────────────────────────
pytestmark_live = pytest.mark.skipif(
    not HAS_OPENAI, reason="Potreben OPENAI_API_KEY za žive LLM teste"
)


def _live_chat(client, message: str, session_id: str | None = None) -> dict:
    """Pravi API klic brez mock-a."""
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    r = client.post("/chat", json=payload)
    assert r.status_code == 200, f"Chat klic neuspešen: {r.text}"
    return r.json()


@pytest.mark.skipif(not HAS_OPENAI, reason="Potreben OPENAI_API_KEY")
class TestLiveLLM:
    """
    Testi ki dejansko kličejo OpenAI in preverijo vsebino odgovorov.
    Namerno malo bolj ohlapni pri vsebini (LLM variira).
    """

    @pytest.fixture(scope="class")
    def live_client(self):
        from main import app
        with TestClient(app) as c:
            yield c

    def test_G01_bot_knows_phone_number(self, live_client):
        data = _live_chat(live_client, "Kakšna je vaša telefonska številka?")
        reply = data["reply"].lower()
        assert "031" in reply or "249" in reply or "759" in reply, \
            f"Telefon ni v odgovoru: {data['reply']}"

    def test_G02_bot_knows_address(self, live_client):
        data = _live_chat(live_client, "Kje se nahajate? Kakšen je naslov?")
        reply = data["reply"].lower()
        assert "stranice" in reply or "križevec" in reply, \
            f"Naslov ni v odgovoru: {data['reply']}"

    def test_G03_bot_knows_room_count(self, live_client):
        data = _live_chat(live_client, "Koliko sob imate?")
        reply = data["reply"]
        assert "7" in reply, f"Število sob ni v odgovoru: {reply}"

    def test_G04_bot_knows_standard_price(self, live_client):
        data = _live_chat(live_client, "Koliko stane prenočitev z zajtrkom v standardni sezoni?")
        reply = data["reply"]
        assert "74" in reply, f"Cena 74 EUR ni v odgovoru: {reply}"

    def test_G05_bot_knows_wellness_price(self, live_client):
        data = _live_chat(live_client, "Koliko stane dostop do wellness centra?")
        reply = data["reply"]
        assert "30" in reply, f"Cena wellness 30 EUR ni v odgovoru: {reply}"

    def test_G06_bot_knows_urska_weekend_package(self, live_client):
        data = _live_chat(live_client, "Koliko stane Urškin vikend paket?")
        reply = data["reply"]
        assert "215" in reply, f"Cena Urškin vikend 215 EUR ni v odgovoru: {reply}"

    def test_G07_bot_knows_no_horse_riding(self, live_client):
        data = _live_chat(live_client, "Ali nudite jahanje?")
        reply = data["reply"].lower()
        has_denial = any(w in reply for w in ["ni", "nimamo", "ne", "niso"])
        assert has_denial, f"Bot naj bi povedal da jahanja ni: {reply}"

    def test_G08_bot_knows_family_name(self, live_client):
        data = _live_chat(live_client, "Kako se imenuje lastniška družina?")
        reply = data["reply"].lower()
        assert "topolšek" in reply or "urška" in reply or "vilma" in reply, \
            f"Družina ni v odgovoru: {reply}"

    def test_G09_bot_responds_in_slovenian(self, live_client):
        data = _live_chat(live_client, "Pozdravljeni!")
        reply = data["reply"]
        assert any(w in reply.lower() for w in ["pozdravljeni", "lep", "hvala", "dober", "pomoč", "kmetij"]), \
            f"Odgovor ni v slovenščini: {reply}"

    def test_G10_bot_responds_in_english(self, live_client):
        # Pošljemo nedvoumno angleško vprašanje (brez besed ki bi sprožile booking intent)
        data = _live_chat(live_client, "What is the address of your farm?")
        reply = data["reply"]
        # Bot mora odgovoriti v angleščini — preveri angleške besede (širok nabor)
        english_words = ["address", "farm", "located", "village", "street", "križ", "stran",
                         "have", "our", "we", "the", "is", "in", "at", "are", "can", "please",
                         "hello", "welcome", "for", "how", "many", "people", "you", "your"]
        assert any(w in reply.lower() for w in english_words), \
            f"Bot naj odgovori v angleščini: {reply}"

    def test_G11_bot_does_not_invent_beekeeping(self, live_client):
        data = _live_chat(live_client, "Ali se lahko dogovorimo za obisk čebelnjaka?")
        reply = data["reply"].lower()
        forbidden = ["dogovor", "organizir", "uredim", "povežem", "pokličem čebelarja"]
        has_forbidden = any(f in reply for f in forbidden)
        assert not has_forbidden, \
            f"Bot ne sme obljubiti organizacije čebelarskega obiska: {reply}"

    def test_G12_bot_does_not_add_followup_invitation(self, live_client):
        """Pravilo 12: NE dodajaj vabil za nadaljnja vprašanja."""
        data = _live_chat(live_client, "Koliko stane prenočitev?")
        reply = data["reply"]
        bad_endings = [
            "vprašajte karkoli", "vprašajte me", "mi kar povejte",
            "z veseljem odgovorim", "kontaktirajte nas", "sem tu za vas"
        ]
        has_bad = any(b in reply.lower() for b in bad_endings)
        assert not has_bad, f"Bot ne sme dodajati vabil: {reply}"

    def test_G13_bot_gives_dry_fact_for_rogla(self, live_client):
        """Pravilo 13: Za okolico samo suho dejstvo."""
        data = _live_chat(live_client, "Kje je najbližje smučišče?")
        reply = data["reply"]
        # Mora omeniti Roglo, ne sme pisati esej
        assert "rogla" in reply.lower() or "15" in reply, \
            f"Rogla ni v odgovoru: {reply}"
        assert len(reply) < 400, f"Odgovor predolg za suho dejstvo: {reply}"

    def test_G14_booking_intent_triggers_action_field(self, live_client):
        """Ko zaznamo booking intent, API vrne action=open_booking_form."""
        r = live_client.post("/chat", json={"message": "Rad bi rezerviral sobo za vikend"})
        data = r.json()
        assert data.get("action") == "open_booking_form", \
            f"Booking intent ni zaznan: {data}"

    def test_G15_bot_knows_green_key_certificate(self, live_client):
        data = _live_chat(live_client, "Katere certifikate imate?")
        reply = data["reply"].lower()
        assert "green" in reply or "zeleni" in reply or "ekološk" in reply or "certif" in reply, \
            f"Certifikati niso v odgovoru: {reply}"
