"""
Unit testi za Router/Intent detection
Poženi z: python3 -m pytest tests/test_router.py -v
"""

from app.services.chat_router import detect_router_intent, detect_info_intent

# ============================================
# BOOKING INTENT TESTI
# ============================================

def test_booking_room_typo_slovenian():
    """rad bi rezerveru sobo za 4 → BOOKING_ROOM"""
    result = detect_router_intent("rad bi rezerveru sobo za 4", {"step": None})
    assert result == "booking_room", f"Got: {result}"

def test_booking_table_typo():
    """rezr mizo 6 oseb → BOOKING_TABLE"""
    result = detect_router_intent("rezr mizo 6 oseb", {"step": None})
    assert result == "booking_table", f"Got: {result}"

def test_booking_room_english():
    """bookng room for 3 nights → BOOKING_ROOM"""
    result = detect_router_intent("bookng room for 3 nights", {"step": None})
    assert result == "booking_room", f"Got: {result}"

def test_booking_table_typo_tomorrow():
    """rezev mizo jutri ob 13:00 → BOOKING_TABLE"""
    result = detect_router_intent("rezev mizo jutri ob 13:00", {"step": None})
    assert result == "booking_table", f"Got: {result}"

def test_booking_room_german():
    """zimmer reserviern 2 kinder → BOOKING_ROOM"""
    result = detect_router_intent("zimmer reserviern 2 kinder", {"step": None})
    assert result == "booking_room", f"Got: {result}"

def test_booking_table_english():
    """buking table sunday 5 ppl → BOOKING_TABLE"""
    result = detect_router_intent("buking table sunday 5 ppl", {"step": None})
    assert result == "booking_table", f"Got: {result}"

def test_booking_room_german_typo_reserve():
    """rezerveirt zimmer → BOOKING_ROOM"""
    result = detect_router_intent("rezerveirt zimmer", {"step": None})
    assert result == "booking_room", f"Got: {result}"

def test_booking_table_typo_tabel():
    """tabel 4 osebe → BOOKING_TABLE"""
    result = detect_router_intent("tabel 4 osebe", {"step": None})
    assert result == "booking_table", f"Got: {result}"

# ============================================
# INFO INTENT TESTI (NE SME SPROŽITI BOOKING!)
# ============================================

def test_menu_typo_not_booking():
    """kaj je na jedilnku za koslo → INFO (ne booking!)"""
    info = detect_info_intent("kaj je na jedilnku za koslo")
    assert info == "jedilnik", f"Got: {info} - Menu vprašanje NE sme sprožiti booking!"

def test_menu_typo_menij():
    """kaj je na meniju jutri → INFO (ne booking!)"""
    info = detect_info_intent("kaj je na meniju jutri")
    assert info == "jedilnik", f"Got: {info}"

def test_klima_typo_info():
    """ali imate klima v sboah → INFO"""
    info = detect_info_intent("ali imate klima v sboah")
    assert info == "klima", f"Got: {info}"

# ============================================
# EDGE CASES
# ============================================

def test_incomplete_booking_trigger():
    """rezev (samo to, brez konteksta) → GENERAL (premalo info)"""
    result = detect_router_intent("rezev", {"step": None})
    assert result == "none", f"Got: {result} - Samo 'rezev' ne sme začeti booking!"

def test_info_during_active_booking():
    """Med aktivno rezervacijo: 'a imate wifi?' → INFO (ne prekine bookinga)"""
    router = detect_router_intent("a imate wifi?", {"step": "awaiting_nights"})
    info = detect_info_intent("a imate wifi?")
    assert router == "booking_continue", f"Router got: {router}"
    assert info == "wifi", f"Info got: {info}"


# ============================================
# NOVI INFO KLJUČI
# ============================================

def test_info_turizem():
    info = detect_info_intent("kaj priporočate za izlet na Pohorju?")
    assert info == "turizem", f"Got: {info}"


def test_info_kolesa():
    info = detect_info_intent("imate e-kolesa za izposojo?")
    assert info == "kolesa", f"Got: {info}"


def test_info_darilni_bon():
    info = detect_info_intent("ali imate darilne bone?")
    assert info == "darilni_boni", f"Got: {info}"


def test_info_vina():
    info = detect_info_intent("vinska karta?")
    assert info == "vina", f"Got: {info}"


# ============================================
# RUNNER
# ============================================

if __name__ == "__main__":
    tests = [
        test_booking_room_typo_slovenian,
        test_booking_table_typo,
        test_booking_room_english,
        test_booking_table_typo_tomorrow,
        test_booking_room_german,
        test_booking_table_english,
        test_menu_typo_not_booking,
        test_klima_typo_info,
        test_incomplete_booking_trigger,
        test_info_during_active_booking,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠️ {test.__name__}: ERROR - {e}")
            failed += 1
    
    print(f"\n{'='*40}")
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
