# Kmetija Urška - Rezervacijski Sistem

## 📋 Pregled

Kmetija Urška ima **4 vrste rezervacij**:

1. **Namestitev (room)** - Sobe in družinske suite
2. **Wellness** - Hiša dobrega počutja
3. **Kulinarika (meal)** - Degustacijska kosila/večerje, poslovni zajtrki/kosila
4. **Paketi (package)** - Vnaprej pripravljeni paketi

---

## 🛏️ 1. NAMESTITEV (room)

### Sobe

**5 dvoposteljnih sob:**
- MARIJA (2 osebi)
- TINKARA (2 osebi)
- CILKA (2 osebi)
- HANA (2 osebi)
- MANCA (2 osebi, prilagojena invalidom)

**2 družinski suiti:**
- URŠKA SUITE (4 osebe, z mini kuhinjico)
- ANA SUITE (4 osebe, z mini kuhinjico)

### Pravila

- ✅ **Odprto:** Vse dni v tednu (ni zaprtih dni)
- ⏱️ **Minimalno bivanje:**
  - Julij/Avgust: **5 noči**
  - Ostalo leto: **2 noči**
- 💰 **Cene (na osebo/noč):**
  - Nočitev z zajtrkom: **72 €**
  - Polpenzion (zajtrk + večerja): **87 €**
  - Polpenzion razširjen (julij/avg, + kosilo + bazen): **97 €**

### Primer uporabe

```python
from app.services.reservation_service import ReservationService

rs = ReservationService()

# Validacija
valid, error = rs.validate_room_rules("15.07.2026", 5)  # Julij = 5 noči min
if not valid:
    print(error)  # "V juliju in avgustu je minimalno bivanje 5 noči..."

# Preveri razpoložljivost
available, suggestion = rs.check_room_availability("15.07.2026", 5, 4, rooms=2)
if available:
    # Ustvari rezervacijo
    res_id = rs.create_reservation(
        date="15.07.2026",
        people=4,
        reservation_type="room",
        nights=5,
        rooms=2,
        room_preference="MARIJA,TINKARA",
        accommodation_type="polpenzion",
        name="Janez Novak",
        phone="041123456",
        email="janez@example.com",
        source="chat"
    )
    print(f"Rezervacija ustvarjena: ID {res_id}")
```

---

## 🧖 2. WELLNESS (Hiša dobrega počutja)

### Ponudba

- Parna in turška savna
- Masažni tuši
- Bazen z mehurčki
- Senena kopel
- Soba za počitek
- Zdravi zeliščni čaji

### Pravila

- ⏱️ **Obratovalni čas:** 10:00 - 20:00
- ⌛ **Trajanje:** 2, 3 ali 4 ure
- 👥 **Kapaciteta:** 1-10 oseb (nad 10 = telefonski dogovor)
- 💰 **Cena:** **30 € / 2 uri / osebo**

### Izračun cene

```
Cena = (30 € / 2h) × trajanje_ur × število_oseb

Primeri:
- 2 osebi, 2 uri = 30 € × 2 = 60 €
- 3 osebe, 3 ure = (30/2) × 3 × 3 = 135 €
- 4 osebe, 4 ure = (30/2) × 4 × 4 = 240 €
```

### Primer uporabe

```python
from app.services.urska_extensions import (
    validate_wellness_rules,
    calculate_wellness_price,
    format_wellness_summary
)

# Validacija
valid, error = validate_wellness_rules(
    date_str="20.06.2026",
    time_str="14:00",
    duration_hours=3,
    people=4
)

if valid:
    # Izračunaj ceno
    price = calculate_wellness_price(people=4, duration_hours=3)
    print(f"Cena: {price} €")  # 180 €

    # Ustvari rezervacijo
    res_id = rs.create_reservation(
        date="20.06.2026",
        people=4,
        reservation_type="wellness",
        time="14:00",
        wellness_duration_hours=3,
        name="Ana Kovač",
        phone="031987654",
        email="ana@example.com"
    )

    # Prikaz povzetka
    summary = format_wellness_summary("20.06.2026", "14:00", 3, 4)
    print(summary)
```

---

## 🍽️ 3. KULINARIKA (meal)

### Vrste

1. **Degustacijsko kosilo** (degustacijsko_kosilo)
2. **Degustacijska večerja** (degustacijska_vecerja)
3. **Poslovni zajtrk** (poslovni_zajtrk)
4. **Poslovni kosilo** (poslovni_kosilo)

### Pravila

- 📅 **Dnevi:** Petek, sobota, nedelja (glavni dnevi), ostalo po dogovoru
- 👥 **Kapaciteta:** 1-20 oseb
- ✅ **Obvezna rezervacija**
- 🌿 **80% lastnih ekoloških izdelkov**

### Primer uporabe

```python
from app.services.urska_extensions import (
    validate_meal_rules,
    format_meal_summary
)

# Validacija
valid, error = validate_meal_rules(
    date_str="28.06.2026",  # Sobota
    time_str="12:30",
    people=15,
    meal_type="degustacijsko_kosilo"
)

if valid:
    res_id = rs.create_reservation(
        date="28.06.2026",
        people=15,
        reservation_type="meal",
        time="12:30",
        meal_type="degustacijsko_kosilo",
        name="Podjetje d.o.o.",
        phone="031555666",
        email="info@podjetje.si",
        note="Želimo vegetarijansko opcijo za 3 osebe"
    )

    summary = format_meal_summary("28.06.2026", 15, "degustacijsko_kosilo", "12:30")
    print(summary)
```

---

## 🎁 4. PAKETI (package)

### Razpoložljivi paketi

| Paket | Cena/oseba | Noči | Opis |
|-------|------------|------|------|
| **eko_vikend** | 199 € | 2 | Eko vikend razvajanja |
| **dusa_telo** | 225 € | 2 | Vikend za dušo in telo |
| **urskin** | 215 € | 2 | Urškin vikend (+ vino) |
| **enodnevni** | 150 € | 1 | Enodnevni pobeg |
| **druzinski** | 734 € | 7 | Družinski paket (kmetija, bazen, MiniZoo) |

### Primer uporabe

```python
from app.services.urska_extensions import (
    validate_package_rules,
    get_package_info,
    format_package_summary
)

# Validacija
valid, error = validate_package_rules(
    package_type="eko_vikend",
    date_str="05.07.2026",
    people=2
)

if valid:
    package_info = get_package_info("eko_vikend")
    print(f"Paket: {package_info['name']}")
    print(f"Cena: {package_info['price']} €/oseba")
    print(f"Noči: {package_info['nights']}")

    # Ustvari rezervacijo
    res_id = rs.create_reservation(
        date="05.07.2026",
        people=2,
        reservation_type="package",
        nights=package_info["nights"],
        package_type="eko_vikend",
        package_price=package_info["price"] * 2,  # Skupna cena
        name="Marko in Sara",
        phone="040111222",
        email="marko@example.com"
    )

    summary = format_package_summary("eko_vikend", "05.07.2026", 2)
    print(summary)
```

---

## 🗄️ Baza podatkov

### Rezervacije tabela

Vsi tipi rezervacij se shranjujejo v isto tabelo `reservations`:

```sql
CREATE TABLE reservations (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    nights INTEGER,
    rooms INTEGER,
    people INTEGER NOT NULL,
    reservation_type TEXT NOT NULL,  -- "room", "wellness", "meal", "package"
    time TEXT,
    location TEXT,
    name TEXT,
    phone TEXT,
    email TEXT,
    note TEXT,
    status TEXT DEFAULT 'pending',  -- "pending", "confirmed", "rejected", "cancelled"
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,  -- "chat", "admin", "phone", "api"

    -- Urška-specific fields
    wellness_duration_hours INTEGER,  -- Za wellness: 2, 3, 4
    meal_type TEXT,  -- Za meal: "degustacijsko_kosilo", itd.
    package_type TEXT,  -- Za package: "eko_vikend", itd.
    package_price REAL,  -- Skupna cena paketa
    room_preference TEXT,  -- Za room: "MARIJA", "TINKARA,CILKA"
    accommodation_type TEXT,  -- Za room: "zajtrk", "polpenzion", "polpenzion_razširjen"

    -- Dodatna polja
    admin_notes TEXT,
    confirmed_at TEXT,
    confirmed_by TEXT,
    guest_message TEXT,
    country TEXT,
    kids TEXT,
    kids_small TEXT,
    confirm_via TEXT,
    event_type TEXT,
    special_needs TEXT
);
```

### Primeri query-jev

```python
# Samo wellness rezervacije
wellness_bookings = rs.read_reservations(
    reservation_type="wellness",
    status="confirmed",
    limit=50
)

# Samo paketi
packages = rs.read_reservations(
    reservation_type="package",
    limit=100
)

# Meal rezervacije za določen datum
from app.services.reservation_service import ReservationService
rs = ReservationService()
all_meals = rs.read_reservations(reservation_type="meal")
for meal in all_meals:
    if meal['date'] == '28.06.2026':
        print(f"{meal['people']} oseb, {meal['meal_type']}, {meal['time']}")
```

---

## 🔄 Workflow - Celoten primer

```python
from app.services.reservation_service import ReservationService
from app.services.urska_extensions import *

rs = ReservationService()

# 1. UPORABNIK: "Želim wellness za 4 osebe, 20. junija ob 14h, 3 ure"

# Validacija
valid, error = validate_wellness_rules("20.06.2026", "14:00", 3, 4)
if not valid:
    print(f"❌ Napaka: {error}")
    exit()

# Izračun cene
price = calculate_wellness_price(4, 3)

# Prikaz povzetka
summary = format_wellness_summary("20.06.2026", "14:00", 3, 4)
print(summary)

# Vprašaj za podatke
name = "Ana Kovač"
phone = "031123456"
email = "ana@example.com"

# Ustvari rezervacijo
res_id = rs.create_reservation(
    date="20.06.2026",
    people=4,
    reservation_type="wellness",
    time="14:00",
    wellness_duration_hours=3,
    name=name,
    phone=phone,
    email=email,
    source="chat"
)

print(f"✅ Rezervacija ustvarjena! ID: {res_id}")

# Pošlji email potrditev (integracija z email_service.py)
# send_wellness_confirmation(email, res_id, summary)
```

---

## 📊 Statistika

```python
# Število wellness rezervacij danes
wellness_today = rs.read_reservations(
    reservation_type="wellness",
    limit=100
)
today = datetime.now().strftime("%Y-%m-%d")
count = sum(1 for w in wellness_today if w['created_at'].startswith(today))
print(f"Wellness rezervacij danes: {count}")

# Najpogostejši paketi
packages = rs.read_reservations(reservation_type="package", limit=500)
from collections import Counter
package_types = [p['package_type'] for p in packages if p['package_type']]
popular = Counter(package_types).most_common(3)
print("Najpogostejši paketi:", popular)
```

---

## ✅ Status rezervacij

- **pending** = Čaka na potrditev
- **confirmed** = Potrjena
- **rejected** = Zavrnjena
- **cancelled** = Preklicana

```python
# Posodobi status
rs.update_status(reservation_id=123, new_status="confirmed")

# Ali uporabi update_reservation
rs.update_reservation(
    123,
    status="confirmed",
    confirmed_at=datetime.now().isoformat(),
    confirmed_by="Urška"
)
```

---

## 🚀 Integracija s chatbotom

AI chatbot lahko uporablja te funkcije za avtomatsko kreiranje rezervacij:

1. **Prepozna intent** → "wellness", "meal", "room", "package"
2. **Izvleče podatke** → datum, čas, število oseb, itd.
3. **Validira** → `validate_*_rules()`
4. **Ustvari rezervacijo** → `rs.create_reservation()`
5. **Pošlje email** → potrditev gostu in obvestilo admin

---

## 📞 Kontakt za pomoč

**Kmetija Urška**
- Tel: 031 249 812 / 03 759 04 10
- Email: urska@kmetija-urska.si
- Lokacija: Križevec 11A, 3206 Stranice

---

**Sistem implementiran:** Januar 2026
**Avtor:** Marko Šatler (z Claude Sonnet 4.5)
