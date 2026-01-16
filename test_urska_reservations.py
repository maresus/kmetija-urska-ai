"""
Test script za Kmetija Urška rezervacijski sistem
Testira vse 4 tipe rezervacij: room, wellness, meal, package
"""

from app.services.reservation_service import ReservationService
from app.services.urska_extensions import (
    validate_wellness_rules,
    calculate_wellness_price,
    format_wellness_summary,
    validate_meal_rules,
    format_meal_summary,
    validate_package_rules,
    get_package_info,
    format_package_summary,
)


def test_room_reservation():
    print("\n" + "=" * 60)
    print("TEST 1: NAMESTITEV (room)")
    print("=" * 60)

    rs = ReservationService()

    # Test: Julij = minimalno 5 noči
    print("\n1a) Validacija: Julij 2026, 3 noči (premalo)")
    valid, error = rs.validate_room_rules("15.07.2026", 3)
    print(f"  Valid: {valid}")
    print(f"  Error: {error}")

    # Test: Julij = 5 noči (OK)
    print("\n1b) Validacija: Julij 2026, 5 noči (OK)")
    valid, error = rs.validate_room_rules("15.07.2026", 5)
    print(f"  Valid: {valid}")

    # Test: Ustvari rezervacijo
    if valid:
        print("\n1c) Ustvarjam rezervacijo...")
        res_id = rs.create_reservation(
            date="15.07.2026",
            people=4,
            reservation_type="room",
            nights=5,
            rooms=2,
            room_preference="MARIJA,TINKARA",
            accommodation_type="polpenzion_razširjen",  # Julij/avg
            name="Test Uporabnik",
            phone="031123456",
            email="test@example.com",
            source="test",
        )
        print(f"  ✅ Rezervacija ustvarjena! ID: {res_id}")

        # Preberi nazaj
        reservation = rs.get_reservation(res_id)
        print(f"  Tip: {reservation['reservation_type']}")
        print(f"  Sobe: {reservation['room_preference']}")
        print(f"  Akomodacija: {reservation['accommodation_type']}")


def test_wellness_reservation():
    print("\n" + "=" * 60)
    print("TEST 2: WELLNESS")
    print("=" * 60)

    rs = ReservationService()

    # Validacija
    print("\n2a) Validacija: 20.06.2026, 14:00, 3 ure, 4 osebe")
    valid, error = validate_wellness_rules(
        date_str="20.06.2026", time_str="14:00", duration_hours=3, people=4
    )
    print(f"  Valid: {valid}")

    if valid:
        # Cena
        price = calculate_wellness_price(people=4, duration_hours=3)
        print(f"  Cena: {price} €")

        # Povzetek
        print("\n2b) Povzetek:")
        summary = format_wellness_summary("20.06.2026", "14:00", 3, 4)
        print(summary)

        # Ustvari rezervacijo
        print("\n2c) Ustvarjam rezervacijo...")
        res_id = rs.create_reservation(
            date="20.06.2026",
            people=4,
            reservation_type="wellness",
            time="14:00",
            wellness_duration_hours=3,
            name="Ana Kovač",
            phone="031987654",
            email="ana@example.com",
            source="test",
        )
        print(f"  ✅ Rezervacija ustvarjena! ID: {res_id}")

        reservation = rs.get_reservation(res_id)
        print(f"  Wellness trajanje: {reservation['wellness_duration_hours']}h")


def test_meal_reservation():
    print("\n" + "=" * 60)
    print("TEST 3: KULINARIKA (meal)")
    print("=" * 60)

    rs = ReservationService()

    # Validacija
    print("\n3a) Validacija: 28.06.2026 (sobota), 12:30, 15 oseb, degustacijsko kosilo")
    valid, error = validate_meal_rules(
        date_str="28.06.2026",
        time_str="12:30",
        people=15,
        meal_type="degustacijsko_kosilo",
    )
    print(f"  Valid: {valid}")

    if valid:
        # Povzetek
        print("\n3b) Povzetek:")
        summary = format_meal_summary("28.06.2026", 15, "degustacijsko_kosilo", "12:30")
        print(summary)

        # Ustvari rezervacijo
        print("\n3c) Ustvarjam rezervacijo...")
        res_id = rs.create_reservation(
            date="28.06.2026",
            people=15,
            reservation_type="meal",
            time="12:30",
            meal_type="degustacijsko_kosilo",
            name="Podjetje d.o.o.",
            phone="031555666",
            email="info@podjetje.si",
            note="Želimo vegetarijansko opcijo za 3 osebe",
            source="test",
        )
        print(f"  ✅ Rezervacija ustvarjena! ID: {res_id}")

        reservation = rs.get_reservation(res_id)
        print(f"  Meal type: {reservation['meal_type']}")


def test_package_reservation():
    print("\n" + "=" * 60)
    print("TEST 4: PAKETI (package)")
    print("=" * 60)

    rs = ReservationService()

    # Validacija
    print("\n4a) Validacija: Eko vikend, 05.07.2026, 2 osebi")
    valid, error = validate_package_rules(
        package_type="eko_vikend", date_str="05.07.2026", people=2
    )
    print(f"  Valid: {valid}")

    if valid:
        # Info o paketu
        package_info = get_package_info("eko_vikend")
        print(f"\n  Paket: {package_info['name']}")
        print(f"  Cena: {package_info['price']} €/oseba")
        print(f"  Noči: {package_info['nights']}")

        # Povzetek
        print("\n4b) Povzetek:")
        summary = format_package_summary("eko_vikend", "05.07.2026", 2)
        print(summary)

        # Ustvari rezervacijo
        print("\n4c) Ustvarjam rezervacijo...")
        total_price = package_info["price"] * 2
        res_id = rs.create_reservation(
            date="05.07.2026",
            people=2,
            reservation_type="package",
            nights=package_info["nights"],
            package_type="eko_vikend",
            package_price=total_price,
            name="Marko in Sara",
            phone="040111222",
            email="marko@example.com",
            source="test",
        )
        print(f"  ✅ Rezervacija ustvarjena! ID: {res_id}")

        reservation = rs.get_reservation(res_id)
        print(f"  Package type: {reservation['package_type']}")
        print(f"  Package price: {reservation['package_price']} €")


def test_read_all_reservations():
    print("\n" + "=" * 60)
    print("TEST 5: BRANJE VSE REZERVACIJ")
    print("=" * 60)

    rs = ReservationService()

    # Preberi vse rezervacije
    all_res = rs.read_reservations(limit=100)
    print(f"\nSkupaj rezervacij: {len(all_res)}")

    # Po tipih
    room_count = sum(1 for r in all_res if r["reservation_type"] == "room")
    wellness_count = sum(1 for r in all_res if r["reservation_type"] == "wellness")
    meal_count = sum(1 for r in all_res if r["reservation_type"] == "meal")
    package_count = sum(1 for r in all_res if r["reservation_type"] == "package")

    print(f"  - Room: {room_count}")
    print(f"  - Wellness: {wellness_count}")
    print(f"  - Meal: {meal_count}")
    print(f"  - Package: {package_count}")


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "KMETIJA URŠKA - TEST REZERVACIJ" + " " * 16 + "║")
    print("╚" + "=" * 58 + "╝")

    try:
        test_room_reservation()
        test_wellness_reservation()
        test_meal_reservation()
        test_package_reservation()
        test_read_all_reservations()

        print("\n" + "=" * 60)
        print("✅ VSI TESTI SO USPEŠNO ZAKLJUČENI!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ NAPAKA: {e}")
        import traceback

        traceback.print_exc()
