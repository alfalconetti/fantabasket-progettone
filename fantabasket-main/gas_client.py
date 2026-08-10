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


def _build_team_payload(team_id: str) -> dict:
    """Costruisce il payload JSON per un team da inviare al GAS."""
    stagione  = settings.stagione_corrente()
    roster    = db.get_roster_team(team_id)
    contratti = {r["giocatore_id"]: r for r in roster}
    impatti   = db.get_impatto_taglio_team(team_id, stagione)
    tagli_usati = db.get_tagli_gratuiti_usati(team_id, stagione)

    # Giocatori ordinati per importo DESC poi cognome
    giocatori = sorted(roster, key=lambda r: (-r["importo"], r["nome_common"].split()[-1]))

    # Flag rookie/RFA
    def _flag(r):
        if r.get("tipo_contratto") == "rookie":
            anni_scala = r.get("anni_scala", 0)
            anni_firmati = int(stagione) - r.get("stagione_firma", int(stagione))
            anno_scala = anni_firmati + 1
            if 1 <= anno_scala <= 4:
                return f"R{anno_scala - 1}"
        return ""

    giocatori_payload = [
        {
            "ruolo":   "",  # da implementare con i ruoli
            "nome":    r["nome_common"],
            "importo": r["importo"],
            "anni":    r["anni_originali"] - (int(stagione) - int(r["stagione_firma"])),
            "flag":    _flag(r),
        }
        for r in giocatori
    ]

    # Impatti tagli — max 2 righe nel foglio
    impatti_payload = [
        {
            "nome":    imp["nome_common"],
            "importo": imp["importo"],
            "anni":    1,  # ogni rata è 1 anno
        }
        for imp in impatti[:2]
    ]

    return {
        "team_id":             team_id,
        "tagli_gratuiti_usati": tagli_usati,
        "cambi_ruolo_usati":   0,  # da implementare con i ruoli
        "giocatori":           giocatori_payload,
        "impatti_tagli":       impatti_payload,
    }


def sync_teams(team_ids: list[str]) -> bool:
    """
    Invia aggiornamento roster per i team indicati al GAS Router.
    Ritorna True se la chiamata ha avuto successo, False altrimenti.
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
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            f"{router_url}/gas/roster",
            data=data,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {router_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            logger.info("GAS sync OK: %s", result)
            return True
    except urllib.error.HTTPError as e:
        logger.warning("GAS sync HTTP error %d: %s", e.code, e.reason)
    except urllib.error.URLError as e:
        logger.warning("GAS sync URL error: %s", e.reason)
    except Exception as e:
        logger.warning("GAS sync error: %s", e)
    return False


def sync_after_trade(trade_id: int) -> None:
    """Sync tutti i team coinvolti in una trade."""
    try:
        squadre = db.get_trade_squadre(trade_id)
        team_ids = [sq["team_id"] for sq in squadre]
        if team_ids:
            sync_teams(team_ids)
    except Exception as e:
        logger.warning("sync_after_trade(%d): %s", trade_id, e)


def sync_after_taglio(team_id: str) -> None:
    """Sync team dopo un taglio."""
    try:
        sync_teams([team_id])
    except Exception as e:
        logger.warning("sync_after_taglio(%s): %s", team_id, e)


def sync_after_firma(team_id: str) -> None:
    """Sync team dopo una firma FA/RFA."""
    try:
        sync_teams([team_id])
    except Exception as e:
        logger.warning("sync_after_firma(%s): %s", team_id, e)


def sync_after_dpe(team_id: str) -> None:
    """Sync team dopo una DPE."""
    try:
        sync_teams([team_id])
    except Exception as e:
        logger.warning("sync_after_dpe(%s): %s", team_id, e)


def sync_after_rookie(team_id: str) -> None:
    """Sync team dopo attivazione diritti rookie."""
    try:
        sync_teams([team_id])
    except Exception as e:
        logger.warning("sync_after_rookie(%s): %s", team_id, e)


def sync_all() -> bool:
    """Sync completo di tutti i team — per inizializzazione o recovery."""
    try:
        import teams as tm
        all_teams = tm.get_all_teams()
        team_ids  = [t["id"] for t in all_teams]
        return sync_teams(team_ids)
    except Exception as e:
        logger.warning("sync_all: %s", e)
        return False
