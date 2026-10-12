import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Cambio di stagione (v3.11.0): rookie scale, Doncic, x0, rinnovo rookie, RFA dichiarati,
regola delle trade RFA, scadenza degli x0, pick nuove, report di inizio regular season."""
import asyncio
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe, "
      "impatto_taglio, rfa_dichiarati, migrazioni RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)


def fase(f, stagione=None):
    g = settings.load_globals(); g["fase"] = f
    if stagione:
        g["stagione_corrente"] = str(stagione)
    settings.save_globals(g)


def gioc(n):
    return db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))


def contratto(gid, team, imp, anni, sf, tipo="normale"):
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (gid, team, imp, anni, str(sf), tipo))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s)",
          (gid, team, str(sf), c))
    return c


def rookie(n, team, pick, anno_firma, imp, anni, sf=None):
    gid = gioc(n)
    db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft,anno_firma,firmato) "
          "VALUES (%s,%s,1,%s,%s,%s,TRUE)", (gid, team, pick, str(anno_firma), str(anno_firma)))
    contratto(gid, team, imp, anni, sf or anno_firma, "rookie")
    return gid


def fm(n, stagione_lega, valore):
    """fantamedia = pts/2 (le altre voci a 0); stagione bref = stagione di lega + 1."""
    db._q("""INSERT INTO bref_stats (stagione,nome_bref,team,g,fga,fgm,ftm,fta,fg3m,pts,orb,drb,ast,stl,blk,tov)
             VALUES (%s,%s,'X',50,0,0,0,0,0,%s,0,0,0,0,0,0)""", (str(stagione_lega + 1), n, valore * 2))


def attivo(gid):
    return db._q("SELECT * FROM contratti WHERE giocatore_id=%s AND attivo", (gid,), one=True)


import handlers.stagione as S

# ── Doncic: fantamedia per difetto, importo per eccesso ────────────────────────
casi = {19.99: None, 20: 12, 21: 13, 22: 14, 24.99: 15, 25: 15, 26: 16, 27.9: 16, 28: 17, 30: 17, 32.4: 18, 40: 21}
ok(all(S.doncic(k) == v for k, v in casi.items()),
   "Doncic: " + ", ".join(f"{k}→{S.doncic(k)}" for k in casi))

# ── situazione di partenza: stagione 2026, contratti rookie col vecchio formato ─
fase("offseason-ruoli", 2026)
r1 = rookie("Primo Anno", "team01", 1, 2026, 12, 2)        # I anno 12x2
r2 = rookie("Secondo Anno", "team01", 1, 2025, 13, 1)      # II anno 13x1
r3 = rookie("Terzo Scala", "team02", 2, 2024, 12, 2)       # III anno di scala (pick 2: 10/11/12/13)
r4 = rookie("Terzo Doncic", "team02", 1, 2024, 20, 2)      # III anno con Doncic: niente scalino
r5 = rookie("Quarto Bravo", "team03", 4, 2023, 11, 1)      # IV anno (pick 4: 8/9/10/11), fantamedia alta
r6 = rookie("Quarto Normale", "team03", 4, 2023, 11, 1)    # IV anno senza fantamedia
fm("Quarto Bravo", 2025, 22.5); fm("Quarto Bravo", 2026, 27.95)   # max 27.95 → 27 → 15+⌈0,8⌉ = 16
fm("Secondo Anno", 2025, 21.0); fm("Secondo Anno", 2026, 24.95)   # per il rinnovo: 24 → 12+⌈2,4⌉ = 15 > scala III 14
v1 = gioc("Veterano Uno"); contratto(v1, "team01", 30, 1, 2026)   # x1 nel 2026 → x0 nel 2027
v2 = gioc("Veterano Due"); contratto(v2, "team02", 25, 1, 2026)
v3 = gioc("Veterano Tre"); contratto(v3, "team04", 10, 3, 2026)   # in corso
db._q("DELETE FROM migrazioni WHERE nome='rookie_pezzi_v3_11'"); db._migra_stagioni()
ok([attivo(g)["stagione_firma"] for g in (r1, r2, r3, r4, r5, r6)] == ["2026"] * 6,
   "migrazione: i pezzi successivi al I anno partono dalla stagione in corso")
ok([db.anni_residui(attivo(g), 2026) for g in (r1, r2, r3, r4, r5, r6)] == [2, 1, 2, 2, 1, 1],
   "anni residui nel 2026: I 2, II 1, III 2, IV 1")
n = db._qval("SELECT count(*) FROM contratti"); db._migra_stagioni()
ok(db._qval("SELECT count(*) FROM contratti") == n and attivo(r1)["stagione_firma"] == "2026", "migrazione una volta sola")

# ── anteprima e passaggio alla stagione 2027 ───────────────────────────────────
anteprima = S.piano_stagione(2027)
ok([v["giocatore_id"] for v in anteprima["secondo_anno"]] == [r1] and [v["giocatore_id"] for v in anteprima["quarto_anno"]] == [r3]
   and {v["giocatore_id"] for v in anteprima["fine_scala"]} == {r5, r6} and [v["giocatore_id"] for v in anteprima["da_rinnovare"]] == [r2],
   "anteprima 2027: I→II, III→IV solo di scala, fine scala, II a fine anno da rinnovare")
ok(db._qval("SELECT count(*) FROM contratti") == n, "anteprima: niente scritto")
fase("offseason-rinnovi", 2027)
S.applica_stagione(2027)
c1 = attivo(r1); c3 = attivo(r3); c4 = attivo(r4); c5 = attivo(r5); c6 = attivo(r6)
ok((c1["importo"], c1["anni_originali"], c1["stagione_firma"], c1["tipo"]) == (13, 1, "2027", "rookie"), f"II anno: 13x1 (era 12x2) {dict(c1)}")
ok((c3["importo"], db.anni_residui(c3, 2027)) == (13, 1), "III→IV di scala: 13x1")
ok((c4["importo"], db.anni_residui(c4, 2027), c4["id"]) == (20, 1, db._qval("SELECT min(id) FROM contratti WHERE giocatore_id=%s", (r4,))),
   "III→IV con Doncic: stesso contratto, 20x1")
ok((c5["importo"], db.anni_residui(c5, 2027), c5["tipo"]) == (16, 0, "normale"), "fine scala: Doncic d'ufficio 16x0 (fantamedia 27,95 → 27)")
ok((c6["importo"], db.anni_residui(c6, 2027), c6["tipo"]) == (11, 0, "normale"), "fine scala senza Doncic: 11x0 normale")
ok(db.anni_residui(attivo(r2), 2027) == 0 and attivo(r2)["tipo"] == "rookie", "II anno finito: x0 in attesa del rinnovo rookie")
ok(db._qval("SELECT count(*) FROM transazioni WHERE tipo='rookie_scala' AND rookie_scale") == 2
   and db._qval("SELECT count(*) FROM transazioni WHERE tipo='rookie_fine_scala'") == 2, "movimenti rookie_scala e rookie_fine_scala")
ok(db._qval("SELECT count(*) FROM contratti WHERE attivo=FALSE") == 4, "contratti vecchi chiusi (attivo=FALSE), non cancellati")
ok(db._qval("SELECT anni_scala FROM rookie WHERE giocatore_id=%s", (r5,)) == 4, "rookie.anni_scala aggiornato")
n = db._qval("SELECT count(*) FROM contratti"); S.applica_stagione(2027)
ok(db._qval("SELECT count(*) FROM contratti") == n, "rilanciato: niente di nuovo")
coer = [p for p in db.controlli_coerenza() if "storico di pick" not in p]   # lo storico si crea più avanti
ok(coer == [], f"coerenza dopo il passaggio {coer}")

# ── x0: niente cap e slot ───────────────────────────────────────────────────────
roster1 = db.get_roster_team("team01")
ok(db.cap_occupato_team("team01", "2027") == 13 and db.slot_occupati(roster1) == 1,
   "team01: x0 (Veterano Uno 30, Secondo Anno 13) fuori da cap e slot → 13M, 1 slot")
ok({r["giocatore_id"] for r in roster1 if r["x0"]} == {r2, v1}, "roster: gli x0 restano in squadra, segnati")

# ── rinnovo rookie: max(scala III, Doncic) x2 ──────────────────────────────────
cand = S.candidati_rinnovo_rookie("team01")
ok([(c["giocatore_id"], c["importo_nuovo"], c["doncic"]) for c in cand] == [(r2, 15, True)],
   f"proposta: Doncic 15 (fantamedia 24,95 → 24) contro scala III 14 {[c['spiegazione'] for c in cand]}")
S.esegui_rinnovo_rookie("team01", r2)
c2 = attivo(r2)
ok((c2["importo"], c2["anni_originali"], c2["stagione_firma"], c2["tipo"]) == (15, 2, "2027", "rookie"), "rinnovo: 15x2 rookie")
ok(db._qval("SELECT rookie_scale FROM transazioni WHERE tipo='renewed' AND giocatore_id=%s", (r2,)) is True, "movimento renewed (rookie_scale)")
try:
    S.esegui_rinnovo_rookie("team01", r2); ok(False, "secondo rinnovo rifiutato")
except S.StagioneErrore:
    ok(True, "secondo rinnovo rifiutato")
ok(db.cap_occupato_team("team01", "2027") == 28, "cap dopo il rinnovo: 13 + 15")

# ── RFA dichiarati: cap sì, slot no; uno per squadra ────────────────────────────
try:
    S.dichiara_rfa("team04", v3, "test"); ok(False, "contratto in corso non dichiarabile")
except S.StagioneErrore:
    ok(True, "contratto in corso non dichiarabile")
S.dichiara_rfa("team01", v1, "test")
ok(db.cap_occupato_team("team01", "2027") == 58 and db.slot_occupati(db.get_roster_team("team01")) == 2,
   "RFA dichiarato: +30 di cap, nessuno slot")
S.dichiara_rfa("team03", r5, "test"); S.dichiara_rfa("team03", r6, "test")
ok(db.rfa_squadra("team03", "2027")["giocatore_id"] == r6 and not db.rfa_dichiarato(r5, "2027"),
   "una sola dichiarazione per squadra: la seconda sostituisce la prima")
S.revoca_rfa("team03")
ok(db.rfa_squadra("team03", "2027") is None, "revoca")
S.dichiara_rfa("team02", v2, "test")

# ── regola delle trade RFA ──────────────────────────────────────────────────────
from validators.trade import _errori_rfa
it = lambda gid, da, a: {"tipo": "giocatore", "giocatore_id": gid, "team_id_da": da, "team_id_a": a}
ok(_errori_rfa([it(v1, "team01", "team02"), it(v2, "team02", "team01")], ["team01", "team02"], "2027") == [],
   "RFA contro RFA: ok")
ok(len(_errori_rfa([it(v1, "team01", "team02")], ["team01", "team02"], "2027")) == 1,
   "RFA a chi ne ha già uno: no")
ok(_errori_rfa([it(v1, "team01", "team04")], ["team01", "team04"], "2027") == [],
   "RFA a chi non ne ha: ok")
ok(_errori_rfa([it(r6, "team03", "team04")], ["team03", "team04"], "2027") == [],
   "x0 non dichiarato: si scambia liberamente")
import handlers.trade as T
t = db.crea_trade_bozza("team01", 2, "2027"); db.aggiungi_squadra_trade(t, "team01", 1); db.aggiungi_squadra_trade(t, "team04", 2)
db.aggiungi_item_trade(t, "giocatore", "team01", "team04", giocatore_id=v1)
db._q("UPDATE trade SET stato='in_approvazione' WHERE id=%s", (t,))
T._scrivi_trade(t, "TRADE-2027-001", "adm")
ok(db.rfa_squadra("team04", "2027")["giocatore_id"] == v1 and db.rfa_squadra("team01", "2027") is None,
   "trade: la dichiarazione segue il giocatore")
ok(db.cap_occupato_team("team04", "2027") == 40, "chi lo riceve: l'RFA pesa sul suo cap (10 + 30)")
T._scrivi_trade(t, "TRADE-2027-001", None, inverti=True)
ok(db.rfa_squadra("team01", "2027")["giocatore_id"] == v1, "annullamento: la dichiarazione torna indietro")

# ── pick dell'anno +6 ───────────────────────────────────────────────────────────
for t in ("team01", "team02", "team03", "team04"):
    db._q("INSERT INTO pick (proprietario_orig,proprietario_att,anno,round) VALUES (%s,%s,'2028',1)", (t, t))
db._migra_registro_unico()            # crea lo storico (righe 'iniziale')
ok(S.crea_pick_anno(2033) == 8 and S.crea_pick_anno(2033) == 0, "pick 2033: 2 per squadra, una volta sola")
ok(db._qval("SELECT count(*) FROM transazioni WHERE oggetto='pick' AND tipo='creata'") == 8, "movimento 'creata' nel registro")
ok(db.controlli_coerenza() == [], f"coerenza con le pick nuove {db.controlli_coerenza()}")

# ── inizio FA: scadono gli x0 non RFA ──────────────────────────────────────────
fase("offseason-fa")
ok(any("x0" in p for p in db.controlli_coerenza()), "coerenza: x0 ancora attivi fuori dalle fasi dei rinnovi → segnalati")
scaduti = {c["giocatore_id"] for c in S.scadenza_x0(2027)}
ok(scaduti == {r5, r6}, f"scaduti: i due ex rookie non rinnovati (gli RFA restano) {scaduti}")
ok(attivo(v1) and attivo(v2) and not attivo(r5), "RFA ancora sotto contratto fino alla fine dell'asta")
ok(db._qval("SELECT count(*) FROM transazioni WHERE tipo='expired'") == 2, "movimenti 'expired'")
ok(db.controlli_coerenza() == [], f"coerenza dopo le scadenze {db.controlli_coerenza()}")
# asta RFA conclusa: il bot aste chiude il contratto → la dichiarazione smette di pesare
db._q("UPDATE contratti SET attivo=FALSE WHERE giocatore_id=%s AND attivo", (v1,))
ok(db.rfa_squadra("team01", "2027") is None and db.rfa_usata("team01", "2027") is not None,
   "dopo l'asta: non pesa più, ma la RFA della stagione risulta usata")

# ── inizio regular season: report del floor ────────────────────────────────────
fase("regular-season-fa")
testo = S.testo_report_inizio_rs() or ""
ok("/set_cap_penalizzato team04" in testo and "team03" in testo, "report RS: comando suggerito per chi è sotto il floor")

# ── passaggi di fase: anteprima e hook ─────────────────────────────────────────
class Bot:
    def __init__(self): self.msg = []
    async def send_message(self, chat_id, text, **k): self.msg.append((chat_id, text))
fase("offseason-break", 2027)
ok("stagione 2028" in (S.anteprima_fase("offseason-break", "offseason-rinnovi") or ""), "anteprima del passaggio ai rinnovi")
ok(S.anteprima_fase("offseason-rinnovi", "offseason-draft") is None, "nessuna anteprima per i passaggi senza effetti")
b = Bot()
fase("offseason-rfa")
nota = asyncio.run(S.dopo_cambio_fase(b, "offseason-draft", "offseason-rfa"))
ok(nota == "" and db._qval("SELECT count(*) FROM pick WHERE anno='2034'") == 0, "fase RFA: nessuna pick nuova (si creano ai rinnovi)")
fase("offseason-rinnovi", 2028)
nota = asyncio.run(S.dopo_cambio_fase(b, "offseason-break", "offseason-rinnovi"))
ok("Rookie:" in nota and any(c == -2 for c, _ in b.msg), f"rinnovi 2028: passaggio fatto e dettaglio al gruppo admin {nota!r}")
ok("2034 (8)" in nota and db._qval("SELECT count(*) FROM pick WHERE anno='2034'") == 8, "rinnovi 2028: create le pick del 2034")
nota = asyncio.run(S.dopo_cambio_fase(b, "offseason-draft", "offseason-rinnovi"))
ok("2034" not in nota and db._qval("SELECT count(*) FROM pick WHERE anno='2034'") == 8, "tornando ai rinnovi: nessun doppione")

# messaggi lunghi: file Markdown al posto dei messaggi spezzati
from shared.messaggi import manda_lungo, html_a_markdown
class BotDoc(Bot):
    def __init__(self): super().__init__(); self.doc = []
    async def send_document(self, chat_id=None, document=None, filename=None, caption=None, **k):
        self.doc.append((chat_id, filename, document.getvalue().decode(), caption))
bd = BotDoc()
asyncio.run(manda_lungo(bd, -2, "<b>Breve</b>\nok", "prova"))
ok(bd.msg == [(-2, "<b>Breve</b>\nok")] and not bd.doc, "testo corto: messaggio normale")
lungo = "📅 <b>Titolo &amp; co.</b>\n\n<b>📈 Sezione</b> (3)\n" + "\n".join(f"  • Giocatore {i} (<i>Squadra</i>): 3x1 → 4x1" for i in range(300))
asyncio.run(manda_lungo(bd, -2, lungo, "prova", riassunto="📅 <b>Titolo</b>: 300 righe"))
ch, nome, md, didascalia = bd.doc[-1]
ok(nome.startswith("prova-") and nome.endswith(".md") and "Titolo" in didascalia and len(bd.msg) == 1,
   "testo lungo: un file .md con il riassunto, nessun messaggio spezzato")
ok(md.startswith("# 📅 Titolo & co.") and "## 📈 Sezione (3)" in md and "- Giocatore 0 (_Squadra_): 3x1 → 4x1" in md,
   "Markdown: titolo, sezioni, elenchi, corsivo, entità sciolte")
