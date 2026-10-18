#!/usr/bin/env bash
# Deploy di una versione del progettone da uno zip di rilascio (dalla v3.12.0).
#
# Ogni zip contiene questo script e rilascio.json (versione, messaggio di commit, file da
# cancellare, servizi da riavviare). Uso, dalla cartella ~/bots:
#
#   Z=fantabasket-progettone-vX.Y.Z.zip; bash <(unzip -p $Z deploy.sh) $Z
#
# Cosa fa, fermandosi al primo problema:
#   1. controlli: zip integro e senza config/secrets/.db, secrets richiesti dal compose presenti,
#      versione rispetto a quella installata (avvisa se è uguale o più vecchia), modifiche locali
#      non salvate nel repo;
#   2. riepilogo e conferma;
#   3. dump del database in archivio/backup-deploy/ (tiene gli ultimi 10);
#   4. scompatta lo zip nel repo e cancella i file tolti dal rilascio (git rm);
#   5. riavvia i bot nell'ordine giusto e controlla che siano su e senza errori nei log;
#   6. commit e push; sposta in archivio gli zip oltre gli ultimi 5.
# Se un bot non parte, niente commit: stampa i log e come tornare indietro.
#
# Tutto dentro main(): bash legge l'intera funzione prima di eseguirla.

main() {
    set -euo pipefail
    local Z="${1:-}"
    local R="${REPO:-$HOME/bots/fantabasket-progettone}"
    local TIENI_ZIP=5 TIENI_BACKUP=10

    command -v python3 >/dev/null || { echo "❌ Serve python3"; exit 1; }
    [ -n "$Z" ] && [ -f "$Z" ] || { echo "❌ Zip non trovato: '$Z'"; exit 1; }
    Z="$(readlink -f "$Z")"
    local D; D="$(dirname "$Z")"
    [ -d "$R/.git" ] || { echo "❌ Repo non trovato in $R (variabile REPO per cambiarlo)"; exit 1; }
    unzip -tq "$Z" >/dev/null || { echo "❌ Lo zip è rovinato: riscaricalo"; exit 1; }

    local MAN
    MAN="$(unzip -p "$Z" rilascio.json 2>/dev/null)" || { echo "❌ Nello zip manca rilascio.json"; exit 1; }
    campo() {   # campo del manifest: liste una voce per riga
        python3 -c 'import json,sys
v = json.loads(sys.argv[1]).get(sys.argv[2])
print("\n".join(map(str, v)) if isinstance(v, list) else ("" if v is None else str(v).lower() if isinstance(v, bool) else v))' "$MAN" "$1"
    }
    local VER MSG FERMA ATTESA
    VER="$(campo versione)"; MSG="$(campo messaggio)"; FERMA="$(campo ferma_aste_prima)"; ATTESA="$(campo attesa_main)"
    local -a ELIMINA RIAVVIA LOGS
    mapfile -t ELIMINA < <(campo elimina | sed '/^$/d')
    mapfile -t RIAVVIA < <(campo riavvia | sed '/^$/d')
    mapfile -t LOGS < <(campo log_attesi | sed '/^$/d')
    [ ${#RIAVVIA[@]} -gt 0 ] || RIAVVIA=(bot-main bot-aste-beta)
    [ -n "$ATTESA" ] || ATTESA=20

    # 1. controlli
    if unzip -Z1 "$Z" | grep -qE '(^|/)(config|secrets)/|\.db$|globals\.gs$'; then
        echo "❌ Lo zip contiene config/, secrets/, database o globals.gs: non lo installo"; exit 1
    fi
    # i secrets che il docker-compose.yml nuovo si aspetta (un bot nuovo vuole il suo token)
    local MANCANTI f
    MANCANTI="$( { unzip -p "$Z" docker-compose.yml 2>/dev/null || cat "$R/docker-compose.yml"; } \
                 | grep -oE 'file: \./secrets/[^[:space:]]+' | sed 's#^file: \./##' \
                 | while read -r f; do [ -e "$R/$f" ] || echo "$f"; done )" || true
    if [ -n "$MANCANTI" ]; then
        echo "❌ Mancano questi file, servono al docker-compose.yml di questa versione:"
        echo "$MANCANTI" | sed "s#^#   $R/#"
        echo "   Creali prima (istruzioni nel CHANGELOG della versione), poi rilancia il deploy: non ho toccato niente."
        exit 1
    fi
    local ATTUALE
    ATTUALE="$(grep -oE '^## v[0-9]+\.[0-9]+\.[0-9]+' "$R/fantabasket-main/CHANGELOG.md" | tail -1 | sed 's/^## v//')" || true
    local AVVISO=""
    if [ -n "$ATTUALE" ]; then
        if [ "$VER" = "$ATTUALE" ]; then
            AVVISO="⚠️  La v$VER risulta già installata: la reinstallo."
        elif [ "$(printf '%s\n%s\n' "$VER" "$ATTUALE" | sort -V | tail -1)" = "$ATTUALE" ]; then
            AVVISO="⚠️  ATTENZIONE: la v$VER è PIÙ VECCHIA di quella installata (v$ATTUALE). Hai preso lo zip giusto?"
        fi
    fi
    local SPORCO
    SPORCO="$(git -C "$R" status --porcelain)"

    # 2. riepilogo e conferma
    echo "════════════════════════════════════════════════"
    echo " Deploy v$VER   (installata: v${ATTUALE:-?})"
    echo " Zip:      $(basename "$Z")  ($(unzip -Z1 "$Z" | grep -vcE '^(deploy\.sh|rilascio\.json)$|/$') file)"
    echo " Riavvio:  ${RIAVVIA[*]}$( [ "$FERMA" = "true" ] && echo "  (bot aste fermato prima)")"
    [ ${#ELIMINA[@]} -gt 0 ] && printf ' Cancello: %s\n' "${ELIMINA[@]}"
    echo " Commit:   $MSG"
    echo "════════════════════════════════════════════════"
    [ -n "$AVVISO" ] && echo "$AVVISO"
    if [ -n "$SPORCO" ]; then
        echo "⚠️  Nel repo ci sono modifiche non salvate in git (verranno sovrascritte se lo zip tocca gli stessi file):"
        echo "$SPORCO" | head -20
    fi
    local RISP
    read -r -p "Procedo? [s/N] " RISP
    [[ "$RISP" =~ ^[sS]$ ]] || { echo "Annullato, non ho toccato niente."; exit 1; }

    cd "$R"

    # 3. backup del database
    local BKDIR="$D/archivio/backup-deploy" BK
    mkdir -p "$BKDIR"
    BK="$BKDIR/fantabasket-prima-v$VER-$(date +%Y%m%d-%H%M).sql"
    echo "💾 Backup del database…"
    docker compose exec -T postgres pg_dump -U fantabasket -d fantabasket --clean --if-exists --no-owner > "$BK"
    tail -15 "$BK" | grep -q "dump complete" || { echo "❌ Backup non riuscito ($BK): mi fermo prima di toccare qualcosa"; exit 1; }
    ls -1t "$BKDIR"/fantabasket-prima-*.sql | tail -n +$((TIENI_BACKUP + 1)) | xargs -r rm -f
    echo "   $BK ($(du -h "$BK" | cut -f1))"

    # 4. file
    echo "📦 Scompatto…"
    unzip -o -q "$Z" -x deploy.sh rilascio.json -d "$R"
    [ -f "$R/tests/run.sh" ] && chmod a-x "$R/tests/run.sh"
    local f
    for f in "${ELIMINA[@]}"; do
        git rm -q --ignore-unmatch -- "$f"
        rm -f -- "$f"
    done

    torna_indietro() {
        echo
        echo "Niente commit. Per tornare indietro:"
        echo "  cd $R && git checkout -- . && git clean -fd -- fantabasket-main fantabasket-aste-beta shared tests scripts"
        echo "  docker compose exec -T postgres psql -U fantabasket -d fantabasket -q < $BK   # solo se serve il database di prima"
        echo "  docker compose up --build -d --force-recreate ${RIAVVIA[*]}"
    }

    # 5. riavvio e controlli
    local INIZIO; INIZIO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    [ "$FERMA" = "true" ] && docker compose stop bot-aste-beta >/dev/null 2>&1
    local S
    for S in "${RIAVVIA[@]}"; do
        echo "🔄 $S…"
        # l'output di build e avvio (le rotelline) va in un file: si vede solo se qualcosa va storto
        local OUT; OUT="$(mktemp)"
        # --force-recreate: si riavvia sempre, anche se l'immagine non è cambiata (es. cambia solo shared/,
        # che è montato: senza riavvio il bot continuerebbe a usare il codice vecchio, e niente messaggio di avvio)
        if ! docker compose up --build -d --force-recreate "$S" >"$OUT" 2>&1; then
            echo "❌ Build o avvio di $S non riusciti:"; tail -30 "$OUT"; rm -f "$OUT"
            torna_indietro; exit 1
        fi
        rm -f "$OUT"
        if [ "$S" = "bot-main" ]; then sleep "$ATTESA"; else sleep 10; fi
        if ! docker compose ps --status running --services | grep -qx "$S"; then
            echo "❌ $S non è partito. Ultime righe di log:"
            docker compose logs --since "$INIZIO" --tail 40 "$S" || true
            torna_indietro; exit 1
        fi
        if docker compose logs --since "$INIZIO" "$S" 2>&1 | grep -q "Traceback"; then
            echo "⚠️  $S è su, ma nei log c'è un errore:"
            docker compose logs --since "$INIZIO" "$S" 2>&1 | grep -B2 -A12 "Traceback" | tail -40 || true
            read -r -p "Continuo lo stesso? [s/N] " RISP
            [[ "$RISP" =~ ^[sS]$ ]] || { torna_indietro; exit 1; }
        else
            echo "   ✅ $S su, nessun errore nei log"
        fi
    done
    local P
    for P in "${LOGS[@]}"; do
        echo "🔎 log \"$P\":"
        docker compose logs --since "$INIZIO" bot-main 2>&1 | grep -i -- "$P" || echo "   (non trovato)"
    done

    # 6. commit, push, zip vecchi in archivio
    git add -A
    # rete di sicurezza: token, config e database non vanno mai su GitHub, anche senza .gitignore
    local SENSIBILI
    SENSIBILI="$(git diff --cached --name-only | grep -E '^(secrets|config)/|\.db$|globals\.gs$' || true)"
    if [ -n "$SENSIBILI" ]; then
        printf '%s\n' "$SENSIBILI" | while read -r f; do git reset -q -- "$f"; done
        echo "🔒 Tenuti fuori dal commit ($(printf '%s\n' "$SENSIBILI" | wc -l) file in secrets/, config/, .db, globals.gs)."
        echo "   Controlla che .gitignore li escluda:  grep -nE 'secrets|config' .gitignore"
    fi
    if git diff --cached --quiet; then
        echo "ℹ️  Niente da salvare in git (versione già committata)."
    else
        git commit -q -m "$MSG" && git push -q origin main && echo "📤 Commit e push fatti."
    fi
    mkdir -p "$D/archivio/progettone/v3"
    ls -1v "$D"/fantabasket-progettone-v*.zip 2>/dev/null | head -n -$TIENI_ZIP | xargs -r mv -t "$D/archivio/progettone/v3/" || true

    echo
    echo "✅ v$VER installata."
    echo "   Backup di prima: $BK"
    echo "   Per tornare indietro: cd $R && git revert --no-edit HEAD && git push && docker compose up --build -d --force-recreate ${RIAVVIA[*]}"
    echo "   (e, se serve, il database: docker compose exec -T postgres psql -U fantabasket -d fantabasket -q < $BK)"
}

main "$@"
exit $?
