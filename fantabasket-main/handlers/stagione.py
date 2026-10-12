"""
Cambio di stagione, rookie scale e RFA (v3.11.0).

Regole (regolamento + decisioni di Luca, 12/10/2026):
  - anni residui calcolati: anni_originali − (stagione − stagione_firma), 0 = x0;
  - un x0 resta in squadra durante l'offseason, si può scambiare, ma NON pesa su cap né
    slot; l'unico x0 che pesa è l'RFA dichiarato (cap sì, slot no);
  - ogni cambio di importo = contratto nuovo (vecchio attivo=FALSE + movimento).

Rookie scale (tabella `rookie_scale` di settings, per pick: I x2, II x1, III x2, IV x1):
  - entrata nel II anno: contratto nuovo con l'importo del II anno, x1 (automatico; se
    l'importo è lo stesso, come per le pick basse, resta il contratto x2 del I anno);
  - fine II anno: x0 → rinnovo rookie a scala III o Doncic (GM), oppure RFA o FA;
  - entrata nel IV anno: se il contratto III-IV è sotto l'importo del IV anno (rinnovo
    di scala), contratto nuovo con quell'importo, x1; una Doncic è più alta e resta;
  - fine IV anno: Doncic d'ufficio sulla fantamedia del III/IV anno → contratto x0
    "normale" (max tra importo attuale e Doncic): da lì rinnovo normale, RFA o FA.
  Doncic: X = massima fantamedia delle due stagioni, per difetto all'intero;
    20 ≤ X ≤ 24 → 12 + 0,6·(X−20); X ≥ 25 → 15 + 0,4·(X−25); risultato per eccesso;
    vale solo se più alta della tabella.

Passaggi di fase:
  offseason-rinnovi  stagione +1 (admin_panel), applica_stagione(): rookie al II/IV anno
                     e fine scala (da qui gli x0 smettono di pesare); pick dell'anno +6
  durante i rinnovi  /rinnovo_rookie e /dichiara_rfa (GM; admin dal pannello)
  offseason-rfa      le aste RFA dei dichiarati le apre il bot aste
  offseason-fa       scadenza_x0(): gli x0 non RFA scadono (attivo=FALSE + 'expired')
  regular-season-fa  report_inizio_rs(): sotto il floor / sopra il tetto → gruppo admin
"""
import html
import logging
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import settings
import teams as tm
from settings import solo_privato

logger = logging.getLogger(__name__)

FASE_RINNOVI = "offseason-rinnovi"
FASI_ADMIN_RINNOVI = {"offseason-rinnovi", "offseason-draft"}


# Si entra nella stagione nuova passando ai rinnovi da una di queste fasi. Tornando ai
# rinnovi da una fase successiva (draft, RFA, FA, ruoli: un errore corretto con "Salta a")
# la stagione resta quella: prima si sarebbe andati avanti di un anno.
FASI_PRIMA_DEI_RINNOVI = {"regular-season-fa", "regular-season-deadline", "playoff", "offseason-break"}


def nuova_stagione(fase_vecchia: str, nuova_fase: str) -> bool:
    return nuova_fase == FASE_RINNOVI and fase_vecchia in FASI_PRIMA_DEI_RINNOVI


class StagioneErrore(Exception):
    """Operazione non consentita: il messaggio va mostrato così com'è."""


# ── regole ─────────────────────────────────────────────────────────────────────

def scala(pick_numero: int) -> list[dict] | None:
    """Le 4 voci della rookie scale per quella pick ({'anno', 'imp', 'anni'})."""
    for fascia, valori in settings.get().get("rookie_scale", {}).items():
        lim = fascia.split("-")
        if int(lim[0]) <= int(pick_numero) <= int(lim[-1]):
            return valori
    return None


def importo_scala(pick_numero: int, indice: int) -> int | None:
    """Importo della scala all'anno `indice` (0 = I anno … 3 = IV anno)."""
    v = scala(pick_numero)
    return int(v[indice]["imp"]) if v and len(v) > indice else None


def doncic(fantamedia) -> int | None:
    """Contratto Doncic per quella fantamedia, None sotto 20. X per difetto all'intero,
    risultato per eccesso (con aritmetica intera: niente errori di arrotondamento)."""
    if fantamedia is None:
        return None
    x = math.floor(float(fantamedia))
    s1, s2 = settings.doncic_soglia_1(), settings.doncic_soglia_2()      # 20 e 25
    if x < s1:
        return None
    if x < s2:
        return 12 + (6 * (x - s1) + 9) // 10      # 12 + ⌈0,6·(X−20)⌉
    return 15 + (4 * (x - s2) + 9) // 10          # 15 + ⌈0,4·(X−25)⌉


def fantamedia_max(giocatore_id: int, stagioni_lega: list[int]) -> float | None:
    """Massima fantamedia del giocatore nelle stagioni di lega indicate (2026 = 2026-27,
    che per Basketball-Reference è la stagione 2027)."""
    valori = []
    for s in stagioni_lega:
        fm = db.fantamedie([giocatore_id], str(int(s) + 1)).get(giocatore_id)
        if fm is not None:
            valori.append(float(fm))
    return max(valori) if valori else None


def _contratto_str(importo, anni) -> str:
    return f"{importo}x{anni}"


# ── piano del cambio di stagione ───────────────────────────────────────────────

def _rookie_attivi(cur) -> list[dict]:
    cur.execute("""SELECT c.*, r.anno_firma, r.pick_numero, r.round, g.nome_common
                   FROM contratti c
                   JOIN rookie r ON r.giocatore_id = c.giocatore_id AND r.firmato
                   JOIN giocatori g ON g.id = c.giocatore_id
                   WHERE c.attivo AND c.tipo = 'rookie' AND r.anno_firma IS NOT NULL
                   ORDER BY c.team_id, g.nome_common""")
    return cur.fetchall()


def _calcola_piano(cur, stagione: int) -> dict:
    """Cosa succede ai rookie entrando nella stagione `stagione` (già incrementata). Elenca
    tutti i rookie che cambiano anno di scala, anche quelli che restano com'erano (con il
    motivo), così il report si controlla giocatore per giocatore."""
    piano = {"secondo_anno": [], "secondo_anno_uguali": [], "quarto_anno": [], "quarto_anno_uguali": [],
             "fine_scala": [], "da_rinnovare": [], "anomalie": []}
    for c in _rookie_attivi(cur):
        k = stagione - int(c["anno_firma"])          # 0 = I anno … 3 = IV anno
        residui = db.anni_residui(c, stagione)
        sf, anni, imp_ora = int(c["stagione_firma"]), int(c["anni_originali"]), int(c["importo"])
        base = {"contratto_id": c["id"], "giocatore_id": c["giocatore_id"], "nome": c["nome_common"],
                "team_id": c["team_id"], "pick": c["pick_numero"], "importo": imp_ora,
                "da": _contratto_str(imp_ora, max(residui, 0))}
        strano = (f"{c['nome_common']} ({c['team_id']}): contratto rookie {imp_ora}x{anni} firmato nel {sf} "
                  f"non riconosciuto al {k + 1}° anno di scala")
        if k == 1:
            if sf == stagione and anni == 1:
                continue                          # già passato al II anno (passaggio ripetuto)
            if sf != int(c["anno_firma"]):
                piano["anomalie"].append(strano)
                continue
            imp = importo_scala(c["pick_numero"], 1)
            if imp is None:
                piano["anomalie"].append(f"{c['nome_common']}: pick {c['pick_numero']} fuori dalla rookie scale")
            elif imp == imp_ora:
                # pick basse: stesso importo, il contratto x2 del I anno vale anche per il II
                piano["secondo_anno_uguali"].append({**base, "motivo": "stesso importo in tabella"})
            else:
                piano["secondo_anno"].append({**base, "importo_nuovo": imp, "anni_nuovi": 1, "tipo": "rookie",
                                              "a": _contratto_str(imp, 1), "nota": f"Rookie scale: II anno {imp}x1"})
        elif k == 2:
            if residui <= 0:
                # proposta del rinnovo rookie (la decide il GM): scala III o Doncic se più alta
                piano["da_rinnovare"].append({**base, "proposta": proposta_rinnovo_rookie(c, stagione)})
            else:
                piano["anomalie"].append(strano)
        elif k == 3:
            if sf == stagione and anni == 1:
                continue                          # già passato al IV anno (passaggio ripetuto)
            if not (sf == stagione - 1 and anni == 2):
                piano["anomalie"].append(strano)
                continue
            # IV anno: mai sotto la tabella (Luca, 12/10/2026). Il rinnovo di scala sale
            # all'importo del IV anno; una Doncic è già più alta e resta com'è (x1)
            scala_iv = importo_scala(c["pick_numero"], 3)
            if scala_iv is None:
                piano["anomalie"].append(f"{c['nome_common']}: pick {c['pick_numero']} fuori dalla rookie scale")
            elif imp_ora < scala_iv:
                piano["quarto_anno"].append({**base, "importo_nuovo": scala_iv, "anni_nuovi": 1, "tipo": "rookie",
                                             "a": _contratto_str(scala_iv, 1), "nota": f"Rookie scale: IV anno {scala_iv}x1"})
            else:
                motivo = (f"Doncic, la tabella dice {scala_iv}" if imp_ora > scala_iv else "stesso importo in tabella")
                piano["quarto_anno_uguali"].append({**base, "motivo": motivo})
        elif k == 4:
            if residui > 0:
                piano["anomalie"].append(strano)
                continue
            fm = fantamedia_max(c["giocatore_id"], [stagione - 2, stagione - 1])
            d = doncic(fm)
            imp = max(imp_ora, d or 0)
            nota = (f"Fine rookie scale: Doncic d'ufficio (fantamedia {math.floor(fm)}) {imp}x0"
                    if d and d > imp_ora else f"Fine rookie scale: {imp}x0")
            piano["fine_scala"].append({**base, "importo_nuovo": imp, "anni_nuovi": 0, "tipo": "normale",
                                        "a": _contratto_str(imp, 0), "nota": nota, "fantamedia": fm})
        elif k >= 5 or k < 0:
            piano["anomalie"].append(f"{c['nome_common']} ({c['team_id']}): contratto rookie al {k + 1}° anno di scala")
    return piano


def piano_stagione(stagione: int) -> dict:
    """Piano in sola lettura (anteprima del cambio di stagione e /dev_stagione), più gli
    x0 che si creano per squadra."""
    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            piano = _calcola_piano(cur, stagione)
            piano["x0"] = _x0_per_squadra(cur, stagione)
    return piano


def _x0_per_squadra(cur, stagione: int) -> list[dict]:
    cur.execute("""SELECT c.team_id, count(*) AS n, sum(c.importo) AS importi FROM contratti c
                   WHERE c.attivo AND (c.anni_originali - (%s::int - c.stagione_firma::int)) <= 0
                   GROUP BY c.team_id ORDER BY c.team_id""", (stagione,))
    return cur.fetchall()


def _nuovo_contratto(cur, voce: dict, stagione: int, tipo_mov: str, nota: str, rookie_scale: bool) -> int:
    """Chiude il contratto della voce e ne apre uno nuovo, con il movimento. Restituisce il
    nuovo contratto_id; StagioneErrore se il vecchio non è più attivo."""
    cur.execute("UPDATE contratti SET attivo = FALSE WHERE id = %s AND attivo RETURNING team_id",
                (voce["contratto_id"],))
    r = cur.fetchone()
    if not r:
        raise StagioneErrore(f"❌ Il contratto di {voce['nome']} non è più attivo.")
    team = r["team_id"] if isinstance(r, dict) else r[0]
    cur.execute("""INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (voce["giocatore_id"], team, voce["importo_nuovo"], voce["anni_nuovi"], str(stagione), voce["tipo"]))
    r = cur.fetchone()
    nuovo = r["id"] if isinstance(r, dict) else r[0]
    cur.execute("""INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, contratto_id,
                                            rookie_scale, note)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (tipo_mov, voce["giocatore_id"], team, team, str(stagione), nuovo, rookie_scale, nota))
    return nuovo


def applica_stagione(stagione: int) -> dict:
    """Esegue il piano in un'unica transazione DB. Rilanciabile: le condizioni del piano non
    valgono più per i contratti già sistemati."""
    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            piano = _calcola_piano(cur, stagione)
            for v in piano["secondo_anno"]:
                _nuovo_contratto(cur, v, stagione, "rookie_scala", f"{v['nota']} (era {v['da']})", True)
            for v in piano["quarto_anno"]:
                _nuovo_contratto(cur, v, stagione, "rookie_scala", f"{v['nota']} (era {v['da']})", True)
            for v in piano["fine_scala"]:
                _nuovo_contratto(cur, v, stagione, "rookie_fine_scala", v["nota"], True)
            # colonna informativa (dev_player, NocoDB): anno di scala = stagione − anno di firma
            cur.execute("""UPDATE rookie SET anni_scala = %s::int - anno_firma::int
                           WHERE firmato AND anno_firma IS NOT NULL""", (stagione,))
            piano["x0"] = _x0_per_squadra(cur, stagione)
    logger.warning("Cambio di stagione %s: %d al II anno, %d al IV anno, %d a fine scala, %d da rinnovare.",
                   stagione, len(piano["secondo_anno"]), len(piano["quarto_anno"]),
                   len(piano["fine_scala"]), len(piano["da_rinnovare"]))
    return piano


def _nome_team(team_id: str) -> str:
    """Nome della squadra già pronto per i messaggi HTML."""
    t = tm.get_team_by_id(team_id)
    return html.escape(t["nome"] if t else team_id)


def _n(piano: dict, chiave: str) -> int:
    return len(piano.get(chiave) or [])


def testo_piano_breve(piano: dict, titolo: str) -> str:
    """Riassunto per la conferma del cambio di fase (il messaggio deve stare in 4096 caratteri)."""
    doncic_fine = [v for v in piano.get("fine_scala", []) if "Doncic" in v.get("nota", "")]
    righe = [titolo, "",
             f"📈 Rookie al II anno: <b>{_n(piano, 'secondo_anno') + _n(piano, 'secondo_anno_uguali')}</b> "
             f"({_n(piano, 'secondo_anno')} con l'importo nuovo, {_n(piano, 'secondo_anno_uguali')} uguali)",
             f"📈 Rookie al IV anno: <b>{_n(piano, 'quarto_anno') + _n(piano, 'quarto_anno_uguali')}</b> "
             f"({_n(piano, 'quarto_anno')} con l'importo nuovo, {_n(piano, 'quarto_anno_uguali')} uguali)",
             f"🎓 Fine rookie scale → x0 normali: <b>{_n(piano, 'fine_scala')}</b>"
             + (f" (Doncic d'ufficio: {', '.join(html.escape(v['nome']) for v in doncic_fine)})" if doncic_fine else ""),
             f"🔁 Rookie a fine II anno da rinnovare: <b>{_n(piano, 'da_rinnovare')}</b>"]
    if piano.get("x0"):
        righe.append(f"⏳ Contratti x0 dopo il passaggio: <b>{sum(int(r['n']) for r in piano['x0'])}</b> "
                     f"(non pesano su cap e slot finché non vengono rinnovati o dichiarati RFA)")
    if piano.get("anomalie"):
        righe.append(f"⚠️ Da controllare: {len(piano['anomalie'])} (dettaglio con /dev_stagione)")
    righe += ["", "<i>Il dettaglio arriva nel gruppo admin dopo il passaggio.</i>"]
    return "\n".join(righe)


def _testo_proposta(v: dict) -> str:
    p = v.get("proposta") or {}
    if not p:
        return "?"
    fm = p.get("fantamedia")
    fm_txt = f"fantamedia {fm:.2f}".replace(".", ",") if fm is not None else "nessuna fantamedia"
    if p.get("doncic"):
        return f"<b>{p['importo_nuovo']}x2</b> <i>Doncic</i> ({fm_txt})"
    return f"{p['importo_nuovo']}x2 di scala ({fm_txt})"


def testo_piano(piano: dict, titolo: str) -> str:
    """Dettaglio completo: ogni rookie che cambia anno di scala, anche se l'importo resta."""
    righe = [titolo, ""]

    def cambi(voci):
        return [f"  • {html.escape(v['nome'])} ({_nome_team(v['team_id'])}): {v['da']} → {v['a']}"
                + (" <i>Doncic</i>" if "Doncic" in v.get("nota", "") else "") for v in voci]

    def uguali(voci):
        return [f"  • {html.escape(v['nome'])} ({_nome_team(v['team_id'])}): {v['da']}, resta "
                f"<i>({html.escape(v['motivo'])})</i>" for v in voci]

    for etichetta, k_nuovi, k_uguali in (("📈 Rookie dal I al II anno", "secondo_anno", "secondo_anno_uguali"),
                                         ("📈 Rookie dal III al IV anno", "quarto_anno", "quarto_anno_uguali")):
        nuovi, stessi = piano.get(k_nuovi) or [], piano.get(k_uguali) or []
        if nuovi or stessi:
            righe.append(f"<b>{etichetta}</b> ({len(nuovi) + len(stessi)}: {len(nuovi)} con l'importo nuovo, "
                         f"{len(stessi)} uguali)")
            righe += cambi(nuovi) + uguali(stessi)
            righe.append("")
    if piano.get("fine_scala"):
        righe.append(f"<b>🎓 Fine rookie scale (x0, da rinnovare come normali)</b> ({len(piano['fine_scala'])})")
        righe += cambi(piano["fine_scala"])
        righe.append("")
    if piano.get("da_rinnovare"):
        righe.append(f"<b>🔁 Rookie a fine II anno (x0: rinnovo rookie, RFA o FA)</b> ({len(piano['da_rinnovare'])})")
        righe.append("  <i>Rinnovo proposto: scala del III anno, o Doncic se più alta (sulla fantamedia migliore del "
                     "I e II anno). Lo decide il GM.</i>")
        righe += [f"  • {html.escape(v['nome'])} ({_nome_team(v['team_id'])}): {v['da']} → rinnovo {_testo_proposta(v)}"
                  for v in piano["da_rinnovare"]]
        righe.append("")
    if piano.get("x0"):
        tot = sum(int(r["n"]) for r in piano["x0"])
        righe.append(f"<b>⏳ Contratti x0</b>: {tot} (non pesano su cap e slot; scadono all'inizio della FA se "
                     f"non rinnovati o dichiarati RFA)")
        righe.append("  " + " · ".join(f"{_nome_team(r['team_id'])} {r['n']}" for r in piano["x0"]))
    if piano.get("anomalie"):
        righe.append("")
        righe.append("<b>⚠️ Da controllare</b>")
        righe += [f"  • {html.escape(a)}" for a in piano["anomalie"]]
    return "\n".join(righe)


# ── altri passaggi di fase ─────────────────────────────────────────────────────

def x0_in_scadenza(stagione: int) -> list[dict]:
    """x0 attivi non dichiarati RFA (quelli che scadono entrando in FA)."""
    return db._q(f"""SELECT c.*, g.nome_common FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                     WHERE c.attivo AND NOT ({db.SQL_IN_CORSO}) AND NOT {db.SQL_RFA}
                     ORDER BY c.team_id, g.nome_common""", (str(stagione), str(stagione)), many=True) or []


def scadenza_x0(stagione: int) -> list[dict]:
    """Entrata in offseason-fa: gli x0 non dichiarati RFA scadono (attivo=FALSE + 'expired'),
    in un'unica transazione. Tornano free agent."""
    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""UPDATE contratti c SET attivo = FALSE
                            WHERE c.attivo AND NOT ({db.SQL_IN_CORSO}) AND NOT {db.SQL_RFA}
                            RETURNING c.id, c.giocatore_id, c.team_id, c.importo""",
                        (str(stagione), str(stagione)))
            scaduti = cur.fetchall()
            for c in scaduti:
                cur.execute("""INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione,
                                                        contratto_id, note)
                               VALUES ('expired', %s, %s, NULL, %s, %s, 'Contratto scaduto (x0)')""",
                            (c["giocatore_id"], c["team_id"], str(stagione), c["id"]))
    for c in scaduti:
        c["nome_common"] = (db.get_giocatore(c["giocatore_id"]) or {}).get("nome_common", str(c["giocatore_id"]))
    logger.warning("Inizio FA %s: %d contratti x0 scaduti.", stagione, len(scaduti))
    return scaduti


def crea_pick_anno(anno: int) -> int:
    """Pick (1st e 2nd) dell'anno per tutte le squadre, se mancano, con il loro movimento
    'creata' nel registro. Si creano al cambio di stagione (entrando nei rinnovi della
    stagione S, l'anno S+6), come deciso con Luca: fino al draft di S le annate
    scambiabili sono quindi 7 (S ancora da fare, poi S+1 … S+6)."""
    registra = db.storico_pick_diritti_presente()
    nuove = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for t in tm.get_all_teams():
                for rnd in (1, 2):
                    cur.execute("""INSERT INTO pick (proprietario_orig, proprietario_att, anno, round)
                                   SELECT %s, %s, %s, %s WHERE NOT EXISTS (
                                       SELECT 1 FROM pick WHERE proprietario_orig = %s AND anno = %s AND round = %s)
                                   RETURNING id""",
                                (t["id"], t["id"], str(anno), rnd, t["id"], str(anno), rnd))
                    r = cur.fetchone()
                    if r:
                        nuove += 1
                        if registra:
                            cur.execute("""INSERT INTO transazioni (oggetto, tipo, pick_id, team_id_a, stagione, note)
                                           VALUES ('pick', 'creata', %s, %s, %s, %s)""",
                                        (r[0], t["id"], settings.stagione_corrente(), f"Pick {anno} creata"))
    if nuove:
        logger.warning("Create %d pick del draft %s.", nuove, anno)
    return nuove


def testo_report_inizio_rs() -> str | None:
    """Squadre sotto il salary floor o sopra il tetto all'inizio della regular season, con
    il comando suggerito. Niente automatismi: decidono gli admin."""
    stagione = settings.stagione_corrente()
    floor, righe = settings.salary_floor(), []
    for t in tm.get_all_teams():
        cap = db.cap_occupato_team(t["id"], stagione)
        tetto = settings.cap_limite_team(t)
        if cap < floor:
            mancano = floor - cap
            pen = 2 * mancano
            gia = int(t.get("cap_penalizzato") or 0)
            righe.append(f"• <b>{html.escape(t['nome'])}</b>: {cap}M, {mancano}M sotto il floor → penalità {pen}M "
                         f"(2M per milione)\n  <code>/set_cap_penalizzato {t['id']} {gia + pen}</code>"
                         + (f" <i>(ha già {gia}M)</i>" if gia else ""))
        elif cap > tetto:
            righe.append(f"• <b>{html.escape(t['nome'])}</b>: {cap}M, oltre il tetto di {tetto}M di {cap - tetto}M "
                         f"— va riportata in regola (tagli o trade)")
    if not righe:
        return None
    return "🏁 <b>Inizio regular season: cap da sistemare</b>\n\n" + "\n".join(righe)


async def dopo_cambio_fase(bot, fase_vecchia: str, nuova_fase: str) -> str:
    """Passaggi automatici legati alla fase. Restituisce un riepilogo per l'admin (o '').
    Ogni passaggio è a sé: se uno fallisce gli altri vanno avanti, e tutti si possono
    ripetere con /dev_stagione rifai (quello che è già fatto non si rifà)."""
    if nuova_fase == fase_vecchia:
        return ""
    stagione = int(settings.stagione_corrente())
    gruppo = settings.admin_group_id()
    note = []

    async def passo(nome, funzione):
        try:
            await funzione()
        except Exception as e:
            logger.exception("Passaggio di fase '%s' (%s → %s)", nome, fase_vecchia, nuova_fase)
            note.append(f"\n🚨 {nome}: NON riuscito ({html.escape(str(e))}) — /dev_stagione rifai per riprovare")
            try:
                from types import SimpleNamespace
                from handlers.helpers import log_warn
                await log_warn(SimpleNamespace(bot=bot), f"🚨 Passaggio di fase '{nome}' ({fase_vecchia} → {nuova_fase}) "
                                                         f"fallito: {html.escape(str(e))}")
            except Exception:
                pass

    async def rookie():
        piano = applica_stagione(stagione)       # rilanciabile: tornando ai rinnovi non rifà niente
        cambiati = len(piano["secondo_anno"]) + len(piano["quarto_anno"]) + len(piano["fine_scala"])
        if cambiati or nuova_stagione(fase_vecchia, nuova_fase):
            note.append(f"\n📈 Rookie: importo nuovo per {_n(piano, 'secondo_anno')} al II anno e "
                        f"{_n(piano, 'quarto_anno')} al IV, {_n(piano, 'fine_scala')} a fine scala, "
                        f"{_n(piano, 'da_rinnovare')} da rinnovare")
            if gruppo:
                from shared.messaggi import manda_lungo
                await manda_lungo(bot, gruppo, testo_piano(piano, f"📅 <b>Stagione {stagione}: contratti aggiornati</b>"),
                                  f"stagione-{stagione}", riassunto=riassunto_piano(piano, stagione))

    async def pick():
        # pick dell'anno + 6 al cambio di stagione (deciso con Luca il 12/10/2026)
        n = crea_pick_anno(stagione + 6)
        if n:
            note.append(f"\n🎟 Create le pick del draft {stagione + 6} ({n})")
            try:
                import gas_client
                gas_client.sync_scelte()
            except Exception as e:
                logger.warning("Sync scelte dopo le pick nuove: %s", e)

    async def scadenze():
        scaduti = scadenza_x0(stagione)
        note.append(f"\n⌛ Contratti x0 scaduti: {len(scaduti)}")
        if scaduti:
            ch = settings.load_globals().get("main_channel_id")
            if ch:
                await _invia_lungo(bot, ch, testo_scaduti(scaduti))
        try:
            import gas_client
            gas_client.sync_all()
        except Exception as e:
            logger.warning("Sync fogli dopo le scadenze: %s", e)

    async def report_rs():
        testo = testo_report_inizio_rs()
        if testo and gruppo:
            from shared.messaggi import manda_lungo
            await manda_lungo(bot, gruppo, testo, "inizio-regular-season")

    if nuova_fase == FASE_RINNOVI:
        await passo("rookie scale", rookie)
        await passo("pick nuove", pick)
    elif nuova_fase == "offseason-fa":
        await passo("scadenza degli x0", scadenze)
    elif nuova_fase == "regular-season-fa":
        await passo("report di inizio regular season", report_rs)
    return "".join(note)


def riassunto_piano(piano: dict, stagione: int) -> str:
    """Una riga per la didascalia del file con il dettaglio del cambio di stagione."""
    doncic_fine = sum(1 for v in piano.get("fine_scala", []) if "Doncic" in v.get("nota", ""))
    x0 = sum(int(r["n"]) for r in piano.get("x0") or [])
    return (f"📅 <b>Stagione {stagione}: contratti aggiornati</b>\n"
            f"📈 II anno: {_n(piano, 'secondo_anno')} importi nuovi, {_n(piano, 'secondo_anno_uguali')} uguali · "
            f"IV anno: {_n(piano, 'quarto_anno')} importi nuovi, {_n(piano, 'quarto_anno_uguali')} uguali · "
            f"{_n(piano, 'fine_scala')} a fine scala ({doncic_fine} con Doncic) · "
            f"{_n(piano, 'da_rinnovare')} da rinnovare · {x0} contratti x0")


def testo_scaduti(scaduti: list[dict]) -> str:
    """Annuncio sul canale degli x0 scaduti, raggruppati per squadra."""
    per_team: dict[str, list[str]] = {}
    for c in scaduti:
        per_team.setdefault(c["team_id"], []).append(html.escape(c["nome_common"]))
    righe = [f"⌛ <b>Contratti scaduti: tornano free agent</b> ({len(scaduti)})", ""]
    righe += [f"• <b>{_nome_team(t)}</b>: {', '.join(sorted(nomi))}" for t, nomi in sorted(per_team.items())]
    return "\n".join(righe)


async def _invia_lungo(bot, chat_id, testo: str):
    """Messaggi per il canale (non amministrativi): spezzati tra una riga e l'altra."""
    blocco = ""
    for riga in testo.split("\n"):
        if len(blocco) + len(riga) > 3900:
            await bot.send_message(chat_id=chat_id, text=blocco, parse_mode="HTML")
            blocco = ""
        blocco += riga + "\n"
    if blocco.strip():
        await bot.send_message(chat_id=chat_id, text=blocco, parse_mode="HTML")


def anteprima_fase(fase_vecchia: str, nuova_fase: str) -> str | None:
    """Testo di conferma per i passaggi che cambiano i contratti (None = nessuna anteprima)."""
    s = int(settings.stagione_corrente())
    if nuova_stagione(fase_vecchia, nuova_fase):
        return testo_piano_breve(piano_stagione(s + 1), f"📅 <b>Si passa alla stagione {s + 1}</b> — cosa succede ai contratti")
    if nuova_fase == "offseason-fa" and fase_vecchia != "offseason-fa":
        x0 = x0_in_scadenza(s)
        righe = [f"⌛ <b>Inizio free agency</b> — scadono {len(x0)} contratti x0 non rinnovati e non RFA:", ""]
        righe += [f"• {html.escape(c['nome_common'])} ({_nome_team(c['team_id'])}) {c['importo']}M"
                  for c in x0[:40]]
        if len(x0) > 40:
            righe.append(f"… e altri {len(x0) - 40} (l'elenco completo esce sul canale)")
        righe += ["", "<i>Gli RFA dichiarati restano fino alla fine della loro asta.</i>"]
        return "\n".join(righe)
    return None


# ── rinnovo rookie (fine II anno) ──────────────────────────────────────────────

def candidati_rinnovo_rookie(team_id: str) -> list[dict]:
    """Rookie della squadra a fine II anno (x0), non dichiarati RFA, con la proposta."""
    s = int(settings.stagione_corrente())
    out = []
    for c in db._q("""SELECT c.*, r.anno_firma, r.pick_numero, g.nome_common FROM contratti c
                      JOIN rookie r ON r.giocatore_id = c.giocatore_id AND r.firmato
                      JOIN giocatori g ON g.id = c.giocatore_id
                      WHERE c.team_id = %s AND c.attivo AND c.tipo = 'rookie' AND r.anno_firma IS NOT NULL
                      ORDER BY g.nome_common""", (team_id,), many=True) or []:
        if s - int(c["anno_firma"]) == 2 and db.anni_residui(c, s) <= 0 and not db.rfa_dichiarato(c["giocatore_id"], str(s)):
            out.append({**c, **proposta_rinnovo_rookie(c, s)})
    return out


def proposta_rinnovo_rookie(c: dict, stagione: int) -> dict:
    """Contratto del rinnovo rookie: scala III anno x2, oppure Doncic se più alta."""
    scala_iii = importo_scala(c["pick_numero"], 2) or 0
    fm = fantamedia_max(c["giocatore_id"], [stagione - 2, stagione - 1])
    d = doncic(fm)
    if d and d > scala_iii:
        return {"importo_nuovo": d, "anni_nuovi": 2, "doncic": True, "fantamedia": fm,
                "spiegazione": f"Doncic: fantamedia {fm:.2f} → {math.floor(fm)} → {d}M (scala {scala_iii}M)"}
    spieg = f"scala III anno {scala_iii}M" + (f" (fantamedia {fm:.2f}: la Doncic non supera la scala)"
                                              if fm is not None else " (nessuna fantamedia)")
    return {"importo_nuovo": scala_iii, "anni_nuovi": 2, "doncic": False, "fantamedia": fm, "spiegazione": spieg}


def esegui_rinnovo_rookie(team_id: str, giocatore_id: int) -> dict:
    """Rinnovo rookie III-IV: contratto nuovo (tipo rookie, x2), movimento 'renewed'."""
    import psycopg2.extras
    team = tm.get_team_by_id(team_id)
    s = int(settings.stagione_corrente())
    voce = next((c for c in candidati_rinnovo_rookie(team_id) if c["giocatore_id"] == giocatore_id), None)
    if not voce:
        raise StagioneErrore("❌ Il giocatore non è un rookie da rinnovare per questa squadra (già rinnovato, "
                             "dichiarato RFA, o non a fine II anno).")
    cap_lib = settings.cap_limite_team(team) - db.cap_occupato_team(team_id, str(s))
    if cap_lib < voce["importo_nuovo"]:
        raise StagioneErrore(f"❌ Cap insufficiente: liberi {cap_lib}M, rinnovo {voce['importo_nuovo']}M.")
    if db.slot_occupati(db.get_roster_team(team_id) or []) >= settings.max_roster():
        raise StagioneErrore(f"❌ Roster pieno ({settings.max_roster()}): libera uno slot prima di rinnovare.")
    v = {"contratto_id": voce["id"], "giocatore_id": giocatore_id, "nome": voce["nome_common"],
         "importo_nuovo": voce["importo_nuovo"], "anni_nuovi": 2, "tipo": "rookie"}
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _nuovo_contratto(cur, v, s, "renewed", f"Rinnovo rookie III-IV: {voce['spiegazione']}", True)
    return voce


# ── dichiarazione RFA ──────────────────────────────────────────────────────────

def candidati_rfa(team_id: str) -> list[dict]:
    """x0 della squadra (contratti finiti): possono essere dichiarati RFA."""
    return [r for r in db.get_roster_team(team_id) or [] if r.get("x0")]


def dichiara_rfa(team_id: str, giocatore_id: int, da: str) -> dict:
    """Dichiara l'RFA della squadra (sostituisce quello di prima). Solo x0."""
    s = settings.stagione_corrente()
    c = next((r for r in candidati_rfa(team_id) if r["giocatore_id"] == giocatore_id), None)
    if not c:
        raise StagioneErrore("❌ Si può dichiarare RFA solo un giocatore della squadra con il contratto finito (x0).")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE rfa_dichiarati SET stato = 'revocata', chiuso = NOW() "
                        "WHERE stagione = %s AND stato = 'attiva' AND (team_id = %s OR giocatore_id = %s)",
                        (s, team_id, giocatore_id))
            cur.execute("INSERT INTO rfa_dichiarati (stagione, team_id, giocatore_id, contratto_id, da) "
                        "VALUES (%s, %s, %s, %s, %s)", (s, team_id, giocatore_id, c["contratto_id"], da))
    return c


def revoca_rfa(team_id: str) -> dict | None:
    s = settings.stagione_corrente()
    prima = db.rfa_squadra(team_id, s)
    db._q("UPDATE rfa_dichiarati SET stato = 'revocata', chiuso = NOW() "
          "WHERE stagione = %s AND team_id = %s AND stato = 'attiva'", (s, team_id))
    return prima


# ── interfaccia (GM: sg:… · admin: sga:<team>:…) ──────────────────────────────

def _cb(admin_team: str | None, *parti) -> str:
    return ":".join(["sga", admin_team, *parti] if admin_team else ["sg", *parti])


def _testo_rinnovi(team: dict, admin_team: str | None) -> tuple[str, InlineKeyboardMarkup]:
    cand = candidati_rinnovo_rookie(team["id"])
    if not cand:
        testo = (f"🔁 <b>Rinnovi rookie — {html.escape(team['nome'])}</b>\n\n"
                 f"Nessun rookie a fine II anno da rinnovare.")
        return testo, None
    righe = [f"🔁 <b>Rinnovi rookie — {html.escape(team['nome'])}</b>",
             "<i>Rookie a fine II anno (x0). Se non li rinnovi puoi dichiararli RFA, altrimenti "
             "all'inizio della FA tornano free agent. Rinnovi illimitati, non contano nei 2.</i>", ""]
    kb = []
    for c in cand:
        righe.append(f"• <b>{html.escape(c['nome_common'])}</b> {c['importo']}x0 → "
                     f"<b>{c['importo_nuovo']}x2</b> ({html.escape(c['spiegazione'])})")
        kb.append([InlineKeyboardButton(f"{c['nome_common']} → {c['importo_nuovo']}x2",
                                        callback_data=_cb(admin_team, "rrg", str(c["giocatore_id"])))])
    return "\n".join(righe), InlineKeyboardMarkup(kb)


def _testo_rfa(team: dict, admin_team: str | None) -> tuple[str, InlineKeyboardMarkup]:
    s = settings.stagione_corrente()
    att = db.rfa_squadra(team["id"], s)
    cand = candidati_rfa(team["id"])
    righe = [f"🔒 <b>RFA — {html.escape(team['nome'])}</b>",
             "<i>Massimo un giocatore con il contratto finito (x0). L'RFA pesa sul cap (non sugli slot) e "
             "va all'asta nella fase RFA. Fino alla fine delle aste si scambia solo con un altro RFA o verso "
             "chi non ne ha.</i>", ""]
    righe.append(f"Dichiarato: <b>{html.escape(att['nome_common'])}</b> ({att['importo']}M)" if att
                 else "Dichiarato: <b>nessuno</b>")
    kb = [[InlineKeyboardButton(("✅ " if att and att["giocatore_id"] == c["giocatore_id"] else "")
                                + f"{c['nome_common']} ({c['importo_originale']}M)",
                                callback_data=_cb(admin_team, "rfag", str(c["giocatore_id"])))] for c in cand]
    if att:
        kb.append([InlineKeyboardButton("❌ Nessun RFA", callback_data=_cb(admin_team, "rfano"))])
    if not cand:
        righe.append("\nNessun giocatore con il contratto finito.")
    return "\n".join(righe), (InlineKeyboardMarkup(kb) if kb else None)


async def _annuncia(bot, testo: str):
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        try:
            await bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio canale: %s", e)


def _sync(team_id: str):
    try:
        import gas_client
        gas_client.sync_teams([team_id])
    except Exception as e:
        logger.warning("Sync fogli: %s", e)


@solo_privato
async def cmd_rinnovo_rookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    if settings.fase() != FASE_RINNOVI:
        await update.effective_message.reply_text("❌ I rinnovi rookie si fanno nella fase dei rinnovi.")
        return
    testo, kb = _testo_rinnovi(team, None)
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


@solo_privato
async def cmd_dichiara_rfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    if settings.fase() != FASE_RINNOVI:
        await update.effective_message.reply_text("❌ L'RFA si dichiara nella fase dei rinnovi.")
        return
    testo, kb = _testo_rfa(team, None)
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_stagione(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """sg:… (GM sulla propria squadra) e sga:<team>:… (admin per conto di una squadra)."""
    query = update.callback_query
    parti = query.data.split(":")
    user = query.from_user
    if parti[0] == "sga":
        if not settings.is_admin(user.id):
            await query.answer("⛔ Solo admin.", show_alert=True)
            return
        if parti[1] == "scegli":                      # sga:scegli:rr|rfa → elenco squadre
            await query.answer()
            bottoni = [InlineKeyboardButton(t["nome"], callback_data=f"sga:{t['id']}:{parti[2]}")
                       for t in tm.get_all_teams()]
            kb = [bottoni[i:i + 2] for i in range(0, len(bottoni), 2)]
            if parti[2] == "rfa":
                kb.insert(0, [InlineKeyboardButton("📋 RFA dichiarati", callback_data="sga:elenco")])
            await query.edit_message_text("Scegli la squadra:", reply_markup=InlineKeyboardMarkup(kb))
            return
        if parti[1] == "elenco":                      # sga:elenco → RFA dichiarati di tutte
            await query.answer()
            s = settings.stagione_corrente()
            righe = [f"📋 <b>RFA dichiarati — stagione {s}</b>", ""]
            for t in tm.get_all_teams():
                r = db.rfa_usata(t["id"], s)
                if r:
                    in_vigore = db.rfa_squadra(t["id"], s)
                    righe.append(f"• {html.escape(t['nome'])}: <b>{html.escape(r['nome_common'])}</b>"
                                 + ("" if in_vigore else " <i>(asta conclusa)</i>"))
            if len(righe) == 2:
                righe.append("Nessuno.")
            await query.edit_message_text("\n".join(righe), parse_mode="HTML")
            return
        admin_team, azione, resto = parti[1], parti[2], parti[3:]
        team = tm.get_team_by_id(admin_team)
        if settings.fase() not in FASI_ADMIN_RINNOVI:
            await query.answer("❌ Solo nelle fasi rinnovi e draft.", show_alert=True)
            return
        chi = f"un admin ({user.first_name or user.username})"
    else:
        admin_team, azione, resto = None, parti[1], parti[2:]
        team = tm.get_team_by_gm(user.id)
        if not team:
            await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
            return
        if settings.fase() != FASE_RINNOVI:
            await query.answer("❌ Solo nella fase dei rinnovi.", show_alert=True)
            return
        chi = None
    await query.answer()
    bot = query.get_bot()

    try:
        if azione == "rr":
            testo, kb = _testo_rinnovi(team, admin_team)
            await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        elif azione == "rrg":
            gid = int(resto[0])
            c = next((x for x in candidati_rinnovo_rookie(team["id"]) if x["giocatore_id"] == gid), None)
            if not c:
                raise StagioneErrore("❌ Rookie non più da rinnovare.")
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Rinnova", callback_data=_cb(admin_team, "rrok", str(gid))),
                InlineKeyboardButton("← Indietro", callback_data=_cb(admin_team, "rr"))]])
            await query.edit_message_text(
                f"🔁 <b>Rinnovo rookie — {html.escape(c['nome_common'])}</b>\n\n"
                f"Contratto attuale: {c['importo']}x0 (fine II anno)\n"
                f"Nuovo contratto: <b>{c['importo_nuovo']}x2</b> (III e IV anno)\n"
                f"<i>{html.escape(c['spiegazione'])}</i>", parse_mode="HTML", reply_markup=kb)
        elif azione == "rrok":
            c = esegui_rinnovo_rookie(team["id"], int(resto[0]))
            await query.edit_message_text(f"✅ <b>{html.escape(c['nome_common'])}</b> rinnovato: "
                                          f"<b>{c['importo_nuovo']}x2</b>.", parse_mode="HTML")
            await _annuncia(bot, f"🔁 <b>{html.escape(team.get('gm_nome', team['nome']))}</b> rinnova il rookie "
                                 f"<b>{html.escape(c['nome_common'])}</b>: {c['importo_nuovo']}x2"
                                 + (" <i>(Doncic)</i>" if c["doncic"] else "")
                                 + (f"\n<i>Registrato da {chi}</i>" if chi else ""))
            if chi:
                await _avvisa_gm(bot, team, f"🛠 {chi} ha rinnovato il rookie <b>{html.escape(c['nome_common'])}</b>: "
                                            f"{c['importo_nuovo']}x2.")
            _sync(team["id"])
        elif azione == "rfa":
            testo, kb = _testo_rfa(team, admin_team)
            await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        elif azione == "rfag":
            gid = int(resto[0])
            c = next((x for x in candidati_rfa(team["id"]) if x["giocatore_id"] == gid), None)
            if not c:
                raise StagioneErrore("❌ Giocatore non più dichiarabile.")
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Dichiara RFA", callback_data=_cb(admin_team, "rfaok", str(gid))),
                InlineKeyboardButton("← Indietro", callback_data=_cb(admin_team, "rfa"))]])
            att = db.rfa_squadra(team["id"], settings.stagione_corrente())
            await query.edit_message_text(
                f"🔒 Dichiari RFA <b>{html.escape(c['nome_common'])}</b> ({c['importo_originale']}M)?\n"
                + (f"<i>Sostituisce {html.escape(att['nome_common'])}.</i>\n" if att and att["giocatore_id"] != gid else "")
                + f"\nPeserà {c['importo_originale']}M sul cap finché la sua asta non è conclusa.",
                parse_mode="HTML", reply_markup=kb)
        elif azione == "rfaok":
            c = dichiara_rfa(team["id"], int(resto[0]), chi or f"GM {user.id}")
            await query.edit_message_text(f"✅ <b>{html.escape(c['nome_common'])}</b> dichiarato RFA.", parse_mode="HTML")
            await _annuncia(bot, f"🔒 <b>{html.escape(team.get('gm_nome', team['nome']))}</b> dichiara RFA "
                                 f"<b>{html.escape(c['nome_common'])}</b> ({c['importo_originale']}M)"
                                 + (f"\n<i>Registrato da {chi}</i>" if chi else ""))
            if chi:
                await _avvisa_gm(bot, team, f"🛠 {chi} ha dichiarato RFA <b>{html.escape(c['nome_common'])}</b>.")
            _sync(team["id"])
        elif azione == "rfano":
            prima = revoca_rfa(team["id"])
            await query.edit_message_text("✅ Nessun RFA dichiarato.")
            if prima:
                await _annuncia(bot, f"🔓 <b>{html.escape(team.get('gm_nome', team['nome']))}</b> ritira la "
                                     f"dichiarazione RFA di <b>{html.escape(prima['nome_common'])}</b>")
            _sync(team["id"])
    except StagioneErrore as e:
        await query.edit_message_text(str(e))


async def _avvisa_gm(bot, team: dict, testo: str):
    for gm in team.get("gm_ids", []):
        try:
            await bot.send_message(chat_id=int(gm), text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Avviso al GM: %s", e)


async def cmd_dev_stagione(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dev_stagione → anteprima del prossimo cambio di stagione (sola lettura).
    /dev_stagione rifai → ripete i passaggi automatici della fase in corso (se al cambio di
    fase sono falliti): rookie della stagione, pick nuove, scadenza degli x0, report. Sono
    tutti rilanciabili: quello che è già stato fatto non si rifà."""
    if update.effective_user.id != settings.dev_id():
        return
    s = int(settings.stagione_corrente())
    bot = update.get_bot()
    if context.args and context.args[0] == "rifai":
        nota = await dopo_cambio_fase(bot, "manuale", settings.fase())
        await update.effective_message.reply_text(
            f"🔁 Passaggi della fase <b>{settings.fase()}</b> (stagione {s}) ripetuti.{nota or ' Niente da fare.'}",
            parse_mode="HTML")
        return
    piano = piano_stagione(s + 1)
    from shared.messaggi import manda_lungo
    await manda_lungo(bot, update.effective_chat.id,
                      testo_piano(piano, f"🔮 <b>Anteprima stagione {s + 1}</b> (niente viene scritto)\n"
                                         f"<i>Doncic e rinnovi sono stime con le fantamedie di oggi: al cambio di "
                                         f"stagione si usano quelle di fine stagione.</i>"),
                      f"anteprima-stagione-{s + 1}",
                      riassunto=riassunto_piano(piano, s + 1).replace("contratti aggiornati", "anteprima, niente viene scritto"))


def get_handlers() -> list:
    return [
        CommandHandler("rinnovo_rookie", cmd_rinnovo_rookie),
        CommandHandler("dichiara_rfa",   cmd_dichiara_rfa),
        CommandHandler("dev_stagione",   cmd_dev_stagione),
        CallbackQueryHandler(cb_stagione, pattern=r"^sga?:"),
    ]
