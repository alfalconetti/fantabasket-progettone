"""
Validazione trade prima della proposta.
Restituisce (ok: bool, errori: list[str]).
Tutti gli errori vengono raccolti prima di restituire il risultato.
"""
from __future__ import annotations
import database as db
import settings
import teams as tm


def _cap_post_team(team_id: str, items: list, stagione: str) -> tuple[int, int]:
    """(cap attuale, cap post-trade) di una squadra; contratti con DPE contati all'importo ridotto."""
    def _importo_effettivo(giocatore_id):
        dpe = db.get_dpe_attiva(giocatore_id, stagione)
        if dpe:
            return dpe["importo_dpe"]
        return (db.get_contratto_attivo(giocatore_id) or {}).get("importo", 0)
    cap_attuale = db.cap_occupato_team(team_id, stagione)
    cap_out = sum(_importo_effettivo(i["giocatore_id"]) for i in items
                  if i["team_id_da"] == team_id and i["tipo"] == "giocatore")
    cap_in  = sum(_importo_effettivo(i["giocatore_id"]) for i in items
                  if i["team_id_a"] == team_id and i["tipo"] == "giocatore")
    return cap_attuale, cap_attuale - cap_out + cap_in


def avvisi_trade(trade_id: int) -> list[str]:
    """Avvisi NON bloccanti. In offseason: squadre che dopo la trade superano i 150M
    (permesso fino a 165M, ma va riportato in regola entro l'inizio della regular season)."""
    if not settings.fase().startswith("offseason"):
        return []
    trade = db.get_trade(trade_id)
    if not trade:
        return []
    items = db.get_items_trade(trade_id)
    avvisi = []
    for s in db.get_squadre_trade(trade_id):
        team_id = s["team_id"]
        _, cap_post = _cap_post_team(team_id, items, trade["stagione"])
        team = tm.get_team_by_id(team_id)
        cap_rs = settings.cap_massimo() - int((team or {}).get("cap_penalizzato") or 0)
        if cap_rs < cap_post <= settings.luxury_cap():
            avvisi.append(f"⚠️ {team['nome'] if team else team_id}: cap post-trade {cap_post}M, sopra i "
                          f"{cap_rs}M della regular season (va riportato in regola prima dell'inizio)")
    return avvisi


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
        cap_attuale, cap_post = _cap_post_team(team_id, items, stagione)

        # Tetto: in offseason 165M per tutti; in regular season 150M meno
        # l'eventuale penalità della squadra.
        offseason = settings.fase().startswith("offseason")
        cap_pen   = 0 if offseason else int((team or {}).get("cap_penalizzato") or 0)
        limite    = settings.luxury_cap() if offseason else settings.cap_massimo() - cap_pen
        if cap_post > limite:
            tipo = "luxury" if offseason else "cap"
            nota = f" (penalità {cap_pen}M)" if cap_pen else ""
            errori.append(
                f"❌ {nome}: cap post-trade {cap_post}M supera il limite {tipo} di {limite}M{nota}"
            )

        # Salary floor: in stagione una trade non può portare (o lasciare
        # scendere ulteriormente) una squadra sotto il floor.
        floor = settings.salary_floor()
        if not offseason and cap_post < floor and cap_post < cap_attuale:
            errori.append(
                f"❌ {nome}: cap post-trade {cap_post}M sotto il salary floor di {floor}M"
            )

        # ── 1b. Vincoli di ruolo (solo regular season) ────────────────────
        # Deve esistere un'assegnazione dei ruoli eleggibili ai nuovi arrivati che
        # rispetti 4 G / 4 F / 2 C; se la squadra è già fuori regola, la trade non
        # deve peggiorare la situazione.
        if settings.fase() in settings.FASI_RUOLI_RS:
            from validators.ruoli import deficit_team
            prima = deficit_team(team_id, stagione)
            dopo  = deficit_team(team_id, stagione,
                                 togli=[i["giocatore_id"] for i in out_g],
                                 aggiungi=[i["giocatore_id"] for i in in_g])
            if dopo > 0 and dopo > prima:
                errori.append(
                    f"❌ {nome}: dopo la trade il roster non può rispettare i ruoli minimi "
                    f"(4 G, 4 F, 2 C) con le posizioni eleggibili dei giocatori"
                )

        # ── 2. Roster size ────────────────────────────────────────────────
        roster = db.get_roster_team(team_id)
        fase = settings.fase()
        pre_deadline = (fase != "regular-season-deadline")
        # Giocatori con DPE in fase pre-deadline non occupano slot
        slot_dpe_liberati = sum(1 for r in roster if r.get("ha_dpe") and pre_deadline)
        roster_count = len(roster) - slot_dpe_liberati
        roster_post = roster_count - len(out_g) + len(in_g)
        if roster_post > settings.max_roster():
            errori.append(
                f"❌ {nome}: roster post-trade {roster_post} supera il massimo {settings.max_roster()}"
            )
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


# ── Stepien Rule (logica unica: trade, foglio scelte, /assets) ───────────────

# Il DB ha pick solo dal 2027 in poi: gli anni <= 2026 sono considerati coperti.
STEPIEN_ANNO_STORICO_LIMITE = 2026


def anni_coperti_stepien(team_id: str, out_ids=(), in_ids=()) -> set:
    """Anni in cui la squadra ha una PROPRIA 1st pick:
    - draft già svolti (scattata): usata dalla squadra stessa;
    - draft futuri: posseduta oggi, applicando eventuali pick in uscita/entrata
      (le pick protette cedute contano come cedute)."""
    out_ids, in_ids = set(out_ids), set(in_ids)
    coperti = set()
    for p in db.get_proprie_1st_pick_storico(team_id):
        if p["scattata"]:
            if p["proprietario_att"] == team_id:
                coperti.add(int(p["anno"]))
            continue
        detentore = p["proprietario_att"]
        if p["id"] in out_ids:
            detentore = None
        if p["id"] in in_ids:
            detentore = team_id
        if detentore == team_id:
            coperti.add(int(p["anno"]))
    return coperti


def finestra_scoperta(coperti: set) -> tuple[int, int] | None:
    """Prima finestra di N anni contigui senza alcun anno coperto, o None."""
    n = settings.stepien_anni()
    max_pick_anno = db.get_max_pick_anno()
    for anno_start in range(STEPIEN_ANNO_STORICO_LIMITE + 1, max_pick_anno - n + 2):
        if not any(a in coperti for a in range(anno_start, anno_start + n)):
            return anno_start, anno_start + n - 1
    return None


def anni_1st_bloccate_stepien(team_id: str) -> set:
    """Anni delle proprie 1st (possedute, non scattate) che NON si possono cedere
    senza violare la Stepien Rule → tag [STEPIEN] su foglio e /assets."""
    coperti = anni_coperti_stepien(team_id)
    bloccate = set()
    for p in db.get_proprie_1st_pick_storico(team_id):
        if p["scattata"] or p["proprietario_att"] != team_id:
            continue
        anno = int(p["anno"])
        if finestra_scoperta(coperti - {anno}):
            bloccate.add(anno)
    return bloccate


def _valida_stepien(team_id: str, trade_id: int, out_picks: list, in_picks: list,
                     stagione: str) -> str | None:
    """Stepien Rule: in ogni finestra di N anni contigui (settings.stepien_anni)
    la squadra deve avere almeno una delle PROPRIE 1st pick (vedi anni_coperti_stepien)."""
    out_ids = {i["pick_id"] for i in out_picks if i.get("pick_id") is not None}
    in_ids  = {i["pick_id"] for i in in_picks if i.get("pick_id") is not None}
    finestra = finestra_scoperta(anni_coperti_stepien(team_id, out_ids, in_ids))
    if finestra:
        return (f"viola la Stepien Rule: nessuna propria 1st pick "
                f"nella finestra {finestra[0]}–{finestra[1]}")
    return None
