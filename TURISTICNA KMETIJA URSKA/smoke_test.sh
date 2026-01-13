#!/usr/bin/env bash
# Quick smoke test for Kovačnik AI chat API.
# Usage: ./smoke_test.sh [base_url]
# Default base_url: http://127.0.0.1:8000

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"

post_chat() {
  local msg="$1"
  local sid="$2"
  printf "\n==> %s\n" "$msg"
  curl -s -X POST "$BASE_URL/chat" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$sid\",\"message\":\"$msg\"}" \
    -w "\nHTTP:%{http_code}\n"
}

echo "Running smoke tests against $BASE_URL"

post_chat "Rad bi rezerviral sobo 12.7.2026 za 3 nočitve za 4 osebe" "room-smoke"
post_chat "Rezervacija mize 13.7.2026 ob 13:00 za 6 oseb" "table-smoke"
post_chat "Imate marmelade?" "product-smoke"
post_chat "Koliko je star kozmos?" "info-smoke"

echo -e "\nDone."
