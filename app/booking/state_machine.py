"""
Booking state machine for structured reservation flow.
Step-by-step data collection for room and table reservations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class BookingState:
    """State for a booking in progress."""
    type: str = ""  # "room" or "table"
    step: str = "start"  # start, awaiting_date, awaiting_nights, awaiting_adults, awaiting_children_count, awaiting_children_ages, awaiting_contact, awaiting_confirm

    # Collected data
    date: str = ""
    time: str = ""  # For table reservations
    nights: int = 0
    adults: int = 0
    children: int = 0
    children_ages: list[int] = field(default_factory=list)
    name: str = ""
    phone: str = ""
    email: str = ""
    room_preference: str = ""
    dinner: bool = False
    note: str = ""

    # After save
    reservation_id: Optional[int] = None


def _save_reservation(state: BookingState, source: str = "chatbot") -> Optional[int]:
    """Save completed booking to database and send notifications."""
    try:
        from app.services.reservation_service import ReservationService
        from app.services.email_service import send_guest_confirmation, send_admin_notification

        service = ReservationService()

        # Calculate total people
        total_people = state.adults + state.children

        # Build kids string
        kids_str = ""
        if state.children > 0:
            ages_str = ", ".join(str(a) for a in state.children_ages) if state.children_ages else ""
            kids_str = f"{state.children} ({ages_str} let)" if ages_str else str(state.children)

        # Build note with dinner preference
        note_parts = []
        if state.type == "room" and state.dinner:
            note_parts.append("Večerja: Da")
        if state.note:
            note_parts.append(state.note)
        note = "; ".join(note_parts) if note_parts else None

        # Create reservation in DB
        reservation_id = service.create_reservation(
            date=state.date,
            people=total_people,
            reservation_type=state.type,
            nights=state.nights if state.type == "room" else None,
            time=state.time if state.type == "table" else None,
            name=state.name,
            phone=state.phone,
            email=state.email if state.email else None,
            note=note,
            kids=kids_str if kids_str else None,
            source=source,
            status="pending",
        )

        # Build data dict for emails
        email_data = {
            "id": reservation_id,
            "date": state.date,
            "people": total_people,
            "reservation_type": state.type,
            "name": state.name,
            "phone": state.phone,
            "email": state.email if state.email else None,
            "nights": state.nights if state.type == "room" else None,
            "time": state.time if state.type == "table" else None,
            "kids": kids_str if kids_str else None,
            "kids_ages": ", ".join(str(a) for a in state.children_ages) if state.children_ages else None,
            "note": note,
            "source": source,
        }

        # Send emails (will fail silently if not configured)
        if state.email:
            send_guest_confirmation(email_data)
        send_admin_notification(email_data)

        print(f"[BOOKING] Reservation #{reservation_id} saved to database")
        return reservation_id

    except Exception as e:
        print(f"[BOOKING] Error saving reservation: {e}")
        return None


def detect_booking_intent(message: str) -> str | None:
    """
    Detect if user wants to start a booking.
    Returns "room", "table", or None.
    """
    msg_l = message.lower()

    # Booking phrases - including common typos and colloquial expressions
    booking_phrases = (
        "rezervir", "rezervacij", "rezevir", "rezerir", "rezerv", "rezerw",
        "book", "bukiram", "bukir", "zarezrv", "zarezev", "zarezerv",
        "rad bi rezerv", "bi rad rezerv", "rad bi rezev", "bi rad rezev",
        "želim rezerv", "zelim rezerv", "želim rezev", "zelim rezev",
        "bi radi rezerv", "hočemo rezerv", "hocemo rezerv",
        "lahko rezerv", "lahk rezerv", "lahko rezev", "lahk rezev",
        "bi rad nočil", "bi radi nočil", "bi rad nocil", "bi radi nocil",
        "bi rad prenočil", "bi radi prenočil",
        "bi rad ostal", "bi radi ostali", "bi rad prenoči", "bi radi prenoči",
        "nočitev", "nocitev", "prenočitev", "prenočiti", "prenociti",
        "spavanje", "spati pri", "postat pri", "ostati pri",
    )

    has_booking = any(phrase in msg_l for phrase in booking_phrases)

    # Room indicators
    room_words = ("sobo", "soba", "sobi", "sobe", "nočitev", "nocitev", "prenočitev", "nastanitev")
    # Table indicators
    table_words = ("mizo", "miza", "mizi", "kosilo", "kosilom", "degustacij")

    has_room = any(w in msg_l for w in room_words)
    has_table = any(w in msg_l for w in table_words)

    # Must have booking phrase
    if not has_booking:
        return None

    # Determine type
    if has_room and not has_table:
        return "room"
    if has_table and not has_room:
        return "table"
    if has_room or has_table:
        return "room"  # Default to room if ambiguous

    # Generic booking request without specifying type
    return "ask"  # Ask user what they want


def start_booking(booking_type: str) -> tuple[BookingState, str]:
    """Start a new booking flow."""
    state = BookingState(type=booking_type, step="awaiting_date")

    if booking_type == "room":
        reply = (
            "Odlično, rezervacija sobe!\n\n"
            "Za kateri datum prihoda razmišljate? (npr. 15.7.2026)"
        )
    elif booking_type == "table":
        reply = (
            "Odlično, rezervacija mize za kosilo!\n\n"
            "Za kateri datum in uro? (npr. nedelja 20.7.2026 ob 13:00)"
        )
    else:
        reply = (
            "Z veseljem pomagam pri rezervaciji!\n\n"
            "Ali želite rezervirati **sobo** (nastanitev) ali **mizo** (kosilo/degustacija)?"
        )
        state.step = "awaiting_type"

    return state, reply


def _parse_date(text: str) -> str | None:
    """Try to parse a date from text."""
    # Try DD.MM.YYYY or DD.MM
    match = re.search(r'(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?', text)
    if match:
        day, month = match.group(1), match.group(2)
        year = match.group(3) or str(datetime.now().year)
        return f"{int(day):02d}.{int(month):02d}.{year}"
    return None


def _parse_number(text: str) -> int | None:
    """Parse a number from text."""
    # Try digits
    match = re.search(r'\d+', text)
    if match:
        return int(match.group())
    # Try Slovene words
    words = {"ena": 1, "en": 1, "dva": 2, "dve": 2, "tri": 3, "štiri": 4, "stiri": 4, "pet": 5, "šest": 6, "sest": 6}
    for word, num in words.items():
        if word in text.lower():
            return num
    return None


def _parse_phone(text: str) -> str | None:
    """Parse phone number from text."""
    # Remove spaces and common separators
    cleaned = re.sub(r'[\s\-\.\(\)]', '', text)
    # Look for phone pattern
    match = re.search(r'(\+?386)?0?([0-9]{8,9})', cleaned)
    if match:
        return match.group(0)
    # Any sequence of 6+ digits
    match = re.search(r'[\d\s+\-\.]{7,}', text)
    if match:
        return match.group().strip()
    return None


def _parse_email(text: str) -> str | None:
    """Parse email from text."""
    match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    return match.group() if match else None


def _is_affirmative(text: str) -> bool:
    """Check if response is affirmative."""
    affirmatives = {"da", "ja", "yes", "ok", "okay", "v redu", "vredu", "seveda", "lahko", "prosim"}
    return text.strip().lower() in affirmatives


def _is_negative(text: str) -> bool:
    """Check if response is negative."""
    negatives = {"ne", "no", "nočem", "nocem", "brez", "ni treba", "ne hvala"}
    return text.strip().lower() in negatives


def _wants_to_cancel(message: str) -> bool:
    """Check if user wants to cancel booking."""
    msg_l = message.lower().strip()
    cancel_phrases = (
        "prekliči", "preklici", "storniraj", "ustavi", "pusti", "pozabi",
        "ne želim", "ne zelim", "nočem", "nocem", "ne bom", "nehaj",
        "cancel", "stop", "quit", "exit",
        "ne morem", "ne morem več", "premislil", "premislila",
    )
    return any(phrase in msg_l for phrase in cancel_phrases)


def process_booking(state: BookingState, message: str) -> tuple[BookingState, str]:
    """Process a message in the booking flow."""
    msg_l = message.lower().strip()

    # Check for cancellation at any step
    if _wants_to_cancel(message):
        state.step = "cancelled"
        return state, "Rezervacija je preklicana. Če si premislite, sem tu!"

    # Handle type selection
    if state.step == "awaiting_type":
        if any(w in msg_l for w in ("sobo", "soba", "nastanitev", "nočitev", "nocitev")):
            state.type = "room"
            state.step = "awaiting_date"
            return state, "Za kateri datum prihoda razmišljate? (npr. 15.7.2026)"
        if any(w in msg_l for w in ("mizo", "miza", "kosilo", "degustacij")):
            state.type = "table"
            state.step = "awaiting_date"
            return state, "Za kateri datum in uro? (npr. nedelja 20.7.2026 ob 13:00)"
        return state, "Prosim povejte: želite rezervirati **sobo** ali **mizo**?"

    # Handle date
    if state.step == "awaiting_date":
        date = _parse_date(message)
        if date:
            state.date = date
            if state.type == "room":
                state.step = "awaiting_nights"
                return state, f"Datum: {date}\n\nKoliko nočitev? (npr. 3)"
            else:
                state.step = "awaiting_adults"
                return state, f"Datum: {date}\n\nKoliko odraslih oseb?"
        return state, "Prosim vpišite datum v obliki DD.MM.YYYY (npr. 15.7.2026)"

    # Handle nights (room only)
    if state.step == "awaiting_nights":
        nights = _parse_number(message)
        if nights and nights > 0:
            # Check minimum nights
            month = int(state.date.split('.')[1]) if state.date else 0
            min_nights = 3 if month in (6, 7, 8) else 2
            if nights < min_nights:
                return state, f"Minimalno število nočitev je {min_nights} ({'junij-avgust' if min_nights == 3 else 'ostali meseci'}). Koliko nočitev?"
            state.nights = nights
            state.step = "awaiting_adults"
            return state, f"Število nočitev: {nights}\n\nKoliko odraslih oseb?"
        return state, "Koliko nočitev želite? (npr. 3)"

    # Handle adults count
    if state.step == "awaiting_adults":
        num = _parse_number(message)
        if num and num > 0:
            state.adults = num
            state.step = "awaiting_children_count"
            return state, f"Število odraslih: {num}\n\nAli boste imeli otroke? Če da, koliko? (ali 'ne' če brez otrok)"
        return state, "Koliko odraslih oseb? (npr. 2)"

    # Handle children count
    if state.step == "awaiting_children_count":
        # Check for "no children" response
        if _is_negative(msg_l) or any(w in msg_l for w in ("brez", "nimamo", "samo odrasl", "samo mi")):
            state.children = 0
            state.children_ages = []
            state.step = "awaiting_contact"
            return state, "V redu, brez otrok.\n\nVaše ime in priimek?"

        num = _parse_number(message)
        if num is not None and num >= 0:
            if num == 0:
                state.children = 0
                state.children_ages = []
                state.step = "awaiting_contact"
                return state, "V redu, brez otrok.\n\nVaše ime in priimek?"
            state.children = num
            state.step = "awaiting_children_ages"
            if num == 1:
                return state, f"Število otrok: {num}\n\nKoliko let ima otrok?"
            return state, f"Število otrok: {num}\n\nKoliko let imajo otroci? (npr. '5 in 8' ali '5, 8')"
        return state, "Koliko otrok? (število ali 'ne' če brez)"

    # Handle children ages
    if state.step == "awaiting_children_ages":
        # Extract all numbers as ages
        ages = re.findall(r'\d+', message)
        if ages:
            state.children_ages = [int(a) for a in ages[:state.children]]  # Take only as many as children count
            # If we got fewer ages than children, ask again
            if len(state.children_ages) < state.children:
                return state, f"Prosim vpišite starost za vseh {state.children} otrok (npr. '5 in 8')"
            state.step = "awaiting_contact"
            ages_str = ", ".join(str(a) for a in state.children_ages)
            return state, f"Starost otrok: {ages_str} let\n\nVaše ime in priimek?"
        return state, f"Prosim vpišite starost {'otroka' if state.children == 1 else 'otrok'} (npr. {'8' if state.children == 1 else '5 in 8'})"

    # Handle contact - name
    if state.step == "awaiting_contact":
        # Check if it looks like a name (at least 2 words, no numbers)
        words = message.strip().split()
        if len(words) >= 1 and not any(c.isdigit() for c in message):
            state.name = message.strip().title()
            state.step = "awaiting_phone"
            return state, f"Ime: {state.name}\n\nVaša telefonska številka?"
        return state, "Prosim vpišite vaše ime in priimek."

    # Handle phone
    if state.step == "awaiting_phone":
        phone = _parse_phone(message)
        if phone:
            state.phone = phone
            state.step = "awaiting_email"
            return state, f"Telefon: {phone}\n\nVaš email naslov? (za potrditev rezervacije, ali 'preskoči' če ne želite)"
        return state, "Prosim vpišite telefonsko številko (npr. 031 123 456)"

    # Handle email (optional)
    if state.step == "awaiting_email":
        # Check for skip
        skip_words = ("preskoči", "preskoci", "ne", "nimam", "brez", "skip", "-")
        if msg_l in skip_words or any(w in msg_l for w in skip_words):
            state.email = ""
            state.step = "awaiting_dinner" if state.type == "room" else "awaiting_confirm"
            if state.type == "room":
                return state, "V redu.\n\nŽelite tudi večerjo? (30 €/odraslo osebo, 15 €/otrok do 12 let — ponedeljek in torek brez večerij)"
            else:
                return state, _build_confirmation(state)

        email = _parse_email(message)
        if email:
            state.email = email
            state.step = "awaiting_dinner" if state.type == "room" else "awaiting_confirm"
            if state.type == "room":
                return state, f"Email: {email}\n\nŽelite tudi večerjo? (30 €/odraslo osebo, 15 €/otrok do 12 let — ponedeljek in torek brez večerij)"
            else:
                return state, _build_confirmation(state)
        return state, "Prosim vpišite veljaven email naslov (npr. janez@example.com) ali 'preskoči'"

    # Handle dinner preference (room only)
    if state.step == "awaiting_dinner":
        if _is_affirmative(msg_l):
            state.dinner = True
        state.step = "awaiting_confirm"
        return state, _build_confirmation(state)

    # Handle confirmation
    if state.step == "awaiting_confirm":
        if _is_affirmative(msg_l):
            # Save to database
            reservation_id = _save_reservation(state)
            state.reservation_id = reservation_id
            state.step = "confirmed"

            if reservation_id:
                return state, (
                    f"✅ Rezervacija #{reservation_id} je sprejeta!\n\n"
                    "Kmalu boste prejeli potrditev. Se vidimo na Domačiji Kovačnik! 🏡"
                )
            else:
                return state, (
                    "✅ Rezervacija je sprejeta!\n\n"
                    "Kmalu boste prejeli potrditev. Se vidimo na Domačiji Kovačnik! 🏡"
                )
        if _is_negative(msg_l) or "prekli" in msg_l or "storn" in msg_l:
            state.step = "cancelled"
            return state, "Rezervacija je preklicana. Če si premislite, sem tu!"
        return state, "Prosim potrdite rezervacijo z 'da' ali prekličite z 'ne'."

    # Fallback
    return state, "Oprostite, nisem razumel. Kako vam lahko pomagam?"


def _build_confirmation(state: BookingState) -> str:
    """Build confirmation message."""
    lines = ["Povzetek rezervacije:\n"]

    if state.type == "room":
        lines.append(f"Datum prihoda: {state.date}")
        lines.append(f"Število nočitev: {state.nights}")
    else:
        lines.append(f"Datum: {state.date}")
        if state.time:
            lines.append(f"Ura: {state.time}")

    people = f"{state.adults} odrasl{'a' if state.adults == 2 else 'ih' if state.adults > 2 else ''}"
    if state.children:
        people += f" + {state.children} otrok"
        if state.children_ages:
            ages_str = ", ".join(str(a) for a in state.children_ages)
            people += f" ({ages_str} let)"
    lines.append(f"Osebe: {people}")
    lines.append(f"Ime: {state.name}")
    lines.append(f"Telefon: {state.phone}")
    if state.email:
        lines.append(f"Email: {state.email}")

    if state.type == "room":
        lines.append(f"Večerja: {'Da' if state.dinner else 'Ne'}")

    lines.append("\nAli potrjujete rezervacijo? (da/ne)")

    return "\n".join(lines)


def is_booking_active(state: BookingState | None) -> bool:
    """Check if booking flow is active."""
    if state is None:
        return False
    return state.step not in ("", "confirmed", "cancelled")
