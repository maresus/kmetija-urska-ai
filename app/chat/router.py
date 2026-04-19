"""
Chat API router for Kmetija Urška AI.
"""
from __future__ import annotations

import uuid
import asyncio
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.chat.llm_chat import chat
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/chat", tags=["chat"])
_service = ReservationService()

# In-memory sessions
_sessions: dict[str, dict] = {}


class QuickBookingRequest(BaseModel):
    session_id: str | None = None
    booking_type: str = "room"  # "room" or "wellness"
    date: str
    nights: int | None = None
    adults: int = 2
    children: int = 0
    children_ages: list[int] = []
    name: str
    phone: str
    email: str = ""
    half_board: bool = False
    note: str = ""
    gdpr: bool = False


@router.post("/quick-booking")
async def quick_booking(payload: QuickBookingRequest):
    """Sprejme celo rezervacijo naenkrat iz forme v widgetu."""
    if not payload.gdpr:
        return {"ok": False, "error": "Strinjanje z obdelavo podatkov je obvezno."}

    from datetime import datetime as _dt2
    conn = _service._conn()
    cursor = conn.cursor()
    now_ts = _dt2.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = _service._placeholder()

    half_board_note = " | Polpenzion: DA" if payload.half_board else ""
    note_full = (payload.note + half_board_note).strip(" |")

    returning = " RETURNING id" if _service.use_postgres else ""
    cursor.execute(f"""
        INSERT INTO reservations (date, nights, people, reservation_type, source, status, name, phone, email, note, created_at)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}){returning}
    """, (
        payload.date,
        payload.nights or 0,
        payload.adults + payload.children,
        payload.booking_type,
        "widget_form",
        "pending",
        payload.name,
        payload.phone,
        payload.email,
        note_full or "Rezervacija iz widget forme.",
        now_ts,
    ))
    if _service.use_postgres:
        row = cursor.fetchone()
        reservation_id = row["id"] if isinstance(row, dict) else row[0]
    else:
        reservation_id = cursor.lastrowid
    conn.commit()
    conn.close()

    session_id = payload.session_id or str(uuid.uuid4())
    _service.log_conversation(
        session_id=session_id,
        user_message=f"[Forma] {payload.booking_type}: {payload.date}, {payload.adults}+{payload.children} oseb, {payload.name}",
        bot_response=f"Rezervacija #{reservation_id} shranjena.",
        intent="quick_booking_form",
    )

    # Email obvestilo
    try:
        from app.services.email_service import send_custom_message
        import os as _os
        notify_email = _os.getenv("NOTIFY_EMAIL", "")
        if notify_email:
            send_custom_message(
                to=notify_email,
                subject=f"[Kmetija Urška Widget] Nova rezervacija #{reservation_id} — {payload.name}",
                body=f"""Nova rezervacija iz widget forme:

Ime: {payload.name}
Telefon: {payload.phone}
Email: {payload.email or '-'}
Datum: {payload.date}
Tip: {payload.booking_type}
Noči: {payload.nights or '-'}
Odrasli: {payload.adults} | Otroci: {payload.children}
Polpenzion: {'DA' if payload.half_board else 'NE'}
Opomba: {payload.note or '-'}

Rezervacija #{reservation_id}
""",
            )
    except Exception as e:
        print(f"[quick-booking] Email napaka: {e}")

    if reservation_id:
        return {"ok": True, "reservation_id": reservation_id}
    else:
        return {"ok": False, "error": "Napaka pri shranjevanju."}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    action: str | None = None
    booking_type_hint: str | None = None


def _get_session(session_id: str | None) -> tuple[str, dict]:
    if session_id:
        if session_id not in _sessions:
            _sessions[session_id] = {"history": []}
        return session_id, _sessions[session_id]
    new_id = str(uuid.uuid4())
    _sessions[new_id] = {"history": []}
    return new_id, _sessions[new_id]


def _detect_booking_intent(message: str) -> str | None:
    """Detect if user wants to make a booking. Returns 'room', 'wellness' or None."""
    msg = message.lower()
    # Koreni brez končnic — pokrijejo vse sklanjatve (soba/sobo/sobe, savna/savno/savne...)
    room_keywords = ("rezervir", "sob", "prenočit", "prenočev", "nastanit", "noč", "apartma")
    wellness_keywords = ("wellness", "savn", "jacuzzi", "kopel v senu", "hiša dobrega počutja", "razvajanj", "spa")
    if any(k in msg for k in room_keywords):
        return "room"
    if any(k in msg for k in wellness_keywords):
        return "wellness"
    return None


@router.post("", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest, background_tasks: BackgroundTasks) -> ChatResponse:
    session_id, session = _get_session(payload.session_id)
    message = payload.message.strip()

    # Detect booking intent → offer the quick form
    booking_type = _detect_booking_intent(message)
    if booking_type and not session.get("form_offered"):
        session["form_offered"] = True
        result = chat(message=message, history=session["history"])
        session["history"].append({"role": "user", "content": message})
        session["history"].append({"role": "assistant", "content": result["reply"]})
        _service.log_conversation(
            session_id=session_id,
            user_message=message,
            bot_response=result["reply"],
            intent=f"booking_intent_{booking_type}",
        )
        return ChatResponse(
            reply=result["reply"],
            session_id=session_id,
            action="open_booking_form",
            booking_type_hint=booking_type,
        )

    result = chat(message=message, history=session["history"])

    session["history"].append({"role": "user", "content": message})
    session["history"].append({"role": "assistant", "content": result["reply"]})

    if len(session["history"]) > 20:
        session["history"] = session["history"][-20:]

    # Auto-extract booking v ozadju — ne blokira odgovora
    background_tasks.add_task(_try_auto_save_inquiry, session_id, session)

    _service.log_conversation(
        session_id=session_id,
        user_message=message,
        bot_response=result["reply"],
        intent="info_query",
    )

    return ChatResponse(reply=result["reply"], session_id=session_id)


def _try_auto_save_inquiry(session_id: str, session: dict) -> int | None:
    """Auto-extract and save reservation from conversation when enough data collected."""
    if session.get("auto_saved"):
        return None

    history = session.get("history", [])
    if len(history) < 4:
        return None

    conversation_text = ""
    for msg in history[-16:]:
        role = "Uporabnik" if msg["role"] == "user" else "AI"
        conversation_text += f"{role}: {msg['content']}\n"

    import os, json
    from openai import OpenAI
    from datetime import datetime as _dt
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    current_year = _dt.now().year
    extraction_prompt = f"""Iz spodnjega pogovora izvleci podatke o rezervaciji/povpraševanju za turistično kmetijo.
Vrni SAMO JSON brez razlage. Če podatek manjka, daj null.
Zahtevani podatki: ime (vsaj priimek), kontakt (telefon ali email), datum, število oseb.
Če kateri koli od teh 4 podatkov manjka → vrni: {{"complete": false}}

POMEMBNO:
- Tekoče leto je {current_year}. Če leto ni eksplicitno navedeno, uporabi {current_year}.
- "število oseb" = skupaj oseb (odrasli + otroci).
- date format: DD.MM.YYYY

Format če je kompletno:
{{
  "complete": true,
  "booking_type": "room" ali "wellness",
  "name": "...",
  "phone": "..." ali null,
  "email": "..." ali null,
  "date": "DD.MM.YYYY",
  "people": 2,
  "note": "..." ali null
}}"""

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": extraction_prompt},
                {"role": "user", "content": conversation_text},
            ],
            max_output_tokens=300,
        )
        raw = getattr(resp, "output_text", "") or ""
        if not raw:
            for block in getattr(resp, "output", []) or []:
                for c in getattr(block, "content", []) or []:
                    raw += getattr(c, "text", "")

        raw = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(raw)
    except Exception:
        return None

    if not data.get("complete"):
        return None

    from app.services.reservation_service import ReservationService
    _svc = ReservationService()
    conn = _svc._connect()
    cursor = conn.cursor()
    from datetime import datetime as _dt2
    now_ts = _dt2.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO reservations (date, people, reservation_type, source, status, name, phone, email, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("date", ""),
        int(data.get("people") or 1),
        data.get("booking_type", "room"),
        "chatbot",
        "pending",
        data.get("name", ""),
        data.get("phone") or "",
        data.get("email") or "",
        data.get("note") or "Povpraševanje zbrano v pogovoru z botom.",
        now_ts,
    ))
    reservation_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if reservation_id:
        session["auto_saved"] = True
        _service.log_conversation(
            session_id=session_id,
            user_message="[AUTO] Sistem je samodejno zaznal in shranil povpraševanje.",
            bot_response=f"Rezervacija #{reservation_id} samodejno shranjena.",
            intent="auto_extracted_booking",
        )

    # Send notification email
    try:
        from app.services.email_service import send_custom_message
        import os as _os
        notify_email = _os.getenv("NOTIFY_EMAIL", "")
        if notify_email:
            send_custom_message(
                to=notify_email,
                subject=f"[Kmetija Urška Bot] Nova rezervacija #{reservation_id} — {data.get('name', '')}",
                body=f"""Nova rezervacija zbrana iz pogovora z botom:

Ime: {data.get('name', '')}
Telefon: {data.get('phone', '-')}
Email: {data.get('email', '-')}
Datum: {data.get('date', '')}
Osebe: {data.get('people', '')}
Tip: {data.get('booking_type', '')}
Opomba: {data.get('note', '')}

Rezervacija #{reservation_id}
""",
            )
    except Exception as e:
        print(f"[auto-save] Email napaka: {e}")

    return reservation_id
