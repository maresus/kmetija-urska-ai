"""
Admin Router for Kovačnik V2 AI
Simplified version without IMAP polling - V2 doesn't need email sync.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from app.services.email_service import (
    send_custom_message,
    send_reservation_confirmed,
    send_reservation_rejected,
)
from app.services.reservation_service import ROOMS, TOTAL_TABLE_CAPACITY, ReservationService

router = APIRouter(tags=["admin"])
service = ReservationService()

# Admin auth token from env (if empty = dev mode, no auth required)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def verify_admin(token: str = Header(None, alias="X-Admin-Token"), t: str = Query(None)):
    """Verify admin token from header or query param."""
    if not ADMIN_TOKEN:
        return  # No token configured = allow all (dev mode)
    provided = token or t
    if provided != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Neveljaven admin token")


ROOM_IDS = {r["id"] for r in ROOMS}


def _log(event: str, **kwargs) -> None:
    """Preprost log za admin API klice."""
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        extras = " ".join([f"{k}={v}" for k, v in kwargs.items() if v is not None])
        print(f"[ADMIN API] {ts} {event} {extras}")
    except Exception:
        pass


def _ensure_subject_tag(reservation_id: Optional[int], subject: str) -> str:
    if not reservation_id:
        return subject or ""
    tag = f"Rezervacija #{reservation_id}"
    if tag.lower() in (subject or "").lower():
        return subject
    if subject:
        return f"{tag} - {subject}"
    return tag


def _normalize_room_id(room: Optional[str]) -> Optional[str]:
    if not room:
        return None
    upper = room.strip().upper()
    for rid in ROOM_IDS:
        if rid in upper or upper in rid:
            return rid
    return None


def _parse_ddmmyyyy(date_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y")
    except Exception:
        return None


def _reservation_days(date_str: str, nights: Optional[int]) -> list[datetime]:
    nights_int = 1
    try:
        nights_int = int(nights or 1)
    except Exception:
        import re
        m = re.search(r"\d+", str(nights or ""))
        if m:
            try:
                nights_int = int(m.group(0))
            except Exception:
                nights_int = 1
    if nights_int <= 0:
        nights_int = 1
    start = _parse_ddmmyyyy(date_str)
    if not start:
        return []
    return [start + timedelta(days=i) for i in range(nights_int)]


def _room_conflicts(reservation_id: int, room_id: str, date_str: str, nights: Optional[int]) -> list[str]:
    """Vrne seznam datumov (dd.mm.yyyy) kjer je soba že zasedena."""
    occupied: list[str] = []
    days = _reservation_days(date_str, nights)
    if not days:
        return occupied
    other_reservations = service.read_reservations(limit=1000, reservation_type="room")
    for r in other_reservations:
        if r.get("id") == reservation_id:
            continue
        status = r.get("status")
        if status not in {"confirmed", "processing"}:
            continue
        other_room = _normalize_room_id(r.get("location"))
        if other_room != room_id:
            continue
        other_days = _reservation_days(r.get("date", ""), r.get("nights"))
        overlaps = {d.date() for d in days} & {d.date() for d in other_days}
        if overlaps:
            occupied.extend(sorted({d.strftime("%d.%m.%Y") for d in overlaps}))
    return occupied


# ============================================================
# PYDANTIC MODELS
# ============================================================

class ReservationUpdate(BaseModel):
    status: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    people: Optional[int] = None
    nights: Optional[int] = None
    location: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    event_type: Optional[str] = None
    special_needs: Optional[str] = None
    admin_notes: Optional[str] = None
    kids: Optional[str] = None
    kids_small: Optional[str] = None


class SendMessageRequest(BaseModel):
    reservation_id: int
    email: str
    subject: str
    body: str
    set_processing: bool = True


class ConfirmReservationRequest(BaseModel):
    room: Optional[str] = None
    location: Optional[str] = None


class AdminCreateReservation(BaseModel):
    date: str
    people: int
    reservation_type: str
    source: str = "admin"
    status: Optional[str] = None
    nights: Optional[int] = None
    rooms: Optional[int] = None
    time: Optional[str] = None
    location: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    note: Optional[str] = None
    admin_notes: Optional[str] = None
    kids: Optional[str] = None
    kids_small: Optional[str] = None
    event_type: Optional[str] = None
    special_needs: Optional[str] = None


class KnowledgeFeedbackRequest(BaseModel):
    question: str
    suggestion: str


# ============================================================
# STATIC FILE ROUTES
# ============================================================

@router.get("/admin", response_class=HTMLResponse)
def admin_page() -> HTMLResponse:
    """Postreže statično datoteko admin UI (static/admin.html)."""
    html_path = Path("static/admin.html")
    if not html_path.exists():
        return HTMLResponse("<h1>Admin UI manjka (static/admin.html)</h1>", status_code=500)
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/admin/conversations", response_class=HTMLResponse)
def admin_conversations_page() -> HTMLResponse:
    """Postreže statično datoteko za pogovore."""
    html_path = Path("static/conversations.html")
    if not html_path.exists():
        return HTMLResponse("<h1>Conversations UI manjka</h1>", status_code=500)
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/admin/inquiries", response_class=HTMLResponse)
def admin_inquiries_page() -> HTMLResponse:
    """Postreže statično datoteko za povpraševanja."""
    html_path = Path("static/inquiries.html")
    if not html_path.exists():
        return HTMLResponse("<h1>Inquiries UI manjka</h1>", status_code=500)
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/admin/mize", response_class=HTMLResponse)
def admin_mize_page() -> HTMLResponse:
    """Poenostavljen admin panel samo za mize (za Barbaro)."""
    html_path = Path("static/admin_mize.html")
    if not html_path.exists():
        return HTMLResponse("<h1>Admin Mize UI manjka (static/admin_mize.html)</h1>", status_code=500)
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


# ============================================================
# CONVERSATIONS API
# ============================================================

@router.get("/api/admin/conversations")
def get_conversations(limit: int = 200, needs_followup_only: bool = False):
    """Vrne zadnje pogovore za admin pregled."""
    _log("conversations", limit=limit, needs_followup_only=needs_followup_only)
    conversations = service.get_conversations(limit=limit, needs_followup_only=needs_followup_only)
    stats = {
        "total": len(conversations),
        "followup": len([c for c in conversations if c.get("needs_followup")]),
    }
    return {"conversations": conversations, "stats": stats}


@router.get("/api/admin/conversations/session/{session_id}")
def get_conversations_by_session(session_id: str, limit: int = 200):
    """Vrne pogovor za posamezen session_id."""
    _log("conversations_session", session_id=session_id, limit=limit)
    conversations = service.get_conversations_by_session(session_id=session_id, limit=limit)
    return {"session_id": session_id, "conversations": conversations, "total": len(conversations)}


@router.get("/api/admin/conversations/recent")
def get_recent_conversations(hours: int = 1):
    """Vrne pogovore iz zadnjih N ur, grupirane po session-ih."""
    _log("conversations_recent", hours=hours)
    sessions = service.get_recent_sessions(hours=hours)
    return {
        "hours": hours,
        "sessions": sessions,
        "total_sessions": len(sessions),
        "total_messages": sum(len(s.get("messages", [])) for s in sessions),
    }


@router.get("/api/admin/notify/conversations")
def notify_new_conversations(hours: int = 1):
    """Pošlje email obvestilo o novih pogovorih. Za cron job ali brskalnik."""
    _log("notify_conversations", hours=hours)
    sessions = service.get_recent_sessions(hours=hours)

    if not sessions:
        return {"sent": False, "reason": "Ni novih pogovorov"}

    # Pripravi HTML vsebino za email
    from app.services.email_service import send_admin_notification_email

    html_content = _build_conversations_email_html(sessions, hours)
    subject = f"Chatbot: {len(sessions)} {'nov pogovor' if len(sessions) == 1 else 'novih pogovorov'} v zadnji uri"

    success = send_admin_notification_email(subject=subject, html_content=html_content)
    return {"sent": success, "sessions_count": len(sessions)}


@router.get("/api/admin/notify/daily-report")
def notify_daily_report(hours: int = 0, mode: str = ""):
    """Poročilo vseh botov.
    mode=daily  → celodnevno (prejšnji dan 00:00-23:59), vedno pošlje
    mode=hourly → zadnja ura, pošlje SAMO če total > 0
    brez mode   → od zadnjega emaila naprej (staro obnašanje)
    """
    import requests as _req
    from datetime import date, datetime, timedelta
    from app.services.email_service import send_admin_notification_email

    now = datetime.now()
    today_str = now.strftime("%-d. %-m. %Y")

    if mode == "daily":
        # Celoten prejšnji dan
        yesterday = now.date() - timedelta(days=1)
        cutoff_dt = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
        cutoff_end = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)
        period_from = cutoff_dt.strftime("%-d. %-m.")
        period_to = period_from
        report_type = "daily"
    elif mode == "hourly":
        # Zadnja ura natančno
        cutoff_dt = now - timedelta(hours=1)
        cutoff_end = now
        period_from = cutoff_dt.strftime("%H:%M")
        period_to = now.strftime("%H:%M")
        report_type = "hourly"
    else:
        # Fallback: od zadnjega emaila naprej ali hours param
        last_sent = service.get_last_report_time("daily")
        if last_sent:
            try:
                cutoff_dt = datetime.strptime(last_sent.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                cutoff_dt = now - timedelta(hours=max(hours, 8))
            period_from = cutoff_dt.strftime("%d.%m %H:%M")
        elif hours > 0:
            cutoff_dt = now - timedelta(hours=hours)
            period_from = cutoff_dt.strftime("%H:%M")
        else:
            cutoff_dt = now - timedelta(hours=8)
            period_from = cutoff_dt.strftime("%H:%M")
        cutoff_end = now
        period_to = now.strftime("%H:%M")
        report_type = "daily"

    hours_since = max(1, int((now - cutoff_dt).total_seconds() / 3600) + 1)
    cutoff = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _fetch_json(url, timeout=10):
        try:
            r = _req.get(url, timeout=timeout)
            return r.json() if r.ok else None
        except Exception:
            return None

    def _bot_section(title, emoji, color, border, bg, sessions_html, count, note=""):
        empty = f'<tr><td style="padding:12px 0;font-size:13px;color:#aaa;font-style:italic;">Ni novih pogovorov v tem obdobju.</td></tr>'
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
          <tr>
            <td style="padding-bottom:10px;border-bottom:3px solid {border};">
              <span style="font-size:16px;font-weight:700;color:{color};">{emoji}&nbsp;{title}</span>
            </td>
            <td align="right" style="padding-bottom:10px;border-bottom:3px solid {border};">
              <span style="background:{border};color:#fff;border-radius:12px;padding:2px 10px;font-size:12px;font-weight:700;">{count}</span>
            </td>
          </tr>
          {sessions_html if sessions_html else empty}
        </table>"""

    def _session_block(idx, time_str, msg_count, messages, accent, bg):
        """En pogovor - vse sporočila vidna, chat bubble stil."""
        rows = f"""
          <tr>
            <td colspan="2" style="padding:10px 0 6px 0;">
              <span style="font-size:11px;font-weight:700;color:{accent};text-transform:uppercase;letter-spacing:1px;">
                Pogovor #{idx}
              </span>
              <span style="font-size:11px;color:#aaa;margin-left:8px;">{time_str} &middot; {msg_count} sporočil</span>
            </td>
          </tr>"""

        for m in messages:
            u = (m.get("user") or "").strip()
            b = (m.get("bot") or "").strip()
            role = m.get("role", "")
            if role == "user":
                u, b = (m.get("content") or "").strip(), ""
            elif role == "assistant":
                u, b = "", (m.get("content") or "").strip()

            if u:
                rows += f"""
          <tr>
            <td width="20" style="padding:3px 6px 3px 0;vertical-align:top;font-size:13px;color:#888;">👤</td>
            <td style="padding:3px 0;">
              <div style="background:#ffffff;border:1px solid #e0e0e0;border-radius:0 8px 8px 8px;padding:8px 12px;font-size:13px;color:#222;line-height:1.5;">{u}</div>
            </td>
          </tr>"""
            if b:
                rows += f"""
          <tr>
            <td width="20" style="padding:3px 6px 8px 0;vertical-align:top;font-size:13px;color:{accent};">🤖</td>
            <td style="padding:3px 0 8px 0;">
              <div style="background:{bg};border:1px solid {accent}22;border-radius:8px 8px 8px 0;padding:8px 12px;font-size:13px;color:#444;line-height:1.6;">{b}</div>
            </td>
          </tr>"""

        rows += '<tr><td colspan="2" style="padding:0 0 4px 0;border-bottom:1px dashed #eee;"></td></tr>'
        return rows

    # ── 1. KOVAČNIK ───────────────────────────────────────────────────────────
    kov_sessions = service.get_recent_sessions(since=cutoff)
    kov_html = ""
    for i, s in enumerate(kov_sessions, 1):
        msgs = s.get("messages", [])
        kov_html += _session_block(i, s.get("first_message_at","")[:16], len(msgs), msgs, "#7b5e3b", "#fdf8f3")

    def _norm_ts(ts: str) -> str:
        """Normalize timestamp to 'YYYY-MM-DD HH:MM:SS' for consistent comparison."""
        return (ts or "").replace("T", " ")[:19]

    # ── 2. SV ANA ─────────────────────────────────────────────────────────────
    sv_sessions_raw = _fetch_json("https://web-production-13aea.up.railway.app/admin/sessions") or []
    sv_sessions = [s for s in sv_sessions_raw if _norm_ts(s.get("last_msg","") or s.get("started","")) >= cutoff]
    sv_html = ""
    for i, s in enumerate(sv_sessions, 1):
        sid = s.get("session_id","")
        msgs_raw = _fetch_json(f"https://web-production-13aea.up.railway.app/admin/sessions/{sid}") or []
        sv_html += _session_block(i, s.get("started","")[:16], len(msgs_raw), msgs_raw, "#3a7ca5", "#f0f6fb")

    # ── 3. SPOZNAJ AI ─────────────────────────────────────────────────────────
    sp_sessions_raw = _fetch_json("https://web-production-ce7f8.up.railway.app/admin/sessions") or []
    sp_sessions = [s for s in sp_sessions_raw if _norm_ts(s.get("last_msg","") or s.get("started","")) >= cutoff]
    sp_html = ""
    for i, s in enumerate(sp_sessions, 1):
        sid = s.get("session_id","")
        msgs_raw = _fetch_json(f"https://web-production-ce7f8.up.railway.app/admin/sessions/{sid}") or []
        sp_html += _session_block(i, s.get("started","")[:16], len(msgs_raw), msgs_raw, "#5b3fa5", "#f5f2fb")

    # ── 4. POD GORO ───────────────────────────────────────────────────────────
    pg_data = _fetch_json(f"https://kmetija-pod-goro-production.up.railway.app/api/admin/conversations?hours={hours_since}") or {}
    pg_convs = [c for c in pg_data.get("conversations", []) if c.get("created_at","") >= cutoff]
    pg_sessions_map = {}
    for c in pg_convs:
        sid = c.get("session_id","unknown")
        if sid not in pg_sessions_map:
            pg_sessions_map[sid] = {"time": c.get("created_at","")[:16], "msgs": []}
        pg_sessions_map[sid]["msgs"].append({"user": c.get("user_message",""), "bot": c.get("bot_response","")})
    pg_html = ""
    for i, (sid, s) in enumerate(pg_sessions_map.items(), 1):
        pg_html += _session_block(i, s["time"], len(s["msgs"]), s["msgs"], "#2d7a4f", "#f0faf4")

    # ── 5. ZDRAVSTVENI ────────────────────────────────────────────────────────
    zd_data = _fetch_json(f"https://zdravstvenicenter-production.up.railway.app/api/admin/conversations?hours={hours_since}") or {}
    zd_convs = [c for c in zd_data.get("conversations", []) if c.get("created_at","") >= cutoff]
    zd_sessions_map = {}
    for c in zd_convs:
        sid = c.get("session_id","unknown")
        if sid not in zd_sessions_map:
            zd_sessions_map[sid] = {"time": c.get("created_at","")[:16], "msgs": []}
        zd_sessions_map[sid]["msgs"].append({"user": c.get("user_message",""), "bot": c.get("bot_response","")})
    zd_html = ""
    for i, (sid, s) in enumerate(zd_sessions_map.items(), 1):
        zd_html += _session_block(i, s["time"], len(s["msgs"]), s["msgs"], "#c0392b", "#fdf5f4")

    # ── Skupaj ────────────────────────────────────────────────────────────────
    totals = {
        "kovacnik": len(kov_sessions),
        "sv_ana": len(sv_sessions),
        "spoznaj_ai": len(sp_sessions),
        "pod_goro": len(pg_sessions_map),
        "zdravstveni": len(zd_sessions_map),
    }
    grand_total = sum(totals.values())

    # Hourly mode: ne pošiljaj če ni nič novega
    if mode == "hourly" and grand_total == 0:
        return {"sent": False, **totals, "total": 0, "reason": "no_new_conversations"}

    bots_meta = [
        ("🏡 Domačija Kovačnik", totals["kovacnik"], "#7b5e3b", "#c19a6b"),
        ("🏛️ Občina Sveta Ana",  totals["sv_ana"],   "#3a7ca5", "#5b9fc8"),
        ("💡 Spoznaj AI",         totals["spoznaj_ai"],"#5b3fa5","#8b6fd4"),
        ("🌲 Kmetija Pod Goro",   totals["pod_goro"], "#2d7a4f", "#4da870"),
        ("🏥 Zdravstveni center", totals["zdravstveni"],"#c0392b","#e05c4a"),
    ]

    summary_rows = ""
    for name, cnt, clr, _ in bots_meta:
        bar_w = max(4, int(cnt / max(grand_total,1) * 180)) if grand_total else 4
        status_icon = "✅" if cnt > 0 else "⬜"
        summary_rows += f"""
        <tr>
          <td style="padding:5px 10px;font-size:13px;color:{clr};font-weight:600;">{status_icon} {name}</td>
          <td style="padding:5px 10px;">
            <div style="background:{clr};height:8px;width:{bar_w}px;border-radius:4px;display:inline-block;opacity:0.8;"></div>
          </td>
          <td style="padding:5px 10px;font-size:13px;font-weight:700;color:#333;text-align:right;">{cnt}</td>
        </tr>"""

    # Header glede na mode
    if mode == "daily":
        header_title = f"📊 Dnevno poročilo — {period_from}"
        header_sub = f"Skupaj pogovorov včeraj: {grand_total}"
        subject = f"📊 Dnevno poročilo {period_from} — {grand_total} pogovorov"
    elif mode == "hourly":
        header_title = f"🔔 Novi pogovori — {period_from}–{period_to}"
        header_sub = f"V zadnji uri: {grand_total} novih pogovorov"
        subject = f"🔔 Novi pogovori ({grand_total}) — {period_from}–{period_to}"
    else:
        header_title = f"📊 Poročilo botov"
        header_sub = f"{today_str} · od {period_from} do {period_to}"
        subject = f"📊 Boti — {grand_total} pogovorov | {today_str}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:20px;background:#f0f0f0;font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:700px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.1);">

  <!-- HEADER -->
  <div style="background:linear-gradient(135deg,#1a2a1a,#2d4a2d);padding:22px 26px;">
    <div style="color:#fff;font-size:20px;font-weight:700;">{header_title}</div>
    <div style="color:#a8c8a8;font-size:13px;margin-top:4px;">{header_sub}</div>
  </div>

  <!-- STATISTIKA -->
  <div style="padding:18px 26px;background:#fafafa;border-bottom:2px solid #eee;">
    <div style="font-size:11px;color:#999;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Statistika po botih</div>
    <table cellpadding="0" cellspacing="0" width="100%">
      {summary_rows}
      <tr style="border-top:2px solid #ddd;margin-top:4px;">
        <td style="padding:8px 10px;font-size:14px;font-weight:800;color:#1a2a1a;">SKUPAJ</td>
        <td></td>
        <td style="padding:8px 10px;font-size:18px;font-weight:800;color:#1a2a1a;text-align:right;">{grand_total}</td>
      </tr>
    </table>
  </div>

  <!-- BOT SECTIONS -->
  <div style="padding:8px 26px 26px 26px;">
    {_bot_section("Domačija Kovačnik","🏡","#7b5e3b","#c19a6b","#fdf8f3", kov_html, totals["kovacnik"])}
    {_bot_section("Občina Sveta Ana","🏛️","#3a7ca5","#5b9fc8","#f0f6fb", sv_html, totals["sv_ana"])}
    {_bot_section("Spoznaj AI","💡","#5b3fa5","#8b6fd4","#f5f2fb", sp_html, totals["spoznaj_ai"])}
    {_bot_section("Kmetija Pod Goro","🌲","#2d7a4f","#4da870","#f0faf4", pg_html, totals["pod_goro"])}
    {_bot_section("Zdravstveni center","🏥","#c0392b","#e05c4a","#fdf5f4", zd_html, totals["zdravstveni"])}
  </div>

  <!-- FOOTER -->
  <div style="background:#f5f5f5;padding:12px 26px;border-top:1px solid #e8e8e8;font-size:11px;color:#bbb;text-align:center;">
    spoznaj-ai.si &nbsp;·&nbsp; {today_str} {now.strftime("%H:%M")} &nbsp;·&nbsp;
    <a href="https://kovacnik-ai-production.up.railway.app/admin" style="color:#7b5e3b;">Admin panel</a>
  </div>
</div>
</body></html>"""

    success = send_admin_notification_email(subject=subject, html_content=html)
    if success and mode != "hourly":
        service.save_report_time(report_type)
    return {"sent": success, **totals, "total": grand_total}

def _build_conversations_email_html(sessions: list, hours: int) -> str:
    """Zgradi HTML vsebino za email obvestilo o pogovorih."""
    html = f"""
    <h2 style="margin-top:0;">Novi pogovori ({len(sessions)})</h2>
    <p style="color:#666;">V zadnjih {hours} {'uri' if hours == 1 else 'urah'}</p>
    """

    for i, session in enumerate(sessions, 1):
        messages = session.get("messages", [])
        first_msg = messages[0] if messages else {}
        first_question = first_msg.get("user", "—")[:100]

        html += f"""
        <div style="background:#f9f7f5; border:1px solid #e8e0d8; border-radius:10px; padding:16px; margin:16px 0;">
            <div style="font-weight:600; color:#7b5e3b; margin-bottom:8px;">
                Pogovor #{i} ({len(messages)} sporočil)
            </div>
            <div style="font-size:14px; color:#333; margin-bottom:12px;">
                <strong>Prvo vprašanje:</strong> {first_question}{"..." if len(first_msg.get("user", "")) > 100 else ""}
            </div>
            <details style="cursor:pointer;">
                <summary style="color:#7b5e3b; font-weight:600;">Prikaži celoten pogovor</summary>
                <div style="margin-top:12px; padding:12px; background:#fff; border-radius:8px;">
        """

        for msg in messages:
            user_msg = msg.get("user", "")
            bot_msg = msg.get("bot", "")
            html += f"""
                <div style="margin-bottom:12px;">
                    <div style="background:#e3f2fd; padding:8px 12px; border-radius:8px; margin-bottom:4px;">
                        <strong>Uporabnik:</strong> {user_msg}
                    </div>
                    <div style="background:#f5f5f5; padding:8px 12px; border-radius:8px;">
                        <strong>Bot:</strong> {bot_msg[:500]}{"..." if len(bot_msg) > 500 else ""}
                    </div>
                </div>
            """

        html += """
                </div>
            </details>
        </div>
        """

    html += f"""
    <p style="margin-top:24px; text-align:center;">
        <a href="https://kovacnik-ai-production.up.railway.app/admin"
           style="display:inline-block; background:#7b5e3b; color:#fff; padding:12px 24px; border-radius:8px; text-decoration:none; font-weight:600;">
            Odpri Admin Panel
        </a>
    </p>
    """

    return html


@router.get("/api/admin/inquiries")
def get_inquiries(limit: int = 200, status: Optional[str] = None):
    _log("inquiries", limit=limit, status=status)
    inquiries = service.get_inquiries(limit=limit, status=status)
    return {"inquiries": inquiries}


@router.get("/api/admin/usage_stats")
def get_usage_stats():
    _log("usage_stats")
    return service.get_usage_stats()


@router.get("/api/admin/question_stats")
def get_question_stats(limit: int = 10):
    _log("question_stats", limit=limit)
    return {"questions": service.get_top_questions(limit=limit)}


@router.get("/api/admin/lost_intents")
def get_lost_intents(limit: int = 10):
    _log("lost_intents", limit=limit)
    return {"items": service.get_lost_intents(limit=limit)}


@router.get("/api/admin/funnel_stats")
def get_funnel_stats(days: int = 30):
    _log("funnel_stats", days=days)
    return service.get_funnel_stats(days=days)


@router.post("/api/admin/knowledge_feedback")
def create_knowledge_feedback(payload: KnowledgeFeedbackRequest):
    _log("knowledge_feedback", question=payload.question[:60] if payload.question else "")
    feedback_id = service.create_knowledge_feedback(payload.question.strip(), payload.suggestion.strip())
    if not feedback_id:
        raise HTTPException(status_code=400, detail="Neveljaven predlog.")
    return {"ok": True, "id": feedback_id}


# ============================================================
# RESERVATIONS API
# ============================================================

@router.get("/api/admin/reservations")
def get_reservations(
    limit: int = 100,
    status: Optional[str] = None,
    type: Optional[str] = None,
    source: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Vrne seznam rezervacij s filtri ter osnovno statistiko."""
    _log("reservations", limit=limit, status=status, type=type, source=source, date_from=date_from, date_to=date_to)
    reservations = service.read_reservations(limit=limit, status=status, reservation_type=type, source=source)

    def _parse_date(date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        date_str = date_str.replace(" ", "")
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        return None

    if date_from or date_to:
        start = _parse_date(date_from) if date_from else None
        end = _parse_date(date_to) if date_to else None
        filtered = []
        for r in reservations:
            days = _reservation_days(r.get("date", ""), r.get("nights"))
            if not days:
                filtered.append(r)
                continue
            overlaps = False
            for d in days:
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                overlaps = True
                break
            if overlaps:
                filtered.append(r)
        reservations = filtered

    all_res = service.read_reservations(limit=1000)
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    stats = {
        "pending": len([r for r in all_res if r.get("status") == "pending"]),
        "processing": len([r for r in all_res if r.get("status") == "processing"]),
        "confirmed": len([r for r in all_res if r.get("status") == "confirmed"]),
        "today": len([r for r in all_res if str(r.get("created_at", "")).startswith(today_prefix)]),
    }

    return {"reservations": reservations, "stats": stats}


@router.put("/api/admin/reservations/{reservation_id}")
def update_reservation(reservation_id: int, data: ReservationUpdate):
    """Posodobi rezervacijo."""
    existing = service.get_reservation(reservation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rezervacija ni najdena")
    res_type = existing.get("reservation_type")
    location = data.location
    valid_rooms = {"", None, "ALJAZ", "JULIJA", "ANA"}
    valid_tables = {"Pri peči", "Pri vrtu"}
    if res_type == "room" and location is not None and location not in valid_rooms:
        raise HTTPException(status_code=400, detail="Neveljavna soba")
    if res_type == "table" and location is not None and location not in valid_tables:
        raise HTTPException(status_code=400, detail="Neveljavna jedilnica")
    ok = service.update_reservation(
        reservation_id,
        status=data.status,
        date=data.date,
        time=data.time,
        people=data.people,
        nights=data.nights,
        location=data.location,
        name=data.name,
        email=data.email,
        phone=data.phone,
        event_type=data.event_type,
        special_needs=data.special_needs,
        admin_notes=data.admin_notes,
        kids=data.kids,
        kids_small=data.kids_small,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Rezervacija ni najdena")
    return {"ok": True}


@router.patch("/api/admin/reservations/{reservation_id}")
def patch_reservation(reservation_id: int, data: ReservationUpdate):
    """Partial update rezervacije."""
    fields = {
        "status": data.status,
        "admin_notes": data.admin_notes,
        "kids": data.kids,
    }
    if data.status == "confirmed":
        fields["confirmed_at"] = datetime.now().isoformat()
    ok = service.update_reservation(reservation_id, **fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Rezervacija ni najdena")
    return {"ok": True}


@router.post("/api/admin/reservations/{reservation_id}/confirm")
def confirm_reservation(reservation_id: int, data: Optional[ConfirmReservationRequest] = None):
    """Potrdi rezervacijo, preveri zasedenost sobe in pošlje email gostu."""
    res = service.get_reservation(reservation_id)
    if not res:
        raise HTTPException(status_code=404, detail="Rezervacija ni najdena")
    requested_room = _normalize_room_id((data.room if data else None) or res.get("location"))
    requested_location = (data.location if data else None) or res.get("location")
    if res.get("reservation_type") == "room":
        if not requested_room:
            raise HTTPException(status_code=400, detail="Soba mora biti izbrana.")
        conflicts = _room_conflicts(reservation_id, requested_room, res.get("date", ""), res.get("nights"))
        if conflicts:
            return {"success": False, "warning": f"Soba {requested_room} je zasedena: {', '.join(conflicts)}"}
    else:
        requested_room = None

    service.update_reservation(
        reservation_id,
        status="confirmed",
        confirmed_at=datetime.now().isoformat(),
        confirmed_by=os.getenv("ADMIN_EMAIL", "info@kovacnik.com"),
        location=requested_room or requested_location,
    )
    res = service.get_reservation(reservation_id) or res
    send_reservation_confirmed(res)
    subject = _ensure_subject_tag(reservation_id, "Potrditev rezervacije")
    service.add_reservation_message(
        reservation_id=reservation_id,
        direction="outbound",
        subject=subject,
        body="Rezervacija potrjena.",
        from_email=os.getenv("ADMIN_EMAIL", "info@kovacnik.com"),
        to_email=res.get("email") or "",
        message_id=None,
    )
    return {"success": True, "email_sent": True, "room": requested_room or requested_location}


@router.post("/api/admin/reservations/{reservation_id}/reject")
def reject_reservation(reservation_id: int):
    """Zavrne rezervacijo in pošlje email gostu."""
    res = service.get_reservation(reservation_id)
    if not res:
        raise HTTPException(status_code=404, detail="Rezervacija ni najdena")
    service.update_reservation(reservation_id, status="rejected")
    res = service.get_reservation(reservation_id) or res
    send_reservation_rejected(res)
    subject = _ensure_subject_tag(reservation_id, "Zavrnjena rezervacija")
    service.add_reservation_message(
        reservation_id=reservation_id,
        direction="outbound",
        subject=subject,
        body="Rezervacija zavrnjena.",
        from_email=os.getenv("ADMIN_EMAIL", "info@kovacnik.com"),
        to_email=res.get("email") or "",
        message_id=None,
    )
    return {"success": True, "email_sent": True}


# ============================================================
# EMAIL LINK HANDLERS (GET) - za klik iz emaila
# ============================================================

def _email_action_html(title: str, message: str, success: bool = True) -> str:
    """Generira HTML stran za prikaz po kliku na email link."""
    color = "#22c55e" if success else "#ef4444"
    icon = "+" if success else "x"
    return f"""
    <!DOCTYPE html>
    <html lang="sl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - Domačija Kovačnik</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #f7f3ee; margin: 0; padding: 40px 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; padding: 40px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
            .icon {{ font-size: 64px; margin-bottom: 20px; color: {color}; }}
            h1 {{ color: #7b5e3b; margin: 0 0 16px; font-size: 24px; }}
            p {{ color: #666; line-height: 1.6; margin: 0 0 24px; }}
            a {{ display: inline-block; margin-top: 24px; color: #7b5e3b; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">{icon}</div>
            <h1>{title}</h1>
            <p>{message}</p>
            <a href="/admin">Nazaj na admin panel</a>
        </div>
    </body>
    </html>
    """


@router.get("/api/admin/reservations/{reservation_id}/confirm")
def confirm_reservation_get(reservation_id: int):
    """GET handler za potrditev iz emaila - vrne HTML stran."""
    res = service.get_reservation(reservation_id)
    if not res:
        return HTMLResponse(_email_action_html(
            "Rezervacija ni najdena",
            f"Rezervacija #{reservation_id} ne obstaja.",
            success=False
        ), status_code=404)

    if res.get("status") == "confirmed":
        return HTMLResponse(_email_action_html(
            "Že potrjeno",
            f"Rezervacija #{reservation_id} je bila že potrjena.",
            success=True
        ))

    service.update_reservation(
        reservation_id,
        status="confirmed",
        confirmed_at=datetime.now().isoformat(),
        confirmed_by=os.getenv("ADMIN_EMAIL", "info@kovacnik.com"),
    )
    res = service.get_reservation(reservation_id) or res
    send_reservation_confirmed(res)

    return HTMLResponse(_email_action_html(
        "Rezervacija potrjena",
        f"Rezervacija #{reservation_id} za {res.get('name', 'gosta')} je bila uspešno potrjena. Gostu je bil poslan email.",
        success=True
    ))


@router.get("/api/admin/reservations/{reservation_id}/reject")
def reject_reservation_get(reservation_id: int):
    """GET handler za zavrnitev iz emaila - vrne HTML stran."""
    res = service.get_reservation(reservation_id)
    if not res:
        return HTMLResponse(_email_action_html(
            "Rezervacija ni najdena",
            f"Rezervacija #{reservation_id} ne obstaja.",
            success=False
        ), status_code=404)

    if res.get("status") == "rejected":
        return HTMLResponse(_email_action_html(
            "Že zavrnjeno",
            f"Rezervacija #{reservation_id} je bila že zavrnjena.",
            success=False
        ))

    service.update_reservation(reservation_id, status="rejected")
    res = service.get_reservation(reservation_id) or res
    send_reservation_rejected(res)

    return HTMLResponse(_email_action_html(
        "Rezervacija zavrnjena",
        f"Rezervacija #{reservation_id} za {res.get('name', 'gosta')} je bila zavrnjena. Gostu je bil poslan email.",
        success=False
    ))


@router.post("/api/admin/send-message")
def send_message(data: SendMessageRequest):
    """Pošlje sporočilo gostu in opcijsko status nastavi na 'processing'."""
    if not data.email:
        raise HTTPException(status_code=400, detail="Email manjka")
    subject = _ensure_subject_tag(data.reservation_id, data.subject or "")
    send_custom_message(data.email, subject, data.body)
    if data.reservation_id:
        service.add_reservation_message(
            reservation_id=data.reservation_id,
            direction="outbound",
            subject=subject,
            body=data.body,
            from_email=os.getenv("ADMIN_EMAIL", "info@kovacnik.com"),
            to_email=data.email,
            message_id=None,
        )
    if data.set_processing:
        service.update_reservation(
            data.reservation_id,
            status="processing",
            guest_message=data.body,
        )
    return {"ok": True}


@router.get("/api/admin/reservations/{reservation_id}/messages")
def get_reservation_messages(reservation_id: int):
    """Vrne sporočila za izbrano rezervacijo."""
    messages = service.list_reservation_messages(reservation_id)
    return {"messages": messages}


@router.get("/api/admin/stats")
def get_stats():
    """Agregirani podatki za dashboard."""
    _log("stats")
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    week_ago = datetime.now() - timedelta(days=7)
    month_ago = datetime.now().replace(day=1)
    res_list = service.read_reservations(limit=1000)

    def parse_created(r) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(str(r.get("created_at", "")))
        except Exception:
            return None

    counts = {
        "danes": 0,
        "ta_teden": 0,
        "ta_mesec": 0,
        "po_statusu": {"pending": 0, "processing": 0, "confirmed": 0, "rejected": 0},
        "po_tipu": {"room": 0, "table": 0},
    }
    for r in res_list:
        created = parse_created(r)
        if created:
            if str(r.get("created_at", "")).startswith(today_prefix):
                counts["danes"] += 1
            if created >= week_ago:
                counts["ta_teden"] += 1
            if created >= month_ago:
                counts["ta_mesec"] += 1
        status = r.get("status")
        if status in counts["po_statusu"]:
            counts["po_statusu"][status] += 1
        rtype = r.get("reservation_type")
        if rtype in counts["po_tipu"]:
            counts["po_tipu"][rtype] += 1
    return counts


@router.get("/api/admin/export")
def export_reservations(
    status: Optional[str] = None,
    type: Optional[str] = None,
    source: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Izvoz rezervacij v CSV."""
    data = get_reservations(limit=1000, status=status, type=type, source=source, date_from=date_from, date_to=date_to)
    reservations = data.get("reservations", [])
    headers = [
        "id", "date", "time", "nights", "rooms", "people", "kids", "kids_small",
        "reservation_type", "name", "email", "phone", "location", "note",
        "status", "source", "created_at",
    ]
    lines = [",".join(headers)]
    for r in reservations:
        row = []
        for h in headers:
            val = r.get(h, "")
            if val is None:
                val = ""
            cell = str(val).replace('"', '""')
            if any(c in cell for c in [",", "\n", '"']):
                cell = f'"{cell}"'
            row.append(cell)
        lines.append(",".join(row))
    csv_content = "\n".join(lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reservations.csv"},
    )


@router.get("/api/admin/calendar/rooms")
def calendar_rooms(month: int, year: int):
    """Vrne zasedenost sob po dnevih z ločenimi pending/confirmed."""
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Neveljaven mesec")
    days: dict[str, dict[str, Any]] = {}
    reservations = service.read_reservations(limit=1000, reservation_type="room")
    for r in reservations:
        status = r.get("status")
        if status not in {"pending", "processing", "confirmed"}:
            continue
        room_id = _normalize_room_id(r.get("location"))
        if not room_id:
            continue
        for day in _reservation_days(r.get("date", ""), r.get("nights")):
            if day.month != month or day.year != year:
                continue
            key = day.strftime("%Y-%m-%d")
            bucket = "confirmed" if status == "confirmed" else "pending"
            entry = days.setdefault(key, {"confirmed": [], "pending": [], "reservations": []})
            if room_id not in entry[bucket]:
                entry[bucket].append(room_id)
            entry["reservations"].append({
                "id": r.get("id"),
                "reservation_type": "room",
                "name": r.get("name"),
                "people": r.get("people"),
                "kids": r.get("kids"),
                "kids_small": r.get("kids_small"),
                "location": room_id,
                "email": r.get("email"),
                "phone": r.get("phone"),
                "status": status,
                "date": r.get("date"),
                "nights": r.get("nights"),
                "note": r.get("note"),
                "admin_notes": r.get("admin_notes"),
            })
    return {"days": days}


@router.get("/api/admin/calendar/tables")
def calendar_tables(month: int, year: int):
    """Zasedenost miz po dnevih in urah."""
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Neveljaven mesec")
    calendar: dict[str, dict[str, Any]] = {}
    reservations = service.read_reservations(limit=1000, reservation_type="table")
    for r in reservations:
        status = r.get("status")
        if status in {"rejected", "cancelled"}:
            continue
        day = _parse_ddmmyyyy(r.get("date", ""))
        if not day or day.month != month or day.year != year:
            continue
        iso = day.strftime("%Y-%m-%d")
        people = 0
        try:
            people = int(r.get("people") or 0)
        except Exception:
            people = 0
        entry = calendar.setdefault(
            iso, {"total_people": 0, "capacity": TOTAL_TABLE_CAPACITY, "reservations": []}
        )
        entry["total_people"] += people
        entry["reservations"].append({
            "id": r.get("id"),
            "reservation_type": "table",
            "time": r.get("time"),
            "people": people,
            "name": r.get("name"),
            "status": status,
            "location": r.get("location"),
            "email": r.get("email"),
            "phone": r.get("phone"),
            "date": r.get("date"),
            "note": r.get("note"),
            "special_needs": r.get("special_needs"),
            "admin_notes": r.get("admin_notes"),
        })
    return calendar


@router.post("/api/admin/reservations")
def create_admin_reservation(data: AdminCreateReservation):
    """Ročno dodajanje rezervacije (admin)."""
    warning: Optional[str] = None
    valid_rooms = {"", None, "ALJAZ", "JULIJA", "ANA"}
    valid_tables = {"Pri peči", "Pri vrtu"}
    location = _normalize_room_id(data.location) if data.reservation_type == "room" else data.location

    if data.reservation_type == "room":
        if location not in valid_rooms:
            raise HTTPException(status_code=400, detail="Neveljavna soba")
    if data.reservation_type == "table":
        if location and location not in valid_tables:
            raise HTTPException(status_code=400, detail="Neveljavna jedilnica")

    if data.reservation_type == "room" and location:
        conflicts = _room_conflicts(0, location, data.date, data.nights)
        if conflicts:
            warning = f"Soba {location} je zasedena: {', '.join(conflicts)}"
    if data.reservation_type == "table" and data.time:
        ok, suggested_location, suggestions = service.check_table_availability(data.date, data.time, data.people)
        if not ok:
            warning = "Kapaciteta je polna za izbrano uro."
            if suggestions:
                warning += f" Predlogi: {', '.join(suggestions)}"
        if suggested_location and not data.location:
            location = suggested_location

    final_status = data.status
    if not final_status:
        final_status = "pending" if data.source == "wordpress" else "confirmed"

    new_id = service.create_reservation(
        date=data.date,
        nights=data.nights,
        rooms=data.rooms,
        people=data.people,
        reservation_type=data.reservation_type,
        time=data.time,
        location=location,
        name=data.name,
        phone=data.phone,
        email=data.email,
        note=data.note,
        status=final_status,
        admin_notes=data.admin_notes,
        kids=data.kids,
        kids_small=data.kids_small,
        source=data.source,
        event_type=data.event_type,
        special_needs=data.special_needs,
    )
    return {"success": True, "id": new_id, "warning": warning}


@router.delete("/api/admin/reservations/all")
def delete_all_reservations(token: str = Header(None, alias="X-Admin-Token"), t: str = Query(None)):
    """Izbriše VSE rezervacije - za reset baze pred predajo stranki. ZAHTEVA TOKEN."""
    verify_admin(token, t)
    _log("delete_all_reservations")
    count = service.delete_all_reservations()
    return {"success": True, "deleted": count, "message": f"Izbrisanih {count} rezervacij"}
