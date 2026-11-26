import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.35.1: una stagione intera di passaggi di fase dal pannello admin, dalla regular season 2026 alla regular season
2027: blocchi (playoff, calendario), anche con un «Confermo» rimasto da prima, passaggi automatici (stagione nuova,
rookie scale e Doncic, pick, rinnovi, RFA, x0 che scadono, promemoria di lottery e calendario), registro coerente."""
import asyncio, types
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("DELETE FROM inizi_stagione")
db._q("TRUNCATE giocatori, contratti, pick, rookie, transazioni, dpe, impatto_taglio, rfa_dichiarati, messaggi_fissi, "
      "rinnovi_normali, trade RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
db._q("""CREATE TABLE IF NOT EXISTS lega_giornate (stagione TEXT NOT NULL, numero INT NOT NULL, tipo TEXT NOT NULL DEFAULT 'regular',
         dal DATE NOT NULL, al DATE NOT NULL, media_file TEXT[] NOT NULL DEFAULT '{}', prima_partita TIMESTAMPTZ, media TEXT[],
         calcolato TIMESTAMPTZ, PRIMARY KEY (stagione, numero))""")
db._q("DELETE FROM lega_giornate WHERE stagione = '2027'")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ADMIN, GRUPPO = 900, -2


def fase(f, stagione=None):
    g = settings.load_globals(); g["fase"] = f
    if stagione:
        g["stagione_corrente"] = str(stagione)
    settings.save_globals(g)


def gioc(n, team, imp, anni, sf, tipo="normale", pick=None, anno_firma=None):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    if pick:
        db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft,anno_firma,firmato) "
              "VALUES (%s,%s,1,%s,%s,%s,TRUE)", (gid, team, pick, str(anno_firma), str(anno_firma)))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (gid, team, imp, anni, str(sf), tipo))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) "
          "VALUES ('signed',%s,%s,%s,%s,NOW() - INTERVAL '1 day')", (gid, team, str(sf), c))
    return gid


def fm(n, stagione_lega, valore):
    db._q("""INSERT INTO bref_stats (stagione,nome_bref,team,g,fga,fgm,ftm,fta,fg3m,pts,orb,drb,ast,stl,blk,tov)
             VALUES (%s,%s,'X',50,0,0,0,0,0,%s,0,0,0,0,0,0)""", (str(stagione_lega + 1), n, valore * 2))


def attivo(gid):
    return db._q("SELECT * FROM contratti WHERE giocatore_id=%s AND attivo", (gid,), one=True)


msgs = []


class Bot:
    username = "bot"
    async def send_message(self, chat_id=None, text=None, **k):
        msgs.append((chat_id, text)); return types.SimpleNamespace(message_id=len(msgs))
    async def edit_message_text(self, *a, **k): pass
    async def set_my_commands(self, *a, **k): pass
    async def delete_my_commands(self, *a, **k): pass
    async def pin_chat_message(self, *a, **k): pass


class Q:
    def __init__(s, data):
        s.data = data; s.t = None; s.kb = None
        s.from_user = types.SimpleNamespace(id=ADMIN, first_name="Admin", username="adm")
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t = t; s.kb = k.get("reply_markup")
    def get_bot(s): return Bot()


import handlers.admin_panel as A
import handlers.stagione as S
import handlers.rinnovi as R


def tap(cb, data):
    q = Q(data)
    asyncio.run(cb(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot())))
    return q


testi = []


def passa(nuova, tipo="normal"):
    """Come l'admin: sceglie la fase e, se c'è l'anteprima, conferma."""
    q = tap(A.cb_fase_set, f"fase_set:{nuova}:{tipo}")
    anteprima = q.t
    if q.kb and any(b.callback_data == f"fase_conferma:{nuova}" for r in q.kb.inline_keyboard for b in r):
        q = tap(A.cb_fase_conferma, f"fase_conferma:{nuova}")
    testi.append(q.t or "")
    return anteprima, q.t or ""


nostri = ("Tagliato Dopo", "Scambiato", "Scade", "Va In Rfa", "Rinnovabile", "Rookie Secondo", "Rookie Quarto", "Rookie Primo")


def coerente():
    return not [p for p in db.controlli_coerenza() if any(n in p for n in nostri)]


# ── regular season 2026 ────────────────────────────────────────────────────────
fase("regular-season-fa", 2026)
scade = gioc("Scade", "team01", 8, 1, 2026)
rfa = gioc("Va In Rfa", "team02", 9, 1, 2026)
rinn = gioc("Rinnovabile", "team01", 12, 2, 2026); fm("Rinnovabile", 2026, 21.4)
r2 = gioc("Rookie Secondo", "team01", 13, 1, 2026, "rookie", pick=1, anno_firma=2025); fm("Rookie Secondo", 2026, 26.1)
r4 = gioc("Rookie Quarto", "team02", 8, 1, 2026, "rookie", pick=6, anno_firma=2023)
fm("Rookie Quarto", 2025, 22); fm("Rookie Quarto", 2026, 24.3)
tagl = gioc("Tagliato Dopo", "team04", 6, 2, 2026); fm("Tagliato Dopo", 2026, 14)
scamb = gioc("Scambiato", "team01", 10, 2, 2026); fm("Scambiato", 2026, 12)   # x1 nel 2027, va a team03 nei rinnovi
r1 = gioc("Rookie Primo", "team02", S.importo_scala(3, 0) or 5, 1, 2026, "rookie", pick=3, anno_firma=2026)

passa("regular-season-deadline")
ok(settings.fase() == "regular-season-deadline", "RS → dopo la deadline")
_, t = passa("playoff")
ok(settings.fase() == "regular-season-deadline" and "Non si può ancora passare ai playoff" in t, "ai playoff no senza RS finita e calendario")
q = tap(A.cb_fase_conferma, "fase_conferma:playoff")
ok(settings.fase() == "regular-season-deadline" and "Non si può" in (q.t or ""), "neanche con un «Confermo» rimasto da prima")
from shared import playoff_base
_problemi = playoff_base.problemi_passaggio
playoff_base.problemi_passaggio = lambda s=None: []
passa("playoff")
ok(settings.fase() == "playoff", "ai playoff col tabellone pronto")
playoff_base.problemi_passaggio = _problemi
msgs.clear()
passa("offseason-break")
ok(settings.fase() == "offseason-break" and settings.stagione_corrente() == "2026", "break: la stagione non cambia ancora")
ok(any(ch == GRUPPO and "/archivia_calcolo" in (tx or "") for ch, tx in msgs), "break: promemoria dell'archivio del foglio di controllo")

# ── offseason 2027 ─────────────────────────────────────────────────────────────
db._q("""CREATE TABLE IF NOT EXISTS lega_playoff (stagione TEXT PRIMARY KEY, stato TEXT NOT NULL DEFAULT 'bozza',
         bozza_chat BIGINT, bozza_msg BIGINT, canale_chat BIGINT, canale_msg BIGINT, confermato TIMESTAMPTZ,
         confermato_da TEXT, bloccato TIMESTAMPTZ, creato TIMESTAMPTZ NOT NULL DEFAULT NOW(), campione TEXT)""")
db._q("DELETE FROM lega_playoff WHERE stagione IN ('2026', '2027')")
db._q("INSERT INTO lega_playoff (stagione, stato) VALUES ('2026', 'bloccato')")
_, t = passa("offseason-rinnovi")
ok(settings.fase() == "offseason-break" and "finale dei playoff 2026" in t, "ai rinnovi no finché la finale non è convalidata")
q = tap(A.cb_fase_conferma, "fase_conferma:offseason-rinnovi")
ok(settings.stagione_corrente() == "2026", "neanche con un «Confermo» rimasto da prima")
db._q("UPDATE lega_playoff SET campione = 'team01' WHERE stagione = '2026'")
_, t = passa("offseason-draft", "skip")
ok(settings.fase() == "offseason-break" and "Non si saltano i rinnovi" in t and settings.stagione_corrente() == "2026",
   "dal break non si saltano i rinnovi (la stagione non avanzerebbe)")
anteprima, t = passa("offseason-rinnovi")
ok("2027" in anteprima and settings.fase() == "offseason-rinnovi" and settings.stagione_corrente() == "2027",
   "rinnovi: anteprima, conferma e stagione 2027")
c4, c2, c1 = attivo(r4), attivo(r2), attivo(r1)
ok((c4["importo"], c4["anni_originali"], c4["tipo"], c4["stagione_firma"]) == (15, 0, "normale", "2027"),
   "rookie al IV anno: fine scala con la Doncic d'ufficio, 15x0")
ok(c2["tipo"] == "rookie" and any(c["giocatore_id"] == r2 for c in S.candidati_rinnovo_rookie("team01")),
   "rookie a fine II anno: in attesa del rinnovo rookie")
ok(c1["stagione_firma"] == "2027" and c1["importo"] == (S.importo_scala(3, 1) or c1["importo"]), "rookie al I anno: passa alla scala del II")
ok(db._qval("SELECT count(*) FROM pick WHERE anno = '2033'") > 0, "pick dell'anno nuovo create")
ok(coerente(), "registro coerente dopo il cambio di stagione")
anteprima, t = passa("offseason-rinnovi", "skip")
ok(settings.stagione_corrente() == "2027", "tornare ai rinnovi non fa avanzare la stagione di nuovo")

_, t = passa("offseason-break", "skip")
ok(settings.fase() == "offseason-rinnovi" and "Non si torna alla stagione prima" in t, "dai rinnovi non si torna al break")
r = R.esegui("team01", rinn, "quarto", 2, "prova")
ok(r["dopo"] == "15x2", "rinnovo da ¼: 12x1 → 15x2")
r = R.esegui("team02", r4, "mezzo", 3, "prova")
ok(r["dopo"] == "23x3", "rinnovo da ½ dell'ex rookie: 15x0 → 23x3")
S.dichiara_rfa("team02", rfa, "prova")
# trade nei rinnovi: l'x1 lo rinnova chi lo riceve; un rinnovo non si annulla più dopo una trade
import handlers.trade_esegui as TE
def trade_di(gid, da, a):
    t = db.crea_trade_bozza(da, 2, "2027"); db.aggiungi_squadra_trade(t, da, 1); db.aggiungi_squadra_trade(t, a, 2)
    db.aggiungi_item_trade(t, "giocatore", da, a, giocatore_id=gid)
    db._q("UPDATE trade SET stato='in_approvazione' WHERE id=%s", (t,))
    return t
ok(any(c["giocatore_id"] == scamb for c in R.candidati("team01")), "x1 rinnovabile da chi lo ha")
TE._scrivi_trade(trade_di(scamb, "team01", "team03"), "TRADE-2027-001", "adm")
ok(not any(c["giocatore_id"] == scamb for c in R.candidati("team01")) and any(c["giocatore_id"] == scamb for c in R.candidati("team03")),
   "dopo la trade lo rinnova chi l'ha ricevuto")
r = R.esegui("team03", scamb, "quarto", 2, "prova")
ok(r["dopo"] == "13x2" and attivo(scamb)["team_id"] == "team03", "rinnovato dalla squadra nuova: 10 → 13x2")
# annullare la trade dopo il rinnovo riporterebbe a team01 il contratto rinnovato da team03: non si può
t1 = db._qval("SELECT id FROM trade WHERE trade_ref = 'TRADE-2027-001'") or db._qval("SELECT min(id) FROM trade")
db._q("UPDATE trade SET stato = 'approvata' WHERE id = %s", (t1,))
try:
    TE._scrivi_trade(t1, "TRADE-2027-001", None, inverti=True); ok(False, "trade non annullabile dopo il rinnovo")
except TE.TradeNonEseguibile as e:
    ok("contratto nuovo dopo la trade" in str(e) and attivo(scamb)["team_id"] == "team03",
       "annullare la trade dopo il rinnovo: rifiutato, prima va annullato il rinnovo")
ok(R.usati("team03")["quarto"]["giocatore_id"] == scamb and R.usati("team01")["quarto"]["giocatore_id"] == rinn,
   "il rinnovo da ¼ è consumato da chi l'ha fatto")
TE._scrivi_trade(trade_di(scamb, "team03", "team04"), "TRADE-2027-002", "adm")
try:
    R.annulla("team03", r["id"]); ok(False, "rinnovo ceduto: non si annulla")
except R.StagioneErrore as e:
    ok("non è più attivo" in str(e) and attivo(scamb)["importo"] == 13, "rinnovo poi ceduto: non si annulla, il contratto resta")
ok(R.usati("team03")["quarto"]["giocatore_id"] == scamb and "quarto" not in R.usati("team04"),
   "ceduto il rinnovato: il ¼ resta consumato per team03, team04 ha ancora il suo")
ok(db.rfa_squadra("team02", "2027")["giocatore_id"] == rfa, "RFA dichiarato")

# rinnovato e poi tagliato: l'impatto è sul contratto nuovo, e il rinnovo non si annulla più
import teams as tm
from handlers.tagli import esegui_taglio
r = R.esegui("team04", tagl, "mezzo", 2, "prova")
ok(r["dopo"] == "9x2", "6x1 → 9x2 da ½")
esegui_taglio(tm.get_team_by_id("team04"), tagl)
rate = db._q("SELECT stagione, importo FROM impatto_taglio WHERE giocatore_id = %s ORDER BY stagione", (tagl,), many=True)
ok(sum(x["importo"] for x in rate) == 18 and rate[0]["stagione"] == "2027", f"taglio del rinnovato: impatto su 9x2 (18M) {rate}")
try:
    R.annulla("team04", r["id"]); ok(False, "rinnovo di un tagliato non annullabile")
except R.StagioneErrore as e:
    ok(attivo(tagl) is None and "½" not in "" and "mezzo" in R.usati("team04"), "rinnovo poi tagliato: non si annulla, il ½ resta usato")

msgs.clear()
passa("offseason-draft")
ok(settings.fase() == "offseason-draft" and any(ch == GRUPPO and "lottery" in (tx or "").lower() for ch, tx in msgs),
   "draft: promemoria della lottery agli admin")
# tornare ai rinnovi dopo i rinnovi fatti (e rilanciare i passaggi): niente si rifà sui contratti nuovi
prima = {g: (attivo(g) or {}).get("id") for g in (rinn, r4, scamb, r1)}
passa("offseason-rinnovi", "skip")
S.applica_stagione(2027)
ok(settings.stagione_corrente() == "2027" and {g: (attivo(g) or {}).get("id") for g in prima} == prima,
   "di nuovo ai rinnovi e passaggi rilanciati: i contratti rinnovati e scalati restano quelli")
ok(attivo(r4)["importo"] == 23 and attivo(r4)["anni_originali"] == 3, "l'ex rookie rinnovato non torna 15x0")
passa("offseason-draft")
passa("offseason-rfa")
ok(settings.fase() == "offseason-rfa", "RFA")
msgs.clear()
anteprima, t = passa("offseason-fa")
ok(settings.fase() == "offseason-fa" and "Scade" in (anteprima or ""), "FA: anteprima con gli x0 che scadono")
ok(attivo(scade) is None and attivo(r2) is None and attivo(rfa) is not None,
   "FA: scadono gli x0 non RFA (anche il rookie non rinnovato), l'RFA resta")
ok(db._qval("SELECT count(*) FROM transazioni WHERE tipo = 'expired' AND giocatore_id = ANY(%s)", ([scade, r2],)) == 2,
   "FA: movimento 'expired' per ognuno")
ok(any(ch == GRUPPO and "Calendario 2027-28" in (tx or "") for ch, tx in msgs), "FA: promemoria del calendario")
msgs.clear()
passa("offseason-ruoli")
ok(any(ch == GRUPPO and "Calendario 2027-28" in (tx or "") for ch, tx in msgs), "ruoli: di nuovo il promemoria")

# ── verso la regular season 2027 ───────────────────────────────────────────────
_, t = passa("regular-season-fa")
ok(settings.fase() == "offseason-ruoli" and "Non si può ancora passare alla regular season" in t, "regular season no senza calendario")
q = tap(A.cb_fase_conferma, "fase_conferma:regular-season-fa")
ok(settings.fase() == "offseason-ruoli", "neanche con un «Confermo» rimasto da prima")
_, t = passa("regular-season-deadline", "skip")
ok(settings.fase() == "offseason-ruoli", "né col «Salta a»")
for n in range(1, 39):
    db._q("INSERT INTO lega_giornate (stagione, numero, dal, al) VALUES ('2027', %s, '2027-10-20', '2027-10-21')", (n,))
passa("regular-season-fa")
ok(settings.fase() == "regular-season-fa" and settings.stagione_corrente() == "2027", "regular season 2027 col calendario")
ok(not any("🚨" in x for x in testi), f"nessun passaggio automatico fallito {[x[-120:] for x in testi if '🚨' in x]}")
c = attivo(rinn)
ok((c["importo"], c["anni_originali"], c["stagione_firma"]) == (15, 2, "2027"), "il rinnovo resta com'era")
ok(coerente(), "registro coerente a fine giro")

# ── il giro dopo: verso i rinnovi 2028 ─────────────────────────────────────────
fm("Rinnovabile", 2027, 18)
passa("regular-season-deadline")
playoff_base.problemi_passaggio = lambda s=None: []
passa("playoff")
playoff_base.problemi_passaggio = _problemi
passa("offseason-break")
db._q("INSERT INTO lega_playoff (stagione, stato, campione) VALUES ('2027', 'bloccato', 'team02')")
passa("offseason-rinnovi")
ok(settings.stagione_corrente() == "2028" and R.usati("team01") == {} and R.usati("team03") == {},
   "stagione 2028: i due rinnovi tornano liberi per tutti")
c = next((c for c in R.candidati("team01") if c["giocatore_id"] == rinn), None)
ok(c is not None and c["base"] == 15 and R.opzione(c, "quarto")["importo"] == 19,
   "il rinnovato x2 del 2027 è x1 nel 2028 e si rinnova di nuovo (15 → 19)")
ok(attivo(r1)["tipo"] == "rookie" and any(x["giocatore_id"] == r1 for x in S.candidati_rinnovo_rookie("team02")),
   "il rookie del 2026 arriva a fine II anno")
ok(coerente() and not any("🚨" in x for x in testi), "secondo giro: registro coerente, nessun passaggio fallito")

db._q("DELETE FROM lega_giornate WHERE stagione = '2027'")
db._q("DELETE FROM lega_playoff WHERE stagione IN ('2026', '2027')")
fase("offseason-fa", 2026)
db._q("DELETE FROM inizi_stagione")   # v7.35.4: gli inizi di stagione di prova non restano per le altre prove
