#!/bin/bash
set -e
BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-test-token}"

echo "🧪 Running smoke tests against $BASE_URL"

# Test 1: Health
echo "Test 1: Health check..."
curl -sf "$BASE_URL/health" | grep -q "ok" && echo "✅ Health OK"

# Test 2: Chat basic
echo "Test 2: Chat basic..."
REPLY=$(curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke-test","message":"Pozdravljeni"}')
echo "$REPLY" | grep -q "reply" && echo "✅ Chat OK"

# Test 3: Reservation EN
echo "Test 3: Reservation EN..."
REPLY_EN=$(curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke-en","message":"I want to book a room"}')
echo "$REPLY_EN" | grep -qi "datum" && echo "✅ Reservation EN OK"

# Test 4: Reservation DE
echo "Test 4: Reservation DE..."
REPLY_DE=$(curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke-de","message":"Zimmer reservieren"}')
echo "$REPLY_DE" | grep -qi "datum" && echo "✅ Reservation DE OK"

# Test 5: Reservation typo SL
echo "Test 5: Reservation typo SL..."
REPLY_TYPO=$(curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke-typo","message":"rad bi rezerivral sobo"}')
echo "$REPLY_TYPO" | grep -qi "datum" && echo "✅ Reservation typo OK"

# Test 6: Reservation asks about kids when only total given
echo "Test 6: Kids prompt from total..."
REPLY_TOTAL=$(curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"kids-total","message":"Rad bi rezerviral sobo 12.7.2026 za 4 osebe"}')
echo "$REPLY_TOTAL" | grep -qi "otrok" && echo "✅ Kids prompt OK"

# Test 7: Reservation asks ages when split given
echo "Test 7: Kids ages prompt..."
REPLY_SPLIT=$(curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"kids-split","message":"Rezervacija mize 13.7.2026 ob 13:00 za 2+2"}')
echo "$REPLY_SPLIT" | grep -qi "stari otroci" && echo "✅ Kids ages prompt OK"

# Test 8: Reservation + product escape
echo "Test 8: Reservation with product interjection..."
SESSION="smoke-res-table"
curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\",\"message\":\"Rezervacija mize 13.7.2026 ob 13:00 za 6 oseb\"}" > /dev/null
REPLY2=$(curl -sf -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\",\"message\":\"Imate marmelade?\"}")
echo "$REPLY2" | grep -qi "marmelad" && echo "✅ Product answer during reservation OK"

# Test 9: Admin reservations
echo "Test 9: Admin reservations..."
curl -sf "$BASE_URL/api/admin/reservations" | grep -q "reservations" && echo "✅ Admin OK"

echo ""
echo "✅✅✅ ALL SMOKE TESTS PASSED ✅✅✅"
