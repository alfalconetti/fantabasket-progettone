"""
Validazione trade prima della proposta.
Restituisce (ok: bool, errori: list[str]).
Tutti gli errori vengono raccolti prima di restituire il risultato.
"""
from __future__ import annotations
import database as db
import settings
import teams as tm


def valida_trade(trade_id: int) -> tuple[bool, list[str]]:
    """
    Valida una trade completa:
    1. Cap post-trade per ogni squadra
    2. Roster size post-trade per ogni squadra
    3. Stepien Rule per ogni squadra
    Returns (ok, lista_errori).
    """
    errori = []
    trade = db.get_trade(trade_id)
    if not trade:
        return False, ["Trade non trovata."]

    stagione = trade["stagione"]
    items = db.get_items_trade(trade_id)
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]

    for team_id in squadre:
        # Asset che escono da questo team
        out_g = [i for i in items if i["team_id_da"] == team_id and i["tipo"] == "giocatore"]
        out_p = [i for i in items if i["team_id_da"] == team_id and i["tipo"] == "pick"]
        # Asset che entrano in questo team
        in_g  = [i for i in items if i["team_id_a"]  == team_id and i["tipo"] == "giocatore"]
        in_p  = [i for i in items if i["team_id_a"]  == team_id and i["tipo"] == "pick"]

        team = tm.get_team_by_id(team_id)
        nome = team["nome"] if team else team_id

        # ── 0. Ownership e corrispondenza contratto ──────────────────────
        for i in out_g:
            contratto = db.get_contratto_attivo(i["giocatore_id"])
            nome_g = i.get("nome_common") or str(i["giocatore_id"])
            if not contratto:
                errori.append(f"❌ {nome}: {nome_g} non ha un contratto attivo")
                continue
            if contratto["team_id"] != team_id:
                team_reale = tm.get_team_by_id(contratto["team_id"])
                nome_reale = team_reale["nome"] if team_reale else contratto["team_id"]
                errori.append(
                    f"❌ {nome}: {nome_g} non è nel roster (appartiene a {nome_reale})"
                )
                continue
            # Verifica che importo e anni nella trade corrispondano al DB
            imp_db   = contratto.get("importo")
            anni_db  = contratto.get("anni_originali")
            imp_item = i.get("giocatore_importo")
            anni_item = i.get("giocatore_anni")
            if imp_item is not None and imp_db is not None and int(imp_item) != int(imp_db):
                errori.append(
                    f"⚠️ {nome}: {nome_g} — importo trade {imp_item}M ≠ DB {imp_db}M"
                )
            if anni_item is not None and anni_db is not None and int(anni_item) != int(anni_db):
                errori.append(
                    f"⚠️ {nome}: {nome_g} — anni trade {anni_item} ≠ DB {anni_db}"
                )
        cap_attuale = db.cap_occupato_team(team_id, stagione)
        cap_out = sum(
            (db.get_contratto_attivo(i["giocatore_id"]) or {}).get("importo", 0)
            for i in out_g
        )
        cap_in = sum(
            (db.get_contratto_attivo(i["giocatore_id"]) or {}).get("importo", 0)
            for i in in_g
        )
        cap_post = cap_attuale - cap_out + cap_in

        if cap_post > settings.luxury_cap():
            errori.append(
                f"❌ {nome}: cap post-trade {cap_post}M supera luxury cap {settings.luxury_cap()}M"
            )

        # ── 2. Roster size ────────────────────────────────────────────────
        roster = db.get_roster_team(team_id)
        roster_post = len(roster) - len(out_g) + len(in_g)
        if roster_post > settings.max_roster():
            errori.append(
                f"❌ {nome}: roster post-trade {roster_post} supera il massimo {settings.max_roster()}"
            )
        fase = settings.fase()
        if "regular" in fase and roster_post < settings.min_roster():
            errori.append(
                f"❌ {nome}: roster post-trade {roster_post} sotto il minimo {settings.min_roster()} (regular season)"
            )

        # ── 3. Stepien Rule ───────────────────────────────────────────────
        errore_stepien = _valida_stepien(team_id, trade_id, out_p, in_p, stagione)
        if errore_stepien:
            errori.append(f"❌ {nome}: {errore_stepien}")

    ok = len(errori) == 0
    return ok, errori


def _valida_stepien(team_id: str, trade_id: int, out_picks: list, in_picks: list,
                     stagione: str) -> str | None:
    """
    Stepien Rule: in qualsiasi finestra di N anni contigui deve esserci
    almeno un anno in cui il team aveva la propria 1st pick.
    - Anni futuri: pick propria ancora in possesso (non scattata)
    - Anni passati: pick propria già scattata (l'ha usata al draft)
    """
    n = settings.stepien_anni()
    anno_base = int(stagione)

    # Tutte le 1st pick originali del team (scattate e non)
    storico = db.get_proprie_1st_pick_storico(team_id)

    # Il DB ha pick solo dal 2027 in poi — la 2026 1st non è in tabella pick.
    # Anni <= 2026 sono considerati automaticamente coperti (dati non disponibili).
    ANNO_STORICO_LIMITE = 2026

    proprie_1st = set()
    for p in storico:
        if not p["scattata"] and int(p["anno"]) > anno_base:
            proprie_1st.add(str(p["anno"]))

    # Rimuovi quelle cedute in questa trade
    for item in out_picks:
        pick = db.get_pick(item["pick_id"])
        if pick and pick["round"] == 1 and pick["proprietario_orig"] == team_id:
            proprie_1st.discard(str(pick["anno"]))

    # Controlla finestre fino al max anno di pick presenti nel DB.
    # Es: max_pick=2032, n=4 → ultima finestra valida 2029-2032 (start=2029)
    max_pick_anno = db.get_max_pick_anno()
    ultimo_start  = max_pick_anno - n + 1

    for anno_start in range(ANNO_STORICO_LIMITE + 1, ultimo_start + 1):
        finestra = {str(a) for a in range(anno_start, anno_start + n)}
        anni_storici = {a for a in finestra if int(a) <= ANNO_STORICO_LIMITE}

        if anni_storici:
            continue  # finestra parzialmente storica → coperta automaticamente

        if not (proprie_1st & finestra):
            return (
                f"viola la Stepien Rule: nessuna propria 1st pick "
                f"nella finestra {anno_start}–{anno_start + n - 1}"
            )

    return None
