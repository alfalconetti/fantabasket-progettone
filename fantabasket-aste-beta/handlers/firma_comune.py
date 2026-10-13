"""
Firma: regole e scritture comuni ai moduli firma*.py. Anni minimi e soglie dell'RFA, ruolo da
scegliere in regular season, validazione degli anni, e le due sole funzioni che chiudono un'asta
nel database: _registra_firma_finale (contratto, cap e slot, RFA liberata) e
_concludi_rfa_senza_contratto (lascia andare, RFA annullata senza offerte).
"""
import html
import logging
from datetime import datetime, timezone

import database as db
import teams as tm
import utils
import settings
from handlers.helpers import (
    aggiorna_canale as _aggiorna_canale, notifica_admin_group as _notifica_admin_group,
    notifica_watchers as _notifica_watchers, log_warn as _log_warn,
)

logger = logging.getLogger(__name__)


# ── ruoli (regular season) — regole nel modulo condiviso col bot main ─────────

def _ruoli_attivi(asta: dict) -> bool:
    """Ruolo da scegliere insieme agli anni: solo FA, solo in regular season, con PG."""
    import pg_client
    from shared.ruoli_core import FASI_RUOLI_RS
    return (asta["tipo"] == "FA" and pg_client.pg_disponibile()
            and utils.load_globals().get("fase", "") in FASI_RUOLI_RS)


def _info_ruolo(asta: dict, team_id: str) -> dict:
    """gid, posizioni eleggibili, ruolo imposto dalla regola dei 60 giorni, ruoli validi."""
    import pg_client
    from shared import ruoli_core as core
    stagione = utils.load_globals().get("stagione_corrente", "2025")
    gid = pg_client.id_giocatore_asta(asta)
    if gid is None:
        return {"gid": None, "eleggibili": [], "fisso": None, "validi": []}
    eleg = core.eleggibili(pg_client.q, gid)
    fisso = core.ruolo_riacquisto(pg_client.q, gid, team_id)
    validi = [r for r in eleg if core.scelta_valida(pg_client.q, team_id, stagione, gid, r, in_arrivo=True)]
    return {"gid": gid, "eleggibili": eleg, "fisso": fisso, "validi": validi or eleg}


# ── helpers soglie RFA ────────────────────────────────────────────────────────

def anni_minimi(importo: int) -> int:
    s = settings.get()
    if importo >= s["soglia_anni_3"]:
        return 3
    if importo >= s["soglia_anni_2"]:
        return 2
    return 1


def soglia_pareggio(vecchio_compenso: int) -> int:
    """
    Importo minimo che il proprietario deve offrire.
    ≤fascia_bassa_max: 1M
    fascia_bassa_max+1..fascia_media_max: ⌊vecchio/3⌋
    >fascia_media_max: ⌊vecchio/2⌋
    """
    s = settings.get()
    if vecchio_compenso <= s["fascia_bassa_max"]:
        return 1
    if vecchio_compenso <= s["fascia_media_max"]:
        return vecchio_compenso // 3
    return vecchio_compenso // 2


def importo_minimo_pareggio(offerta: int, vecchio_compenso: int) -> int:
    soglia = soglia_pareggio(vecchio_compenso)
    return max(offerta, soglia)


# ── chiusura RFA senza contratto (lascia andare / annullata senza offerte) ────

async def _concludi_rfa_senza_contratto(context, asta_id: int):
    """
    Chiude una RFA senza assegnare nessun contratto.
    Libera il vecchio compenso dal cap del proprietario.
    """
    asta = db.get_asta(asta_id)
    if not asta:
        return
    import pg_client
    if pg_client.pg_disponibile():
        # contratto disattivato + movimento di uscita (prima libera_cap veniva chiamata
        # senza il nome del giocatore: su PG non succedeva niente e l'RFA restava in squadra)
        stagione = utils.load_globals().get("stagione_corrente", "2025")
        if not pg_client.rilascia_rfa(asta["squadra_proprietaria"], asta["giocatore"], stagione,
                                      giocatore_id=pg_client.id_giocatore_asta(asta)):
            await _log_warn(context, f"RFA {asta['giocatore']} lasciato andare ma contratto non trovato su PG "
                                     f"({asta['squadra_proprietaria']}): verificare a mano.")
        pg_client.accoda_sync_gas(f"RFA lasciato andare {asta['giocatore']}")
    elif asta["vecchio_compenso"]:
        tm.libera_cap(asta["squadra_proprietaria"], asta["vecchio_compenso"])   # modalità isolata (JSON)
    logger.info("RFA senza contratto chiusa: asta_id=%d giocatore=%s", asta_id, asta["giocatore"])


# ── registrazione firma finale ────────────────────────────────────────────────

async def _registra_firma_finale(
    context, asta_id: int, anni: int, team_id: str,
    query=None, importo_override: int = None, pareggiato: bool = False,
    ruolo: str | None = None, nota_tempo: str | None = None,
) -> str | None:
    """
    Gestisce SEMPRE:
    1. Liberazione vecchio compenso RFA dal cap del proprietario
    2. Scala cap e slot a chi firma
    3. Registra contratto nel DB
    4. Aggiorna messaggio canale
    5. Annuncio firma nel canale

    Quando qualcosa è stato deciso d'ufficio perché è scaduto il tempo (anni di penale, anni
    minimi RFA, pareggio non deciso, ruolo estratto), l'annuncio sul canale lo dice: ⏰ Tempo scaduto.
    """
    asta = db.get_asta(asta_id)
    if not asta:
        return

    importo = importo_override if importo_override is not None else asta["offerta_corrente"]
    now     = datetime.now(timezone.utc).isoformat()
    stagione = utils.load_globals().get("stagione_corrente", "2025")

    if asta["tipo"] == "FA":
        tm.scala_cap_slot(team_id, importo)
        import utils as _utils
        _utils.segna_giocatore_firmato(asta["giocatore"])
    else:
        # RFA: libera sempre il vecchio compenso dal proprietario
        if asta["vecchio_compenso"]:
            import pg_client as _pg
            tm.libera_cap(asta["squadra_proprietaria"], asta["vecchio_compenso"],
                          nome_giocatore=asta["giocatore"], giocatore_id=_pg.id_giocatore_asta(asta))
        # scala cap e slot a chi firma (il giocatore RFA non occupava slot)
        tm.scala_cap_slot(team_id, importo)

    # Scrivi firma su PostgreSQL
    import pg_client
    ok_pg = pg_client.registra_firma(team_id, asta["giocatore"], importo, anni, stagione,
                                     giocatore_id=pg_client.id_giocatore_asta(asta))
    if not ok_pg:
        logger.warning("Firma PG fallita per %s — verificare manualmente.", asta["giocatore"])

    # Ruolo (FA in regular season): scelto dal GM, imposto dalla regola dei 60 giorni,
    # oppure estratto se il GM non ha risposto in tempo
    riga_ruolo = ""
    if ok_pg and _ruoli_attivi(asta):
        try:
            from shared import ruoli_core as core
            gid = pg_client.id_giocatore_asta(asta) or pg_client.trova_o_crea_giocatore(asta["giocatore"])
            nota = ""
            fisso = core.ruolo_riacquisto(pg_client.q, gid, team_id)
            if fisso:
                ruolo, nota = fisso, " (regola dei 60 giorni)"
            elif ruolo is None:
                ruolo = core.estrai_ruolo(pg_client.q, team_id, stagione, gid)
                nota = ((" (⏰ estratto: tempo scaduto)" if nota_tempo else " (estratto)") if ruolo else "")
            if ruolo:
                core.registra_ruolo(pg_client.q, gid, team_id, ruolo, stagione, "post_firma")
                riga_ruolo = f"\n🎽 Ruolo: <b>{ruolo}</b>{nota}"
            else:
                riga_ruolo = "\n🎽 Ruolo: da assegnare (posizioni eleggibili mancanti)"
                await _notifica_admin_group(
                    context, f"⚠️ {asta['giocatore']} firmato da {team_id} senza ruolo: posizioni eleggibili "
                             f"mancanti. Impostale con /set_posizioni_eleggibili e assegna il ruolo dal bot main.")
        except Exception as e:
            ruolo = None
            await _log_warn(context, f"Registrazione ruolo firma {asta['giocatore']} fallita: {e}")

    db.registra_contratto(
        asta_id=asta_id, giocatore=asta["giocatore"],
        team_id=team_id, importo=importo, anni=anni,
        ruolo=ruolo, firmato_at=now,
    )
    # Cose decise d'ufficio perché è scaduto il tempo: nell'annuncio e nel messaggio dell'asta
    scaduti = [nota_tempo] if nota_tempo else []
    if asta["tipo"] == "RFA" and not pareggiato and asta["anni_automatici"]:
        scaduti.insert(0, "il vincitore non ha scelto gli anni: minimi per fascia d'ufficio")
    riga_tempo = "".join(f"\n⏰ <i>Tempo scaduto: {html.escape(x, quote=False)}</i>" for x in scaduti)

    db.concludi_asta(asta_id, anni_contratto=anni, firmato_at=now, team_firma=team_id, importo_firma=importo,
                     note_tempo=scaduti)

    await _aggiorna_canale(context, asta_id)

    team      = tm.get_team_by_id(team_id)
    team_nome = team["nome"] if team else team_id
    gm_nome   = team.get("gm_nome", "") if team else ""

    # Annuncio nel canale principale lega
    main_channel_id = utils.load_globals().get("main_channel_id")
    if main_channel_id:
        try:
            if asta["tipo"] == "RFA" and pareggiato and not asta["offerente_team_id"]:
                # Nessuna offerta: il proprietario rifirma (non è un pareggio)
                testo_main = (
                    f"🖊️ <b>{team_nome} rifirma {asta['giocatore']}</b> (RFA senza offerte)\n"
                    f"💰 {importo}M × {anni} ann{'o' if anni==1 else 'i'}"
                )
            elif asta["tipo"] == "RFA" and pareggiato:
                # Proprietario ha pareggiato
                testo_main = (
                    f"⚖️ <b>{team_nome} pareggia {asta['giocatore']}</b>\n"
                    f"💰 {importo}M × {anni} ann{'o' if anni==1 else 'i'}"
                )
            elif asta["tipo"] == "RFA" and not pareggiato:
                # Proprietario non ha pareggiato — firma il vincitore
                team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
                team_prop_nome = team_prop["nome"] if team_prop else "il proprietario"
                firma_label = f"🖊️ {gm_nome} firma" if gm_nome else "🖊️ Firma"
                testo_main = (
                    f"❌ {team_prop_nome} non pareggia\n"
                    f"<b>{firma_label} {asta['giocatore']}</b> con <b>{team_nome}</b>\n"
                    f"💰 {importo}M × {anni} ann{'o' if anni==1 else 'i'}"
                    f"{riga_tempo}"
                )
            else:
                # FA normale
                firma_label = f"🖊️ {gm_nome} firma" if gm_nome else "🖊️ Firma"
                testo_main = (
                    f"<b>{firma_label} {asta['giocatore']}</b> con <b>{team_nome}</b>\n"
                    f"💰 {importo}M × {anni} ann{'o' if anni==1 else 'i'}"
                    f"{riga_ruolo}{riga_tempo}"
                )
            await context.bot.send_message(
                chat_id=main_channel_id,
                text=testo_main,
                parse_mode="HTML",
            )
        except Exception as e:
            await _log_warn(context, f"Annuncio firma canale principale fallito: {e}")

    # notifica watcher della firma
    team_nome_w = team["nome"] if team else team_id
    await _notifica_watchers(
        context, asta_id,
        f"✅ <b>{asta['giocatore']}</b> firmato con <b>{team_nome_w}</b>\n"
        f"💰 {importo}M × {anni} ann{'o' if anni==1 else 'i'}"
    )

    logger.info("Firma finale: asta_id=%d team=%s anni=%d importo=%d",
                asta_id, team_id, anni, importo)

    # Segnala al bot main di risincronizzare i fogli Google
    try:
        import pg_client
        pg_client.accoda_sync_gas(f"firma {asta['giocatore']} → {team_id}")
    except Exception as e:
        logger.warning("Accodamento sync GAS fallito: %s", e)

    return ruolo


# ── validazione anni ──────────────────────────────────────────────────────────

def _valida_anni(importo: int, anni: int) -> str | None:
    s = settings.get()
    if importo >= s["soglia_anni_3"] and anni != 3:
        return f"Con un contratto da {s['soglia_anni_3']}M+ sono obbligatori 3 anni."
    if importo >= s["soglia_anni_2"] and anni < 2:
        return f"Con un contratto da {s['soglia_anni_2']}M+ sono obbligatori almeno 2 anni."
    if anni not in (1, 2, 3):
        return "Anni non validi."
    return None
