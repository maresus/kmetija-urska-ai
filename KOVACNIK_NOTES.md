# Urška AI Agent – Projektni dnevnik

## Verzija 0.1 – OGRODJE (19. 11. 2025)

✅ FastAPI projekt postavljen  
✅ `requirements.txt` (fastapi, uvicorn, pydantic, httpx, python-dotenv)  
✅ Osnovna struktura:
- app/core/config.py (Settings)
- app/models (chat, product, reservation)
- app/services (chat_router, product_service, reservation_service)
- app/rag (RAGEngine – zaenkrat samo placeholder)
- app/utils (logging_utils)

✅ Endpointi:
- `GET /health` → {"status": "ok"}
- `POST /chat`:
  - default: pozdravno sporočilo
  - product intent: vrne dummy izdelke (salama, klobasa, sir)
  - reservation intent: vrne “Za rezervacije mi prosim napišite datum in število oseb.”

---
## Verzija 0.2 – Rezervacijski dialog (osnova)

✅ /chat zna prepoznati:
- vprašanja o izdelkih → vrne dummy seznam izdelkov
- rezervacijo → začne vodeni dialog (1. namen, 2. datum, 3. št. oseb)

✅ Osnovni rezervacijski tok dela:
- "Rad bi rezerviral sobo."
- "12.7.2025"
- "4 osebe"
→ vrne povzetek rezervacije.
