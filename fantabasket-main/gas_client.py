"""
GAS Client — invia aggiornamenti roster al GAS Router dopo ogni transazione.
"""
import os
import logging
import urllib.request
import urllib.error
import json

import database as db
import settings

logger = logging.getLogger(__name__)


def _read_secret(env_var: str) -> str:
    path = os.environ.get(env_var)
    if path and os.path.exists(path):
        return open(path).read().strip()
    return os.environ.get(env_var.replace("_FILE", ""), "")


def _get_config():
    router_url = os.environ.get("GAS_ROUTER_URL", "")
    router_token = _read_secret("GAS_ROUTER_TOKEN_FILE")
    return router_url, router_token


def _q_rookie_scale(anni_colonne: list) -> list:
    """Costruisce i dati delle 4 colonne rookie scale."""
    result = []
    for anno in anni_colonne:
        if anno is None:
            result.append({"anno": None, "picks": [None]*24, "diritti": []})
        else:
            result.append(db.get_rookie_scale_per_anno(anno))
    return result


def _build_team_payload(team_id: str) -> dict:
    """Costruisce il payload JSON per un team da inviare al GAS."""
    stagione  = settings.stagione_corrente()
    roster    = db.get_roster_team(team_id)
    contratti = {r["giocatore_id"]: r for r in roster}
    # Per il foglio vogliamo tutte le rate future, non solo quella corrente
    impatti   = db.get_impatti_taglio_team_futuri(team_id, stagione)
    tagli_usati = db.get_tagli_gratuiti_usati(team_id, stagione)

    # Giocatori ordinati per importo DESC poi cognome
    giocatori = sorted(roster, key=lambda r: (-r["importo"], r["nome_common"].split()[-1]))

    # Flag rookie/RFA
    def _flag(r):
        if r.get("tipo_contratto") == "rookie":
            scala = int(r.get("anni_scala") or 0)
            return f"R{min(scala, 3)}"
        return ""

    giocatori_payload = [
        {
            "ruolo":   "",  # da implementare con i ruoli
            "nome":    r["nome_common"],
            "importo": r["importo"],
            "anni":    (2 if int(r.get("anni_scala") or 0) in (0, 2) else 1)
                       if r.get("tipo_contratto") == "rookie"
                       else max(1, r["anni_originali"] - (int(stagione) - int(r.get("stagione_firma") or stagione))),
            "flag":    _flag(r),
        }
        for r in giocatori
        if not r.get("ha_dpe")  # giocatori con DPE vanno nella sezione DIS. separata
    ]

    # Impatti tagli — raggruppa per giocatore, max 2 righe nel foglio
    # Formato: "importo x anni" se rate uguali, "imp1-imp2 x anni" se diverse
    from collections import defaultdict
    impatti_by_giocatore = defaultdict(list)
    for imp in impatti:
        impatti_by_giocatore[imp["nome_common"]].append(imp["importo"])

    impatti_payload = []
    for nome, rate in list(impatti_by_giocatore.items())[:2]:
        n_anni = len(rate)
        if len(set(rate)) == 1:
            # tutte le rate uguali: "importo x anni"
            stringa = f"{rate[0]}x{n_anni}"
        else:
            # rate diverse: "imp1-imp2 x anni"
            stringa = "-".join(str(r) for r in rate) + f"x{n_anni}"
        impatti_payload.append({
            "nome":    nome,
            "stringa": stringa,
        })

    import teams as tm
    team = tm.get_team_by_id(team_id)
    cap_penalizzato = team.get("cap_penalizzato", 0) or 0 if team else 0

    # Rookie scale — 4 colonne per anno di draft (ring buffer modulo 4)
    # col_idx = anno_draft % 4, con mapping: 2→0, 3→1, 0→2, 1→3
    stagione_int = int(stagione)
    anni_draft = [stagione_int - 1 + i for i in range(-2, 2)]  # 4 anni: -3,-2,-1,0 dalla stagione
    # Gli anni attivi nelle 4 colonne sono quelli il cui (anno % 4) corrisponde alla posizione
    # Colonna 0: anno%4==2, Colonna 1: anno%4==3, Colonna 2: anno%4==0, Colonna 3: anno%4==1
    col_map = {2: 0, 3: 1, 0: 2, 1: 3}

    # Le 4 colonne sono gli ultimi 4 anni di draft completati (stagione-1 e i 3 precedenti)
    anni_colonne = [None, None, None, None]
    for y in range(stagione_int - 3, stagione_int + 1):  # es. 2023,2024,2025,2026 se stagione=2026
        col = col_map[y % 4]
        anni_colonne[col] = y

    rookie_scale = _q_rookie_scale(anni_colonne)

    # DPE attive per questo team
    dpe_attive = db.get_dpe_attive_team(team_id, stagione)
    dpe_payload = [
        {
            "nome":          d["nome_common"],
            "importo_orig":  d["importo_originale"],
            "importo_dpe":   d["importo_dpe"],
            "anni":          max(1, d.get("anni_originali", 1) - (int(stagione) - int(d.get("stagione_firma") or stagione))),
        }
        for d in dpe_attive
    ]

    return {
        "team_id":              team_id,
        "tagli_gratuiti_usati": tagli_usati,
        "cambi_ruolo_usati":    0,  # da implementare con i ruoli
        "cap_penalizzato":      cap_penalizzato,
        "giocatori":            giocatori_payload,
        "impatti_tagli":        impatti_payload,
        "dpe":                  dpe_payload,
        "rookie_scale":         rookie_scale,
        "anni_colonne":         anni_colonne,
    }


def _do_sync(router_url: str, router_token: str, payload: dict, attempt: int = 1) -> None:
    """Esegue il sync in background. Riprova una volta se fallisce."""
    try:
        data = json.dumps(payload).encode()
        path = "/gas/scelte" if payload.get("action") == "scelte" else "/gas/roster"
        req  = urllib.request.Request(
            f"{router_url}{path}",
            data=data,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {router_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            logger.info("GAS sync OK: %s", result)
    except Exception as e:
        if attempt == 1:
            import time, threading
            logger.warning("GAS sync fallito (tentativo 1): %s — riprovo tra 30s", e)
            timer = threading.Timer(30, _do_sync, args=[router_url, router_token, payload, 2])
            timer.daemon = True
            timer.start()
        else:
            if attempt == 99:
                raise
            logger.warning("GAS sync fallito definitivamente: %s", e)


def sync_teams(team_ids: list[str]) -> bool:
    """
    Invia aggiornamento roster per i team indicati al GAS Router.
    Fire and forget — non blocca il bot, riprova una volta dopo 30s se fallisce.
    """
    router_url, router_token = _get_config()
    if not router_url or not router_token:
        logger.debug("GAS Router non configurato — skip sync")
        return False

    try:
        teams_payload = [_build_team_payload(tid) for tid in team_ids]
        payload = {
            "action": "roster",
            "teams":  teams_payload,
        }
        import threading
        t = threading.Thread(target=_do_sync, args=[router_url, router_token, payload], daemon=True)
        t.start()
        return True
    except Exception as e:
        logger.warning("GAS sync build payload error: %s", e)
        return False


def sync_teams_sync(team_ids: list[str]) -> bool:
    """Sync sincrono — per comandi manuali come /sync_sheets. Timeout 60s."""
    router_url, router_token = _get_config()
    if not router_url or not router_token:
        return False
    try:
        teams_payload = [_build_team_payload(tid) for tid in team_ids]
        payload = {"action": "roster", "teams": teams_payload}
        _do_sync(router_url, router_token, payload, attempt=99)  # no retry
        return True
    except Exception as e:
        logger.warning("GAS sync_sync error: %s", e)
        return False


def sync_after_trade(trade_id: int) -> None:
    """Sync tutti i team coinvolti in una trade + foglio Scelte."""
    try:
        squadre = db.get_squadre_trade(trade_id)
        team_ids = [sq["team_id"] for sq in squadre]
        if team_ids:
            sync_teams(team_ids)
        sync_scelte()
    except Exception as e:
        logger.warning("sync_after_trade(%d): %s", trade_id, e)


def sync_after_taglio(team_id: str) -> None:
    """Sync team dopo un taglio + foglio Scelte."""
    try:
        sync_teams([team_id])
        sync_scelte()
    except Exception as e:
        logger.warning("sync_after_taglio(%s): %s", team_id, e)


def sync_after_firma(team_id: str) -> None:
    """Sync team dopo una firma FA/RFA + foglio Scelte."""
    try:
        sync_teams([team_id])
        sync_scelte()
    except Exception as e:
        logger.warning("sync_after_firma(%s): %s", team_id, e)


def sync_after_dpe(team_id: str) -> None:
    """Sync team dopo una DPE + foglio Scelte."""
    try:
        sync_teams([team_id])
        sync_scelte()
    except Exception as e:
        logger.warning("sync_after_dpe(%s): %s", team_id, e)


def sync_after_rookie(team_id: str) -> None:
    """Sync team dopo attivazione diritti rookie + foglio Scelte."""
    try:
        sync_teams([team_id])
        sync_scelte()
    except Exception as e:
        logger.warning("sync_after_rookie(%s): %s", team_id, e)




# ── Divisioni per foglio Scelte ───────────────────────────────────────────────
# Caricate da config/divisions.json (non nel repo)

def _load_divisions() -> tuple[dict, list, dict]:
    import json, os
    path = os.path.join(os.environ.get("CONFIG_DIR", "/config"), "divisions.json")
    with open(path) as f:
        data = json.load(f)
    return data["team_div"], data["team_order"], data["team_pick_nome"]


def _ordinal(n) -> str:
    n = int(n)
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{'st' if n%10==1 else 'nd' if n%10==2 else 'rd' if n%10==3 else 'th'}"


def _build_scelte_payload() -> dict:
    """Costruisce il payload per il foglio Scelte (pick + diritti)."""
    import teams as tm
    stagione_int = int(settings.stagione_corrente())
    anni = list(range(stagione_int + 1, stagione_int + 7))  # 6 anni scambiabili

    _TEAM_DIV, _TEAM_ORDER, _PICK_NOME = _load_divisions()
    teams_payload = []
    for team_id in _TEAM_ORDER:
        team      = tm.get_team_by_id(team_id)
        picks     = db.get_pick_team(team_id)          # pick detenute attualmente
        all_picks = db.get_all_picks_by_orig(team_id)  # pick con orig=questo team
        diritti   = db.get_diritti_2nd_team(team_id)

        # Diritti 2nd pick
        diritti_labels = [
            f"{d['nome_common']} ({_ordinal(d['pick_numero'])} {d['anno_draft']})"
            for d in diritti
        ]

        # Numeri draft corrente detenuti
        draft_anno = stagione_int + 1
        draft_nums = sorted([
            _ordinal(p["numero_draft"])
            for p in picks
            if str(p.get("anno")) == str(draft_anno) and p.get("numero_draft")
        ])

        # Pick proprie ancora in possesso del team (proprietario_orig == proprietario_att == team_id)
        # [STEPIEN] = pick 1st che non può essere ceduta senza violare la Stepien Rule
        # (stessa funzione usata dal validatore trade e da /assets)
        from validators.trade import anni_1st_bloccate_stepien
        bloccate_stepien = anni_1st_bloccate_stepien(team_id)

        picks_proprie = []
        for p in all_picks:
            anno = int(p["anno"])
            if anno not in anni:
                continue
            # Solo pick ancora in possesso del team
            if p.get("proprietario_att") != team_id:
                continue
            stepien_flag = p["round"] == 1 and anno in bloccate_stepien
            pick_nome = _PICK_NOME.get(team_id, team['gm_nome'])
            label = f"{pick_nome} {'1st' if p['round']==1 else '2nd'} {anno}"
            if stepien_flag:
                label += " [STEPIEN]"
            picks_proprie.append({
                "anno":  anno,
                "round": p["round"],
                "label": label,
            })

        # Pick altrui detenute (orig != questo team)
        picks_altrui = {anno: [] for anno in anni}
        for p in picks:
            anno = int(p["anno"])
            if anno not in anni:
                continue
            if p.get("proprietario_orig") == team_id:
                continue
            orig_id   = p.get("proprietario_orig", "")
            orig_nome = _PICK_NOME.get(orig_id)
            if not orig_nome:
                orig_team = tm.get_team_by_id(orig_id)
                orig_nome = orig_team["gm_nome"] if orig_team else orig_id
            label = f"{orig_nome} {'1st' if p['round']==1 else '2nd'} {anno}"
            picks_altrui[anno].append(label)

        teams_payload.append({
            "team_id":       team_id,
            "nome":          team["nome"],
            "gm":            _PICK_NOME.get(team_id, team.get("gm_nome", "")),
            "div":           _TEAM_DIV[team_id],
            "diritti":       diritti_labels,
            "draft_nums":    draft_nums,
            "picks_proprie": picks_proprie,
            "picks_altrui":  picks_altrui,
        })

    return {
        "action": "scelte",
        "anni":   anni,
        "teams":  teams_payload,
    }


def sync_scelte(sincrono: bool = False) -> bool:
    """Sync foglio Scelte — fire-and-forget o sincrono."""
    router_url, router_token = _get_config()
    if not router_url or not router_token:
        logger.debug("GAS Router non configurato — skip sync scelte")
        return False
    try:
        payload = _build_scelte_payload()
        if sincrono:
            _do_sync(router_url, router_token, payload, attempt=99)
            return True
        import threading
        t = threading.Thread(
            target=_do_sync,
            args=[router_url, router_token, payload],
            daemon=True
        )
        t.start()
        return True
    except Exception as e:
        logger.warning("sync_scelte error: %s", e)
        return False

def sync_all(sincrono: bool = False) -> bool:
    """Sync completo di tutti i team (roster + scelte) — per /sync_sheets o recovery.
    sincrono=True per /sync_sheets (aspetta risposta), False per sync automatico."""
    try:
        import teams as tm
        all_teams = tm.get_all_teams()
        team_ids  = [t["id"] for t in all_teams]
        ok_roster = sync_teams_sync(team_ids) if sincrono else sync_teams(team_ids)
        ok_scelte = sync_scelte(sincrono=sincrono)
        return ok_roster and ok_scelte
    except Exception as e:
        logger.warning("sync_all: %s", e)
        return False
