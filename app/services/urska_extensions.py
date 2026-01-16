"""
Kmetija Urška - Razširitve za wellness, meal in package rezervacije
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple

# Import konstant iz reservation_service
from app.services.reservation_service import (
    WELLNESS_PRICE_PER_2H,
    WELLNESS_AVAILABLE_HOURS,
    MAX_MEAL_CAPACITY,
    MEAL_DAYS,
    PACKAGES,
)


def validate_wellness_rules(date_str: str, time_str: str, duration_hours: int, people: int) -> Tuple[bool, str]:
    """
    Validira pravila za wellness rezervacijo (Hiša dobrega počutja).

    Args:
        date_str: Datum v formatu DD.MM.YYYY
        time_str: Čas v formatu HH:MM
        duration_hours: Trajanje v urah (2, 3, 4)
        people: Število oseb

    Returns:
        (is_valid, error_message)
    """
    # Parse date
    try:
        visit_date = datetime.strptime(date_str.strip(), "%d.%m.%Y")
    except ValueError:
        return False, "Datum prosimo v obliki DD.MM.YYYY (npr. 15.6.2025)."

    # Check if date is in future
    today = datetime.now().date()
    if visit_date.date() < today:
        today_str = today.strftime("%d.%m.%Y")
        return False, f"Ta datum je že mimo (danes je {today_str}). Prosimo izberite datum v prihodnosti."

    # Parse time
    try:
        hour = int(time_str.split(":")[0])
        minute = int(time_str.split(":")[1]) if ":" in time_str else 0
    except (ValueError, IndexError):
        return False, "Uro prosimo v obliki HH:MM (npr. 14:00)."

    # Check if time is within available hours
    if hour not in WELLNESS_AVAILABLE_HOURS:
        return False, f"Wellness je na voljo med {WELLNESS_AVAILABLE_HOURS[0]}:00 in {WELLNESS_AVAILABLE_HOURS[-1]}:00."

    # Check duration
    if duration_hours not in [2, 3, 4]:
        return False, "Trajanje wellness obiska je lahko 2, 3 ali 4 ure."

    # Check end time doesn't exceed closing
    end_hour = hour + duration_hours
    if end_hour > WELLNESS_AVAILABLE_HOURS[-1] + 1:
        return False, f"Z izbranim trajanjem ({duration_hours}h) bi wellness presegel obratovalni čas. Prosimo izberite zgodnejšo uro."

    # Check people count
    if people < 1:
        return False, "Prosimo vnesite število oseb (min. 1)."
    if people > 10:
        return False, "Za skupine večje od 10 oseb nas prosimo kontaktirajte telefonsko na 031 249 812."

    return True, ""


def calculate_wellness_price(people: int, duration_hours: int) -> float:
    """
    Izračuna ceno wellness obiska.

    Cena: 30 €/2h/oseba
    """
    base_price = WELLNESS_PRICE_PER_2H  # 30 EUR za 2 uri
    price_per_hour = base_price / 2
    total = people * price_per_hour * duration_hours
    return round(total, 2)


def validate_meal_rules(date_str: str, time_str: str, people: int, meal_type: str) -> Tuple[bool, str]:
    """
    Validira pravila za meal rezervacijo (degustacijska kosila/večerje).

    Args:
        date_str: Datum v formatu DD.MM.YYYY
        time_str: Čas v formatu HH:MM (opcijsko)
        people: Število oseb
        meal_type: "degustacijsko_kosilo", "degustacijska_vecerja", "poslovni_zajtrk", "poslovni_kosilo"

    Returns:
        (is_valid, error_message)
    """
    # Parse date
    try:
        meal_date = datetime.strptime(date_str.strip(), "%d.%m.%Y")
    except ValueError:
        return False, "Datum prosimo v obliki DD.MM.YYYY (npr. 15.6.2025)."

    # Check if date is in future
    today = datetime.now().date()
    if meal_date.date() < today:
        today_str = today.strftime("%d.%m.%Y")
        return False, f"Ta datum je že mimo (danes je {today_str}). Prosimo izberite datum v prihodnosti."

    # Check day of week (petek, sobota, nedelja so glavni dnevi, ostalo po dogovoru)
    weekday = meal_date.weekday()
    if weekday not in MEAL_DAYS:
        return False, "Kulinarične storitve so predvsem ob petkih, sobotah in nedeljah. Za druge dni nas prosimo kontaktirajte na 031 249 812."

    # Check capacity
    if people < 1:
        return False, "Prosimo vnesite število oseb (min. 1)."
    if people > MAX_MEAL_CAPACITY:
        return False, f"Za degustacijska kosila/večerje sprejemamo do {MAX_MEAL_CAPACITY} oseb. Za večje skupine nas prosimo kontaktirajte."

    # Validate meal type
    valid_meal_types = ["degustacijsko_kosilo", "degustacijska_vecerja", "poslovni_zajtrk", "poslovni_kosilo"]
    if meal_type not in valid_meal_types:
        return False, f"Neveljavna vrsta obroka. Možnosti: {', '.join(valid_meal_types)}"

    return True, ""


def validate_package_rules(package_type: str, date_str: str, people: int) -> Tuple[bool, str]:
    """
    Validira pravila za paket rezervacijo.

    Args:
        package_type: "eko_vikend", "dusa_telo", "urskin", "enodnevni", "druzinski"
        date_str: Datum prihoda v formatu DD.MM.YYYY
        people: Število oseb

    Returns:
        (is_valid, error_message)
    """
    # Check if package exists
    if package_type not in PACKAGES:
        available = ", ".join(PACKAGES.keys())
        return False, f"Neveljaven paket. Možnosti: {available}"

    # Parse date
    try:
        arrival_date = datetime.strptime(date_str.strip(), "%d.%m.%Y")
    except ValueError:
        return False, "Datum prosimo v obliki DD.MM.YYYY (npr. 15.6.2025)."

    # Check if date is in future
    today = datetime.now().date()
    if arrival_date.date() < today:
        today_str = today.strftime("%d.%m.%Y")
        return False, f"Ta datum je že mimo (danes je {today_str}). Prosimo izberite datum v prihodnosti."

    # Check people count
    if people < 1:
        return False, "Prosimo vnesite število oseb (min. 1)."
    if people > 10:
        return False, "Za skupine večje od 10 oseb nas prosimo kontaktirajte na 031 249 812."

    package_info = PACKAGES[package_type]

    # Special validation for family package
    if package_type == "druzinski" and people < 2:
        return False, "Družinski paket je namenjen družinam (min. 2 osebi)."

    return True, ""


def get_package_info(package_type: str) -> Optional[dict]:
    """
    Vrne informacije o paketu.

    Returns:
        {"name": str, "price": float, "nights": int} or None
    """
    return PACKAGES.get(package_type)


def format_wellness_summary(date: str, time: str, duration_hours: int, people: int) -> str:
    """
    Formatira povzetek wellness rezervacije za prikaz uporabniku.
    """
    price = calculate_wellness_price(people, duration_hours)
    return f"""
🧖 **Wellness rezervacija - Hiša dobrega počutja**

📅 Datum: {date}
🕐 Čas: {time}
⏱️ Trajanje: {duration_hours} uri
👥 Število oseb: {people}
💰 Cena: {price} € ({WELLNESS_PRICE_PER_2H} €/2h/oseba)

Vključuje: parna in turška savna, masažni tuši, bazen z mehurčki, senena kopel, soba za počitek.
""".strip()


def format_meal_summary(date: str, people: int, meal_type: str, time: Optional[str] = None) -> str:
    """
    Formatira povzetek meal rezervacije za prikaz uporabniku.
    """
    meal_names = {
        "degustacijsko_kosilo": "Degustacijsko kosilo",
        "degustacijska_vecerja": "Degustacijska večerja",
        "poslovni_zajtrk": "Poslovni zajtrk",
        "poslovni_kosilo": "Poslovni kosilo",
    }
    meal_name = meal_names.get(meal_type, meal_type)

    time_info = f"\n🕐 Čas: {time}" if time else ""

    return f"""
🍽️ **Kulinarična rezervacija**

Vrsta: {meal_name}
📅 Datum: {date}{time_info}
👥 Število oseb: {people}

Vključuje sezonsko izbiro surovin z 80% lastnih ekoloških proizvodov.
Cena bo določena ob potrditvi rezervacije.
""".strip()


def format_package_summary(package_type: str, date: str, people: int) -> str:
    """
    Formatira povzetek package rezervacije za prikaz uporabniku.
    """
    package = PACKAGES[package_type]
    total_price = package["price"] * people

    return f"""
🎁 **Paket: {package['name']}**

📅 Datum prihoda: {date}
🌙 Število noči: {package['nights']}
👥 Število oseb: {people}
💰 Cena: {total_price} € ({package['price']} €/oseba)
""".strip()
