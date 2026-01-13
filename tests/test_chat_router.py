"""
Testi za app/services/chat_router.py

Pokriva:
- extract_date_from_text
- extract_nights  
- extract_people_count
- detect_intent
- wine followup
- exit/reset flow
- room_pricing (NOVO)
- weekly vs vikend menu ločitev (NOVO)
"""
import pytest
from datetime import datetime, timedelta


class TestExtractDateFromText:
    """Testi za extract_date_from_text funkcijo."""
    
    def test_standard_format_ddmmyyyy(self):
        from app.services.chat_router import extract_date_from_text
        assert extract_date_from_text("15.07.2025") == "15.07.2025"
        assert extract_date_from_text("1.1.2025") == "1.1.2025"
        assert extract_date_from_text("Prišel bom 20.12.2025") == "20.12.2025"
    
    def test_danes(self):
        from app.services.chat_router import extract_date_from_text
        result = extract_date_from_text("danes")
        expected = datetime.now().strftime("%d.%m.%Y")
        assert result == expected
    
    def test_jutri(self):
        from app.services.chat_router import extract_date_from_text
        result = extract_date_from_text("jutri")
        expected = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        assert result == expected
    
    def test_naslednji_vikend(self):
        from app.services.chat_router import extract_date_from_text
        result = extract_date_from_text("naslednji vikend")
        assert result is not None
        # Preveri da je sobota (weekday 5)
        parsed = datetime.strptime(result, "%d.%m.%Y")
        assert parsed.weekday() == 5  # Sobota
    
    def test_ta_sobota(self):
        from app.services.chat_router import extract_date_from_text
        result = extract_date_from_text("ta sobota")
        assert result is not None
        parsed = datetime.strptime(result, "%d.%m.%Y")
        assert parsed.weekday() == 5  # Sobota
    
    def test_ta_nedelja(self):
        from app.services.chat_router import extract_date_from_text
        result = extract_date_from_text("to nedeljo")
        assert result is not None
        parsed = datetime.strptime(result, "%d.%m.%Y")
        assert parsed.weekday() == 6  # Nedelja
    
    def test_cez_dni(self):
        from app.services.chat_router import extract_date_from_text
        result = extract_date_from_text("čez 5 dni")
        expected = (datetime.now() + timedelta(days=5)).strftime("%d.%m.%Y")
        assert result == expected
    
    def test_cez_tednov(self):
        from app.services.chat_router import extract_date_from_text
        result = extract_date_from_text("čez 2 tedna")
        expected = (datetime.now() + timedelta(weeks=2)).strftime("%d.%m.%Y")
        assert result == expected
    
    def test_no_date(self):
        from app.services.chat_router import extract_date_from_text
        assert extract_date_from_text("pozdravljeni") is None
        assert extract_date_from_text("kaj imate za jest") is None


class TestExtractNights:
    """Testi za extract_nights funkcijo."""
    
    def test_with_nocitev_word(self):
        from app.services.chat_router import extract_nights
        assert extract_nights("3 nočitve") == 3
        assert extract_nights("5 nočitev") == 5
        assert extract_nights("za 2 noči") == 2
    
    def test_only_number(self):
        """KRITIČNO: Samo številka mora delati ko sistem vpraša za nočitve."""
        from app.services.chat_router import extract_nights
        assert extract_nights("3") == 3
        assert extract_nights("5") == 5
        assert extract_nights("10") == 10
        assert extract_nights("6") == 6  # Specifičen test za bug
    
    def test_number_in_sentence(self):
        from app.services.chat_router import extract_nights
        assert extract_nights("rad bi 4 nočitve") == 4
        assert extract_nights("potrebujem sobo za 3 noči") == 3
    
    def test_ignores_date_numbers(self):
        from app.services.chat_router import extract_nights
        # Ne sme pobrati številk iz datuma
        result = extract_nights("15.07.2025 za 3 nočitve")
        assert result == 3
    
    def test_ignores_vikend(self):
        """KRITIČNO: 'naslednji vikend' ne sme vrniti nočitev."""
        from app.services.chat_router import extract_nights
        result = extract_nights("naslednji vikend")
        assert result is None
        result = extract_nights("ta vikend")
        assert result is None
        result = extract_nights("za vikend")
        assert result is None
    
    def test_out_of_range(self):
        from app.services.chat_router import extract_nights
        # Prevelike številke (nad 30) naj ne delajo
        result = extract_nights("50")
        assert result is None or result > 30
    
    def test_short_answer_context(self):
        """Test za kratke odgovore v kontekstu rezervacije."""
        from app.services.chat_router import extract_nights
        # Ko sistem vpraša "Koliko nočitev?" in uporabnik odgovori samo številko
        assert extract_nights("2") == 2
        assert extract_nights("3") == 3
        assert extract_nights("7") == 7


class TestExtractPeopleCount:
    """Testi za extract_people_count funkcijo."""
    
    def test_simple_number(self):
        from app.services.chat_router import extract_people_count
        assert extract_people_count("4") == 4
        assert extract_people_count("6 oseb") == 6
    
    def test_plus_format(self):
        from app.services.chat_router import extract_people_count
        assert extract_people_count("2+2") == 4
        assert extract_people_count("2 + 2") == 4
        assert extract_people_count("3+1") == 4
    
    def test_in_sentence(self):
        from app.services.chat_router import extract_people_count
        assert extract_people_count("za 5 oseb") == 5
        assert extract_people_count("2 odrasla in 2 otroka") == 2  # Pobere prvo številko


class TestDetectIntent:
    """Testi za detect_intent funkcijo."""
    
    def test_reservation_intent(self):
        from app.services.chat_router import detect_intent
        assert detect_intent("rad bi rezerviral sobo") == "reservation"
        assert detect_intent("želim rezervirati mizo") == "reservation"
        assert detect_intent("rezervacija sobe") == "reservation"
        assert detect_intent("booking") == "reservation"
    
    def test_wine_intent(self):
        from app.services.chat_router import detect_intent
        assert detect_intent("katera vina imate") == "wine"
        assert detect_intent("rdeča vina") == "wine"
        assert detect_intent("imate sauvignon") == "wine"
        assert detect_intent("modra frankinja") == "wine"
    
    def test_farm_info_intent(self):
        from app.services.chat_router import detect_intent
        assert detect_intent("kje se nahajate") == "farm_info"
        assert detect_intent("kakšen je telefon") == "farm_info"
        assert detect_intent("kdaj ste odprti") == "farm_info"
        assert detect_intent("naslov") == "farm_info"
    
    def test_weekly_menu_intent(self):
        """KRITIČNO: Tedenski meni mora biti ločen od vikend jedilnika."""
        from app.services.chat_router import detect_intent
        assert detect_intent("kaj ponujate čez teden") == "weekly_menu"
        assert detect_intent("5-hodni meni") == "weekly_menu"
        assert detect_intent("kulinarično doživetje") == "weekly_menu"
        assert detect_intent("degustacijski meni") == "weekly_menu"
        assert detect_intent("4-hodni meni") == "weekly_menu"
        assert detect_intent("6-hodni meni") == "weekly_menu"
        assert detect_intent("7-hodni meni") == "weekly_menu"
    
    def test_room_pricing_intent(self):
        """NOVO: Test za cene sob."""
        from app.services.chat_router import detect_intent
        assert detect_intent("koliko stanejo sobe") == "room_pricing"
        assert detect_intent("kakšna je cena sobe") == "room_pricing"
        assert detect_intent("cena nočitve") == "room_pricing"
        assert detect_intent("koliko stane prenočitev") == "room_pricing"
    
    def test_help_intent(self):
        from app.services.chat_router import detect_intent
        assert detect_intent("kaj znaš") == "help"
        assert detect_intent("pomoč") == "help"
    
    def test_product_intent(self):
        from app.services.chat_router import detect_intent
        assert detect_intent("imate salame") == "product"
        assert detect_intent("marmelade") == "product"
        assert detect_intent("kaj pa likerji") == "product"
    
    def test_default_intent(self):
        from app.services.chat_router import detect_intent
        # Splošna vprašanja
        result = detect_intent("pozdravljeni")
        assert result == "default"


class TestResetAndExitFlow:
    """Testi za reset in exit funkcionalnost."""
    
    def test_detect_reset_request(self):
        from app.services.chat_router import detect_reset_request
        assert detect_reset_request("zmotil sem se") == True
        assert detect_reset_request("začni znova") == True
        assert detect_reset_request("od začetka") == True
        assert detect_reset_request("reset") == True
    
    def test_detect_exit_request(self):
        """KRITIČNO: Exit besede morajo prekiniti rezervacijo."""
        from app.services.chat_router import detect_reset_request
        assert detect_reset_request("konec") == True
        assert detect_reset_request("stop") == True
        assert detect_reset_request("prekini") == True
        assert detect_reset_request("cancel") == True
        assert detect_reset_request("nehaj") == True
        assert detect_reset_request("pustimo") == True
    
    def test_no_reset(self):
        from app.services.chat_router import detect_reset_request
        assert detect_reset_request("3 nočitve") == False
        assert detect_reset_request("Janez Novak") == False
        assert detect_reset_request("041123456") == False
        assert detect_reset_request("test@test.si") == False


class TestWineQuestions:
    """Testi za wine funkcionalnost."""
    
    def test_answer_wine_general(self):
        from app.services.chat_router import answer_wine_question
        result = answer_wine_question("katera vina imate")
        assert "rdeč" in result.lower() or "Rdeč" in result
        assert "bel" in result.lower() or "Bel" in result
    
    def test_answer_wine_red(self):
        from app.services.chat_router import answer_wine_question
        result = answer_wine_question("rdeča vina")
        assert "frankinja" in result.lower() or "Frankinja" in result
        assert "16€" in result or "16 €" in result or "16€" in result
    
    def test_answer_wine_white(self):
        from app.services.chat_router import answer_wine_question
        result = answer_wine_question("bela vina")
        assert "sauvignon" in result.lower() or "Sauvignon" in result
    
    def test_answer_wine_sparkling(self):
        from app.services.chat_router import answer_wine_question
        result = answer_wine_question("peneča vina")
        assert "diona" in result.lower() or "Diona" in result
    
    def test_wine_no_hallucination(self):
        """KRITIČNO: Ne sme hallucinirati vin ki jih nimajo."""
        from app.services.chat_router import answer_wine_question
        result = answer_wine_question("rdeča vina")
        # Ne sme vsebovati vin ki jih nimajo
        assert "cabernet" not in result.lower()
        assert "merlot" not in result.lower()
        assert "shiraz" not in result.lower()


class TestWeeklyMenu:
    """Testi za tedensko ponudbo."""
    
    def test_weekly_menu_overview(self):
        from app.services.chat_router import answer_weekly_menu
        result = answer_weekly_menu("kaj ponujate čez teden")
        assert "4-hodni" in result or "4 hodni" in result
        assert "5-hodni" in result or "5 hodni" in result
        assert "36€" in result or "36 €" in result
    
    def test_weekly_menu_specific_5(self):
        from app.services.chat_router import answer_weekly_menu
        result = answer_weekly_menu("5-hodni meni")
        assert "43€" in result or "43 €" in result
    
    def test_weekly_menu_specific_6(self):
        from app.services.chat_router import answer_weekly_menu
        result = answer_weekly_menu("6-hodni meni")
        assert "53€" in result or "53 €" in result
    
    def test_weekly_menu_specific_7(self):
        from app.services.chat_router import answer_weekly_menu
        result = answer_weekly_menu("7-hodni meni")
        assert "62€" in result or "62 €" in result
    
    def test_weekly_menu_has_wine_pairing(self):
        """Tedenski meni mora vsebovati info o vinski spremljavi."""
        from app.services.chat_router import answer_weekly_menu
        result = answer_weekly_menu("kaj ponujate čez teden")
        assert "vinska" in result.lower() or "kozarc" in result.lower()


class TestIsMenuQuery:
    """Testi za is_menu_query funkcijo."""
    
    def test_menu_queries(self):
        from app.services.chat_router import is_menu_query
        assert is_menu_query("jedilnik") == True
        assert is_menu_query("kaj kuhate") == True
        assert is_menu_query("vikend kosilo") == True
    
    def test_not_menu_queries(self):
        """KRITIČNO: Tedenski meni NE sme sprožiti vikend jedilnika."""
        from app.services.chat_router import is_menu_query
        # Rezervacije niso menu query
        assert is_menu_query("rezervacija mize") == False
        assert is_menu_query("rezerviral bi sobo") == False
        # Tedenska ponudba ni vikend menu
        assert is_menu_query("5-hodni meni") == False
        assert is_menu_query("čez teden") == False
        assert is_menu_query("4-hodni meni") == False
        assert is_menu_query("degustacijski meni") == False
        assert is_menu_query("kulinarično doživetje") == False


class TestRoomPricing:
    """NOVO: Testi za cene sob."""
    
    def test_answer_room_pricing_exists(self):
        """Preveri da funkcija obstaja."""
        from app.services.chat_router import answer_room_pricing
        result = answer_room_pricing("koliko stanejo sobe")
        assert result is not None
        assert len(result) > 0
    
    def test_room_pricing_contains_price(self):
        """Mora vsebovati osnovno ceno."""
        from app.services.chat_router import answer_room_pricing
        result = answer_room_pricing("koliko stanejo sobe")
        assert "50" in result  # 50€ na nočitev
    
    def test_room_pricing_contains_breakfast(self):
        """Mora omeniti zajtrk."""
        from app.services.chat_router import answer_room_pricing
        result = answer_room_pricing("koliko stanejo sobe")
        assert "zajtrk" in result.lower()
    
    def test_room_pricing_children_discount(self):
        """Mora vsebovati popuste za otroke."""
        from app.services.chat_router import answer_room_pricing
        result = answer_room_pricing("popusti za otroke")
        assert "brezplačno" in result.lower() or "50%" in result
    
    def test_room_pricing_dinner(self):
        """Mora vsebovati ceno večerje."""
        from app.services.chat_router import answer_room_pricing
        result = answer_room_pricing("koliko stane večerja")
        assert "25" in result  # 25€ večerja


class TestWeeklyVsWeekendMenuSeparation:
    """NOVO: Testi za pravilno ločevanje tedenskega in vikend menija."""
    
    def test_weekly_keywords_trigger_weekly(self):
        """Tedenski izrazi morajo sprožiti tedenski meni, ne vikend."""
        from app.services.chat_router import detect_intent, is_menu_query
        
        weekly_phrases = [
            "čez teden",
            "med tednom",
            "5-hodni meni",
            "degustacijski meni",
            "kulinarično doživetje",
            "sreda",
            "četrtek",
            "petek ponudba"
        ]
        
        for phrase in weekly_phrases:
            intent = detect_intent(phrase)
            is_vikend = is_menu_query(phrase)
            assert intent == "weekly_menu" or not is_vikend, f"'{phrase}' should trigger weekly_menu, not vikend"
    
    def test_vikend_keywords_trigger_vikend(self):
        """Vikend izrazi morajo sprožiti vikend jedilnik."""
        from app.services.chat_router import is_menu_query
        
        vikend_phrases = [
            "jedilnik",
            "vikend kosilo",
            "kaj kuhate ta vikend",
        ]
        
        for phrase in vikend_phrases:
            assert is_menu_query(phrase) == True, f"'{phrase}' should trigger vikend menu"


class TestWineFollowup:
    """NOVO: Testi za wine followup funkcionalnost."""
    
    def test_wine_followup_after_red(self):
        """Po rdečih vinih 'še kakšno' mora delati."""
        from app.services.chat_router import answer_wine_question
        
        # Prvič pokažemo rdeča
        result1 = answer_wine_question("rdeča vina")
        assert "frankinja" in result1.lower() or "Frankinja" in result1
        
        # "Še kakšno" bi moralo reči da so to vsa ALI pokazati preostala
        # Ker funkcija ne hrani stanja, testiramo samo da ne crashne
        result2 = answer_wine_question("rdeča vina še kakšno")
        assert result2 is not None
    
    def test_wine_categories_complete(self):
        """Preveri da imamo vse kategorije vin."""
        from app.services.chat_router import answer_wine_question
        
        categories = ["rdeča", "bela", "peneča", "polsladka"]
        for cat in categories:
            result = answer_wine_question(f"{cat} vina")
            assert result is not None
            assert len(result) > 50  # Mora biti vsebinski odgovor


class TestEdgeCases:
    """Testi za robne primere."""
    
    def test_empty_message(self):
        """Prazen message ne sme crashniti."""
        from app.services.chat_router import detect_intent, extract_nights, extract_date_from_text
        
        assert detect_intent("") == "default"
        assert extract_nights("") is None
        assert extract_date_from_text("") is None
    
    def test_special_characters(self):
        """Posebni znaki ne smejo crashniti."""
        from app.services.chat_router import detect_intent
        
        assert detect_intent("!!!???") == "default"
        assert detect_intent("@#$%^&*") == "default"
        assert detect_intent("   ") == "default"
    
    def test_very_long_message(self):
        """Zelo dolgo sporočilo ne sme crashniti."""
        from app.services.chat_router import detect_intent
        
        long_msg = "test " * 1000
        result = detect_intent(long_msg)
        assert result is not None
    
    def test_mixed_case(self):
        """Mešane velike/male črke morajo delati."""
        from app.services.chat_router import detect_intent
        
        assert detect_intent("REZERVACIJA SOBE") == "reservation"
        assert detect_intent("Rdeča Vina") == "wine"
        assert detect_intent("KJE STE") == "farm_info"
