#!/usr/bin/env bash
set -euo pipefail

BASE_URL=${1:-http://127.0.0.1:8000}
SESSION_ID=${2:-semantic-smoke}

ask() {
  local msg="$1"
  echo "\n> $msg"
  curl -s "$BASE_URL/chat" \
    -H 'Content-Type: application/json' \
    -d "{\"session_id\": \"$SESSION_ID\", \"message\": \"$msg\"}" | sed 's/^/  /'
}

ask "kdo je gospodar kmetije"
ask "kdo je Aljaž"
ask "kdo ste vi"
ask "kako vas najdemo"
ask "kakšen je naslov"
ask "ali imate parkirišče"
ask "kakšna je vikend ponudba"
ask "jedilnik"
ask "koliko stane večerja"
ask "kakšen je zajtrk"
ask "katere živali imate"
ask "ali lahko božamo zajčke"
ask "ali lahko jahamo konja"
ask "ali lahko jahamo ponija"
ask "imate marmelado"
ask "imate borovničev liker"
ask "ali prodajate pohorsko bunko"
ask "kako naročim izdelke"
ask "kakšna vina imate"
ask "kako pridem do Areha"
