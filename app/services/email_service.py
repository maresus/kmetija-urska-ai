"""
Email Service za Urška AI Chatbot

STANJE: PRIPRAVLJEN, NEAKTIVEN
- Koda je pripravljena za pošiljanje emailov
- NI povezana z rezervacijskim flowom
- Ko boš pripravljen, aktiviraj v chat_router.py

AKTIVACIJA:
1. Nastavi SMTP credentials v .env
2. V chat_router.py odkomentiraj klic send_reservation_email()

SMTP NASTAVITVE (.env):
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=urska@kmetija-urska.si
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=urska@kmetija-urska.si
SMTP_FROM_NAME=Turistična kmetija Urška
ADMIN_EMAIL=urska@kmetija-urska.si
"""

import os
import smtplib
import resend
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime

# ============================================================
# KONFIGURACIJA - bere iz .env ali environment variables
# ============================================================

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "urska@kmetija-urska.si")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Turistična kmetija Urška")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "urska@kmetija-urska.si")
SMTP_SSL = os.getenv("SMTP_SSL", "").strip().lower() in {"1", "true", "yes"}
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

# Brand barve (enake kot WordPress)
BRAND_COLOR = "#7b5e3b"
BORDER_COLOR = "#e8e0d8"
BG_COLOR = "#f7f3ee"
TEXT_COLOR = "#1b1f1a"
MUTED_COLOR = "#6a6a6a"

# ============================================================
# HTML TEMPLATES
# ============================================================

def _email_wrapper(content: str) -> str:
    """Zavije vsebino v branded HTML template."""
    return f"""
<!DOCTYPE html>
<html lang="sl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Turistična kmetija Urška</title>
</head>
<body style="margin:0; padding:0; background:#faf9f7; font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
    <div style="max-width:620px; margin:0 auto; padding:24px 16px;">
        <!-- Header -->
        <div style="background:{BRAND_COLOR}; color:#fff; padding:18px 24px; border-radius:14px 14px 0 0; font-size:18px; font-weight:700; letter-spacing:.3px;">
            Turistična kmetija Urška
        </div>
        
        <!-- Content -->
        <div style="background:#fff; border:1px solid {BORDER_COLOR}; border-top:none; padding:24px; color:{TEXT_COLOR}; font-size:15px; line-height:1.6;">
            {content}
        </div>
        
        <!-- Footer -->
        <div style="background:{BG_COLOR}; border:1px solid {BORDER_COLOR}; border-top:none; border-radius:0 0 14px 14px; padding:16px 24px; color:{MUTED_COLOR}; font-size:12px;">
            Turistična kmetija Urška • <a href="https://kmetija-urska.si" style="color:{BRAND_COLOR}; text-decoration:none;">kmetija-urska.si</a>
            <br>Križevec 11 A, 3206 Stranice • 03 759 04 10 • 031 249 812
        </div>
    </div>
</body>
</html>
"""


def _kv_table(rows: Dict[str, str]) -> str:
    """Generira HTML tabelo s key-value pari."""
    html = f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%; border:1px solid {BORDER_COLOR}; border-radius:10px; overflow:hidden; font-size:14px; margin:16px 0;">
    """
    items = list(rows.items())
    for i, (key, value) in enumerate(items):
        is_last = i == len(items) - 1
        border_bottom = "0" if is_last else f"1px solid {BORDER_COLOR}"
        html += f"""
        <tr>
            <td style="background:#f9f7f5; padding:10px 12px; width:40%; border-bottom:{border_bottom}; color:#444;">
                <strong>{key}</strong>
            </td>
            <td style="padding:10px 12px; border-bottom:{border_bottom}; color:#111;">
                {value if value else '—'}
            </td>
        </tr>
        """
    html += "</table>"
    return html


# ============================================================
# EMAIL TEMPLATES
# ============================================================

def _guest_room_confirmation_html(data: Dict[str, Any]) -> str:
    """Email gostu - potrditev rezervacije SOBE."""
    content = f"""
    <p>Pozdravljeni <strong>{data.get('name', 'gost')}</strong>,</p>
    
    <p>Hvala za vaše povpraševanje. Posredujemo vam povzetek:</p>
    
    {_kv_table({
        'Datum prihoda': data.get('date', ''),
        'Število nočitev': str(data.get('nights', '')),
        'Število oseb': str(data.get('people', '')),
        'Otroci': f"{data.get('kids', '')} otrok ({data.get('kids_ages', '')})" if data.get('kids') else "",
        'Število sob': str(data.get('rooms', '')),
        'Soba': data.get('location', ''),
        'Kontakt': data.get('phone', ''),
        'Email': data.get('email', ''),
        'Opombe': data.get('note', ''),
    })}
    
    <p style="margin-top:18px;">
        <strong>Cena:</strong> 50€/nočitev na odraslo osebo<br>
        <strong>Zajtrk:</strong> vključen (8:00-9:00)<br>
        <strong>Večerja:</strong> 25€/oseba (po želji)<br>
        <strong>Otroci do 4 let:</strong> brezplačno<br>
        <strong>Otroci 4-12 let:</strong> 50% popust
    </p>
    
    <p style="margin-top:18px;">
        Prijava od 14:00, odjava do 10:00.<br>
        Večerja ob 18:00 (ponedeljki in torki brez večerij).
    </p>
    
    <p><strong>POMEMBNO:</strong> To je povpraševanje, ne potrjena rezervacija.<br>
    Potrditev boste prejeli po pregledu.</p>
    
    <p style="margin-top:18px; color:{MUTED_COLOR};">
        Rezervacijo bomo potrdili po preverjanju razpoložljivosti.<br>
        Za spremembe ali preklic nas kontaktirajte na 03 759 04 10 ali urska@kmetija-urska.si
    </p>
    """
    return _email_wrapper(content)


def _guest_table_confirmation_html(data: Dict[str, Any]) -> str:
    """Email gostu - potrditev rezervacije MIZE."""
    content = f"""
    <p>Pozdravljeni <strong>{data.get('name', 'gost')}</strong>,</p>
    
    <p>Hvala za vaše povpraševanje. Posredujemo vam povzetek:</p>
    
    {_kv_table({
        'Datum': data.get('date', ''),
        'Ura prihoda': data.get('time', ''),
        'Število oseb': str(data.get('people', '')),
        'Otroci': f"{data.get('kids', '')} otrok ({data.get('kids_ages', '')})" if data.get('kids') else "",
        'Jedilnica': data.get('location', ''),
        'Kontakt': data.get('phone', ''),
        'Email': data.get('email', ''),
        'Opombe': data.get('note', ''),
    })}
    
    <p style="margin-top:18px;">
        <strong>Cena kosila:</strong> 36€/oseba<br>
        <strong>Otroci 4-12 let:</strong> 50% popust
    </p>
    
    <p style="margin-top:18px;">
        Prosimo, najavite morebitne omejitve pri hrani (vege, brez glutena, alergije).<br>
        Poslujemo le z gotovino.
    </p>
    
    <p style="margin-top:18px;">
        Več o naši ponudbi: <a href="https://www.kmetija-urska.si/kulinarika/" style="color:{BRAND_COLOR};">kmetija-urska.si/kulinarika</a>
    </p>
    
    <p><strong>POMEMBNO:</strong> To je povpraševanje, ne potrjena rezervacija.<br>
    Potrditev boste prejeli po pregledu.</p>
    
    <p style="margin-top:18px; color:{MUTED_COLOR};">
        Rezervacijo bomo potrdili po preverjanju razpoložljivosti.<br>
        Za spremembe ali preklic nas kontaktirajte najkasneje 2 dni pred terminom.
    </p>
    """
    return _email_wrapper(content)


def _admin_new_reservation_html(data: Dict[str, Any], confirm_url: str = "", reject_url: str = "") -> str:
    """Email adminu - nova rezervacija čaka na obdelavo."""
    res_type = "Soba" if data.get('reservation_type') == 'room' else "Miza"
    
    rows = {
        'ID': f"#{data.get('id', '?')}",
        'Tip': res_type,
        'Ime': data.get('name', ''),
        'Email': data.get('email', ''),
        'Telefon': data.get('phone', ''),
        'Datum': data.get('date', ''),
    }
    
    if data.get('reservation_type') == 'room':
        rows['Nočitve'] = str(data.get('nights', ''))
        rows['Sobe'] = str(data.get('rooms', ''))
    else:
        rows['Ura'] = data.get('time', '')
        rows['Jedilnica'] = data.get('location', '')
    
    rows['Osebe'] = str(data.get('people', ''))
    rows['Vir'] = data.get('source', 'chatbot')
    
    if data.get('note'):
        rows['Opomba'] = data.get('note', '')
    
    # Gumbi za akcije (če so URL-ji podani)
    action_buttons = ""
    if confirm_url and reject_url:
        action_buttons = f"""
        <div style="margin-top:20px;">
            <a href="{confirm_url}" style="display:inline-block; background:{BRAND_COLOR}; color:#fff; padding:12px 20px; border-radius:10px; text-decoration:none; font-weight:700; margin-right:10px;">
                ✅ Potrdi
            </a>
            <a href="{reject_url}" style="display:inline-block; background:#b42318; color:#fff; padding:12px 20px; border-radius:10px; text-decoration:none; font-weight:700;">
                ❌ Zavrni
            </a>
        </div>
        """
    
    content = f"""
    <p><strong>Nova rezervacija čaka na obdelavo:</strong></p>
    
    {_kv_table(rows)}
    
    {action_buttons}
    
    <p style="margin-top:20px; color:{MUTED_COLOR}; font-size:13px;">
        Rezervacija ustvarjena: {datetime.now().strftime('%d.%m.%Y %H:%M')}<br>
        Odpri admin panel: <a href="http://localhost:8000/admin" style="color:{BRAND_COLOR};">Admin rezervacije</a>
    </p>
    """
    return _email_wrapper(content)


def _guest_confirmed_html(data: Dict[str, Any]) -> str:
    """Email gostu - rezervacija POTRJENA."""
    res_type = "sobe" if data.get('reservation_type') == 'room' else "mize"
    
    content = f"""
    <p>Pozdravljeni <strong>{data.get('name', 'gost')}</strong>,</p>
    
    <p>Z veseljem vam sporočamo, da je vaša rezervacija {res_type} <strong style="color:#22c55e;">POTRJENA</strong>.</p>
    
    {_kv_table({
        'Datum': data.get('date', ''),
        'Osebe': str(data.get('people', '')),
    })}
    
    <p style="margin-top:18px;">
        Veselimo se vašega obiska!
    </p>
    
    <p style="color:{MUTED_COLOR};">
        Za morebitne spremembe nas kontaktirajte na 03 759 04 10 ali urska@kmetija-urska.si
    </p>
    """
    return _email_wrapper(content)


def _guest_rejected_html(data: Dict[str, Any]) -> str:
    """Email gostu - rezervacija ZAVRNJENA."""
    content = f"""
    <p>Pozdravljeni <strong>{data.get('name', 'gost')}</strong>,</p>
    
    <p>Zahvaljujemo se za vaše prijazno povpraševanje.</p>
    
    <p>Žal so naše zmogljivosti v izbranem terminu že zapolnjene.</p>
    
    <p>Verjamemo, da se kmalu najde nova priložnost, da vas gostimo.</p>
    
    <p>Priporočamo, da preverite proste termine pri naših sosedih na eko kmetiji Pri Baronu.</p>
    
    <p style="margin-top:24px;">
        Lepo vas pozdravljamo,<br>
        <strong>Turistična kmetija Urška</strong>
    </p>
    """
    return _email_wrapper(content)


# ============================================================
# SEND FUNCTIONS
# ============================================================

def _send_email(to: str, subject: str, html_body: str) -> bool:
    """
    Pošlje email preko SMTP.
    Vrne True če uspešno, False če napaka.
    
    POMEMBNO: Ta funkcija trenutno NI AKTIVNA.
    Za aktivacijo nastavi SMTP credentials v .env
    """
    if RESEND_API_KEY:
        try:
            resend.api_key = RESEND_API_KEY
            resend.Emails.send(
                {
                    "from": RESEND_FROM_EMAIL,
                    "to": to,
                    "subject": subject,
                    "html": html_body,
                }
            )
            print(f"[EMAIL] Resend poslano: {subject} -> {to}")
            return True
        except Exception as e:
            print(f"[EMAIL] Resend napaka: {e}")
            return False

    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL] SMTP ni konfiguriran. Email NI poslan: {subject}")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg['To'] = to
        msg['Reply-To'] = SMTP_FROM_EMAIL
        
        # Plain text verzija
        text_body = "Sporočilo od Turistične kmetije Urška. Za ogled odprite v brskalniku."
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        
        # HTML verzija
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # Pošlji
        # Port 465 = SSL, Port 587 = TLS (ali prisilno preko SMTP_SSL)
        if SMTP_PORT == 465 or SMTP_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        
        print(f"[EMAIL] Poslano: {subject} -> {to}")
        return True
        
    except Exception as e:
        print(f"[EMAIL] Napaka pri pošiljanju: {e}")
        return False


# ============================================================
# PUBLIC API
# ============================================================

def send_guest_confirmation(data: Dict[str, Any]) -> bool:
    """
    Pošlje potrditveni email gostu.
    
    Args:
        data: Podatki rezervacije (name, email, date, people, ...)
    
    Returns:
        True če uspešno poslano
    """
    email = data.get('email')
    if not email:
        return False
    
    if data.get('reservation_type') == 'room':
        html = _guest_room_confirmation_html(data)
        subject = "Vaše povpraševanje za sobo – Urška"
    else:
        html = _guest_table_confirmation_html(data)
        subject = "Vaše povpraševanje za mizo – Urška"
    
    return _send_email(email, subject, html)


def send_admin_notification(data: Dict[str, Any], confirm_url: str = "", reject_url: str = "") -> bool:
    """
    Pošlje obvestilo adminu o novi rezervaciji.
    
    Args:
        data: Podatki rezervacije
        confirm_url: URL za potrditev (opcijsko)
        reject_url: URL za zavrnitev (opcijsko)
    
    Returns:
        True če uspešno poslano
    """
    res_type = "sobe" if data.get('reservation_type') == 'room' else "mize"
    subject = f"Nova rezervacija {res_type} – {data.get('name', 'Neznano')}"
    
    html = _admin_new_reservation_html(data, confirm_url, reject_url)
    return _send_email(ADMIN_EMAIL, subject, html)


def send_reservation_confirmed(data: Dict[str, Any]) -> bool:
    """Pošlje gostu obvestilo da je rezervacija POTRJENA."""
    email = data.get('email')
    if not email:
        return False
    
    html = _guest_confirmed_html(data)
    subject = "Rezervacija potrjena – Urška"
    return _send_email(email, subject, html)


def send_reservation_rejected(data: Dict[str, Any]) -> bool:
    """Pošlje gostu obvestilo da je rezervacija ZAVRNJENA."""
    email = data.get('email')
    if not email:
        return False
    
    html = _guest_rejected_html(data)
    subject = "Obvestilo o rezervaciji – Urška"
    return _send_email(email, subject, html)


def send_custom_message(to_email: str, subject: str, body: str) -> bool:
    """Pošlje poljubno sporočilo gostu."""
    if not to_email:
        return False
    html = _email_wrapper(f"<div style='white-space:pre-wrap;line-height:1.7'>{body}</div>")
    return _send_email(to_email, subject, html)


# ============================================================
# TEST FUNCTION
# ============================================================

def test_email_templates():
    """
    Testna funkcija - generira HTML emaile brez pošiljanja.
    Uporabi za pregled dizajna.
    
    Uporaba:
        from app.services.email_service import test_email_templates
        test_email_templates()
    """
    test_data = {
        'id': 123,
        'name': 'Janez Novak',
        'email': 'janez@example.com',
        'phone': '041 123 456',
        'date': '15.07.2025',
        'nights': 3,
        'rooms': 1,
        'people': 4,
        'location': 'Soba ALJAŽ',
        'reservation_type': 'room',
        'source': 'chatbot',
        'note': 'Potrebujemo otroško posteljico',
    }
    
    print("=" * 60)
    print("TEST: Guest Room Confirmation")
    print("=" * 60)
    html = _guest_room_confirmation_html(test_data)
    
    # Shrani v datoteko za pregled
    with open('/tmp/test_email_guest_room.html', 'w') as f:
        f.write(html)
    print("Shranjeno v: /tmp/test_email_guest_room.html")
    
    print("\n" + "=" * 60)
    print("TEST: Admin Notification")
    print("=" * 60)
    html = _admin_new_reservation_html(test_data, "http://localhost/confirm", "http://localhost/reject")
    
    with open('/tmp/test_email_admin.html', 'w') as f:
        f.write(html)
    print("Shranjeno v: /tmp/test_email_admin.html")
    
    # Test za mizo
    test_data['reservation_type'] = 'table'
    test_data['time'] = '13:00'
    test_data['location'] = 'Jedilnica Pri peči'
    del test_data['nights']
    del test_data['rooms']
    
    print("\n" + "=" * 60)
    print("TEST: Guest Table Confirmation")
    print("=" * 60)
    html = _guest_table_confirmation_html(test_data)
    
    with open('/tmp/test_email_guest_table.html', 'w') as f:
        f.write(html)
    print("Shranjeno v: /tmp/test_email_guest_table.html")
    
    print("\n✅ Vse email template generirane. Odpri HTML datoteke v brskalniku za pregled.")


if __name__ == "__main__":
    test_email_templates()
