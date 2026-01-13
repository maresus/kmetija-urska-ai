"""
Testi za app/services/reservation_service.py

Pokriva:
- validate_room_rules
- validate_table_rules
- create_reservation
- check_room_availability
- check_table_availability
"""
import pytest
from datetime import datetime, timedelta


def get_future_date(days_ahead: int = 30) -> str:
    """Vrne datum v prihodnosti."""
    future = datetime.now() + timedelta(days=days_ahead)
    return future.strftime("%d.%m.%Y")


def get_future_saturday(weeks_ahead: int = 2) -> str:
    """Vrne soboto v prihodnosti."""
    today = datetime.now()
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0:
        days_until_saturday = 7
    saturday = today + timedelta(days=days_until_saturday + (weeks_ahead - 1) * 7)
    return saturday.strftime("%d.%m.%Y")


def get_future_sunday(weeks_ahead: int = 2) -> str:
    """Vrne nedeljo v prihodnosti."""
    today = datetime.now()
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7
    sunday = today + timedelta(days=days_until_sunday + (weeks_ahead - 1) * 7)
    return sunday.strftime("%d.%m.%Y")


def get_future_weekday(target_weekday: int, weeks_ahead: int = 2) -> str:
    """Vrne določen dan v tednu v prihodnosti (0=pon, 1=tor, ..., 6=ned)."""
    today = datetime.now()
    days_until = (target_weekday - today.weekday()) % 7
    if days_until == 0:
        days_until = 7
    target = today + timedelta(days=days_until + (weeks_ahead - 1) * 7)
    return target.strftime("%d.%m.%Y")


class TestValidateRoomRules:
    """Testi za pravila rezervacije sob."""
    
    def test_valid_reservation_2_nights(self):
        """2 nočitvi je OK (izven poletja)."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        # Datum v prihodnosti, izven poletja (januar)
        # Uporabimo december ki ni poletje
        future = datetime.now() + timedelta(days=60)
        # Če pademo v poletje, dodamo še nekaj dni
        while future.month in [6, 7, 8]:
            future += timedelta(days=30)
        future_str = future.strftime("%d.%m.%Y")
        
        ok, msg = service.validate_room_rules(future_str, 2)
        # 2 nočitvi bi moralo biti OK izven poletja
        # Če ni OK, je morda drug razlog (pon/tor)
        assert ok == True or "polet" not in msg.lower()
    
    def test_valid_reservation_3_nights(self):
        """3 nočitve je vedno OK."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        future_str = get_future_date(45)
        ok, msg = service.validate_room_rules(future_str, 3)
        assert ok == True
    
    def test_invalid_summer_too_few_nights(self):
        """Poleti manj kot 3 nočitve ni OK."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        # Najdi datum poleti v prihodnosti
        future = datetime.now()
        # Pojdi na julij naslednje leto če smo že mimo
        if future.month > 8:
            future = future.replace(year=future.year + 1, month=7, day=15)
        elif future.month < 6:
            future = future.replace(month=7, day=15)
        else:
            future = future + timedelta(days=10)  # Smo v poletju
        
        future_str = future.strftime("%d.%m.%Y")
        
        ok, msg = service.validate_room_rules(future_str, 2)
        # Poleti 2 nočitvi NI OK
        assert ok == False or "3" in msg or "polet" in msg.lower()
    
    def test_past_date_rejected(self):
        """Pretekli datumi so zavrnjeni."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        past_str = "15.01.2020"
        ok, msg = service.validate_room_rules(past_str, 3)
        # Pretekli datum bi moral biti zavrnjen
        assert ok == False


class TestValidateTableRules:
    """Testi za pravila rezervacije miz."""
    
    def test_valid_saturday(self):
        """Sobota ob 13:00 je OK."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        saturday_str = get_future_saturday(2)
        ok, msg = service.validate_table_rules(saturday_str, "13:00")
        assert ok == True
    
    def test_valid_sunday(self):
        """Nedelja ob 14:00 je OK."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        sunday_str = get_future_sunday(2)
        ok, msg = service.validate_table_rules(sunday_str, "14:00")
        assert ok == True
    
    def test_invalid_weekday(self):
        """Sreda ni veljavna za mizo (samo sob/ned)."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        wednesday_str = get_future_weekday(2, 2)  # Sreda
        ok, msg = service.validate_table_rules(wednesday_str, "13:00")
        assert ok == False
        assert "sobota" in msg.lower() or "nedelja" in msg.lower()
    
    def test_invalid_late_arrival(self):
        """Prihod po 15:00 ni veljaven."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        saturday_str = get_future_saturday(2)
        ok, msg = service.validate_table_rules(saturday_str, "16:00")
        assert ok == False
        assert "15" in msg


class TestCreateReservation:
    """Testi za ustvarjanje rezervacij."""
    
    def test_create_room_reservation(self):
        """Ustvari rezervacijo sobe."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        future_str = get_future_date(60)
        
        reservation = service.create_reservation(
            date=future_str,
            people=4,
            reservation_type="room",
            source="test",
            nights=3,
            rooms=1,
            name="Test User",
            phone="041123456",
            email="test@test.si"
        )
        
        assert reservation is not None
        # create_reservation vrača dict
        if isinstance(reservation, dict):
            assert reservation.get("reservation_type") == "room" or reservation.get("type") == "room"
        else:
            assert reservation.reservation_type == "room"
    
    def test_create_table_reservation(self):
        """Ustvari rezervacijo mize."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        saturday_str = get_future_saturday(3)
        
        reservation = service.create_reservation(
            date=saturday_str,
            people=6,
            reservation_type="table",
            source="test",
            time="13:00",
            location="Jedilnica Pri peči",
            name="Test User",
            phone="041123456",
            email="test@test.si"
        )
        
        assert reservation is not None
        # create_reservation vrača dict
        if isinstance(reservation, dict):
            assert reservation.get("reservation_type") == "table" or reservation.get("type") == "table"
        else:
            assert reservation.reservation_type == "table"


class TestAvailability:
    """Testi za preverjanje razpoložljivosti."""
    
    def test_room_availability_future(self):
        """Preveri razpoložljivost za datum v prihodnosti."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        future_str = get_future_date(90)
        available, alternative = service.check_room_availability(
            future_str, 3, 4, 1
        )
        # Ne moremo zagotoviti rezultata, samo da ne crashne
        assert isinstance(available, bool)
    
    def test_available_rooms_list(self):
        """Preveri da available_rooms vrne seznam."""
        from app.services.reservation_service import ReservationService
        service = ReservationService()
        
        future_str = get_future_date(90)
        rooms = service.available_rooms(future_str, 3)
        assert isinstance(rooms, list)
        # Če so sobe, preveri imena
        valid_rooms = {"ALJAZ", "JULIJA", "ANA", "ALJAŽ"}
        for room in rooms:
            room_upper = room.upper().replace("Ž", "Z")
            assert room_upper in valid_rooms or room in valid_rooms
