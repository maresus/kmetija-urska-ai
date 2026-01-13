from fastapi import APIRouter

from app.models.reservation import ReservationCreate
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/reservations", tags=["reservations"])
reservation_service = ReservationService()


@router.get("")
def list_reservations() -> list[dict]:
    return reservation_service.read_reservations()


@router.post("")
def create_reservation(payload: ReservationCreate) -> dict:
    new_id = reservation_service.create_reservation(
        date=payload.date,
        people=payload.people,
        reservation_type=payload.reservation_type,
        nights=payload.nights,
        rooms=payload.rooms,
        time=payload.time,
        location=payload.location,
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        note=payload.note,
        source="api",
    )
    created = reservation_service.get_reservation(new_id) or {}
    return {"id": new_id, **created, "message": "Reservation created"}
