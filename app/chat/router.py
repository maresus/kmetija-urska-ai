"""
Chat API router for Kmetija Urška AI.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter
from pydantic import BaseModel

from app.chat.llm_chat import chat
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/chat", tags=["chat"])
_service = ReservationService()

# In-memory sessions
_sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


def _get_session(session_id: str | None) -> tuple[str, dict]:
    if session_id:
        if session_id not in _sessions:
            _sessions[session_id] = {"history": []}
        return session_id, _sessions[session_id]
    new_id = str(uuid.uuid4())
    _sessions[new_id] = {"history": []}
    return new_id, _sessions[new_id]


@router.post("", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    session_id, session = _get_session(payload.session_id)
    message = payload.message.strip()

    result = chat(message=message, history=session["history"])

    session["history"].append({"role": "user", "content": message})
    session["history"].append({"role": "assistant", "content": result["reply"]})

    if len(session["history"]) > 20:
        session["history"] = session["history"][-20:]

    # Auto-extract booking from conversation if enough data
    _try_auto_save_inquiry(session_id, session)

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
