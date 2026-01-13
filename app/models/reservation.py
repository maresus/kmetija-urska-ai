from typing import Optional

from pydantic import BaseModel


class ReservationRequest(BaseModel):
    date: str
    people: int
    note: str | None = None


class ReservationResponse(BaseModel):
    confirmed: bool
    message: str


class ReservationCreate(BaseModel):
    date: str
    people: int
    reservation_type: str
    nights: int | None = None
    rooms: int | None = None
    time: str | None = None
    location: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    note: str | None = None
    status: Optional[str] = None


class ReservationRecord(BaseModel):
    id: int
    date: str
    people: int
    source: str
    created_at: str
    reservation_type: str
    rooms: int | None = None
    nights: int | None = None
    time: str | None = None
    location: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    note: str | None = None
    status: Optional[str] = None
