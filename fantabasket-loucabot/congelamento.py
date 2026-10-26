"""
Congelamento delle giornate e correzioni dei tabellini (v56, regola votata dai GM il 26/10, proposta di Luca).

Regular season: si ricontrollano (controllo delle 10, e /ricalcola riscarica da ESPN) solo le **ultime 3
giornate finite**, convalidate o no: con la 4 in corso la 1, la 2 e la 3; finita la 4, la 2, la 3 e la 4.
Le più vecchie sono **congelate**: niente più riscarichi, /ricalcola usa i tabellini che ci sono.
Gli admin possono congelare una delle ultime 3 (/congela N) o riaprire una vecchia (/scongela N): la scelta
a mano vale più della regola, finché non la si cambia di nuovo. /congelamento mostra lo stato di tutte.
Ogni /congela, /scongela e /correggi_tabellino va nel registro, nel canale log e sul canale principale.

/correggi_tabellino GIOCATORE GN VALORE [DD/MM] (admin): i fantapunti di un giocatore in una partita della
giornata, senza riscaricare; poi /ricalcola N e la convalida (che aggiorna il messaggio dei risultati ufficiali
e, solo se cambia chi vince, manda l'avviso sul canale).

Playoff (da fare col tabellone): nessun ricontrollo, punteggi congelati quando inizia la giornata dopo; dalla
generazione del tabellone stop anche ai ricontrolli della regular season.
"""
import html
import logging
import re
from datetime import datetime

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
import db
import nba
from numeri import testo as tp

logger = logging.getLogger(__name__)
FINESTRA = 3          # ultime giornate finite che si ricontrollano (Luca, 26/10)


def e(x) -> str:
    return html.escape(str(x), quote=False)


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_congelamento (
              stagione  TEXT NOT NULL,
              giornata  INT  NOT NULL,
              congelata BOOLEAN NOT NULL,                 -- scelta a mano: vale più della regola
              da        BIGINT,
              quando    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (stagione, giornata))""")


def oggi_et():
    return datetime.now(nba.ET).date()


def stati(s: str, oggi=None) -> dict[int, dict]:
    """{numero: {stato: 'da giocare'|'in corso'|'aperta'|'congelata', a_mano: bool, g: giornata}}."""
    migra()
    oggi = oggi or oggi_et()
    gg = db.giornate(s)
    finite = [g["numero"] for g in gg if g["al"] < oggi]
    aperte = set(sorted(finite)[-FINESTRA:])
    mano = {r["giornata"]: r["congelata"] for r in db.q("SELECT giornata, congelata FROM lega_congelamento WHERE stagione = %s",
                                                           (s,), many=True) or []}
    out = {}
    for g in gg:
        n = g["numero"]
        if g["al"] >= oggi:
            st = "in corso" if g["dal"] <= oggi else "da giocare"
            out[n] = {"stato": st, "a_mano": False, "g": g}
            continue
        if n in mano:
            out[n] = {"stato": "congelata" if mano[n] else "aperta", "a_mano": True, "g": g}
        else:
            out[n] = {"stato": "aperta" if n in aperte else "congelata", "a_mano": False, "g": g}
    return out


def congelata(s: str, n: int) -> bool:
    """True se la giornata non si ricontrolla più (niente riscarichi da ESPN)."""
    return (stati(s).get(n) or {}).get("stato") == "congelata"


def da_ricontrollare(s: str) -> list[int]:
    """Le giornate finite e aperte: quelle del controllo delle 10."""
    return sorted(n for n, x in stati(s).items() if x["stato"] == "aperta")


# ── comandi ────────────────────────────────────────────────────────────────────

def _chi(update) -> str:
    u = update.effective_user
    return u.full_name or str(u.id)


async def _annuncia(bot, testo: str) -> None:
    """Canale log e canale principale (Luca, 26/10: per correttezza)."""
    from handlers import log
    await log(bot, testo)
    canale = config.globali().get("main_channel_id")
    if canale:
        try:
            await bot.send_message(chat_id=canale, text=testo, parse_mode="HTML")
        except Exception as err:
            logger.warning("Canale principale: %s", err)


def _numero(x: str) -> int | None:
    m = re.fullmatch(r"[Gg]?(\d+)", x or "")
    return int(m.group(1)) if m else None


async def _cambia(update: Update, context: ContextTypes.DEFAULT_TYPE, congela: bool):
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    s = config.stagione()
    n = _numero((context.args or [""])[0])
    st = stati(s)
    if not n or n not in st:
        await msg.reply_text(f"Uso: /{'congela' if congela else 'scongela'} N (es. /{'congela' if congela else 'scongela'} 3)")
        return
    if st[n]["stato"] in ("in corso", "da giocare"):
        await msg.reply_text(f"La giornata {n} non è ancora finita: si congela o scongela solo una giornata finita.")
        return
    prima = st[n]["stato"]
    db.q("""INSERT INTO lega_congelamento (stagione, giornata, congelata, da) VALUES (%s, %s, %s, %s)
            ON CONFLICT (stagione, giornata) DO UPDATE SET congelata = EXCLUDED.congelata, da = EXCLUDED.da, quando = NOW()""",
         (s, n, congela, update.effective_user.id))
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "giornata congelata" if congela else "giornata scongelata",
               oggetto=f"giornata {n}", prima=prima, dopo="congelata" if congela else "aperta")
    testo = (f"🧊 <b>Giornata {n} congelata</b> da {e(_chi(update))}: i suoi tabellini non si riscaricano più da ESPN."
             if congela else
             f"🔓 <b>Giornata {n} scongelata</b> da {e(_chi(update))}: i suoi tabellini si ricontrollano di nuovo "
             f"(controllo delle 10, e /ricalcola riscarica da ESPN).")
    await _annuncia(context.bot, testo)
    await msg.reply_text(testo + "\nLo stato di tutte: /congelamento", parse_mode="HTML")


async def cmd_congela(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cambia(update, context, True)


async def cmd_scongela(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cambia(update, context, False)


def testo_congelamento(s: str) -> str:
    st = stati(s)
    icone = {"aperta": "🔄", "congelata": "🧊", "in corso": "🔴", "da giocare": "⏳"}
    righe = ["🧊 <b>Congelamento delle giornate</b>", ""]
    for n in sorted(st):
        x = st[n]
        if x["stato"] == "da giocare" and n > min([m for m, y in st.items() if y["stato"] == "da giocare"] or [n]):
            continue                                  # delle future basta la prossima
        righe.append(f"{icone[x['stato']]} G{n} ({x['g']['dal']:%d/%m}–{x['g']['al']:%d/%m}): {x['stato']}"
                     + (" <i>(a mano)</i>" if x["a_mano"] else ""))
    righe += ["", f"🔄 aperta: si ricontrolla (le ultime {FINESTRA} finite, o scongelata a mano) · 🧊 congelata: "
                  "tabellini fermi, /ricalcola non riscarica · 🔴 in corso · ⏳ da giocare",
              "Cambiare: /congela N · /scongela N · correggere un punteggio: /correggi_tabellino GIOCATORE GN VALORE [GG/MM]"]
    return "\n".join(righe)


async def cmd_congelamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    await update.effective_message.reply_text(testo_congelamento(config.stagione()), parse_mode="HTML")


def leggi_correzione(args: list[str]) -> tuple[str, int, float, tuple[int, int] | None] | None:
    """GIOCATORE GN VALORE [DD/MM] → (nome, n, valore, (giorno, mese) o None)."""
    a = list(args)
    data = None
    if a and re.fullmatch(r"\d{1,2}/\d{1,2}", a[-1]):
        d, m = a.pop().split("/")
        data = (int(d), int(m))
    if len(a) < 3:
        return None
    try:
        valore = float(a[-1].replace(",", "."))
    except ValueError:
        return None
    n = _numero(a[-2])
    if n is None:
        return None
    return " ".join(a[:-2]), n, valore, data


async def cmd_correggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/correggi_tabellino GIOCATORE GN VALORE [DD/MM] (admin)."""
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    uso = "Uso: /correggi_tabellino GIOCATORE GN VALORE [GG/MM] (es. /correggi_tabellino Norman Powell G1 16)"
    x = leggi_correzione(context.args or [])
    if not x:
        await msg.reply_text(uso)
        return
    nome, n, valore, data = x
    s = config.stagione()
    g = db.giornata(s, n)
    if not g:
        await msg.reply_text(f"La giornata {n} non c'è.")
        return
    import player
    trovati = [t for t in player.cerca(nome) if t.get("espn_id")]
    if len(trovati) != 1 and not (trovati and player.calcolo.norm(trovati[0]["nome_common"]) == player.calcolo.norm(nome)):
        await msg.reply_text(f"Nessun giocatore (abbinato a ESPN) si chiama «{nome}»." if not trovati else
                             "Più giocatori: " + ", ".join(t["nome_common"] for t in trovati[:6]) + ". Scrivi il nome completo.")
        return
    gioc = trovati[0]
    righe = db.q("""SELECT t.partita, t.fp, p.data_et FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                    WHERE t.atleta = %s AND p.data_et BETWEEN %s AND %s ORDER BY p.inizio""",
                 (gioc["espn_id"], g["dal"], g["al"]), many=True) or []
    if data:
        righe = [r for r in righe if (r["data_et"].day, r["data_et"].month) == data]
    if not righe:
        await msg.reply_text(f"{gioc['nome_common']} non ha tabellini nella giornata {n}"
                             + (f" il {data[0]:02d}/{data[1]:02d}." if data else "."))
        return
    if len(righe) > 1:
        await msg.reply_text(f"{gioc['nome_common']} ha {len(righe)} partite nella giornata {n}: aggiungi la data, es. "
                             + " · ".join(f"/correggi_tabellino {gioc['nome_common']} G{n} {tp(valore)} {r['data_et']:%d/%m}"
                                          for r in righe))
        return
    r = righe[0]
    prima = float(r["fp"])
    db.q("UPDATE nba_tabellini SET fp = %s WHERE partita = %s AND atleta = %s", (valore, r["partita"], gioc["espn_id"]))
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "tabellino corretto", oggetto=f"giornata {n}, {gioc['nome_common']} ({r['data_et']:%d/%m})",
               prima=tp(prima), dopo=tp(valore))
    testo = (f"✏️ <b>Correzione G{n}</b>: {e(gioc['nome_common'])} ({r['data_et']:%d/%m}) {tp(prima)} → <b>{tp(valore)}</b> "
             f"fantapunti (admin {e(_chi(update))})")
    await _annuncia(context.bot, testo)
    aperta = not congelata(s, n) and (stati(s).get(n) or {}).get("stato") == "aperta"
    await msg.reply_text(testo + f"\n\nOra /ricalcola {n} e la convalida per aggiornare i risultati."
                         + ("\n⚠️ La giornata è aperta: il controllo delle 10 o /ricalcola riscaricano da ESPN e possono "
                            f"rimettere il valore di ESPN. Per tenerla: /congela {n}" if aperta else ""), parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("congela", cmd_congela), CommandHandler("scongela", cmd_scongela),
            CommandHandler("congelamento", cmd_congelamento), CommandHandler("correggi_tabellino", cmd_correggi)]
