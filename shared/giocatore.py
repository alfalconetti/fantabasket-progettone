"""
La scheda di un giocatore (/player, v5.4.0 in loucabot; v7.3.0 in shared/, anche nel bot principale, Luca 09/11):
dove gioca nella realtà e nel fantabasket, con la media e le statistiche della stagione. Solo lettura: anagrafica
e contratti del bot principale, tabellini, roster e infortunati di ESPN già nel database (niente richieste a ESPN).

- NBA: squadra dei roster ESPN di adesso (se no quella dell'ultimo tabellino), status dall'ultimo
  snapshot degli infortunati (assente = sano), prossima partita.
- Fantabasket (Luca, 23/10): posizioni eleggibili sempre; se firmato squadra, ruolo della stagione
  (o la dichiarazione aperta) e stato del contratto (importo × anni rimasti e fino a quando, rookie,
  10-day, DPE, x0 e RFA); se no free agent o diritti rookie di chi.
- Stagione: partite di regular season e play-in che contano (come la media del calcolo: uno 0 con
  0 minuti no), media dei fantapunti all'ottavo, medie per partita e percentuali al tiro, media delle ultime 5.
- Ultime 5 partite.
Con più giocatori dallo stesso nome, bottoni (callback pl:<id>). I comandi li fa `handlers(scheda)`: ogni bot
passa la sua scheda (klra in loucabot la sostituisce per aggiungere il sistema).
"""
from datetime import datetime
import html
import os

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K

from shared import lettura as L
from shared.numeri import ottavi, testo as tp

def scadenza_diritti(r: dict, stagione: str) -> str:
    """Quando scadono i diritti di una 2nd non firmata (regolamento, come il bot principale:
    database.info_scadenza_diritti): 10 giorni prima della trade deadline della stagione dopo
    quella del draft. Con la deadline in globals (`trade_deadline`) la data, se no la regola
    (Luca, 23/10: prima si leggeva rookie.scadenza_diritti, un campo vecchio e sbagliato).
    "" per le prime scelte (i diritti non scadono così)."""
    from datetime import date, timedelta
    try:
        if int(r.get("round") or 0) != 2 or not r.get("anno_draft"):
            return ""
        anno_scade = int(r["anno_draft"]) + 1                 # la stagione in cui scadono (2026 → 2027-28)
    except (TypeError, ValueError):
        return ""
    stag = lambda y: f"{y}-{str(y + 1)[-2:]}"
    dl = L.globali().get("trade_deadline")
    if dl and int(stagione) == anno_scade:
        try:
            return f"scadono il {date.fromisoformat(dl) - timedelta(days=10):%d/%m/%Y}, 10 giorni prima della trade deadline"
        except ValueError:
            pass
    if int(stagione) > anno_scade:
        return "scaduti: li chiude un admin"
    return f"scadono 10 giorni prima della trade deadline del {stag(anno_scade)}"


ANNO_BOT = "2026"            # prima stagione del bot
NOTA_FIRMA_FINO_AL = 2028    # fino a quando /player spiega l'anno di firma dei contratti di prima del bot
NOTA_FIRMA = ("Il bot è nato nel 2026: i contratti firmati prima risultano firmati nel 2026-27, "
              "anche se la firma vera è di una stagione precedente.")
TIPI = (2, 5)          # regular season e play-in, come la media della stagione


def e(x) -> str:
    return html.escape(str(x), quote=False)


def cerca(testo: str) -> list[dict]:
    """Giocatori dell'anagrafica col nome indicato (anche senza id ESPN), prima quelli a roster."""
    import difflib
    n = L.norm(testo)
    if not n:
        return []
    tutti = L.q("""SELECT g.id, g.nome_common, g.espn_id,
                           EXISTS (SELECT 1 FROM contratti c WHERE c.giocatore_id = g.id AND c.attivo) AS a_roster
                    FROM giocatori g""", many=True) or []
    from shared import parole_nome as PN               # anche con le parole in un altro ordine (Luca, 31/10)
    esatti = [g for g in tutti if L.norm(g["nome_common"]) == n or PN.stesse_parole(testo, g["nome_common"])]
    trovati = esatti or [g for g in tutti if n in L.norm(g["nome_common"]) or PN.contiene_parole(testo, g["nome_common"])]
    if not trovati:
        nomi = {PN.ordinata(g["nome_common"]): g for g in tutti}
        trovati = [nomi[x] for x in difflib.get_close_matches(PN.ordinata(testo), list(nomi), n=5, cutoff=0.75)]
    return sorted(trovati, key=lambda g: (not g["a_roster"], g["espn_id"] is None, g["nome_common"]))[:8]


def _pct(fatti: int, tentati: int) -> str:
    return f"{100 * fatti / tentati:.1f}%".replace(".", ",") if tentati else "—"


def _media(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def eta(nato, oggi=None) -> int:
    from zoneinfo import ZoneInfo
    oggi = oggi or datetime.now(ZoneInfo("Europe/Rome")).date()
    return oggi.year - nato.year - ((oggi.month, oggi.day) < (nato.month, nato.day))


def partite_squadra(tab: list[dict], sq_ora: str | None, stagione: str, atleta: str | None = None) -> list[dict]:
    """Le partite finite delle sue squadre NBA nella stagione, mentre era in quella squadra: la prima
    dall'inizio della stagione, le altre dal giorno dopo l'ultima partita con la squadra prima, e mai prima
    dell'arrivo visto nei roster ESPN (nba_movimenti: firmato a stagione in corso); quella di adesso fino a
    oggi. [{espn_id, data_et, casa, trasferta, squadra}] in ordine."""
    tratti = []                                  # [(squadra, prima data, ultima data)] in ordine
    for r in tab:
        if tratti and tratti[-1][0] == r["squadra"]:
            tratti[-1][2] = r["data_et"]
        else:
            tratti.append([r["squadra"], r["data_et"], r["data_et"]])
    if sq_ora and (not tratti or tratti[-1][0] != sq_ora):
        tratti.append([sq_ora, None, None])
    if not tratti:
        return []
    arrivi = {}
    if atleta:
        for m in L.q("SELECT giorno, a FROM nba_movimenti WHERE atleta = %s AND a IS NOT NULL ORDER BY giorno",
                      (atleta,), many=True) or []:
            arrivi.setdefault(m["a"], []).append(m["giorno"])
    out = []
    for i, (sq, da, al) in enumerate(tratti):
        dal = None if i == 0 else tratti[i - 1][2]
        arrivo = [d for d in arrivi.get(sq, []) if da is None or d <= da]
        arrivato = arrivo[-1] if arrivo else None
        if arrivo:                               # entrato nel roster quel giorno: le partite da lì (comprese)
            from datetime import timedelta
            prima = arrivo[-1] - timedelta(days=1)
            dal = max(dal, prima) if dal else prima
        ultimo = i == len(tratti) - 1 and sq == sq_ora
        righe = L.q("""SELECT espn_id, data_et, casa, trasferta FROM nba_partite
                        WHERE stagione = %s AND tipo = ANY(%s) AND stato = 'STATUS_FINAL' AND %s IN (casa, trasferta)
                          AND (%s::date IS NULL OR data_et > %s) AND (%s::date IS NULL OR data_et <= %s)
                        ORDER BY inizio""",
                     (stagione, list(TIPI), sq, dal, dal, None if ultimo else al, None if ultimo else al), many=True) or []
        out += [{**x, "squadra": sq, "arrivato": arrivato} for x in righe]
    return out


def testo_su(partite: list[dict]) -> str:
    """« su 8 della squadra» · « su 8 da quando è a NYK (dal 12/12)» · « su 15 (BOS poi NYK)» (Luca, 26/10)."""
    if not partite:
        return ""
    squadre = []
    for p in partite:
        if not squadre or squadre[-1] != p["squadra"]:
            squadre.append(p["squadra"])
    if len(squadre) > 1:
        return f" su {len(partite)} ({' poi '.join(e(x) for x in squadre)})"
    if partite[0].get("arrivato"):
        return f" su {len(partite)} da quando è a {e(squadre[0])} (dal {partite[0]['arrivato']:%d/%m})"
    return f" su {len(partite)} della squadra"


def ultime(tab: list[dict], partite: list[dict], quante: int = 5) -> list[str]:
    """Le ultime partite: giocate, «non è entrato», e quelle saltate (assente dal tabellino), di fila in una
    riga sola (Luca, 25/10). Una serie di saltate conta come una voce."""
    sue = {r["partita"]: r for r in tab}
    voci = []                                    # in ordine: ("r", riga) o ("s", [partite saltate di fila])
    viste = set()
    for p in partite:
        viste.add(p["espn_id"])
        if p["espn_id"] in sue:
            voci.append(("r", sue[p["espn_id"]]))
        elif voci and voci[-1][0] == "s":
            voci[-1][1].append(p)
        else:
            voci.append(("s", [p]))
    for r in tab:                                # tabellini fuori dalle partite trovate (es. play-in): restano
        if r["partita"] not in viste:
            voci.append(("r", r))
    voci.sort(key=lambda v: (v[1]["data_et"] if v[0] == "r" else v[1][0]["data_et"]))
    out = []
    for tipo, x in voci[-quante:]:
        if tipo == "s":
            if len(x) == 1:
                p = x[0]
                dove, avv = ("vs", p["trasferta"]) if p["squadra"] == p["casa"] else ("@", p["casa"])
                out.append(f"• {p['data_et']:%d/%m} {dove} {e(avv)}: <i>saltata</i>")
            else:
                out.append(f"• dal {x[0]['data_et']:%d/%m} al {x[-1]['data_et']:%d/%m}: <i>{len(x)} partite saltate</i>")
            continue
        r = x
        avv = r["trasferta"] if r["squadra"] == r["casa"] else r["casa"]
        dove = "vs" if r["squadra"] == r["casa"] else "@"
        if not L.conta(r):
            out.append(f"• {r['data_et']:%d/%m} {dove} {e(avv)}: non è entrato")
            continue
        out.append(f"• {r['data_et']:%d/%m} {dove} {e(avv)}: {r['minuti']}′ · {r['pts']} pt · {r['oreb'] + r['dreb']} rb · "
                   f"{r['ast']} as → <b>{tp(float(r['fp']))}</b>")
    return out


def anno_prima(gid: int, stagione: str) -> str | None:
    """La media della stagione prima da Basketball-Reference (Luca, 26/10): l'ultima riga di bref di
    quella stagione (bref numera col secondo anno: la stagione 2026-27 della lega è la 2027, quella prima
    la 2026), dal nome di bref dell'anagrafica (o dal nome comune). Fantamedia coi pesi della lega."""
    try:
        r = L.q("""SELECT b.g, b.fantamedia FROM giocatori g
                    JOIN bref_stats b ON lower(b.nome_bref) IN (lower(g.nome_bref), lower(g.nome_common))
                    WHERE g.id = %s AND b.stagione = %s AND b.fantamedia IS NOT NULL
                    ORDER BY b.timestamp DESC LIMIT 1""", (gid, str(int(stagione))), one=True)
    except Exception:                            # tabelle del bot principale che mancano (prove, database vuoto)
        return None
    if not r:
        return None
    a = int(stagione)
    return (f"🗓️ Stagione {a - 1}-{str(a)[-2:]}: media <b>{tp(ottavi(float(r['fantamedia'])))}</b> fantapunti"
            + (f" in {r['g']} partite" if r.get("g") else "") + " <i>(Basketball-Reference)</i>")


FONTE = "<i>Dati NBA: tabellini, roster e infortunati di ESPN.</i>"


ULTIME_MEDIA = 5        # partite giocate per la «media delle ultime» (v87)

GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def prossima_partita(sq: str, ora: datetime | None = None) -> str:
    """v7.1.0 (Luca, 05/11): la prossima partita NBA della sua squadra, con avversario, casa/trasferta, giorno e ora
    italiana e la giornata del fantabasket in cui cade. "" se non ce n'è in calendario."""
    from datetime import timezone
    from zoneinfo import ZoneInfo
    ora = ora or datetime.now(timezone.utc)
    p = L.q("""SELECT * FROM nba_partite WHERE (casa = %s OR trasferta = %s) AND inizio > %s
                  AND stato NOT IN ('STATUS_FINAL', 'STATUS_POSTPONED', 'STATUS_CANCELED')
                ORDER BY inizio LIMIT 1""", (sq, sq, ora), one=True)
    if not p:
        return ""
    casa = p["casa"] == sq
    avv = p["trasferta"] if casa else p["casa"]
    t = p["inizio"].astimezone(ZoneInfo("Europe/Rome"))
    gg = L.q("SELECT numero FROM lega_giornate WHERE stagione = %s AND dal <= %s AND al >= %s LIMIT 1",
              (L.stagione(), p["data_et"], p["data_et"]), one=True)
    return (f"📅 Prossima: {'vs' if casa else '@'} <b>{e(avv)}</b>, {GIORNI[t.weekday()]} {t:%d/%m} ore {t:%H:%M}"
            + (f" · giornata {gg['numero']}" if gg else ""))


def scheda(gid: int) -> str:
    s = L.stagione()
    g = L.q("SELECT id, nome_common, espn_id, data_nascita FROM giocatori WHERE id = %s", (gid,), one=True)
    if not g:
        return "Giocatore non trovato."
    righe = [f"🏀 <b>{e(g['nome_common'])}</b>"]
    if g.get("data_nascita"):                    # data di nascita ed età (Luca, 25/10)
        righe.append(f"🎂 {g['data_nascita']:%d/%m/%Y} ({eta(g['data_nascita'])} anni)")
    righe.append("")
    a = g["espn_id"]

    # ── NBA ──
    if a:
        sq = (L.squadre_roster([a]).get(a) or L.ultima_squadra([a], "9999-12-31").get(a))
        ultimo = L.q("SELECT MAX(preso) AS p FROM nba_infortuni", one=True)
        inf = None
        if ultimo and ultimo["p"]:
            inf = L.q("SELECT stato, dettaglio FROM nba_infortuni WHERE atleta = %s AND preso = %s", (a, ultimo["p"]), one=True)
        stato = f" · 🩹 {e(inf['stato'])}" + (f" <i>({e(inf['dettaglio'][:80])})</i>" if inf.get("dettaglio") else "") if inf else ""
        righe.append(f"🇺🇸 NBA: <b>{e(sq) if sq else 'senza squadra'}</b>{stato}")
        pp = prossima_partita(sq) if sq else ""
        if pp:
            righe.append(pp)
    else:
        righe.append("🇺🇸 NBA: <i>non abbinato a ESPN (niente statistiche)</i>")

    # ── fantabasket (Luca, 23/10): posizioni eleggibili sempre; se firmato ruolo e stato del contratto ──
    def _q1(sql, params):
        try:
            return L.q(sql, params, one=True)
        except Exception:                      # tabella del bot principale che manca (prove, database vuoto)
            return None
    pos = _q1("SELECT posizioni FROM posizioni_attuali WHERE giocatore_id = %s", (gid,))
    eleg = [r for r in ("PG", "SG", "SF", "PF", "C") if r in set(((pos or {}).get("posizioni") or "").split(","))]
    righe.append("📋 Posizioni eleggibili: " + (f"<b>{', '.join(eleg)}</b>" if eleg else "<i>non registrate</i>"))
    c = L.q("""SELECT c.*, (SELECT r.ruolo FROM ruolo_attuale r WHERE r.giocatore_id = c.giocatore_id AND r.stagione = %s LIMIT 1) AS ruolo,
                       (SELECT d.importo_dpe FROM dpe d WHERE d.giocatore_id = c.giocatore_id AND d.team_id = c.team_id
                         AND d.stagione = %s LIMIT 1) AS importo_dpe
                FROM contratti c WHERE c.giocatore_id = %s AND c.attivo LIMIT 1""", (s, s, gid), one=True)
    if c:
        righe.append(f"🏆 Fantabasket: <b>{e(L.nome(c['team_id']))}</b>")
        # ruolo della stagione, o la dichiarazione ancora aperta
        pend = _q1("SELECT scadenza FROM ruoli_pendenti WHERE giocatore_id = %s AND team_id = %s AND stato = 'aperta' LIMIT 1",
                   (gid, c["team_id"]))
        if c.get("ruolo"):
            righe.append(f"🎽 Ruolo: <b>{e(c['ruolo'])}</b>")
        elif pend:
            righe.append(f"🎽 Ruolo: <i>da dichiarare entro {pend['scadenza'].astimezone(__import__('zoneinfo').ZoneInfo('Europe/Rome')):%d/%m %H:%M}</i>")
        else:
            righe.append("🎽 Ruolo: <i>non ancora ufficiale</i>")
        # stato del contratto
        anni = int(c["anni_originali"]) - (int(s) - int(c["stagione_firma"]))
        fine = int(c["stagione_firma"]) + int(c["anni_originali"]) - 1
        stagione_txt = lambda y: f"{y}-{str(y + 1)[-2:]}"
        if c["tipo"] == "10day":
            contratto = "10-day" + (f", firmato il {c['firmato_at']:%d/%m}" if c.get("firmato_at") else "")
        elif anni <= 0:
            rfa = _q1("SELECT 1 AS x FROM rfa_dichiarati WHERE contratto_id = %s AND stato = 'attiva'", (c["id"],))
            contratto = (f"{c['importo']}M, contratto finito (x0)" + (" · dichiarato RFA" if rfa else
                         " · a fine stagione la squadra può dichiararlo RFA"))
        else:
            contratto = (f"{c['importo']}M × {anni} {'anno' if anni == 1 else 'anni'} rimasti (fino al {stagione_txt(fine)}; "
                         f"firmato nel {stagione_txt(int(c['stagione_firma']))} per {c['anni_originali']})")
        if c["tipo"] == "rookie":
            contratto += " · contratto rookie"
        if c.get("importo_dpe") is not None:
            contratto += f" · 🏥 DPE quest'anno (pesa {c['importo_dpe']}M)"
        righe.append(f"📝 Contratto: {e(contratto)}")
        # il bot è nato nel 2026: i contratti firmati prima risultano firmati nel 2026-27 (Luca, 23/10;
        # la nota serve finché ci sono in giro contratti di prima, cioè fino al 2028)
        if c["tipo"] != "10day" and str(c["stagione_firma"]) == ANNO_BOT and datetime.now().year <= NOTA_FIRMA_FINO_AL:
            righe.append(f"<i>{NOTA_FIRMA}</i>")
    else:
        diritti = _q1("""SELECT team_id, round, anno_draft FROM rookie WHERE giocatore_id = %s AND NOT firmato
                         AND NOT diritti_scaduti ORDER BY id DESC LIMIT 1""", (gid,))
        if diritti:
            scad = scadenza_diritti(diritti, s)
            righe.append(f"🏆 Fantabasket: <b>svincolato</b>, diritti rookie di <b>{e(L.nome(diritti['team_id']))}</b>"
                         + (f" ({scad})" if scad else ""))
        else:
            righe.append("🏆 Fantabasket: <b>svincolato</b> (free agent)")

    if not a:
        return "\n".join(righe)

    # ── stagione ──
    tab = L.q("""SELECT t.*, p.data_et, p.casa, p.trasferta FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                  WHERE t.atleta = %s AND p.stagione = %s AND p.tipo = ANY(%s) ORDER BY p.inizio""",
               (a, s, list(TIPI)), many=True) or []
    contano = [r for r in tab if L.conta(r)]
    partite = partite_squadra(tab, L.squadre_roster([a]).get(a), s, a)
    su = testo_su(partite)
    righe.append("")
    prima = anno_prima(gid, s)
    if not contano:
        righe.append(f"📊 Stagione {e(s)}: nessuna partita giocata{su}" + (f" ({len(tab)} a referto senza entrare)" if tab else ""))
        if prima:
            righe.append(prima)
        if partite:
            righe += ["", "<b>Ultime partite</b>"] + ultime(tab, partite)
        return "\n".join(righe + ["", FONTE])
    n = len(contano)
    tot = {k: sum(int(r[k]) for r in contano) for k in ("minuti", "pts", "oreb", "dreb", "ast", "stl", "blk", "tov",
                                                       "fgm", "fga", "tpm", "tpa", "ftm", "fta")}
    media_fp = ottavi(sum(float(r["fp"]) for r in contano) / n)
    righe += [f"📊 <b>Stagione {e(s)}</b>: {n} partite{su} · media <b>{tp(media_fp)}</b> fantapunti",
              f"{_media(tot['minuti'] / n)} min · {_media(tot['pts'] / n)} punti · {_media((tot['oreb'] + tot['dreb']) / n)} rimbalzi "
              f"· {_media(tot['ast'] / n)} assist · {_media(tot['stl'] / n)} recuperi · {_media(tot['blk'] / n)} stoppate "
              f"· {_media(tot['tov'] / n)} perse",
              f"Tiro {_pct(tot['fgm'], tot['fga'])} · da tre {_pct(tot['tpm'], tot['tpa'])} · liberi {_pct(tot['ftm'], tot['fta'])}"]
    # media delle ultime 5 giocate (Luca, 09/11): solo se ne ha giocate più di 5, se no è la media della stagione
    if n > ULTIME_MEDIA:
        recenti = contano[-ULTIME_MEDIA:]
        righe.append(f"📈 Ultime {ULTIME_MEDIA} giocate: media <b>{tp(ottavi(sum(float(r['fp']) for r in recenti) / ULTIME_MEDIA))}</b> fantapunti"
                     f" · {_media(sum(int(r['minuti']) for r in recenti) / ULTIME_MEDIA)} min")
    if prima:
        righe.append(prima)

    # ── ultime 5 ──
    righe += ["", "<b>Ultime partite</b>"] + ultime(tab, partite)
    return "\n".join(righe + ["", FONTE])


def foto(gid: int) -> str | None:
    g = L.q("SELECT espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    return L.foto(g["espn_id"]) if g and g.get("espn_id") else None


def immagine(gid: int, f: str) -> bytes:
    """La foto ESPN (trasparente) su uno sfondo viola 640×420 col nome (foto_player.typ): su
    Telegram una PNG trasparente può uscire su fondo nero, e una foto piccola si vede sgranata."""
    import json
    import typst
    g = L.q("SELECT nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True) or {}
    sq = L.squadre_roster([g.get("espn_id")]).get(g.get("espn_id")) if g.get("espn_id") else None
    c = L.q("SELECT team_id FROM contratti WHERE giocatore_id = %s AND attivo LIMIT 1", (gid,), one=True)
    sotto = " · ".join(x for x in (sq or "", L.nome(c["team_id"]) if c else "") if x)
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foto_player.typ")
    return typst.compile(tpl, root="/", format="png", ppi=144,
                         sys_inputs={"dati": json.dumps({"foto": os.path.abspath(f), "nome": g.get("nome_common", ""),
                                                          "sotto": sotto}, ensure_ascii=False)})


def handlers(scheda_di, foto_di=None):
    """(cmd_player, manda, cb_player) con la scheda del bot: scheda_di(gid) -> testo, chiamata ogni volta (così
    chi la sostituisce dopo, come klra, vale anche qui). foto_di(gid) -> file della foto o None."""
    foto_di = foto_di or foto

    async def cmd_player(update, context):
        msg = update.effective_message
        testo = " ".join(context.args or [])
        if not testo:
            await msg.reply_text("Uso: /player NOME (es. /player Wembanyama)")
            return
        trovati = cerca(testo)
        if not trovati:
            await msg.reply_text(f"Nessun giocatore si chiama «{testo}».")
            return
        if len(trovati) > 1 and L.norm(trovati[0]["nome_common"]) != L.norm(testo):
            await msg.reply_text("Quale?", reply_markup=K([[B(x["nome_common"] + (" ✅" if x["a_roster"] else ""),
                                                               callback_data=f"pl:{x['id']}")] for x in trovati]))
            return
        await manda(msg, trovati[0]["id"])

    async def manda(msg, gid: int) -> None:
        """La scheda; con la foto ESPN se c'è già (si scarica di notte, qui mai). La didascalia di
        una foto arriva a 1024 caratteri: oltre, la foto e sotto il testo."""
        t = scheda_di(gid)
        f = foto_di(gid)
        img = None
        if f:
            try:
                img = immagine(gid, f)
            except Exception as err:                          # Typst o foto rovinata: solo testo
                import logging
                logging.getLogger(__name__).warning("Foto di /player: %s", err)
        if not img:
            await msg.reply_text(t, parse_mode="HTML")
            return
        if len(t) <= 1024:
            await msg.reply_photo(img, caption=t, parse_mode="HTML")
            return
        await msg.reply_photo(img)
        await msg.reply_text(t, parse_mode="HTML")

    async def cb_player(update, context):
        q = update.callback_query
        await q.answer()
        gid = int(q.data.split(":")[1])
        if foto_di(gid):                                 # con la foto: il «Quale?» si toglie, la scheda arriva sotto
            await q.edit_message_text("🏀 ⬇️")
            await manda(q.message, gid)
            return
        await q.edit_message_text(scheda_di(gid), parse_mode="HTML")

    return cmd_player, manda, cb_player
