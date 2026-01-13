# Kovačnik AI – Digitalni turistični asistent

## 🧪 Smoke testi
```bash
# Zaženi server
uvicorn main:app --reload --port 8000

# V drugem terminalu
./tests/smoke_test.sh
```

## 🔐 Environment spremenljivke

| Spremenljivka | Opis | Obvezno |
|---------------|------|---------|
| OPENAI_API_KEY | OpenAI API ključ | DA |
| DATABASE_URL | PostgreSQL connection string | DA (production) |
| ADMIN_TOKEN | Token za admin API | DA |
| WEBHOOK_SECRET | HMAC secret za WordPress webhook | NE (dev) |
| RESEND_API_KEY | Resend API za email | DA |

## 📡 API Endpoints

### Chat
- POST /chat - Pošlji sporočilo chatbotu

### Admin
- GET /api/admin/reservations - Seznam rezervacij
- PATCH /api/admin/reservations/{id} - Posodobi rezervacijo
- POST /api/admin/reservations/{id}/confirm - Potrdi
- POST /api/admin/reservations/{id}/reject - Zavrni

### Webhook
- POST /api/webhook/reservation - WordPress webhook (HMAC zaščiten)

## 🚀 Deployment

Railway auto-deploy iz main branch.
