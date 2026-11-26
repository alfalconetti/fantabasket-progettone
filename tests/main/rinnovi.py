import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.32.0: rinnovi normali (uno da ¼ e uno da ½), anteprima, cap, annullamento entro 24 ore."""
import asyncio, types
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, transazioni, dpe, impatto_taglio, rfa_dichiarati, messaggi_fissi, "
      "rinnovi_normali RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)


def fase(f, stagione=None):
    g = settings.load_globals(); g["fase"] = f
    if stagione:
        g["stagione_corrente"] = str(stagione)
    settings.save_globals(g)


def gioc(n, team, imp, anni, sf, tipo="normale"):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (gid, team, imp, anni, str(sf), tipo))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) "
          "VALUES ('signed',%s,%s,%s,%s,NOW() - INTERVAL '1 day')", (gid, team, str(sf), c))
    return gid


def fm(n, stagione_lega, valore):
    """fantamedia = pts/2; stagione bref = stagione di lega + 1."""
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


class Q:
    def __init__(s, data, uid):
        s.data = data; s.t = None; s.kb = None; s.alert = None
        s.from_user = types.SimpleNamespace(id=uid, first_name="Nome", username="u")
    async def answer(s, testo=None, show_alert=False, **k): s.alert = testo
    async def edit_message_text(s, t, **k): s.t = t; s.kb = k.get("reply_markup")
    def get_bot(s): return Bot()


def tap(data, uid):
    q = Q(data, uid)
    asyncio.run(R.cb_rinnovi(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot())))
    return q


def bottoni(q):
    return [b.callback_data for riga in (q.kb.inline_keyboard if q.kb else []) for b in riga]


GM1, GM2, ADMIN = 101, 102, 900
fase("offseason-rinnovi", 2027)
vet = gioc("Veterano", "team01", 11, 2, 2026); fm("Veterano", 2026, 27)        # x1, minimo 15
exr = gioc("Ex Rookie", "team01", 16, 0, 2027); fm("Ex Rookie", 2026, 22)      # fine scala x0, minimo 10
big = gioc("Grosso", "team01", 30, 2, 2026)                                     # ½ → 45: solo x3
nuovo = gioc("Appena Firmato", "team01", 5, 1, 2027)                            # x1 firmato quest'anno: no
lungo = gioc("Lungo", "team01", 8, 3, 2026)                                     # x2: no
x0vecchio = gioc("Vecchio X0", "team01", 9, 1, 2026)                           # x0 normale: no
import handlers.rinnovi as R

# ── regole ─────────────────────────────────────────────────────────────────────
ok((R.aumento(11, "quarto"), R.aumento(11, "mezzo"), R.aumento(8, "quarto"), R.aumento(10, "mezzo")) == (14, 17, 10, 15),
   "+¼ e +½ per eccesso all'intero (11 → 14 e 17, 8 → 10, 10 → 15)")
ok(settings.minimo_contratto_per_media(14.995) == 2 and settings.minimo_contratto_per_media(27) == 15,
   "minimo da tabella: una media tra due fasce resta nella fascia sotto (14,995 → 2)")
cand = {c["giocatore_id"]: c for c in R.candidati("team01")}
ok(set(cand) == {vet, exr, big}, "rinnovabili: x1 appena diventati ed ex rookie x0, non x1 nuovi, x2 o x0 normali")
o1, o2 = R.opzione(cand[vet], "quarto"), R.opzione(cand[vet], "mezzo")
ok((o1["importo"], o1["da_tabella"], o2["importo"], o2["da_tabella"]) == (15, True, 17, False),
   "esempio del regolamento: 11x1 con fantamedia 27 → 15 col ¼ (minimo), 17 col ½")
ok(R.opzione(cand[big], "mezzo")["anni"] == [3] and R.opzione(cand[big], "quarto")["anni"] == [3]
   and o1["anni"] == [2, 3], "x2 o x3, solo x3 da 35M")
ok(cand[exr]["base"] == 16 and cand[exr]["anni_ora"] == 0, "ex rookie: si parte dall'importo dopo la Doncic d'ufficio")

# ── GM: elenco, anteprima, rinnovo ─────────────────────────────────────────────
q = tap("rn:l", GM1)
ok("Da ¼: <b>libero</b>" in q.t and f"rn:g:{vet}" in bottoni(q) and f"rn:g:{nuovo}" not in bottoni(q),
   "GM: elenco con i due rinnovi liberi e i giocatori rinnovabili")
q = tap(f"rn:g:{vet}", GM1)
ok(all(f"rn:s:{vet}:{t}:{a}" in bottoni(q) for t in ("quarto", "mezzo") for a in (2, 3)) and "minimo da tabella" in q.t,
   "GM: anteprima di tutti e due i rinnovi, x2 e x3")
q = tap(f"rn:s:{vet}:quarto:3", GM1)
ok("Simulazione" in q.t and "11x1 → <b>15x3</b>" in q.t and "2029-30" in q.t and f"rn:ok:{vet}:quarto:3" in bottoni(q)
   and attivo(vet)["importo"] == 11 and "resta libero" in q.t, "GM: prima la simulazione (niente scritto), poi la conferma")
q = tap(f"rn:g:{big}", GM1)
ok(f"rn:s:{big}:mezzo:3" in bottoni(q) and f"rn:s:{big}:mezzo:2" not in bottoni(q), "GM: da 35M solo x3")
msgs.clear(); q = tap(f"rn:ok:{vet}:quarto:3", GM1)
c = attivo(vet)
ok("rinnovato" in q.t and (c["importo"], c["anni_originali"], c["stagione_firma"], c["tipo"]) == (15, 3, "2027", "normale"),
   "GM: rinnovato da ¼, 15x3 da questa stagione")
ok(any(ch == -1 and "Veterano" in t and "11x1" in t and "15x3" in t for ch, t in msgs), "annuncio sul canale")
mov = db._q("SELECT tipo FROM movimenti_giocatori WHERE giocatore_id=%s ORDER BY id DESC LIMIT 1", (vet,), one=True)
ok(mov["tipo"] == "renewed", "movimento 'renewed'")
try:
    R.esegui("team01", exr, "quarto", 2, "prova"); ok(False, "secondo ¼ rifiutato")
except R.StagioneErrore as e:
    ok("già usato" in str(e), "secondo rinnovo da ¼ rifiutato")
q = tap(f"rn:g:{exr}", GM1)
ok("già usato per Veterano" in q.t and f"rn:s:{exr}:mezzo:2" in bottoni(q) and f"rn:s:{exr}:quarto:2" not in bottoni(q),
   "anteprima: il ¼ usato non si offre più, il ½ sì")
q = tap(f"rn:ok:{exr}:mezzo:2", GM1)
c = attivo(exr)
ok((c["importo"], c["anni_originali"]) == (24, 2), "ex rookie rinnovato da ½: 16 → 24x2")
q = tap("rn:l", GM1)
ok("tutti e due" in q.t and not any(b.startswith("rn:g:") for b in bottoni(q)), "usati tutti e due: niente più rinnovabili da scegliere")

# ── annullamento entro 24 ore ──────────────────────────────────────────────────
rq = R.usati("team01")["quarto"]
ok(f"rn:u:{rq['id']}" in bottoni(q), "elenco: bottone per annullare")
msgs.clear(); q = tap(f"rn:uok:{rq['id']}", GM1)
c = attivo(vet)
ok((c["importo"], c["anni_originali"], c["stagione_firma"]) == (11, 2, "2026") and "quarto" not in R.usati("team01"),
   "annullato: torna 11x1 e il ¼ è di nuovo libero")
mov = db._q("SELECT tipo FROM movimenti_giocatori WHERE giocatore_id=%s ORDER BY id DESC LIMIT 1", (vet,), one=True)
ok(mov["tipo"] == "signed" and not [p for p in db.controlli_coerenza() if "Veterano" in p or "Ex Rookie" in p], "via il movimento del rinnovo, registro coerente")
ok(any("annulla il rinnovo" in t for _, t in msgs), "annullamento sul canale")
rm = R.usati("team01")["mezzo"]
db._q("UPDATE rinnovi_normali SET creato = NOW() - INTERVAL '25 hours' WHERE id = %s", (rm["id"],))
try:
    R.annulla("team01", rm["id"]); ok(False, "annullamento dopo 24 ore rifiutato")
except R.StagioneErrore as e:
    ok("24 ore" in str(e), "dopo 24 ore non si annulla più")
q = tap("rn:l", GM1)
ok(f"rn:u:{rm['id']}" not in bottoni(q), "dopo 24 ore niente bottone per annullare")

# ── cap: avviso sopra 150, blocco sopra 165 ────────────────────────────────────
gioc("Stipendio", "team02", 140, 3, 2026)
t2 = gioc("Da Rinnovare", "team02", 10, 2, 2026)              # cap 150: ¼ → 13 (153), ½ → 15 (155)
q = tap(f"rn:g:{t2}", GM2)
ok("⚠️ sopra 150M" in q.t and f"rn:s:{t2}:mezzo:2" in bottoni(q), "cap sopra 150: avviso, si può")
gioc("Altro Stipendio", "team02", 12, 3, 2026)                 # cap 162: ¼ → 165 sì, ½ → 167 no
q = tap(f"rn:g:{t2}", GM2)
ok(f"rn:s:{t2}:quarto:2" in bottoni(q) and f"rn:s:{t2}:mezzo:2" not in bottoni(q) and "⛔" in q.t,
   "cap sopra 165: il rinnovo non si offre")
try:
    R.esegui("team02", t2, "mezzo", 2, "prova"); ok(False, "sopra 165 rifiutato")
except R.StagioneErrore as e:
    ok("tetto" in str(e), "sopra 165 rifiutato anche chiamando direttamente")

# ── admin, fasi ────────────────────────────────────────────────────────────────
q = tap("rna:scegli", ADMIN)
ok("rna:team01:l" in bottoni(q), "admin: elenco delle squadre")
msgs.clear(); q = tap(f"rna:team01:ok:{vet}:quarto:2", ADMIN)
ok((attivo(vet)["importo"], attivo(vet)["anni_originali"]) == (15, 2) and any("Registrato da un admin" in t for _, t in msgs)
   and any(ch == 101 for ch, _ in msgs), "admin: rinnovo per conto della squadra, annuncio e avviso al GM")
q = tap("rna:scegli", GM1)
ok(q.alert and "Solo admin" in q.alert, "GM: niente pannello admin")
fase("offseason-draft")
q = tap("rn:l", GM1)
ok(q.alert and "fase dei rinnovi" in q.alert, "GM: fuori dalla fase dei rinnovi no")
q = tap("rna:team01:l", ADMIN)
ok(q.alert is None and "Rinnovi" in (q.t or ""), "admin: anche nella fase del draft")
fase("offseason-fa", 2026)
