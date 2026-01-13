from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.core.config import Settings
from app.services.chat_router import router as chat_router
from app.services.reservation_router import router as reservation_router
from app.services.admin_router import router as admin_router
from app.services.webhook_router import router as webhook_router

# Naloži .env v okolje ob zagonu (za SMTP ipd.)
load_dotenv()

settings = Settings()
app = FastAPI(title=settings.project_name)

@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def chat_ui() -> HTMLResponse:
    """
    Preprost UI za testiranje Kovačnik AI chata.
    Streže datoteko static/chat.html iz root mape projekta.
    """
    html_path = Path("static/chat.html")
    if not html_path.exists():
        return HTMLResponse(
            "<h1>Chat UI ni najden.</h1><p>Manjka datoteka static/chat.html.</p>",
            status_code=500,
        )
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)

@app.get("/widget", response_class=HTMLResponse)
def widget_ui() -> HTMLResponse:
    """
    Widget verzija chata za embed v WordPress.
    """
    html_path = Path("static/widget.html")
    if not html_path.exists():
        return HTMLResponse(
            "<h1>Widget ni najden.</h1>",
            status_code=500,
        )
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)

def configure_routes() -> None:
    app.include_router(chat_router)
    app.include_router(reservation_router)
    app.include_router(admin_router)
    app.include_router(webhook_router)

configure_routes()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
