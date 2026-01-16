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
    reservation_type: str  # "room", "wellness", "meal", "package"
    nights: int | None = None
    rooms: int | None = None
    time: str | None = None
    location: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    note: str | None = None
    status: Optional[str] = None
    # Wellness-specific
    wellness_duration_hours: int | None = None  # 2, 3, 4 hours
    # Meal-specific
    meal_type: str | None = None  # "degustacijsko_kosilo", "degustacijska_vecerja", "poslovni_zajtrk", "poslovni_kosilo"
    # Package-specific
    package_type: str | None = None  # "eko_vikend", "dusa_telo", "urskin", "enodnevni", "druzinski"
    package_price: float | None = None
    # Room preferences
    room_preference: str | None = None  # "marija", "tinkara", "cilka", "hana", "manca", "urska_suite", "ana_suite"
    accommodation_type: str | None = None  # "zajtrk", "polpenzion", "polpenzion_razširjen"


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
    # Wellness-specific
    wellness_duration_hours: int | None = None
    # Meal-specific
    meal_type: str | None = None
    # Package-specific
    package_type: str | None = None
    package_price: float | None = None
    # Room preferences
    room_preference: str | None = None
    accommodation_type: str | None = None
