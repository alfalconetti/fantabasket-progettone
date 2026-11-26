import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.8.0 (Luca, 13–14/11): la watchlist (handlers/watchlist.py, shared/watchlist.py). Gira dopo loucabot (tabelle nba_*):
# giocatori «Watch *», atleti «wa*», utenti 101 (GM di Alfa) e 102 (GM di Beta), 999999 non GM.
import asyncio, types
from datetime import date, datetime, timedelta, timezone
import database as db
import settings
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from shared import watchlist as W
from shared import elenco_giocatori as EG
import handlers.watchlist as WL
import handlers.lega as LG
import comandi

S = settings.stagione_corrente()
ADESSO = datetime.now(timezone.utc)


def pulizia():
    db._q("DELETE FROM watch_avvisi WHERE user_id IN (101, 102, 999999)")
    db._q("DELETE FROM watch_soglie WHERE user_id IN (101, 102, 999999)")
    db._q("DELETE FROM watchlist WHERE user_id IN (101, 102, 999999)")
    db._q("DELETE FROM registro_azioni WHERE oggetto LIKE 'Watch %%'")
    db._q("DELETE FROM nba_infortuni WHERE atleta LIKE 'wa%%'"); db._q("DELETE FROM nba_tabellini WHERE atleta LIKE 'wa%%'")
    db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'wa_%%'"); db._q("DELETE FROM nba_atleti WHERE atleta LIKE 'wa%%'")
    db._q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Watch %%'")
    for r in db._q("SELECT id FROM giocatori WHERE nome_common LIKE 'Watch %%'", many=True) or []:
        for t in ("transazioni", "contratti", "rookie", "posizioni_eleggibili"):
            db._q(f"DELETE FROM {t} WHERE giocatore_id = %s", (r["id"],))
        db._q("DELETE FROM giocatori WHERE id = %s", (r["id"],))


pulizia()
gid = {}
for n, a, sq in (("Watch Uno", "wa1", "WAA"), ("Watch Due", "wa2", "WAB"), ("Watch Tre", "wa3", "WAA"), ("Watch Vecchio", None, None)):
    gid[n] = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
                      (n, n, n.lower(), a))
    if a:
        db._q("INSERT INTO nba_atleti (atleta, nome, squadra) VALUES (%s, %s, %s)", (a, n, sq))
z = ", fga, fgm, ftm, fta, fg3m, orb, drb, ast, stl, blk, tov"
for n in ("Watch Uno", "Watch Due", "Watch Tre"):
    db._q(f"INSERT INTO bref_stats (stagione, nome_bref, team, g, pts{z}) VALUES (%s, %s, 'WAA', 10, 40, 0,0,0,0,0,0,0,0,0,0,0)", (str(int(S) + 1), n))
db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) VALUES (%s, 'team02', 3, 1, %s, 'normale', TRUE)",
      (gid["Watch Due"], S))
db._q(f"INSERT INTO bref_stats (stagione, nome_bref, team, g, pts{z}) VALUES ('2019', 'Watch Vecchio', 'WAA', 60, 20, 0,0,0,0,0,0,0,0,0,0,0)")


class M:
    def __init__(s, chat="private", cid=101): s.out = []; s.chat = types.SimpleNamespace(type=chat, id=cid)
    async def reply_text(s, t, **k): s.out.append(("t", t, k.get("reply_markup")))
    async def reply_photo(s, photo=None, caption=None, **k): s.out.append(("f", caption, k.get("reply_markup")))
    async def reply_media_group(s, media, **k): s.out.append(("a", len(media), None))
    async def reply_document(s, document=None, filename=None, **k): s.out.append(("d", filename, None))


def upd(uid, m, chat="private"):
    return types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m,
                                 effective_chat=types.SimpleNamespace(type=chat, id=uid))


ctx = lambda args: types.SimpleNamespace(args=args, bot=None)

# ── /watch, /unwatch ──
m = M(); asyncio.run(WL.cmd_watch(upd(999999, m), ctx(["Watch", "Uno"])))
ok("per i GM" in m.out[-1][1] and not W.seguiti(999999), "/watch: solo i GM")
m = M(); asyncio.run(WL.cmd_watch(upd(101, m), ctx(["Watch", "Uno"])))
ok("Ora segui <b>Watch Uno</b>" in m.out[-1][1] and "⚠️" not in m.out[-1][1] and W.seguiti(101) == {gid["Watch Uno"]}, "/watch NOME " + m.out[-1][1])
m = M(); asyncio.run(WL.cmd_watch(upd(101, m), ctx(["Watch", "Uno"])))
ok("Segui già" in m.out[-1][1], "/watch due volte: lo dice")
m = M(); asyncio.run(WL.cmd_watch(upd(101, m), ctx(["Watch"])))
ok(m.out[-1][1] == "Quale vuoi seguire?" and m.out[-1][2], "/watch con più giocatori: i bottoni")
m = M(); asyncio.run(WL.cmd_watch(upd(101, m), ctx(["Watch", "Vecchio"])))
ok("Non gioca in NBA dal 2018-19" in m.out[-1][1], "/watch di chi non gioca da più di una stagione: lo dice " + m.out[-1][1])
ok("mai giocato" in WL.non_gioca(db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES ('Watch Mai', 'Watch Mai', 'watch mai') RETURNING id")),
   "/watch di chi non ha mai giocato in NBA: lo dice")
m = M(); asyncio.run(WL.cmd_unwatch(upd(101, m), ctx(["Watch", "Vecchio"])))
ok("Non segui più" in m.out[-1][1] and gid["Watch Vecchio"] not in W.seguiti(101), "/unwatch NOME")
m = M(); asyncio.run(WL.cmd_unwatch(upd(101, m), ctx(["Watch", "Due"])))
ok("non c'è nessuno" in m.out[-1][1], "/unwatch di chi non segui")

# ── privata: un altro GM non vede niente ──
ok(W.seguiti(102) == set(), "la watchlist è di chi l'ha fatta")

# ── /watch_soglia ──
ok(WL.leggi_soglia(["+20"]) == (20.0, None) and WL.leggi_soglia(["45"]) == (None, 45.0) and WL.leggi_soglia(["+20", "45"]) == (20.0, 45.0)
   and WL.leggi_soglia(["default"]) == (None, None) and WL.leggi_soglia(["x"]) is None, "/watch_soglia: +N, N, tutte e due, default")
m = M(); asyncio.run(WL.cmd_watch_soglia(upd(102, m), ctx([])))
ok("media +15" in m.out[-1][1] and "50 fantapunti" in m.out[-1][1], "/watch_soglia: il default")
m = M(); asyncio.run(WL.cmd_watch_soglia(upd(102, m), ctx(["+20"])))
ok(W.soglia(102) == (20.0, 50.0) and "media +20" in m.out[-1][1], "/watch_soglia +20: cambia solo quella sopra la media")
m = M(); asyncio.run(WL.cmd_watch_soglia(upd(102, m), ctx(["default"])))
ok(W.soglia(102) == (15.0, 50.0), "/watch_soglia default")
ok(W.grande(50, None, (15, 50)) and W.grande(40, 24, (15, 50)) and not W.grande(38, 24, (15, 50)), "grande prestazione: assoluta o sopra la media")

# ── il bottone sotto /player: solo in privato e per i GM ──
km = WL.bottoni_player(gid["Watch Uno"], types.SimpleNamespace(type="private", id=101))
ok(km and km.inline_keyboard[0][0].text == "👁 Non seguire più", "/player in privato, giocatore seguito: «Non seguire più»")
ok(WL.bottoni_player(gid["Watch Due"], types.SimpleNamespace(type="private", id=101)).inline_keyboard[0][0].text == "👁 Segui", "«Segui»")
ok(WL.bottoni_player(gid["Watch Uno"], types.SimpleNamespace(type="supergroup", id=-100)) is None
   and WL.bottoni_player(gid["Watch Uno"], types.SimpleNamespace(type="private", id=999999)) is None, "nei gruppi e per chi non è GM niente bottone")


class Q:
    def __init__(s, data, uid): s.data = data; s.from_user = types.SimpleNamespace(id=uid); s.risposte = []; s.km = None; s.t = None
    async def answer(s, t=None, **k): s.risposte.append(t)
    async def edit_message_reply_markup(s, km): s.km = km
    async def edit_message_text(s, t, **k): s.t = t


q = Q(f"wl:+:{gid['Watch Due']}:p", 101); asyncio.run(WL.cb_watch(types.SimpleNamespace(callback_query=q), ctx([])))
ok(gid["Watch Due"] in W.seguiti(101) and q.km.inline_keyboard[0][0].text == "👁 Non seguire più", "bottone «Segui»: lo segue e il bottone si gira")
q = Q(f"wl:-:{gid['Watch Due']}:p", 101); asyncio.run(WL.cb_watch(types.SimpleNamespace(callback_query=q), ctx([])))
ok(gid["Watch Due"] not in W.seguiti(101) and q.km.inline_keyboard[0][0].text == "👁 Segui", "bottone «Non seguire più»")
q = Q(f"wl:+:{gid['Watch Tre']}", 101); asyncio.run(WL.cb_watch(types.SimpleNamespace(callback_query=q), ctx([])))
ok("Ora segui <b>Watch Tre</b>" in q.t, "bottone del «Quale vuoi seguire?»")
_f = []
class MF:
    chat = types.SimpleNamespace(type="private", id=101)
    async def reply_text(s, t, **k): _f.append(("t", None))
    async def reply_photo(s, photo=None, caption=None, **k): _f.append(("f", k.get("reply_markup")))
asyncio.run(LG.manda(MF(), gid["Watch Uno"]))
ok(_f and _f[0][0] == "f" and _f[0][1] and _f[0][1].inline_keyboard[0][0].text == "👁 Non seguire più", "/player nel bot principale: il bottone sotto l'immagine")

# ── /giocatori watch, /watchlist ──
r = EG.risposta("watch", 101, True)
ok(sorted(x["nome"] for p in r.get("pagine", []) for x in p["righe"]) == ["Watch Tre", "Watch Uno"], f"/giocatori watch: solo i seguiti {r.get('testo')}")
ok("solo in privato" in EG.risposta("watch", 101, False)["testo"], "/giocatori watch in un gruppo: no, è privata")
ok([x["nome"] for p in EG.risposta("nome:^Watch -watch", 101, True).get("pagine", []) for x in p["righe"]] == ["Watch Due"],
   "-watch: chi non segui")
m = M(); asyncio.run(WL.cmd_watchlist(upd(101, m), ctx([])))
ok([k for k, *_ in m.out] == ["f", "d"] and "watchlist" in m.out[0][1], f"/watchlist: l'immagine e il file {m.out}")
m = M(); asyncio.run(WL.cmd_watchlist(upd(102, m), ctx([])))
ok("vuota" in m.out[-1][1], "/watchlist vuota")

# ── gli avvisi ──
W.aggiungi(102, gid["Watch Uno"])
db._q("UPDATE watchlist SET da = %s WHERE user_id IN (101, 102)", (ADESSO - timedelta(hours=3),))
seg = {k: v for k, v in W.tutti().items() if k in gid.values()}
dal = ADESSO - timedelta(days=2)
# asta: aperta dopo l'aggiunta da 102 (lui non viene avvisato), e una vecchia
db._q("""INSERT INTO registro_azioni (bot, chi_id, veste, azione, giocatore_id, oggetto, dopo, quando) VALUES
         ('aste', 102, 'gm', 'asta FA aperta', %s, 'Watch Uno (asta FA #1)', 'aperta, 5M Beta', %s),
         ('aste', 102, 'gm', 'asta FA aperta', %s, 'Watch Uno (asta FA #0)', 'aperta, 1M Beta', %s),
         ('aste', 102, 'gm', 'offerta', %s, 'Watch Uno (asta FA #1)', '6M', %s)""",
      (gid["Watch Uno"], ADESSO - timedelta(hours=1), gid["Watch Uno"], ADESSO - timedelta(hours=5), gid["Watch Uno"], ADESSO))
aa = WL.avvisi_aste(seg, dal)
ok([(u, t.startswith("🔨 <b>Asta aperta</b> su <b>Watch Uno</b> (FA): aperta, 5M Beta")) for u, _, t in aa] == [(101, True)],
   f"asta aperta: solo a chi lo seguiva già, non a chi l'ha aperta, niente offerte {aa}")
# movimenti
db._q("INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, timestamp) VALUES ('cut', %s, 'team01', NULL, %s, %s)",
      (gid["Watch Tre"], S, ADESSO - timedelta(minutes=30)))
mv = WL.avvisi_movimenti(seg, dal)
ok([(u, t) for u, _, t in mv] == [(101, "🔁 <b>Watch Tre</b>: tagliato da Alfa, ora è FA")], f"movimenti: il taglio {mv}")
# infortuni: due report; Uno diventa Out, Tre passa da Q a DTD (non è serio)
p1, p2 = ADESSO + timedelta(days=4000), ADESSO + timedelta(days=4001)
db._q("""INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, dettaglio, preso) VALUES
         (%s, 'wa3', 'x', 'WAA', 'Questionable', '', %s), (%s, 'wa1', 'x', 'WAA', 'Out', 'Caviglia', %s),
         (%s, 'wa3', 'x', 'WAA', 'Day-To-Day', '', %s)""", (ADESSO.date(), p1, ADESSO.date(), p2, ADESSO.date(), p2))
inf = WL.avvisi_infortuni(seg)
ok(sorted((u, t) for u, _, t in inf) == [(101, "🩹 <b>Watch Uno</b>: <b>Out</b> (Caviglia)"), (102, "🩹 <b>Watch Uno</b>: <b>Out</b> (Caviglia)")],
   f"injury report: solo le cose serie {inf}")
p3 = ADESSO + timedelta(days=4002)
db._q("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, dettaglio, preso) VALUES (%s, 'wa3', 'x', 'WAA', 'Day-To-Day', '', %s)",
      (ADESSO.date(), p3))
inf = WL.avvisi_infortuni(seg)
ok([t for u, _, t in inf if u == 101] == ["✅ <b>Watch Uno</b>: non è più Out, fuori dall'injury report"], f"injury report: quando esce dall'Out {inf}")
db._q("DELETE FROM nba_infortuni WHERE atleta LIKE 'wa%%'")
# prestazioni: Uno fa 52 (media prima 24 → sopra anche la soglia di 102 a +20), Tre fa 30 (media 28: niente)
notte = WL.notte_di()
for i, (d, st) in enumerate(((notte - timedelta(days=3), "STATUS_FINAL"), (notte, "STATUS_FINAL"))):
    db._q("""INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato, punti_casa, punti_trasferta)
             VALUES (%s, %s, 2, %s, %s, 'WAA', 'WAB', %s, 110, 100)""",
          (f"wa_p{i}", S, d, (ADESSO - timedelta(hours=2)) if i else (ADESSO - timedelta(days=3)), st))
for a, fps in (("wa1", (24, 52)), ("wa3", (28, 30))):
    for i, fp in enumerate(fps):
        db._q("""INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, pts, oreb, dreb, ast, stl, blk, tov, fp)
                 VALUES (%s, %s, %s, 'WAA', TRUE, 30, 20, 2, 8, 4, 1, 1, 2, %s)""", (f"wa_p{i}", a, a, fp))
W.imposta_soglia(102, 20, None)
pf = WL.avvisi_prestazioni(seg, dal)
ok(sorted(u for u, _, _ in pf) == [101, 102] and all("🔥 <b>Watch Uno</b> (FA) · <b>52,00</b> stanotte vs WAB · V 110-100, media 24,00 (+28,00)" == t for _, _, t in pf),
   f"grande prestazione: col risultato e lo scarto, per tutti e due {pf}")
W.imposta_soglia(102, 40, 60)
ok(sorted(u for u, _, _ in WL.avvisi_prestazioni(seg, dal)) == [101], "la soglia di ognuno")
_bt = WL.bottone_prestazione(pf[0][1])
_gw = db._qval("SELECT id FROM giocatori WHERE espn_id = %s", (pf[0][1].split(":")[2],))
ok(_bt is not None and _bt.inline_keyboard[0][0].callback_data.startswith(f"pre:{_gw}:") and WL.bottone_prestazione("inf:x:y") is None,
   "v7.31.2: sotto la grande prestazione il bottone di /prestazione di quella notte")


class BotF:
    def __init__(s): s.msg = []; s.foto = []
    async def send_message(s, chat_id, text, **k): s.msg.append((chat_id, text))
    async def send_photo(s, chat_id, photo, caption=None, **k): s.foto.append((chat_id, caption, photo))


bot = BotF()
asyncio.run(WL.job_avvisi(types.SimpleNamespace(bot=bot)))
n1 = len(bot.msg)
asyncio.run(WL.job_avvisi(types.SimpleNamespace(bot=bot)))
ok(n1 >= 3 and len(bot.msg) == n1, f"job degli avvisi: ognuno una volta sola ({n1})")

# ── il report delle 9:30 ──
d = WL.dati_report(101, notte)
ok(d and [r["nome"] for r in d["giocato"]] == ["Watch Uno", "Watch Tre"] and d["giocato"][0]["top"] and not d["giocato"][1]["top"]
   and d["giocato"][0]["partita"] == "vs WAB · V 110-100" and d["giocato"][0]["delta"] == "28,00" and d["migliore"] == "Watch Uno · 52,00",
   f"report: chi ha giocato, dal migliore, oro sopra soglia {d and d['giocato']}")
W.aggiungi(101, gid["Watch Due"])
d = WL.dati_report(101, notte)
ok(d["non_giocato"] == ["Watch Due (non ha giocato)"], f"report: chi non ha giocato, col motivo {d['non_giocato']}")
_png = WL.immagine_report(d)
ok(_png[:4] == b"\x89PNG", "report: l'immagine")
if _os.environ.get("WATCH_PNG"): open(_os.environ["WATCH_PNG"], "wb").write(_png)
ok(WL.dati_report(101, notte - timedelta(days=1)) is None, "notte senza partite dei seguiti: niente report")
bot = BotF()
asyncio.run(WL.job_report(types.SimpleNamespace(bot=bot)))
asyncio.run(WL.job_report(types.SimpleNamespace(bot=bot)))
ok(sorted(c for c, _, _ in bot.foto) == [101, 102] and all(c.startswith("👁 Watchlist · notte del ") for _, c, _ in bot.foto),
   f"job del report: a chi ha una watchlist, una volta sola {[(c, x) for c, x, _ in bot.foto]}")

# ── menu e privato ──
hs = {next(iter(h.commands)): h for h in WL.get_handlers() if hasattr(h, "commands")}
ok(all("PRIVATE" in str(hs[c].filters).upper() for c in ("watch", "unwatch", "watchlist", "watch_soglia")), "comandi solo in privato")
li = comandi.liste_comandi(settings.fase())
ok({"watch", "unwatch", "watchlist", "watch_soglia"} <= {c.command for c in li["gm"]}
   and not {"watch", "unwatch", "watchlist"} & {c.command for c in li["group"]}, "menu: in privato sì, nei gruppi no")

pulizia()
