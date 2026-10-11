#!/usr/bin/env bash
# Prove dei bot su un PostgreSQL 16 locale e configurazione finta (tests/config).
# Uso: tests/run.sh            → tutte le prove
#      tests/run.sh trade_3_squadre cap_asta_chiusa   → solo quelle
# Prerequisiti e dettagli: tests/README.md
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PGURL=${PGURL:-postgresql://fb:fb@localhost/fbt}
# niente prove sul server: le prove fanno TRUNCATE (stessi controlli di tests/guardia.py)
DATABASE_URL=$PGURL PG_URL=$PGURL python3 "$ROOT/tests/guardia.py" || exit 1
MAIN=(trade_3_squadre revisione_regolamento dpe_trade_tagli team_diff report_spalmature)
ASTE_PG=(pg_rfa_30giorni_dpe rfa_lascio_andare menu_e_listteams)
ASTE_ISOLATO=(apri_asta_admin apertura_gm cap_asta_chiusa rfa_proprietario)
DOCS=(guide_e_menu)
scelti=("$@"); [ ${#scelti[@]} -eq 0 ] && scelti=("${MAIN[@]}" "${ASTE_PG[@]}" "${ASTE_ISOLATO[@]}" "${DOCS[@]}")
in_lista() { local x=$1; shift; for y in "$@"; do [ "$x" = "$y" ] && return 0; done; return 1; }
falliti=0
for t in "${scelti[@]}"; do
  W=$(mktemp -d); cp "$ROOT"/tests/config/* "$W"/      # config pulita per ogni prova (alcune cambiano la fase)
  export SETTINGS_PATH=$W/settings.json GLOBALS_PATH=$W/globals.json TEAMS_PATH=$W/teams.json \
         FA_CSV_PATH=$W/fa_players.csv DB_PATH=$W/aste.db DATABASE_URL=$PGURL PG_PASSWORD_FILE=/nonesiste
  if in_lista "$t" "${MAIN[@]}"; then dir=fantabasket-main; file=tests/main/$t.py; export PG_URL=$PGURL
  elif in_lista "$t" "${ASTE_PG[@]}"; then dir=fantabasket-aste-beta; file=tests/aste/$t.py; export PG_URL=$PGURL
  elif in_lista "$t" "${ASTE_ISOLATO[@]}"; then dir=fantabasket-aste-beta; file=tests/aste/$t.py; export PG_URL=
  elif in_lista "$t" "${DOCS[@]}"; then dir=.; file=tests/docs/$t.py
  else echo "?? prova sconosciuta: $t"; continue; fi
  echo "═══ $t"
  out=$(cd "$ROOT/$dir" && PYTHONPATH=.:.. python3 "$ROOT/$file" 2>&1 | grep -v "^INFO\|WARNING")
  echo "$out"
  if echo "$out" | grep -q "FAIL\|Traceback\|AssertionError"; then falliti=$((falliti+1)); fi
  rm -rf "$W"
done
echo; [ $falliti -eq 0 ] && echo "Tutte le prove passate." || { echo "$falliti prove con errori."; exit 1; }
