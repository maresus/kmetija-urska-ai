import csv
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

from app.models.reservation import ReservationRecord

DATABASE_URL = os.environ.get("DATABASE_URL")

# Kmetija Urška - 5 dvoposteljnih sob + 2 družinska suita
ROOMS = [
    {"id": "MARIJA", "name": "Soba MARIJA", "capacity": 2},
    {"id": "TINKARA", "name": "Soba TINKARA", "capacity": 2},
    {"id": "CILKA", "name": "Soba CILKA", "capacity": 2},
    {"id": "HANA", "name": "Soba HANA", "capacity": 2},
    {"id": "MANCA", "name": "Soba MANCA (prilagojena invalidom)", "capacity": 2},
    {"id": "URSKA_SUITE", "name": "Družinska suita URŠKA (z mini kuhinjico)", "capacity": 4},
    {"id": "ANA_SUITE", "name": "Družinska suita ANA (z mini kuhinjico)", "capacity": 4},
]
ROOM_NAME_MAP = {
    "marija": "MARIJA",
    "tinkara": "TINKARA",
    "cilka": "CILKA",
    "hana": "HANA",
    "manca": "MANCA",
    "urška": "URSKA_SUITE",
    "urska": "URSKA_SUITE",
    "ana": "ANA_SUITE",
}

# Kmetija Urška nima jedilnic za zunanje goste (samo za nastanjene)
# Degustacijska kosila/večerje so do 20 oseb (po naročilu)
MAX_MEAL_CAPACITY = 20
MAX_NIGHTS = 30

# Kmetija Urška obratuje:
# Petek: 15-20h (po dogovoru)
# Sobota: 12-20h (po dogovoru)
# Ostali dnevi: po dogovoru
# Za nastanjene: 24/7
ROOM_CLOSED_DAYS = set()  # Odprto vse dni po dogovoru
MEAL_DAYS = {4, 5, 6}  # pet, sob, ned (glavni dnevi)
OPENING_START_HOUR = 12
OPENING_END_HOUR = 20

# Wellness: Hiša dobrega počutja
WELLNESS_PRICE_PER_2H = 30  # €/2h/oseba
WELLNESS_AVAILABLE_HOURS = list(range(10, 20))  # 10:00 - 20:00

# Paketi
PACKAGES = {
    "eko_vikend": {"name": "Eko vikend razvajanja", "price": 199, "nights": 2},
    "dusa_telo": {"name": "Vikend za dušo in telo", "price": 225, "nights": 2},
    "urskin": {"name": "Urškin vikend", "price": 215, "nights": 2},
    "enodnevni": {"name": "Enodnevni pobeg", "price": 150, "nights": 1},
    "druzinski": {"name": "Družinski paket (7 noči)", "price": 734, "nights": 7},
}

# Accommodation types
ACCOMMODATION_PRICES = {
    "zajtrk": 72,  # Nočitev z zajtrkom
    "polpenzion": 87,  # Zajtrk + večerja
    "polpenzion_razširjen": 97,  # Zajtrk + kosilo + večerja + bazen (julij/avg)
}


class ReservationService:
    def __init__(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.csv_path = os.path.join(project_root, "reservations.csv")
        self.backup_dir = os.path.join(project_root, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        # Če ni DATABASE_URL ali psycopg2, uporabimo SQLite (lokalni razvoj)
        self.use_postgres = bool(DATABASE_URL and HAS_POSTGRES)
        if not self.use_postgres:
            self.data_dir = os.path.join(project_root, "data")
            os.makedirs(self.data_dir, exist_ok=True)
            self.db_path = os.path.join(self.data_dir, "reservations.db")

        self._ensure_db()
        self._import_csv_if_empty()

    # --- DB helpers ------------------------------------------------------
    def _conn(self):
        if self.use_postgres:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            return conn
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _placeholder(self) -> str:
        return "%s" if self.use_postgres else "?"

    def _ensure_db(self) -> None:
        new_columns = [
            ("rooms", "INTEGER"),
            ("status", "TEXT DEFAULT 'pending'"),
            ("admin_notes", "TEXT"),
            ("confirmed_at", "TEXT"),
            ("confirmed_by", "TEXT"),
            ("guest_message", "TEXT"),
            ("country", "TEXT"),
            ("kids", "TEXT"),
            ("kids_small", "TEXT"),
            ("confirm_via", "TEXT"),
            ("event_type", "TEXT"),
            ("special_needs", "TEXT"),
            # Urška-specific fields
            ("wellness_duration_hours", "INTEGER"),
            ("meal_type", "TEXT"),
            ("package_type", "TEXT"),
            ("package_price", "REAL"),
            ("room_preference", "TEXT"),
            ("accommodation_type", "TEXT"),
        ]

        if self.use_postgres:
            conn = self._conn()
            cur = None
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reservations (
                        id SERIAL PRIMARY KEY,
                        date TEXT NOT NULL,
                        nights INTEGER,
                        rooms INTEGER,
                        people INTEGER NOT NULL,
                        reservation_type TEXT NOT NULL,
                        time TEXT,
                        location TEXT,
                        name TEXT,
                        phone TEXT,
                        email TEXT,
                        note TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        source TEXT NOT NULL,
                        admin_notes TEXT,
                        confirmed_at TEXT,
                        confirmed_by TEXT,
                        guest_message TEXT,
                        country TEXT,
                        kids TEXT,
                        kids_small TEXT,
                        confirm_via TEXT,
                        event_type TEXT,
                        special_needs TEXT,
                        wellness_duration_hours INTEGER,
                        meal_type TEXT,
                        package_type TEXT,
                        package_price REAL,
                        room_preference TEXT,
                        accommodation_type TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT,
                        user_message TEXT NOT NULL,
                        bot_response TEXT NOT NULL,
                        intent TEXT,
                        needs_followup BOOLEAN DEFAULT FALSE,
                        followup_email TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS inquiries (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT,
                        details TEXT NOT NULL,
                        deadline TEXT,
                        contact_name TEXT,
                        contact_email TEXT,
                        contact_phone TEXT,
                        contact_raw TEXT,
                        status TEXT DEFAULT 'new',
                        created_at TEXT NOT NULL,
                        source TEXT NOT NULL
                    )
                    """
                )
                # dodaj manjkajoče stolpce na obstoječo tabelo (robustnost)
                for col, definition in new_columns:
                    cur.execute(
                        f"ALTER TABLE reservations ADD COLUMN IF NOT EXISTS {col} {definition}"
                    )
                conn.commit()
            finally:
                if cur:
                    cur.close()
                conn.close()
        else:
            import sqlite3

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    nights INTEGER,
                    rooms INTEGER,
                    people INTEGER NOT NULL,
                    reservation_type TEXT NOT NULL,
                    time TEXT,
                    location TEXT,
                    name TEXT,
                    phone TEXT,
                    email TEXT,
                    note TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    admin_notes TEXT,
                    confirmed_at TEXT,
                    confirmed_by TEXT,
                    guest_message TEXT,
                    country TEXT,
                    kids TEXT,
                    kids_small TEXT,
                    confirm_via TEXT,
                    event_type TEXT,
                    special_needs TEXT,
                    wellness_duration_hours INTEGER,
                    meal_type TEXT,
                    package_type TEXT,
                    package_price REAL,
                    room_preference TEXT,
                    accommodation_type TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    user_message TEXT NOT NULL,
                    bot_response TEXT NOT NULL,
                    intent TEXT,
                    needs_followup BOOLEAN DEFAULT FALSE,
                    followup_email TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inquiries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    details TEXT NOT NULL,
                    deadline TEXT,
                    contact_name TEXT,
                    contact_email TEXT,
                    contact_phone TEXT,
                    contact_raw TEXT,
                    status TEXT DEFAULT 'new',
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL
                )
                """
            )
            # dodaj manjkajoče stolpce za stare tabele
            info = conn.execute("PRAGMA table_info(reservations)").fetchall()
            existing_cols = {row[1] for row in info}
            for col, definition in new_columns:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE reservations ADD COLUMN {col} {definition};")
            conn.commit()
            conn.close()

    def _import_csv_if_empty(self) -> None:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(1) FROM reservations")
            row = cur.fetchone()
            if isinstance(row, dict):
                count = list(row.values())[0]
            elif isinstance(row, (list, tuple)):
                count = row[0]
            elif hasattr(row, "__getitem__"):
                count = row[0]
            else:
                count = 0
            if count > 0 or not os.path.exists(self.csv_path):
                return
        finally:
            cur.close()
            conn.close()
        # preberi obstoječi csv in ga zapiši v sqlite
        legacy_rows = self._read_legacy_csv()
        if not legacy_rows:
            return
        conn = self._conn()
        ph = self._placeholder()
        placeholders = ", ".join([ph] * 11)
        insert_sql = (
            f"INSERT INTO reservations (date, nights, people, reservation_type, time, location, name, phone, email, created_at, source) "
            f"VALUES ({placeholders})"
        )
        try:
            cur = conn.cursor()
            for row in legacy_rows:
                cur.execute(
                    insert_sql,
                    (
                        row.get("date", ""),
                        int(row.get("nights") or 0) or None,
                        int(row.get("people") or 0),
                        row.get("reservation_type") or row.get("type") or "room",
                        row.get("time") or None,
                        row.get("location") or None,
                        row.get("name") or None,
                        row.get("phone") or None,
                        row.get("email") or None,
                        row.get("created_at") or datetime.now().isoformat(),
                        row.get("source") or "import",
                    ),
                )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    # --- helpers ---------------------------------------------------------
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(date_str.strip(), "%d.%m.%Y")
        except ValueError:
            return None

    def _parse_time(self, time_str: str) -> Optional[str]:
        """Normalize various time inputs to HH:MM."""
        if not time_str:
            return None
        cleaned = time_str.strip().lower()
        cleaned = cleaned.replace("h", ":").replace(".", ":")
        match = re.match(r"^(\d{1,2})(?::(\d{2}))?$", cleaned)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if hour > 23 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"

    def _room_min_nights(self, arrival: datetime) -> int:
        return 3 if arrival.month in {6, 7, 8} else 2

    def _rooms_needed(self, people: int) -> int:
        return max(1, math.ceil(people / 4))

    def _normalize_room_location(self, location: Optional[str]) -> list[str]:
        if not location:
            return []
        lowered = location.lower()
        selected = []
        for key, rid in ROOM_NAME_MAP.items():
            if key in lowered and rid not in selected:
                selected.append(rid)
        return selected

    def _room_calendar(self) -> dict[str, set[str]]:
        """Vrne slovar room_id -> set datumov (dd.mm.yyyy) ki so zasedeni."""
        calendar: dict[str, set[str]] = {r["id"]: set() for r in ROOMS}
        for reservation in self._fetch_reservations():
            if reservation.reservation_type != "room":
                continue
            if reservation.status == "cancelled":
                continue
            if not reservation.nights:
                continue
            if reservation.nights > MAX_NIGHTS:
                continue
            if reservation.nights > MAX_NIGHTS:
                continue
            arrival = self._parse_date(reservation.date)
            if not arrival:
                continue
            dates = [(arrival + timedelta(days=offset)).strftime("%d.%m.%Y") for offset in range(reservation.nights)]
            assigned = self._normalize_room_location(reservation.location)
            rooms_to_mark = assigned if assigned else [r["id"] for r in ROOMS]
            rooms_needed = reservation.rooms or self._rooms_needed(reservation.people)
            # če nimamo točne sobe, zapolnimo prve proste
            filled = 0
            for room_id in rooms_to_mark:
                if filled >= rooms_needed:
                    break
                # preveri, ali je soba prosta za vse datume
                if all(date not in calendar[room_id] for date in dates):
                    for d in dates:
                        calendar[room_id].add(d)
                    filled += 1
            # če še vedno kaj manjka, zapolnimo preostale
            if filled < rooms_needed:
                for room_id in [r["id"] for r in ROOMS]:
                    if filled >= rooms_needed:
                        break
                    if all(date not in calendar[room_id] for date in dates):
                        for d in dates:
                            calendar[room_id].add(d)
                        filled += 1
        return calendar

    def available_rooms(self, arrival_str: str, nights: int) -> list[str]:
        arrival = self._parse_date(arrival_str)
        if not arrival:
            return []
        dates = [(arrival + timedelta(days=offset)).strftime("%d.%m.%Y") for offset in range(nights)]
        calendar = self._room_calendar()
        free = []
        for room_id in [r["id"] for r in ROOMS]:
            occupied = calendar.get(room_id, set())
            if all(d not in occupied for d in dates):
                free.append(room_id)
        return free

    def _room_occupancy(self) -> dict[str, int]:
        occupancy: dict[str, int] = defaultdict(int)
        for reservation in self._fetch_reservations():
            if reservation.reservation_type != "room":
                continue
            if reservation.status == "cancelled":
                continue
            if not reservation.nights:
                continue
            arrival = self._parse_date(reservation.date)
            if not arrival:
                continue
            rooms_needed = reservation.rooms or self._rooms_needed(reservation.people)
            for offset in range(reservation.nights):
                day = (arrival + timedelta(days=offset)).strftime("%d.%m.%Y")
                occupancy[day] += rooms_needed
        return occupancy

    def _table_room_occupancy(self) -> dict[tuple[str, str, str], int]:
        occupancy: dict[tuple[str, str, str], int] = defaultdict(int)
        for reservation in self._fetch_reservations():
            if reservation.reservation_type != "table":
                continue
            if reservation.status == "cancelled":
                continue
            if not reservation.time:
                continue
            room_key = reservation.location or "Jedilnica Pri vrtu"
            key = (reservation.date, reservation.time, room_key)
            occupancy[key] += reservation.people
        return occupancy

    # --- availability ----------------------------------------------------
    def validate_room_rules(self, arrival_str: str, nights: int) -> Tuple[bool, str]:
        """Kmetija Urška: Odprto vse dni, minimalno 2 noči (razen julij/avg = 5 noči)"""
        arrival = self._parse_date(arrival_str)
        if not arrival:
            return False, "Tega datuma ne razumem. Prosimo uporabite obliko DD.MM.YYYY (npr. 12.7.2025)."
        today = datetime.now().date()
        if arrival.date() < today:
            today_str = today.strftime("%d.%m.%Y")
            return False, f"Ta datum je že mimo (danes je {today_str}). Prosimo izberite datum v prihodnosti."
        # Kmetija Urška je odprta vse dni (ni zaprtih dni)
        if nights < 1:
            return False, "Prosimo izberite vsaj eno nočitev."
        if nights > MAX_NIGHTS:
            return False, f"Maksimalno število nočitev v eni rezervaciji je {MAX_NIGHTS}. Prosimo izberite manj dni."
        # Minimalno bivanje: julij/avg = 5 noči, ostalo = 2 noči
        min_nights = 5 if arrival.month in {7, 8} else 2
        if nights < min_nights:
            if arrival.month in {7, 8}:
                return (
                    False,
                    "V juliju in avgustu je minimalno bivanje 5 noči. Prosimo izberite vsaj 5 nočitev.",
                )
            return False, "Minimalno bivanje je 2 noči. Prosimo izberite vsaj 2 nočitvi."
        return True, ""

    def check_room_availability(
        self, arrival_str: str, nights: int, people: int, rooms: Optional[int] = None
    ) -> tuple[bool, Optional[str]]:
        arrival = self._parse_date(arrival_str)
        if not arrival:
            return False, None
        if people <= 0:
            return False, None
        rooms_needed = rooms or self._rooms_needed(people)
        if rooms_needed > len(ROOMS):
            return False, None

        occupancy = self._room_occupancy()
        for offset in range(nights):
            day = (arrival + timedelta(days=offset)).strftime("%d.%m.%Y")
            used = occupancy.get(day, 0)
            if used + rooms_needed > len(ROOMS):
                alternative = self.suggest_room_alternative(arrival, nights, rooms_needed)
                return False, alternative
        return True, None

    def suggest_room_alternative(
        self, arrival: datetime, nights: int, rooms_needed: int
    ) -> Optional[str]:
        occupancy = self._room_occupancy()
        for delta in range(1, 31):
            candidate = arrival + timedelta(days=delta)
            if candidate.weekday() in ROOM_CLOSED_DAYS:
                continue
            min_nights = self._room_min_nights(candidate)
            if nights < min_nights:
                continue
            fits = True
            for offset in range(nights):
                day = (candidate + timedelta(days=offset)).strftime("%d.%m.%Y")
                if occupancy.get(day, 0) + rooms_needed > len(ROOMS):
                    fits = False
                    break
            if fits:
                return candidate.strftime("%d.%m.%Y")
        return None

    def validate_table_rules(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        dining_day = self._parse_date(date_str)
        if not dining_day:
            return False, "Datum prosimo v obliki DD.MM.YYYY (npr. 15.6.2025)."
        today = datetime.now().date()
        if dining_day.date() < today:
            today_str = today.strftime("%d.%m.%Y")
            return False, f"Ta datum je že mimo (danes je {today_str}). Prosimo izberite datum v prihodnosti."
        if dining_day.weekday() not in TABLE_OPEN_DAYS:
            return False, "Za mize sprejemamo rezervacije ob sobotah in nedeljah med 12:00 in 20:00."
        normalized_time = self._parse_time(time_str)
        if not normalized_time:
            return False, "Uro prosim vpišite v obliki HH:MM (npr. 12:30)."
        hour, minute = map(int, normalized_time.split(":"))
        if hour < OPENING_START_HOUR or hour > OPENING_END_HOUR:
            return False, "Kuhinja obratuje med 12:00 in 20:00. Prosimo izberite uro znotraj tega okna."
        if hour > LAST_LUNCH_ARRIVAL_HOUR or (hour == LAST_LUNCH_ARRIVAL_HOUR and minute > 0):
            return False, "Zadnji prihod na kosilo je ob 15:00. Prosimo izberite zgodnejšo uro."
        return True, ""

    def check_table_availability(
        self, date_str: str, time_str: str, people: int
    ) -> tuple[bool, Optional[str], list[str]]:
        normalized_time = self._parse_time(time_str)
        if not normalized_time:
            return False, None, []
        occupancy = self._table_room_occupancy()
        suggestions: list[str] = []

        # global limit čez oba prostora
        total_used = 0
        for room in DINING_ROOMS:
            total_used += occupancy.get((date_str, normalized_time, room["name"]), 0)
        if total_used + people > TOTAL_TABLE_CAPACITY:
            suggestions = self.suggest_table_slots(date_str, people, limit=3)
            return False, None, suggestions

        for room in DINING_ROOMS:
            key = (date_str, normalized_time, room["name"])
            used = occupancy.get(key, 0)
            if used + people <= room["capacity"]:
                return True, room["name"], suggestions

        suggestions = self.suggest_table_slots(date_str, people, limit=3)
        return False, None, suggestions

    def suggest_table_slots(self, date_str: str, people: int, limit: int = 3) -> list[str]:
        slots: list[str] = []
        occupancy = self._table_room_occupancy()
        start_times = []
        for hour in range(OPENING_START_HOUR, LAST_LUNCH_ARRIVAL_HOUR + 1):
            start_times.append(f"{hour:02d}:00")
            if hour != LAST_LUNCH_ARRIVAL_HOUR:
                start_times.append(f"{hour:02d}:30")

        # 1) isti dan
        for t in start_times:
            for room in DINING_ROOMS:
                used = occupancy.get((date_str, t, room["name"]), 0)
                if used + people <= room["capacity"]:
                    slots.append(f"{date_str} ob {t} ({room['name']})")
                    break
            if len(slots) >= limit:
                return slots

        # 2) najbližji vikend v prihodnjih dveh tednih
        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return slots
        for delta in range(1, 15):
            candidate = parsed_date + timedelta(days=delta)
            if candidate.weekday() not in TABLE_OPEN_DAYS:
                continue
            candidate_str = candidate.strftime("%d.%m.%Y")
            for t in start_times:
                for room in DINING_ROOMS:
                    used = occupancy.get((candidate_str, t, room["name"]), 0)
                    if used + people <= room["capacity"]:
                        slots.append(f"{candidate_str} ob {t} ({room['name']})")
                        break
                if len(slots) >= limit:
                    return slots
        return slots

    # --- CRUD ------------------------------------------------------------
    def create_reservation(
        self,
        date: str,
        people: int,
        reservation_type: str,
        source: str = "chat",
        nights: Optional[int] = None,
        rooms: Optional[int] = None,
        time: Optional[str] = None,
        location: Optional[str] = None,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        note: Optional[str] = None,
        status: str = "pending",
        admin_notes: Optional[str] = None,
        confirmed_at: Optional[str] = None,
        confirmed_by: Optional[str] = None,
        guest_message: Optional[str] = None,
        country: Optional[str] = None,
        kids: Optional[str] = None,
        kids_small: Optional[str] = None,
        confirm_via: Optional[str] = None,
        event_type: Optional[str] = None,
        special_needs: Optional[str] = None,
        # Urška-specific parameters
        wellness_duration_hours: Optional[int] = None,
        meal_type: Optional[str] = None,
        package_type: Optional[str] = None,
        package_price: Optional[float] = None,
        room_preference: Optional[str] = None,
        accommodation_type: Optional[str] = None,
    ) -> int:
        created_at = datetime.now().isoformat()
        # Admin / telefon / API vnosi se avtomatsko potrdijo
        if source in ("admin", "phone", "api"):
            status = "confirmed"
        conn = self._conn()
        ph = self._placeholder()
        placeholders = ", ".join([ph] * 30)  # Changed from 24 to 30
        sql = (
            f"INSERT INTO reservations "
            f"(date, nights, rooms, people, reservation_type, time, location, name, phone, email, note, status, created_at, source, "
            f"admin_notes, confirmed_at, confirmed_by, guest_message, country, kids, kids_small, confirm_via, event_type, special_needs, "
            f"wellness_duration_hours, meal_type, package_type, package_price, room_preference, accommodation_type) "
            f"VALUES ({placeholders})"
        )
        if self.use_postgres:
            sql += " RETURNING id"
        try:
            cur = conn.cursor()
            cur.execute(
                sql,
                (
                    date,
                    nights,
                    rooms,
                    people,
                    reservation_type,
                    time,
                    location,
                    name,
                    phone,
                    email,
                    note,
                    status,
                    created_at,
                    source,
                    admin_notes,
                    confirmed_at,
                    confirmed_by,
                    guest_message,
                    country,
                    kids,
                    kids_small,
                    confirm_via,
                    event_type,
                    special_needs,
                    wellness_duration_hours,
                    meal_type,
                    package_type,
                    package_price,
                    room_preference,
                    accommodation_type,
                ),
            )
            if self.use_postgres:
                fetched = cur.fetchone()
                new_id = fetched["id"] if isinstance(fetched, dict) else fetched[0]
            else:
                new_id = cur.lastrowid
            conn.commit()
        finally:
            cur.close()
            conn.close()

        return int(new_id)

    def update_status(self, reservation_id: int, new_status: str) -> bool:
        """Posodobi status rezervacije. Vrne True če uspešno."""
        if new_status not in ("pending", "processing", "confirmed", "rejected", "cancelled"):
            return False
        conn = self._conn()
        ph = self._placeholder()
        sql = f"UPDATE reservations SET status = {ph} WHERE id = {ph}"
        try:
            cur = conn.cursor()
            cur.execute(sql, (new_status, reservation_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            cur.close()
            conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM reservations WHERE id = " + self._placeholder(), (reservation_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            cur.close()
            conn.close()

    def read_reservations(
        self,
        limit: int = 100,
        status: Optional[str] = None,
        reservation_type: Optional[str] = None,
        source: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            sql = "SELECT * FROM reservations"
            params: list[Any] = []
            conditions: list[str] = []
            ph = self._placeholder()
            if status:
                conditions.append(f"status = {ph}")
                params.append(status)
            if reservation_type:
                conditions.append(f"reservation_type = {ph}")
                params.append(reservation_type)
            if source:
                conditions.append(f"source = {ph}")
                params.append(source)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY created_at DESC LIMIT " + str(int(limit))
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            cur.close()
            conn.close()

    def update_reservation(self, reservation_id: int, **fields: Any) -> bool:
        """Posodobi poljubna polja rezervacije (le tista, ki niso None)."""
        allowed_fields = {
            "status",
            "date",
            "nights",
            "rooms",
            "people",
            "reservation_type",
            "time",
            "location",
            "name",
            "phone",
            "email",
            "note",
            "admin_notes",
            "confirmed_at",
            "confirmed_by",
            "guest_message",
            "country",
            "kids",
            "kids_small",
            "confirm_via",
            "event_type",
            "special_needs",
            # Urška-specific fields
            "wellness_duration_hours",
            "meal_type",
            "package_type",
            "package_price",
            "room_preference",
            "accommodation_type",
        }
        updates = {k: v for k, v in fields.items() if k in allowed_fields and v is not None}
        if not updates:
            return False
        ph = self._placeholder()
        set_parts = [f"{k} = {ph}" for k in updates.keys()]
        params = list(updates.values())
        params.append(reservation_id)
        conn = self._conn()
        try:
            cur = conn.cursor()
            sql = f"UPDATE reservations SET {', '.join(set_parts)} WHERE id = {ph}"
            cur.execute(sql, tuple(params))
            conn.commit()
            return cur.rowcount > 0
        finally:
            cur.close()
            conn.close()

    def _fetch_reservations(self) -> list[ReservationRecord]:
        records: list[ReservationRecord] = []
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, date, nights, rooms, people, reservation_type, time, location,
                       name, phone, email, note, status, created_at, source
                FROM reservations
                WHERE status NOT IN ('cancelled', 'rejected')
                """
            )
            for row in cur.fetchall():
                try:
                    people = int(row["people"])
                except (TypeError, ValueError, KeyError):
                    people = 0
                try:
                    nights = int(row["nights"]) if row["nights"] is not None else None
                except (TypeError, ValueError, KeyError):
                    nights = None
                try:
                    rooms = int(row["rooms"]) if row["rooms"] is not None else None
                except (TypeError, ValueError, KeyError):
                    rooms = None
                records.append(
                    ReservationRecord(
                        id=row["id"],
                        date=row["date"],
                        nights=nights,
                        rooms=rooms,
                        people=people,
                        name=row["name"],
                        phone=row["phone"],
                        email=row["email"],
                        created_at=row["created_at"],
                        source=row["source"],
                        reservation_type=row["reservation_type"],
                        time=row["time"],
                        location=row["location"],
                        note=row["note"],
                        status=row["status"],
                    )
                )
        finally:
            cur.close()
            conn.close()
        return records

    def _read_legacy_csv(self) -> list[Dict[str, Any]]:
        if not os.path.exists(self.csv_path):
            return []
        reservations: list[Dict[str, Any]] = []
        expected_fields = [
            "date",
            "nights",
            "people",
            "name",
            "phone",
            "email",
            "created_at",
            "source",
            "reservation_type",
            "time",
            "location",
            "note",
        ]
        with open(self.csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                first_value = row[0].strip().lower()
                if first_value == "date":
                    continue
                padded = (row + [""] * len(expected_fields))[: len(expected_fields)]
                reservation = {key: value or "" for key, value in zip(expected_fields, padded)}
                reservations.append(reservation)
        return reservations

    def create_backup_csv(self) -> str:
        """Ustvari CSV backup iz SQLite in vrne pot do datoteke."""
        today_str = datetime.now().strftime("%Y%m%d")
        backup_path = os.path.join(self.backup_dir, f"reservations-{today_str}.csv")
        rows = self.read_reservations()
        with open(backup_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "date",
                    "nights",
                    "rooms",
                    "people",
                    "reservation_type",
                    "time",
                    "location",
                    "name",
                    "phone",
                    "email",
                    "note",
                    "status",
                    "created_at",
                    "source",
                    "admin_notes",
                    "confirmed_at",
                    "confirmed_by",
                    "guest_message",
                    "country",
                    "kids",
                    "kids_small",
                    "confirm_via",
                    "event_type",
                    "special_needs",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row.get("id", ""),
                        row.get("date", ""),
                        row.get("nights", ""),
                        row.get("rooms", ""),
                        row.get("people", ""),
                        row.get("reservation_type", ""),
                        row.get("time", ""),
                        row.get("location", ""),
                        row.get("name", ""),
                        row.get("phone", ""),
                        row.get("email", ""),
                        row.get("note", ""),
                        row.get("status", ""),
                        row.get("created_at", ""),
                        row.get("source", ""),
                        row.get("admin_notes", ""),
                        row.get("confirmed_at", ""),
                        row.get("confirmed_by", ""),
                        row.get("guest_message", ""),
                        row.get("country", ""),
                        row.get("kids", ""),
                        row.get("kids_small", ""),
                        row.get("confirm_via", ""),
                        row.get("event_type", ""),
                        row.get("special_needs", ""),
                    ]
                )
        return backup_path

    # --- conversation logging -------------------------------------------
    def log_conversation(
        self,
        session_id: str,
        user_message: str,
        bot_response: str,
        intent: Optional[str] = None,
        needs_followup: bool = False,
        followup_email: Optional[str] = None,
    ) -> Optional[int]:
        """Shrani pogovor v bazo in vrne ID vrstice."""
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ph = self._placeholder()
        conn = self._conn()
        conv_id: Optional[int] = None
        try:
            cur = conn.cursor()
            sql = (
                "INSERT INTO conversations (session_id, user_message, bot_response, intent, needs_followup, followup_email, created_at) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"
            )
            params = (session_id, user_message, bot_response, intent, needs_followup, followup_email, created_at)
            if self.use_postgres:
                sql += " RETURNING id"
            cur.execute(sql, params)
            if self.use_postgres:
                fetched = cur.fetchone()
                if fetched:
                    conv_id = fetched["id"] if isinstance(fetched, dict) else fetched[0]
            else:
                conv_id = cur.lastrowid
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return conv_id

    def get_conversations(self, limit: int = 100, needs_followup_only: bool = False) -> list[dict]:
        """Vrne zadnje pogovore, opcijsko filtrirane po potrebi po followupu."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            sql = "SELECT * FROM conversations"
            if needs_followup_only:
                sql += " WHERE needs_followup = TRUE"
            sql += " ORDER BY created_at DESC LIMIT " + str(limit)
            cur.execute(sql)
            rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            cur.close()
            conn.close()

    def get_conversations_by_session(self, session_id: str, limit: int = 200) -> list[dict]:
        """Vrne pogovor po session_id."""
        conn = self._conn()
        ph = self._placeholder()
        try:
            cur = conn.cursor()
            sql = f"SELECT * FROM conversations WHERE session_id = {ph} ORDER BY created_at ASC LIMIT {limit}"
            cur.execute(sql, (session_id,))
            rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            cur.close()
            conn.close()

    def update_followup_email(self, conversation_id: int, email: str) -> bool:
        """Posodobi email za followup pogovor."""
        ph = self._placeholder()
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(f"UPDATE conversations SET followup_email = {ph} WHERE id = {ph}", (email, conversation_id))
            conn.commit()
            return True
        finally:
            cur.close()
            conn.close()

    def get_top_questions(self, limit: int = 10) -> list[dict]:
        """Vrne najpogostejša vprašanja."""
        conn = self._conn()
        ph = self._placeholder()
        try:
            cur = conn.cursor()
            sql = (
                "SELECT user_message, COUNT(*) as count "
                "FROM conversations "
                "GROUP BY user_message "
                "ORDER BY count DESC "
                f"LIMIT {ph}"
            )
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            cur.close()
            conn.close()

    # --- inquiries -------------------------------------------
    def create_inquiry(
        self,
        session_id: str,
        details: str,
        deadline: str,
        contact_name: str,
        contact_email: str,
        contact_phone: str,
        contact_raw: str,
        source: str = "chat",
        status: str = "new",
    ) -> Optional[int]:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ph = self._placeholder()
        conn = self._conn()
        inquiry_id: Optional[int] = None
        try:
            cur = conn.cursor()
            sql = (
                "INSERT INTO inquiries (session_id, details, deadline, contact_name, contact_email, contact_phone, contact_raw, status, created_at, source) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"
            )
            params = (
                session_id,
                details,
                deadline,
                contact_name,
                contact_email,
                contact_phone,
                contact_raw,
                status,
                created_at,
                source,
            )
            if self.use_postgres:
                sql += " RETURNING id"
            cur.execute(sql, params)
            if self.use_postgres:
                fetched = cur.fetchone()
                if fetched:
                    inquiry_id = fetched["id"] if isinstance(fetched, dict) else fetched[0]
            else:
                inquiry_id = cur.lastrowid
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return inquiry_id

    def get_inquiries(self, limit: int = 200, status: Optional[str] = None) -> list[dict]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            sql = "SELECT * FROM inquiries"
            params = []
            if status:
                sql += " WHERE status = " + self._placeholder()
                params.append(status)
            sql += " ORDER BY created_at DESC LIMIT " + str(limit)
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            cur.close()
            conn.close()

    def get_usage_stats(self) -> dict:
        """Vrne unikatne session_id za danes/ta mesec/letos."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            today_prefix = datetime.now().strftime("%Y-%m-%d")
            month_prefix = datetime.now().strftime("%Y-%m")
            year_prefix = datetime.now().strftime("%Y")
            ph = self._placeholder()
            sql_base = "SELECT DISTINCT session_id FROM conversations WHERE session_id IS NOT NULL AND session_id != '' AND created_at LIKE "
            cur.execute(sql_base + ph, (today_prefix + "%",))
            today_sessions = {row["session_id"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}
            cur.execute(sql_base + ph, (month_prefix + "%",))
            month_sessions = {row["session_id"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}
            cur.execute(sql_base + ph, (year_prefix + "%",))
            year_sessions = {row["session_id"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}
            return {
                "today": len(today_sessions),
                "month": len(month_sessions),
                "year": len(year_sessions),
            }
        finally:
            cur.close()
            conn.close()
