import os
import time
import hmac
import hashlib
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.services.email_service import send_admin_notification
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/api/webhook", tags=["webhook"])

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30  # requests per window per IP
rate_limit_log: dict[str, list[float]] = {}


class WordPressReservation(BaseModel):
    # Skupna polja
    source: str  # 'wordpress_room' | 'wordpress_table'
    name: str
    email: str
    phone: Optional[str] = None
    date: str
    people: int
    note: Optional[str] = None

    # Polja za sobe
    nights: Optional[int] = None
    room: Optional[str] = None  # 'Aljaž' | 'Ana' | 'Julija'
    country: Optional[str] = None
    adults: Optional[int] = None
    kids: Optional[str] = None
    kids_small: Optional[str] = None
    arrive: Optional[str] = None
    depart: Optional[str] = None
    confirm_via: Optional[str] = None

    # Polja za mize
    time: Optional[str] = None
    event_type: Optional[str] = None
    location: Optional[str] = None  # jedilnica
    special_needs: Optional[str] = None
    kids_count: Optional[int] = None
    kids_ages: Optional[str] = None


@router.post("/reservation")
async def receive_wordpress_reservation(
    request: Request,
    data: WordPressReservation,
    x_webhook_signature: str = Header(None),
    x_webhook_secret: str = Header(None),
):
    """Prejme rezervacijo iz WordPress vtičnika in jo shrani kot pending."""
    # rate limit per IP
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    history = rate_limit_log.get(ip, [])
    history = [ts for ts in history if now - ts < RATE_LIMIT_WINDOW]
    if len(history) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    history.append(now)
    rate_limit_log[ip] = history

    # signature verification (skip if secret not set)
    secret = WEBHOOK_SECRET or ""
    if secret:
        raw_body = await request.body()
        computed = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        expected_sig = f"sha256={computed}"
        provided = x_webhook_signature or x_webhook_secret  # backward compat
        if not provided or not hmac.compare_digest(provided, expected_sig):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    service = ReservationService()
    res_id = service.create_reservation(
        date=data.arrive or data.date,
        people=data.people or data.adults or 0,
        reservation_type="room" if data.source == "wordpress_room" else "table",
        source=data.source,
        nights=data.nights,
        rooms=1 if data.room else None,
        name=data.name,
        phone=data.phone,
        email=data.email,
        time=data.time,
        location=data.room or data.location,
        note=data.note,
        country=data.country,
        kids=data.kids,
        kids_small=data.kids_small,
        confirm_via=data.confirm_via,
        event_type=data.event_type,
        special_needs=data.special_needs or data.kids_ages,
    )

    send_admin_notification(
        {
            "id": res_id,
            "name": data.name,
            "email": data.email,
            "phone": data.phone,
            "date": data.arrive or data.date,
            "people": data.people or data.adults,
            "reservation_type": "room" if data.source == "wordpress_room" else "table",
            "source": data.source,
        }
    )

    return {"status": "ok", "reservation_id": res_id}
