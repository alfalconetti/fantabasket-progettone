import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v3.11.0: bottoni di rinnovo rookie e RFA (GM e admin) e conferma con anteprima del
cambio di fase."""
import asyncio, types
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, transazioni, dpe, impatto_taglio, rfa_dichiarati RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)


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
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s)",
          (gid, team, str(sf), c))
    return gid


msgs = []


class Bot:
    username = "bot"
    async def send_message(self, chat_id=None, text=None, **k): msgs.append((chat_id, text))
    async def set_my_commands(self, *a, **k): pass
    async def delete_my_commands(self, *a, **k): pass


class Q:
    def __init__(s, data, uid):
        s.data = data; s.t = None; s.kb = None; s.alert = None
        s.from_user = types.SimpleNamespace(id=uid, first_name="Nome", username="u")
    async def answer(s, testo=None, show_alert=False, **k): s.alert = testo
    async def edit_message_text(s, t, **k): s.t = t; s.kb = k.get("reply_markup")
    def get_bot(s): return Bot()


def tap(cb, data, uid):
    q = Q(data, uid)
    asyncio.run(cb(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot())))
    return q


def bottoni(q):
    return [b.callback_data for riga in (q.kb.inline_keyboard if q.kb else []) for b in riga]


GM1, GM2, ADMIN = 101, 102, 900
# stagione 2027 già iniziata: rookie a fine II anno (pick 1: scala III 14) e un veterano x0
fase("offseason-rinnovi", 2027)
rk = gioc("Rookie Fine", "team01", 13, 1, 2026, "rookie", pick=1, anno_firma=2025)
vx = gioc("Vecchio X0", "team01", 18, 2, 2025)
v2 = gioc("Altro X0", "team02", 9, 1, 2026)
import handlers.stagione as S

q = tap(S.cb_stagione, "sg:rr", GM1)
ok("Rookie Fine" in q.t and "14x2" in q.t and f"sg:rrg:{rk}" in bottoni(q), "GM: elenco dei rookie da rinnovare con la proposta")
q = tap(S.cb_stagione, f"sg:rrg:{rk}", GM1)
ok(f"sg:rrok:{rk}" in bottoni(q) and "III e IV anno" in q.t, "GM: conferma del rinnovo")
msgs.clear(); q = tap(S.cb_stagione, f"sg:rrok:{rk}", GM1)
c = db._q("SELECT * FROM contratti WHERE giocatore_id=%s AND attivo", (rk,), one=True)
ok("rinnovato" in q.t and (c["importo"], c["anni_originali"]) == (14, 2), "GM: rinnovato 14x2 (scala III)")
ok(any(ch == -1 and "rinnova il rookie" in t for ch, t in msgs), "annuncio sul canale")
q = tap(S.cb_stagione, f"sg:rrok:{rk}", GM1)
ok("❌" in q.t and db._qval("SELECT count(*) FROM contratti WHERE giocatore_id=%s", (rk,)) == 2, "secondo tap: niente doppio rinnovo")

q = tap(S.cb_stagione, "sg:rfa", GM1)
ok(f"sg:rfag:{vx}" in bottoni(q) and f"sg:rfag:{rk}" not in bottoni(q), "GM: RFA solo tra gli x0 (il rookie rinnovato non c'è più)")
q = tap(S.cb_stagione, f"sg:rfag:{vx}", GM1)
ok(f"sg:rfaok:{vx}" in bottoni(q) and "18M sul cap" in q.t, "GM: conferma RFA con il peso sul cap")
msgs.clear(); q = tap(S.cb_stagione, f"sg:rfaok:{vx}", GM1)
ok(db.rfa_squadra("team01", "2027")["giocatore_id"] == vx and any("dichiara RFA" in t for _, t in msgs), "GM: dichiarato e annunciato")
q = tap(S.cb_stagione, "sg:rfa", GM1)
ok("sg:rfano" in bottoni(q) and "Vecchio X0" in q.t, "GM: si vede il dichiarato e si può togliere")
msgs.clear(); q = tap(S.cb_stagione, "sg:rfano", GM1)
ok(db.rfa_squadra("team01", "2027") is None and any("ritira" in t for _, t in msgs), "GM: tolto")

# fuori fase e permessi
fase("offseason-draft")
q = tap(S.cb_stagione, f"sg:rfaok:{vx}", GM1)
ok(q.alert and "rinnovi" in q.alert and db.rfa_squadra("team01", "2027") is None, "GM fuori dalla fase dei rinnovi: niente")
q = tap(S.cb_stagione, f"sga:team02:rfaok:{v2}", GM1)
ok(q.alert and "admin" in q.alert.lower() and db.rfa_squadra("team02", "2027") is None, "callback admin da un GM: rifiutata")
q = tap(S.cb_stagione, "sga:scegli:rfa", ADMIN)
ok("sga:elenco" in bottoni(q) and "sga:team02:rfa" in bottoni(q), "admin: scelta della squadra (anche nella fase del draft)")
msgs.clear(); q = tap(S.cb_stagione, f"sga:team02:rfaok:{v2}", ADMIN)
ok(db.rfa_squadra("team02", "2027")["giocatore_id"] == v2, "admin: dichiarato per conto di team02")
ok(any(ch == GM2 and "admin" in t for ch, t in msgs) and any("Registrato da un admin" in t for _, t in msgs),
   "avviso al GM e annuncio con l'admin")
q = tap(S.cb_stagione, "sga:elenco", ADMIN)
ok("Altro X0" in q.t, "admin: elenco degli RFA dichiarati")

# conferma del cambio di fase con anteprima
import handlers.admin_panel as A
fase("offseason-break", 2027)
q = tap(A.cb_fase_set, "fase_set:offseason-rinnovi:normal", ADMIN)
ok("stagione 2028" in q.t and "fase_conferma:offseason-rinnovi" in bottoni(q) and settings.fase() == "offseason-break",
   "avanzamento ai rinnovi: prima l'anteprima e la conferma")
q = tap(A.cb_fase_conferma, "fase_conferma:offseason-rinnovi", ADMIN)
ok(settings.fase() == "offseason-rinnovi" and settings.stagione_corrente() == "2028" and "Rookie" in q.t,
   f"confermato: stagione 2028 e passaggi fatti ({q.t[-80:]!r})")
c = db._q("SELECT * FROM contratti WHERE giocatore_id=%s AND attivo", (rk,), one=True)
ok((c["importo"], c["anni_originali"], c["stagione_firma"]) == (15, 1, "2028"), "rookie rinnovato a scala: al IV anno passa a 15x1 (scala IV)")
q = tap(A.cb_fase_conferma, "fase_conferma:offseason-rinnovi", ADMIN)
ok(settings.stagione_corrente() == "2028", "doppio tap: la stagione non avanza due volte")
q = tap(A.cb_fase_set, "fase_set:offseason-draft:normal", ADMIN)
ok(settings.fase() == "offseason-draft", "passaggio senza effetti sui contratti: diretto come prima")
# tornare ai rinnovi da una fase successiva (errore corretto con "Salta a"): la stagione resta
q = tap(A.cb_fase_set, "fase_set:offseason-rinnovi:skip", ADMIN)
ok("stagione 2029" not in q.t, "salto indietro ai rinnovi: nessuna anteprima di stagione nuova")
q = tap(A.cb_fase_conferma, "fase_conferma:offseason-rinnovi", ADMIN)
ok(settings.stagione_corrente() == "2028" and settings.fase() == "offseason-rinnovi", "salto indietro ai rinnovi: la stagione non avanza")
