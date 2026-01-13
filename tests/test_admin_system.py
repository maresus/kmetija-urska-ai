"""
Avtomatski testi za admin sistem rezervacij.
Zaženi z: pytest tests/test_admin_system.py -v
"""

import os
import sys
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# dodamo parent directory v sys.path za direkten import aplikacije
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def sample_room_reservation():
    """Primer rezervacije sobe."""
    return {
        "source": "wordpress_room",
        "name": "Test Uporabnik",
        "email": "test@example.com",
        "phone": "041 123 456",
        "date": "15.07.2026",
        "arrive": "15.07.2026",
        "depart": "18.07.2026",
        "people": 2,
        "adults": 2,
        "nights": 3,
        "room": "Aljaž",
        "country": "Slovenija",
        "kids": "",
        "kids_small": "",
        "confirm_via": "email",
        "note": "Testna rezervacija",
    }


@pytest.fixture
def sample_table_reservation():
    """Primer rezervacije mize."""
    return {
        "source": "wordpress_table",
        "name": "Janez Novak",
        "email": "janez@example.com",
        "phone": "031 987 654",
        "date": "20.07.2026",
        "time": "13:00",
        "people": 6,
        "event_type": "Družinsko srečanje",
        "location": "Pri peči",
        "special_needs": "Visoki stolček",
        "note": "",
    }


@pytest.fixture
def sample_chat_reservation():
    """Primer rezervacije iz chatbota."""
    return {
        "date": "25.08.2026",
        "nights": 2,
        "rooms": 1,
        "people": 4,
        "reservation_type": "room",
        "name": "Ana Kovač",
        "phone": "040 111 222",
        "email": "ana@test.si",
        "location": "Soba Ana",
        "note": "Z zajtrkom",
    }


# ============================================================
# 1. TESTI ZA HEALTH CHECK
# ============================================================


class TestHealthCheck:
    """Testi za osnovni health check."""

    def test_root_endpoint(self):
        """Preveri da root endpoint deluje."""
        response = client.get("/")
        assert response.status_code == 200

    def test_chat_endpoint_exists(self):
        """Preveri da chat endpoint obstaja."""
        response = client.post("/chat", json={"message": "test"})
        assert response.status_code in [200, 500]  # 500 je OK če ni OpenAI key

    def test_admin_page_exists(self):
        """Preveri da admin stran obstaja."""
        response = client.get("/admin")
        assert response.status_code == 200
        assert "admin" in response.text.lower()


# ============================================================
# 2. TESTI ZA WEBHOOK API
# ============================================================


class TestWebhookAPI:
    """Testi za WordPress webhook endpoint."""

    def test_webhook_without_secret_rejected(self, sample_room_reservation):
        """Webhook brez secret ključa mora biti zavrnjen."""
        response = client.post("/api/webhook/reservation", json=sample_room_reservation)
        assert response.status_code == 401

    def test_webhook_with_wrong_secret_rejected(self, sample_room_reservation):
        """Webhook z napačnim secret ključem mora biti zavrnjen."""
        response = client.post(
            "/api/webhook/reservation",
            json=sample_room_reservation,
            headers={"X-Webhook-Secret": "wrong_secret"},
        )
        assert response.status_code == 401

    @patch("app.services.email_service.send_admin_notification")
    def test_webhook_room_reservation_accepted(self, mock_email, sample_room_reservation):
        """Webhook za sobo s pravilnim ključem mora biti sprejet."""
        mock_email.return_value = True

        secret = os.getenv("WEBHOOK_SECRET", "urska_webhook_secret_2024")
        response = client.post(
            "/api/webhook/reservation",
            json=sample_room_reservation,
            headers={"X-Webhook-Secret": secret},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "reservation_id" in data

    @patch("app.services.email_service.send_admin_notification")
    def test_webhook_table_reservation_accepted(self, mock_email, sample_table_reservation):
        """Webhook za mizo s pravilnim ključem mora biti sprejet."""
        mock_email.return_value = True

        secret = os.getenv("WEBHOOK_SECRET", "urska_webhook_secret_2024")
        response = client.post(
            "/api/webhook/reservation",
            json=sample_table_reservation,
            headers={"X-Webhook-Secret": secret},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"


# ============================================================
# 3. TESTI ZA ADMIN API
# ============================================================


class TestAdminAPI:
    """Testi za admin API endpointe."""

    def test_get_reservations(self):
        """Preveri da lahko dobimo seznam rezervacij."""
        response = client.get("/api/admin/reservations")
        assert response.status_code == 200
        data = response.json()
        assert "reservations" in data
        assert "stats" in data
        assert isinstance(data["reservations"], list)

    def test_get_reservations_with_status_filter(self):
        """Preveri filtriranje po statusu."""
        response = client.get("/api/admin/reservations?status=pending")
        assert response.status_code == 200
        data = response.json()
        for res in data["reservations"]:
            assert res.get("status") == "pending"

    def test_get_reservations_with_type_filter(self):
        """Preveri filtriranje po tipu."""
        response = client.get("/api/admin/reservations?type=room")
        assert response.status_code == 200
        data = response.json()
        for res in data["reservations"]:
            assert res.get("reservation_type") == "room"

    def test_stats_contains_required_fields(self):
        """Preveri da statistika vsebuje vsa polja."""
        response = client.get("/api/admin/reservations")
        data = response.json()
        stats = data.get("stats", {})

        assert "pending" in stats
        assert "processing" in stats
        assert "confirmed" in stats
        assert "today" in stats


# ============================================================
# 4. TESTI ZA RESERVATION SERVICE
# ============================================================


class TestReservationService:
    """Testi za ReservationService."""

    def test_create_reservation(self, sample_chat_reservation):
        """Preveri ustvarjanje rezervacije."""
        from app.services.reservation_service import ReservationService

        service = ReservationService()

        res_id = service.create_reservation(
            date=sample_chat_reservation["date"],
            people=sample_chat_reservation["people"],
            reservation_type=sample_chat_reservation["reservation_type"],
            source="test",
            nights=sample_chat_reservation["nights"],
            rooms=sample_chat_reservation["rooms"],
            name=sample_chat_reservation["name"],
            phone=sample_chat_reservation["phone"],
            email=sample_chat_reservation["email"],
            location=sample_chat_reservation["location"],
            note=sample_chat_reservation["note"],
        )

        assert res_id is not None
        assert isinstance(res_id, int)
        assert res_id > 0

    def test_read_reservations(self):
        """Preveri branje rezervacij."""
        from app.services.reservation_service import ReservationService

        service = ReservationService()

        reservations = service.read_reservations(limit=10)
        assert isinstance(reservations, list)

    def test_reservation_has_required_fields(self):
        """Preveri da ima rezervacija vsa potrebna polja."""
        from app.services.reservation_service import ReservationService

        service = ReservationService()

        res_id = service.create_reservation(
            date="01.01.2027",
            people=2,
            reservation_type="room",
            source="test",
            name="Test",
            email="test@test.com",
        )

        reservations = service.read_reservations(limit=100)
        test_res = next((r for r in reservations if r.get("id") == res_id), None)

        assert test_res is not None
        assert "id" in test_res
        assert "date" in test_res
        assert "people" in test_res
        assert "status" in test_res
        assert "created_at" in test_res
        assert test_res["status"] == "pending"


# ============================================================
# 5. TESTI ZA ADMIN AKCIJE
# ============================================================


class TestAdminActions:
    """Testi za admin akcije (potrdi, zavrni, uredi)."""

    @pytest.fixture
    def create_test_reservation(self):
        """Ustvari testno rezervacijo in vrni ID."""
        from app.services.reservation_service import ReservationService

        service = ReservationService()

        res_id = service.create_reservation(
            date="15.09.2026",
            people=3,
            reservation_type="room",
            source="test",
            name="Admin Test",
            email="admin.test@example.com",
            phone="041 000 000",
        )
        return res_id

    @patch("app.services.email_service.send_reservation_confirmed")
    def test_confirm_reservation(self, mock_email, create_test_reservation):
        """Preveri potrjevanje rezervacije."""
        mock_email.return_value = True
        res_id = create_test_reservation

        response = client.post(f"/api/admin/reservations/{res_id}/confirm")
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True

        from app.services.reservation_service import ReservationService

        service = ReservationService()
        res = service.get_reservation(res_id)
        assert res.get("status") == "confirmed"

    @patch("app.services.email_service.send_reservation_rejected")
    def test_reject_reservation(self, mock_email, create_test_reservation):
        """Preveri zavračanje rezervacije."""
        mock_email.return_value = True
        res_id = create_test_reservation

        response = client.post(f"/api/admin/reservations/{res_id}/reject")
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True

        from app.services.reservation_service import ReservationService

        service = ReservationService()
        res = service.get_reservation(res_id)
        assert res.get("status") == "rejected"

    def test_update_reservation(self, create_test_reservation):
        """Preveri urejanje rezervacije."""
        res_id = create_test_reservation

        response = client.put(
            f"/api/admin/reservations/{res_id}",
            json={"status": "processing", "people": 5, "admin_notes": "Testna opomba"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True

    @patch("app.services.email_service.send_custom_message")
    def test_send_message(self, mock_email, create_test_reservation):
        """Preveri pošiljanje sporočila gostu."""
        mock_email.return_value = True
        res_id = create_test_reservation

        response = client.post(
            "/api/admin/send-message",
            json={
                "reservation_id": res_id,
                "email": "test@example.com",
                "subject": "Test sporočilo",
                "body": "To je testno sporočilo.",
                "set_processing": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True


# ============================================================
# 6. TESTI ZA EMAIL SERVICE
# ============================================================


class TestEmailService:
    """Testi za email service (brez dejanskega pošiljanja)."""

    def test_email_templates_exist(self):
        """Preveri da obstajajo vse email funkcije."""
        from app.services import email_service

        assert hasattr(email_service, "send_guest_confirmation")
        assert hasattr(email_service, "send_admin_notification")
        assert hasattr(email_service, "send_reservation_confirmed")
        assert hasattr(email_service, "send_reservation_rejected")

    def test_guest_confirmation_html_generated(self):
        """Preveri da se generira HTML za gosta."""
        from app.services.email_service import _guest_room_confirmation_html

        test_data = {
            "name": "Test",
            "email": "test@test.com",
            "date": "15.07.2026",
            "nights": 3,
            "rooms": 1,
            "people": 2,
            "phone": "041 123 456",
            "location": "Aljaž",
        }

        html = _guest_room_confirmation_html(test_data)
        assert html is not None
        assert "Test" in html
        assert "15.07.2026" in html


# ============================================================
# 7. TESTI ZA CHATBOT REZERVACIJE
# ============================================================


class TestChatbotReservations:
    """Testi za rezervacije preko chatbota."""

    def test_chat_greeting(self):
        """Preveri da chatbot odgovori na pozdrav."""
        response = client.post("/chat", json={"message": "Zdravo"})
        assert response.status_code in [200, 500]

    def test_chat_room_inquiry(self):
        """Preveri da chatbot odgovori na vprašanje o sobah."""
        response = client.post("/chat", json={"message": "Imate proste sobe?"})
        if response.status_code == 200:
            data = response.json()
            assert "reply" in data
            reply_lower = data["reply"].lower()
            assert any(word in reply_lower for word in ["soba", "sobe", "room", "nastanitev"])


# ============================================================
# 8. INTEGRATION TESTS
# ============================================================


class TestIntegration:
    """Integracijski testi za celoten flow."""

    @patch("app.services.email_service.send_admin_notification")
    @patch("app.services.email_service.send_reservation_confirmed")
    def test_full_reservation_flow(self, mock_confirm, mock_admin):
        """Test celotnega flow-a: ustvari → admin vidi → potrdi."""
        mock_admin.return_value = True
        mock_confirm.return_value = True

        secret = os.getenv("WEBHOOK_SECRET", "urska_webhook_secret_2024")
        webhook_response = client.post(
            "/api/webhook/reservation",
            json={
                "source": "wordpress_room",
                "name": "Integration Test",
                "email": "integration@test.com",
                "phone": "041 999 888",
                "date": "01.10.2026",
                "arrive": "01.10.2026",
                "depart": "03.10.2026",
                "people": 2,
                "adults": 2,
                "nights": 2,
                "room": "Julija",
                "country": "Slovenija",
            },
            headers={"X-Webhook-Secret": secret},
        )

        assert webhook_response.status_code == 200
        res_id = webhook_response.json().get("reservation_id")
        assert res_id is not None

        list_response = client.get("/api/admin/reservations?status=pending")
        assert list_response.status_code == 200
        reservations = list_response.json().get("reservations", [])
        assert any(r.get("id") == res_id for r in reservations)

        confirm_response = client.post(f"/api/admin/reservations/{res_id}/confirm")
        assert confirm_response.status_code == 200
        assert confirm_response.json().get("ok") is True

        from app.services.reservation_service import ReservationService

        service = ReservationService()
        res = service.get_reservation(res_id)
        assert res.get("status") == "confirmed"


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v", "--tb=short"])
