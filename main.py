"""
Kmetija Urška AI - Chatbot za turistično kmetijo.
"""
from pathlib import Path
import sys
import os

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import requests as _requests

from app.chat.router import router as chat_router
from app.services.admin_router import router as admin_router
from app.rag.search import load_knowledge

app = FastAPI(title="Kmetija Urška AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _trigger_report(mode: str):
    try:
        port = int(os.environ.get("PORT", 8000))
        r = _requests.get(
            f"http://localhost:{port}/api/admin/notify/daily-report",
            params={"mode": mode},
            timeout=60,
        )
        print(f"[scheduler] {mode} report: {r.text[:120]}")
    except Exception as e:
        print(f"[scheduler] {mode} report error: {e}")


@app.on_event("startup")
def startup():
    kb_path = Path(__file__).parent / "knowledge.jsonl"
    count = load_knowledge(kb_path)
    print(f"[startup] Loaded {count} knowledge chunks")
    print(f"[startup] Kmetija Urška AI ready")

    scheduler = BackgroundScheduler(timezone="Europe/Ljubljana")
    scheduler.add_job(
        lambda: _trigger_report("daily"),
        CronTrigger(hour=5, minute=0, timezone="Europe/Ljubljana"),
        id="daily_report",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _trigger_report("hourly"),
        CronTrigger(minute=2, timezone="Europe/Ljubljana"),
        id="hourly_alert",
        replace_existing=True,
    )
    scheduler.start()
    print("[scheduler] Zagnan: dnevno ob 05:00, urno ob :02 (Europe/Ljubljana)")


@app.get("/health")
def health():
    return {"status": "ok", "version": "v1", "bot": "kmetija-urska"}


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kmetija Urška AI</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: system-ui; max-width: 600px; margin: 50px auto; padding: 20px; }
            #chat { border: 1px solid #ddd; height: 400px; overflow-y: auto; padding: 10px; margin-bottom: 10px; border-radius: 8px; }
            .user { color: #1a5276; margin: 5px 0; }
            .bot { color: #1e8449; margin: 5px 0; white-space: pre-wrap; }
            #input { width: 80%; padding: 10px; border-radius: 4px; border: 1px solid #ccc; }
            button { padding: 10px 20px; background: #2e7d32; color: white; border: none; border-radius: 4px; cursor: pointer; }
            nav { margin-bottom: 20px; }
            nav a { margin-right: 15px; color: #2e7d32; }
        </style>
    </head>
    <body>
        <h1>🌿 Kmetija Urška AI</h1>
        <nav>
            <a href="/admin">Admin Panel</a>
            <a href="/widget">Widget</a>
            <a href="/health">Health</a>
        </nav>
        <div id="chat"></div>
        <input type="text" id="input" placeholder="Vprašajte..." onkeypress="if(event.key==='Enter')send()">
        <button onclick="send()">Pošlji</button>

        <script>
            let sessionId = null;
            const chat = document.getElementById('chat');
            const input = document.getElementById('input');

            async function send() {
                const msg = input.value.trim();
                if (!msg) return;
                chat.innerHTML += `<div class="user"><b>Vi:</b> ${msg}</div>`;
                input.value = '';
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: msg, session_id: sessionId})
                });
                const data = await res.json();
                sessionId = data.session_id;
                chat.innerHTML += `<div class="bot"><b>Bot:</b> ${data.reply}</div>`;
                chat.scrollTop = chat.scrollHeight;
            }
        </script>
    </body>
    </html>
    """


@app.get("/widget", response_class=HTMLResponse)
def widget_page():
    html_path = Path("static/widget.html")
    if not html_path.exists():
        return HTMLResponse("<h1>Widget UI manjka (static/widget.html)</h1>", status_code=500)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


app.include_router(chat_router)
app.include_router(admin_router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8002))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
