import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.2.0: 10-day contract. Richiesta del GM, approvazione dell'admin, firma diretta dell'admin,
regole (fase, una volta a squadra, due squadre per giocatore, free agent, ruolo eleggibile),
niente cap né slot, fuori da tagli/DPE/decadimento/trade, scadenza allungata a fine giornata,
roster, foglio e pannello."""
import asyncio, json, os, types
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, rookie, richieste_admin RESTART IDENTITY CASCADE")
db._q("""CREATE TABLE IF NOT EXISTS lega_giornate (stagione TEXT NOT NULL, numero INT NOT NULL, tipo TEXT NOT NULL DEFAULT 'regular',
         dal DATE NOT NULL, al DATE NOT NULL, media_file TEXT[] NOT NULL DEFAULT '{}', prima_partita TIMESTAMPTZ, media TEXT[],
         calcolato TIMESTAMPTZ, PRIMARY KEY (stagione, numero))""")
db._q("""CREATE TABLE IF NOT EXISTS lega_calcoli (stagione TEXT NOT NULL, giornata INT NOT NULL, stato TEXT NOT NULL DEFAULT
         'da_convalidare', risultati JSONB NOT NULL, PRIMARY KEY (stagione, giornata))""")
db._q("TRUNCATE lega_giornate, lega_calcoli")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)


def fase(f):
    g = json.load(open(os.environ["GLOBALS_PATH"])); g["fase"] = f; json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))


def gioc(n, pos, team=None, imp=5, ruolo=None):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) VALUES (%s,%s,'prova')", (gid, pos))
    if team:
        c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                     "VALUES (%s,%s,%s,2,'2026','normale') RETURNING id", (gid, team, imp))
        db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,'2026',%s)", (gid, team, c))
        if ruolo:
            db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_a,stagione,tipo) VALUES (%s,%s,%s,'2026','iniziale')", (gid, team, ruolo))
    return gid


centri = [gioc(f"Centro Alfa {i}", "C", "team01", 10, "C") for i in range(2)]
altri = [gioc(f"Ala Alfa {i}", "SF,PF", "team01", 3, "SF") for i in range(9)]
libero = gioc("Libero Lungo", "PF,C")
secondo = gioc("Secondo Libero", "PG")
diritti = gioc("Diritti Rookie", "SG")
db._q("INSERT INTO rookie (giocatore_id, team_id, anno_draft, round, pick_numero, firmato, diritti_scaduti) VALUES (%s,'team02','2026',2,40,FALSE,FALSE)", (diritti,))

import handlers.dieci_giorni as T
from shared import cap as C

msgs = []


class Bot:
    async def send_message(self, **k):
        msgs.append(k)


class Msg:
    def __init__(s): s.r = []
    async def reply_text(s, t, **k): s.r.append((t, k.get("reply_markup")))


class Q:
    def __init__(s, data, uid):
        s.data = data; s.t = None; s.kb = None; s.risposte = []
        s.from_user = types.SimpleNamespace(id=uid, first_name="Adm" if uid == 900 else "GM", username="x")
        s.message = types.SimpleNamespace(text_html="⏱ richiesta")
    async def answer(s, t=None, **k): s.risposte.append(t)
    async def edit_message_text(s, t, **k): s.t = t; s.kb = k.get("reply_markup")


def comando(f, uid, args):
    m = Msg()
    asyncio.run(f(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid, first_name="GM"), effective_message=m,
                                        effective_chat=types.SimpleNamespace(type="private")),
                  types.SimpleNamespace(args=args, bot=Bot())))
    return m.r


def tap(f, data, uid):
    q = Q(data, uid)
    asyncio.run(f(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot())))
    return q


def cbs(kb):
    return [b.callback_data for r in kb.inline_keyboard for b in r] if kb else []


# ── fase ──
fase("offseason-fa")
ok(T.verifica("team01", libero, "C") == [T.FUORI_FASE], "fuori dalla regular season prima della chiusura della FA: no")
fase("regular-season-deadline")
ok(T.verifica("team01", libero, "C") == [T.FUORI_FASE], "dopo la chiusura della FA (fase deadline): no")
fase("regular-season-fa")

# ── richiesta del GM ──
cap_prima, slot_prima = C.cap_occupato(db._q, "team01", "2026"), C.giocatori_in_slot(db._q, "team01", "2026")
r = comando(T.cmd_firma_10day, 101, ["libero", "lungo"])
ok(r and f"td:g:{libero}" in cbs(r[0][1]), "/firma_10day NOME: i free agent col nome")
ok(not T.cerca("Centro Alfa 0") and not T.cerca("Diritti Rookie"), "chi è sotto contratto o ha diritti 2nd non attivati non è un free agent")
q = tap(T.cb_gm, f"td:g:{libero}", 101)
ok(cbs(q.kb)[:2] == [f"td:r:{libero}:PF", f"td:r:{libero}:C"], "ruoli: le posizioni eleggibili")
q = tap(T.cb_gm, f"td:r:{libero}:C", 101)
ok("Centro Alfa 0 (sano per ESPN)" in q.t and "una volta a stagione" in q.t and f"td:ok:{libero}:C" in cbs(q.kb),
   "conferma: i giocatori nel ruolo e le regole")
msgs.clear(); q = tap(T.cb_gm, f"td:ok:{libero}:C", 101)
gruppo = [m for m in msgs if m["chat_id"] == -2]
ok("mandata agli admin" in q.t and gruppo and "Richiesta 10-day" in gruppo[0]["text"] and "Regole" in gruppo[0]["text"]
   and f"tdq:ok:team01:{libero}:C" in cbs(gruppo[0]["reply_markup"]), "richiesta al gruppo admin con regole e bottoni")
q = tap(T.cb_gm, f"td:ok:{libero}:C", 101)
ok("già una richiesta" in q.t, "seconda richiesta per lo stesso giocatore: in attesa")
ok("Solo admin" in (tap(T.cb_richiesta, f"tdq:ok:team01:{libero}:C", 101).risposte[0] or ""), "approvazione: solo admin")

# ── approvazione ──
msgs.clear(); q = tap(T.cb_richiesta, f"tdq:ok:team01:{libero}:C", 900)
c = db._q("SELECT * FROM contratti WHERE giocatore_id = %s AND attivo", (libero,), one=True)
ok(c and c["tipo"] == "10day" and c["importo"] == 0 and c["team_id"] == "team01"
   and abs((c["scadenza_10day"] - datetime.now(timezone.utc)) - timedelta(days=10)) < timedelta(minutes=1),
   "approvata: contratto 10-day, importo 0, scadenza fra 10 giorni")
ok(db._qval("SELECT count(*) FROM transazioni WHERE tipo='10day_firma' AND giocatore_id=%s AND team_id_a='team01'", (libero,)) == 1
   and db._qval("SELECT ruolo FROM ruolo_attuale WHERE giocatore_id=%s AND stagione='2026'", (libero,)) == "C",
   "movimento 10day_firma e ruolo C")
ok(C.cap_occupato(db._q, "team01", "2026") == cap_prima and C.giocatori_in_slot(db._q, "team01", "2026") == slot_prima,
   "niente cap e niente slot")
ok(any(m["chat_id"] == -1 and "10-day" in m["text"] for m in msgs) and any(m["chat_id"] == 101 for m in msgs)
   and any(m["chat_id"] == -3 for m in msgs), "annuncio sul canale, messaggio al GM, canale log")
ok("Approvata" in q.t and "Richiesta già gestita" in tap(T.cb_richiesta, f"tdq:ok:team01:{libero}:C", 900).t, "doppio tap: già gestita")

# ── regole dopo la firma ──
ok(any("già usato il 10-day" in x for x in T.verifica("team01", secondo, "PG")), "una volta a stagione per squadra")
ok(any("sotto contratto con Alfa (10-day)" in x for x in T.verifica("team02", libero, "C")), "durante il 10-day non è un free agent")
ok(any("non è tra le sue posizioni" in x for x in T.verifica("team02", secondo, "C")), "ruolo non eleggibile: no")
roster = db.get_roster_team("team01")
ok(any(x["giocatore_id"] == libero and x["tipo_contratto"] == "10day" for x in roster)
   and all(x["giocatore_id"] != libero for x in db.get_roster_team("team01", senza_10day=True)), "nel roster sì, nelle liste di tagli/trade no")
import handlers.tagli as TG
try:
    TG._valuta_taglio({"id": "team01", "nome": "Alfa"}, libero); ok(False, "taglio del 10-day")
except TG.TaglioNonEseguibile as err:
    ok("10-day" in str(err), "il 10-day non si taglia")
from shared import ruoli_core
ok(ruoli_core.deficit_team(db._q, "team01", "2026") == ruoli_core.deficit_team(db._q, "team01", "2026", togli=[libero]),
   "i minimi dei ruoli non contano il 10-day")

# ── roster e foglio ──
import handlers.roster as R
s = R._build_giocatori_str(roster, [], ruoli={libero: "C"})
ok(any(p.startswith("Libero Lungo|10d|–|D|") for p in s.split(";")), "roster PNG: flag D, 10d, niente anni")
import gas_client
p = gas_client._build_team_payload("team01")
fino = "fino al " + c["scadenza_10day"].astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m")
ok(all(x["nome"] != "Libero Lungo" for x in p["giocatori"]) and p["dieci_giorni"] == [{"nome": "Libero Lungo", "ruolo": "C", "fine": fino}],
   "foglio Roster: fuori dalle 15 righe, sotto (dieci_giorni)")
ok(R._fine_10day("team01") == fino, "legenda: fino al giorno dei 10 giorni")
s2 = R._build_giocatori_str([{"giocatore_id": i, "nome_common": f"G{i}", "importo": 20 - i, "anni_originali": 2, "stagione_firma": "2026",
                              "tipo_contratto": "normale", "occupa_slot": True} for i in range(3)]
                            + [{"giocatore_id": 99, "nome_common": "Rotto", "importo": 15, "importo_originale": 20, "ha_dpe": True,
                                "occupa_slot": False, "anni_originali": 2, "stagione_firma": "2026", "tipo_contratto": "normale"}]
                            + [x for x in roster if x["giocatore_id"] == libero], [])
ok([q.split("|")[0] for q in s2.split(";")][-2:] == ["Rotto", "Libero Lungo"] and s2.split(";")[-1].endswith("|x")
   and s2.split(";")[-2].endswith("|x") and s2.split(";")[0].endswith("|"), "Typst: DPE che libera lo slot e 10-day in fondo, fuori dai 15")

# ── scadenza allungata a fine giornata ──
base = datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc)
db._q("INSERT INTO lega_giornate (stagione, numero, dal, al, prima_partita) VALUES ('2026', 3, '2026-11-02', '2026-11-04', %s)",
      (datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc),))
dopo = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
ok(T.in_corso_alla_scadenza(base) == 3 and T.testo_scadenza(base) == "alla convalida della giornata 3",
   "10 giorni a giornata in corso: fino alla convalida della giornata")
ok(not T.scaduto(base, dopo) and T.giornate_aperte(base, dopo) == [3], "giornata finita ma non convalidata: resta")
dopo_fine = datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc)
ok(not T.scaduto(dopo_fine, dopo), "10 giorni finiti dopo l'ultima notte, giornata non ancora convalidata: resta")
db._q("INSERT INTO lega_calcoli (stagione, giornata, stato, risultati) VALUES ('2026', 3, 'convalidata', '{}')")
ok(T.scaduto(base, dopo) and T.scaduto(dopo_fine, dopo), "alla convalida della giornata decade")
ok(not T.scaduto(base, base - timedelta(minutes=1)), "prima dei 10 giorni mai")
ok(T.testo_scadenza(datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)) == "al 06/11 alle 11:00", "fuori dalle giornate: i 10 giorni")

# ── job: scadenza ──
db._q("UPDATE contratti SET scadenza_10day = NOW() + INTERVAL '1 hour' WHERE id = %s", (c["id"],))
msgs.clear(); asyncio.run(T.job_scadenza(types.SimpleNamespace(bot=Bot())))
ok(db._qval("SELECT attivo FROM contratti WHERE id=%s", (c["id"],)) and not msgs, "non ancora scaduto: niente")
db._q("UPDATE contratti SET scadenza_10day = NOW() - INTERVAL '1 minute' WHERE id = %s", (c["id"],))
asyncio.run(T.job_scadenza(types.SimpleNamespace(bot=Bot())))
ok(not db._qval("SELECT attivo FROM contratti WHERE id=%s", (c["id"],))
   and db._qval("SELECT count(*) FROM transazioni WHERE tipo='10day_scadenza' AND giocatore_id=%s AND team_id_da='team01' AND team_id_a IS NULL", (libero,)) == 1
   and any(m["chat_id"] == -1 and "torna free agent" in m["text"] for m in msgs), "scaduto: contratto chiuso, movimento, annuncio")
asyncio.run(T.job_scadenza(types.SimpleNamespace(bot=Bot())))
ok(db._qval("SELECT count(*) FROM transazioni WHERE tipo='10day_scadenza'") == 1, "il job non lo chiude due volte")
ok(libero in [g["id"] for g in T.cerca("Libero Lungo")], "di nuovo free agent")
ok(any("già usato" in x for x in T.verifica("team01", secondo, "PG")), "anche scaduto, la squadra l'ha usato")

# ── admin: firma diretta, due squadre al massimo, chiusura dal pannello ──
r = comando(T.cmd_firma_10day_admin, 900, ["Libero"])
ok(f"tda:g:{libero}" in cbs(r[0][1]), "/firma_10day_admin: i free agent")
q = tap(T.cb_admin, f"tda:g:{libero}", 900)
ok(f"tda:t:{libero}:team02" in cbs(q.kb) and any("Alfa (usato)" == b.text for row in q.kb.inline_keyboard for b in row), "squadre, con chi l'ha già usato")
q = tap(T.cb_admin, f"tda:t:{libero}:team02", 900)
ok(f"tda:r:{libero}:team02:PF" in cbs(q.kb), "ruoli")
msgs.clear(); q = tap(T.cb_admin, f"tda:ok:{libero}:team02:PF", 900)
ok(db._qval("SELECT team_id FROM contratti WHERE giocatore_id=%s AND attivo AND tipo='10day'", (libero,)) == "team02"
   and any(m["chat_id"] == 102 and "Un admin" in m["text"] for m in msgs), "firma diretta dell'admin, avviso al GM")
ok("Solo admin" in (tap(T.cb_admin, f"tda:ok:{secondo}:team03:PG", 101).risposte[0] or ""), "firma diretta: solo admin")
q = tap(T.cb_pannello, "tdadm:list", 900)
cid = db._qval("SELECT id FROM contratti WHERE giocatore_id=%s AND attivo", (libero,))
ok("Beta" in q.t and f"tdadm:end:{cid}" in cbs(q.kb), "pannello: i 10-day in corso")
msgs.clear(); q = tap(T.cb_pannello, f"tdadm:endok:{cid}", 900)
ok(not db._qval("SELECT count(*) FROM contratti WHERE giocatore_id=%s AND attivo", (libero,)) and "Nessuno" in q.t
   and any("chiuso da un admin" in m["text"] for m in msgs), "chiuso prima dal pannello")
ok(any("da 2 squadre" in x for x in T.verifica("team03", libero, "C")), "ogni free agent al massimo con due squadre")
ok(not T.verifica("team03", secondo, "PG"), "un'altra squadra con un altro giocatore: sì")
import sqlite3
con = sqlite3.connect(os.environ["DB_PATH"])
con.execute("CREATE TABLE IF NOT EXISTS aste (id INTEGER PRIMARY KEY, giocatore TEXT, stato TEXT, giocatore_id INTEGER)")
con.execute("INSERT INTO aste (giocatore, stato, giocatore_id) VALUES ('Secondo Libero', 'APERTA', %d)" % secondo); con.commit(); con.close()
os.environ["ASTE_DB_PATH"] = os.environ["DB_PATH"]
ok(any("asta in corso" in x for x in T.verifica("team03", secondo, "PG")), "con un'asta aperta su di lui: no")
del os.environ["ASTE_DB_PATH"]

# ── trade ──
c3 = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo,scadenza_10day) "
              "VALUES (%s,'team03',0,1,'2026','10day',NOW() + INTERVAL '5 days') RETURNING id", (secondo,))
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('10day_firma',%s,'team03','2026',%s)", (secondo, c3))
from validators import trade as VT
tid = db.crea_trade_bozza("team03", 2, "2026")
db.aggiungi_squadra_trade(tid, "team03", 1); db.aggiungi_squadra_trade(tid, "team04", 2)
db.aggiungi_item_trade(tid, "giocatore", "team03", "team04", giocatore_id=secondo)
ok(any("10-day, non si può scambiare" in x for x in VT.valida_trade(tid)[1]), "trade: il 10-day non si scambia")
coe = db.controlli_coerenza()
ok(coe == [] or all("storico" in x for x in coe), f"coerenza {coe}")

# ── bottone ✍️ e nome scritto (menu GM e pannello admin) ──
fase("regular-season-fa")
ud = {}
def tap_ud(f, data, uid):
    q = Q(data, uid)
    st = asyncio.run(f(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot(), user_data=ud)))
    return q, st
q = tap(T.cb_gm, "td:home", 103)
ok("td:nome" in cbs(q.kb), "menu GM → ⏱ 10-day: il bottone ✍️")
q = tap(T.cb_pannello, "tdadm:list", 900)
ok("tdadm:nome" in cbs(q.kb), "pannello admin → ⏱ 10-day: il bottone ✍️ per firmarne uno")
q, st = tap_ud(T.cb_chiedi_nome, "tdadm:nome", 900)
ok(st == T.NOME and ud.get("10day_admin") is True, "✍️ admin: aspetta il nome")
m = Msg(); m.text = "Libero"
st = asyncio.run(T.msg_nome(types.SimpleNamespace(effective_message=m, effective_user=types.SimpleNamespace(id=900)),
                            types.SimpleNamespace(bot=Bot(), user_data=ud)))
ok(st == T.ConversationHandler.END and f"tda:g:{libero}" in cbs(m.r[0][1]), "nome scritto: i free agent coi bottoni della firma admin")
q, st = tap_ud(T.cb_chiedi_nome, "tdadm:nome", 101)
ok(st == T.ConversationHandler.END and "Solo admin" in (q.risposte[0] or ""), "✍️ admin: solo admin")
