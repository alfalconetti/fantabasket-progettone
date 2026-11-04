import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v6.5.0 (Luca, 23/10): /carriera, due timeline in parallelo dal 25/07/2026 (fantabasket e NBA reale)
e i cambi di squadra NBA salvati da loucabot (nba_movimenti)."""
import asyncio, importlib.util, json, os, types
from datetime import date, datetime, timezone
import database as db
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe RESTART IDENTITY CASCADE")
# tabelle di loucabot (nba_atleti, nba_movimenti) e bref_stats nello stesso database
spec = importlib.util.spec_from_file_location("louca_db", os.path.join(ROOT, "fantabasket-loucabot", "db.py"))
ldb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ldb); ldb.init_db()
db._q("TRUNCATE nba_atleti, nba_movimenti")
db._q(open(os.path.join(ROOT, "fantabasket-main", "bref_schema.sql")).read())
db._q("TRUNCATE bref_stats")

def g(n, espn=None):
    return db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id", (n, n, n.lower(), espn))
def c(gid, t, imp, anni, att=True, tipo="normale"):
    return db._qval("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) "
                    "VALUES (%s, %s, %s, %s, '2026', %s, %s) RETURNING id", (gid, t, imp, anni, tipo, att))
def tx(tipo, gid, da, a, cid, ts, note=None, trade=None, oggetto="giocatore"):
    db._q("INSERT INTO transazioni (tipo, oggetto, giocatore_id, team_id_da, team_id_a, stagione, contratto_id, timestamp, note, trade_id) "
          "VALUES (%s, %s, %s, %s, %s, '2026', %s, %s, %s, %s)", (tipo, oggetto, gid, da, a, cid, ts, note, trade))
_nt = [0]
def trade():
    _nt[0] += 1
    return db._qval("INSERT INTO trade (stato, stagione, n_squadre, proposta_da, trade_ref) VALUES ('approvata', '2026', 2, 'team01', %s) RETURNING id",
                    (f"TRADE-2026-{_nt[0]:03d}",))

p = g("Gio Prova", "e1")
c1 = c(p, "team01", 10, 3, att=False)
tx("signed", p, None, "team01", c1, "2026-07-25 22:00+02", "migrazione iniziale")
t1, t2 = trade(), trade()
tx("traded", p, "team01", "team02", c1, "2026-08-10 12:00+02", None, t1)
tx("traded", p, "team02", "team03", c1, "2026-09-01 12:00+02", "TRADE-X", t2)
tx("traded", p, "team03", "team02", c1, "2026-09-01 13:00+02", "ANNULLAMENTO TRADE-X", t2)
tx("cut", p, "team02", None, c1, "2026-09-20 12:00+02")
c2 = c(p, "team04", 3, 1)
tx("signed", p, None, "team04", c2, "2026-09-25 12:00+02", "Firma FA bot aste — Gio Prova 3M x1")
db._q("INSERT INTO dpe (giocatore_id, team_id, stagione, importo_originale, importo_dpe, timestamp) VALUES (%s, 'team04', '2026', 3, 1, '2026-10-05 12:00+02')", (p,))
tx("signed", p, None, "team09", c2, "2026-06-01 12:00+02", "prima del bot: non si vede")
# un rookie coi soli diritti
r = g("Rook Prova")
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft) VALUES (%s, 'team02', 1, 4, '2026')", (r,))
tx("iniziale", r, None, "team02", None, "2026-07-25 22:00+02", "Situazione all'avvio", oggetto="diritti")

# NBA: al 25/07 a CHA (bref), poi trade a SAC vista da ESPN il 05/02 e da bref il 07/02 (non si ripete)
for ts, team in [("2026-10-22", "CHO"), ("2026-10-23", "CHO"), ("2027-02-07", "SAC"), ("2027-02-08", "SAC")]:
    db._q("INSERT INTO bref_stats (timestamp, stagione, nome_bref, team, g) VALUES (%s, '2027', 'Gio Prova', %s, 1)", (ts, team))
ldb.salva_atleti([{"atleta": "e1", "nome": "Gio Prova", "squadra": "CHA"}], giorno=date(2026, 10, 23))
ldb.salva_atleti([{"atleta": "e1", "nome": "Gio Prova", "squadra": "SAC"}], giorno=date(2027, 2, 5))
mv = db._q("SELECT giorno, da, a FROM nba_movimenti WHERE atleta = 'e1'", many=True)
ok(len(mv) == 1 and mv[0]["da"] == "CHA" and mv[0]["a"] == "SAC" and mv[0]["giorno"] == date(2027, 2, 5),
   f"loucabot: il cambio di squadra dei roster ESPN finisce in nba_movimenti col giorno {mv}")
ldb.salva_atleti([{"atleta": "e1", "nome": "Gio Prova", "squadra": "SAC"}], giorno=date(2027, 2, 6))
ok(db._qval("SELECT COUNT(*) FROM nba_movimenti WHERE atleta = 'e1'") == 1, "stessa squadra: nessun movimento nuovo")

import handlers.carriera as C
f = C.eventi_fanta(p)
et = [(x["etichetta"], x["titolo"]) for x in f]
nomi = {t: C.tm.get_team_by_id(t)["nome"] for t in ("team01", "team02", "team04")}
ok(et == [("All'avvio", nomi["team01"]), ("Trade", nomi["team02"]), ("Taglio", "Free agent"), ("Firma FA", nomi["team04"]), ("DPE", nomi["team04"])],
   f"fantabasket: avvio, trade, (trade annullata sparita), taglio, firma all'asta, DPE; niente prima del 25/07 {et}")
ok("TRADE-2026-001" in f[1]["dettaglio"], f"trade col suo numero, per ritrovarla: {f[1]['dettaglio']}")
# due trade nello stesso giorno: due righe, la data solo sulla prima
dd = g("Doppio Scambio")
cd = c(dd, "team03", 5, 2)
tx("signed", dd, None, "team01", cd, "2026-07-25 22:00+02", "migrazione iniziale")
tx("traded", dd, "team01", "team02", cd, "2026-11-03 10:00+01", None, trade())
tx("traded", dd, "team02", "team03", cd, "2026-11-03 18:00+01", None, trade())
rd = [x for x in C.righe_timeline(C.eventi_fanta(dd), []) if x["giorno"] == "03/11"]
ok(len(rd) == 2 and rd[0]["mostra_data"] and not rd[1]["mostra_data"] and rd[0]["fanta_sq"]["nome"] != rd[1]["fanta_sq"]["nome"]
   and "TRADE-2026-003" in rd[0]["fanta"]["dettaglio"] and "TRADE-2026-004" in rd[1]["fanta"]["dettaglio"],
   "due trade nello stesso giorno: due schede in ordine, ognuna col suo numero e la sua squadra, la data una volta sola")
ok("10M × 3" in f[0]["dettaglio"] and "2026-27" in f[0]["dettaglio"] and f"da {nomi['team01']}" in f[1]["dettaglio"]
   and "asta vinta: 3M × 1" in f[3]["dettaglio"] and "pesa 1M invece di 3M" in f[4]["dettaglio"], "dettagli: contratto, da chi, asta, DPE")
fr = C.eventi_fanta(r)
ok(fr and fr[0]["etichetta"] == "Draft" and "Draft 2026, 1° giro #4" in fr[0]["dettaglio"], "rookie coi soli diritti: parte dal draft")
# rookie del draft 2026 già sotto contratto all'avvio: parte dal draft anche lui (Luca, 23/10)
rc = g("Rook Firmato")
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft) VALUES (%s, 'team03', 1, 9, '2026')", (rc,))
tx("signed", rc, None, "team03", c(rc, "team03", 4, 4, tipo="rookie"), "2026-07-25 22:00+02", "migrazione iniziale")
fc = C.eventi_fanta(rc)
ok(fc and fc[0]["etichetta"] == "Draft" and "Draft 2026, 1° giro #9" in fc[0]["dettaglio"] and "4M × 4 · rookie" in fc[0]["dettaglio"],
   f"rookie del draft 2026 con contratto all'avvio: parte dal draft col contratto {fc[:1]}")
ro = g("Rook Vecchio")
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft) VALUES (%s, 'team03', 1, 2, '2024')", (ro,))
tx("signed", ro, None, "team03", c(ro, "team03", 8, 4, tipo="rookie"), "2026-07-25 22:00+02", "migrazione iniziale")
ok(C.eventi_fanta(ro)[0]["etichetta"] == "All'avvio", "rookie di un draft precedente: All'avvio (il draft è prima del bot)")
n = C.eventi_nba("e1", "Gio Prova")
ok([(x["etichetta"], x["a"]) for x in n] == [("Al 25/07", "CHA"), ("Cambio squadra", "SAC")] and "Charlotte" in n[1]["dettaglio"],
   f"NBA: Charlotte al 25/07 (sigla di bref CHO → CHA), poi Sacramento una volta sola (ESPN; bref due giorni dopo non si ripete) {[(x['etichetta'], x['a']) for x in n]}")
nb = C.eventi_nba(None, "Gio Prova")
ok([x["a"] for x in nb] == ["CHA", "SAC"] and "Basketball-Reference" in nb[1]["dettaglio"], "senza ESPN: il cambio dalle righe di Basketball-Reference")

d = C.dati(p)
rr = d["righe"]
ok(rr[0]["giorno"] == "25/07" and rr[0]["fanta"] and rr[0]["nba"] and rr[0]["fanta_sq"]["nome"] == nomi["team01"] and rr[0]["nba_sq"]["sigla"] == "CHA",
   "prima riga: il 25/07 da tutte e due le parti")
taglio = next(x for x in rr if x["fanta"] and x["fanta"]["etichetta"] == "Taglio")
ok(taglio["fanta_sq"] is None and taglio["nba_resta"] == "Charlotte Hornets", "da free agent niente barra; dall'altra parte la squadra del momento")
ok(rr[-1]["nba"] and rr[-1]["nba"]["titolo"] == "Sacramento Kings" and rr[-1]["fanta_resta"] == nomi["team04"], "ultima riga: la trade NBA, nel fanta la squadra di adesso")
ok(d["ora"]["fanta"] == nomi["team04"] and d["ora"]["contratto"] == "3M × 1" and d["ora"]["nba"] == "Sacramento Kings"
   and "3 squadre" in d["breve"]["fanta"] and "1 trade" in d["breve"]["fanta"] and "2 squadre · 1 cambio" == d["breve"]["nba"],
   f"testata e riassunto {d['ora']} {d['breve']}")
try:
    import typst
    png = typst.compile(os.path.join(ROOT, "fantabasket-main", "carriera.typ"), root="/", format="png", ppi=72,
                        sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})
    ok(png[:4] == b"\x89PNG", "carriera.typ compila (senza foto: le iniziali; loghi segnaposto)")
    vuoto = C.dati(g("Senza Niente"))
    png = typst.compile(os.path.join(ROOT, "fantabasket-main", "carriera.typ"), root="/", format="png", ppi=72,
                        sys_inputs={"dati": json.dumps(vuoto, ensure_ascii=False, default=str)})
    ok(png[:4] == b"\x89PNG" and vuoto["breve"]["fanta"].startswith("nessun movimento"), "giocatore senza movimenti: compila lo stesso")
except ImportError:
    pass

# v6.13.0: /roster con squadra NBA, età e foto (Luca, 31/10), alla data del roster come la carriera
ok(C.squadra_nba_al("e1", "Gio Prova", datetime(2026, 12, 1, tzinfo=timezone.utc)) == "CHA"
   and C.squadra_nba_al("e1", "Gio Prova", datetime(2027, 3, 1, tzinfo=timezone.utc)) == "SAC"
   and C.squadra_nba_al("e1", "Gio Prova", datetime(2026, 5, 1, tzinfo=timezone.utc)) == "CHA"
   and C.squadra_nba_al(None, None, datetime(2027, 3, 1, tzinfo=timezone.utc)) is None,
   "squadra NBA a una data: prima e dopo la trade, prima del bot quella del 25/07, sconosciuta → niente")
import handlers.roster as RO
db._q("UPDATE giocatori SET data_nascita = '2000-12-15' WHERE id = %s", (p,))
_r = [{"giocatore_id": p, "nome_common": "Gio Prova", "importo": 15, "importo_originale": 20, "ha_dpe": True,
       "anni_originali": 2, "stagione_firma": "2026", "tipo_contratto": "normale", "occupa_slot": True},
      {"giocatore_id": r, "nome_common": "Rook Prova", "importo": 3, "anni_originali": 2, "stagione_firma": "2026",
       "tipo_contratto": "normale", "occupa_slot": True}]
_x = RO._nba_ed_eta(_r, datetime(2027, 3, 1, tzinfo=timezone.utc))
ok(_x[p]["sigla"] == "SAC" and _x[p]["colore"] and _x[p]["eta"] == 26 and _x[r]["sigla"] == "" and _x[r]["eta"] == "",
   f"roster a una data: squadra NBA e età a quel giorno, niente per chi non si conosce ({_x[p]})")
# % G (Luca, 01/11): partite giocate da quando è nella squadra di adesso
db._q("DELETE FROM nba_tabellini WHERE partita LIKE 'pg%%'"); db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'pg%%'")
def _pt(i, giorno, casa, tr, gioca, stato="STATUS_FINAL"):
    db._q("""INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato)
             VALUES (%s, '2026', 2, %s, %s, %s, %s, %s)""", (f"pg{i}", giorno, f"{giorno} 19:00-05", casa, tr, stato))
    if gioca is not None:
        db._q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti) VALUES (%s, 'e1', 'Gio Prova', %s, %s, %s)",
              (f"pg{i}", "CHA" if "CHA" in (casa, tr) else "SAC", gioca, 30 if gioca else 0))
for i, (gg, gioca) in enumerate([("2026-11-01", True), ("2026-11-03", True), ("2026-11-05", False), ("2026-11-07", True), ("2026-11-09", True)]):
    _pt(i, gg, "CHA", "BOS", gioca)
_pt(9, "2026-11-11", "CHA", "BOS", None, "STATUS_SCHEDULED")
_pt(10, "2027-02-01", "SAC", "LAL", None)
_pt(11, "2027-02-06", "SAC", "LAL", True)
_pt(12, "2027-02-08", "DEN", "SAC", False)
_d1 = datetime(2026, 12, 1, tzinfo=timezone.utc)
ok(RO.percentuale_giocate("e1", "CHA", C.squadra_nba_dal("e1", "Gio Prova", _d1)[1], _d1) == 80,
   "% G: 4 partite su 5 finite della sua squadra (quella non ancora giocata non conta)")
_d2 = datetime(2027, 3, 1, tzinfo=timezone.utc)
_s2, _dal2 = C.squadra_nba_dal("e1", "Gio Prova", _d2)
ok(_s2 == "SAC" and RO.percentuale_giocate("e1", "SAC", _dal2, _d2) == 50,
   "% G dopo la trade: solo le partite della squadra nuova da quando c'è (1 su 2, non quella di prima che arrivasse)")
ok(RO.percentuale_giocate(None, "SAC", _dal2, _d2) is None and RO.percentuale_giocate("e1", None, None, _d2) is None
   and RO.percentuale_giocate("e1", "UTA", None, _d2) is None, "% G: senza id ESPN, senza squadra o senza partite → —")
ok(RO._nba_ed_eta(_r, _d2)[p]["pg"] == 50, "% G nella riga del roster")
db._q("DELETE FROM nba_tabellini WHERE partita LIKE 'pg%%'"); db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'pg%%'")
ok(RO._eta(date(2000, 12, 15), date(2026, 12, 14)) == 25 and RO._eta(date(2000, 12, 15), date(2026, 12, 15)) == 26,
   "età a una data: compiuti il giorno del compleanno")
_gs = RO._build_giocatori_str(_r, [], nba=_x)
_campi = _gs.split(";")[0].split("|")
ok(len(_campi) == 16 and _campi[10] == "SAC" and _campi[13] == "26" and "|" not in RO._build_giocatori_str(_r, []).split(";")[0].split("|", 10)[-1],
   "stringa del roster: 6 campi in più solo con le squadre NBA (assets resta com'è)")
try:
    import typst
    _lungo = [{**_r[1], "giocatore_id": 999, "nome_common": "Christian Koloko-Tshiebwe Jr. Antetokounmpo Secondo"}]
    _ins = {"team_nome": "Alfa", "team_gm": "GM", "colore_header": "#F58426", "colore_riga1": "", "colore_riga2": "",
            "colore_sezione": "", "text_on_riga1": "#1a1a1a", "text_on_riga2": "#1a1a1a", "text_on_sezione": "#1a1a1a",
            "text_on_sezione_muted": "#555555", "text_on_footer": "#1a1a1a", "text_on_footer_muted": "#444444",
            "salary_cap": "18", "salary_detail": "18", "eta_media": "26.0", "tagli_usati": "0/3", "cambi_usati": "0/2",
            "logo_path": "", "giocatori": RO._build_giocatori_str(_r + _lungo, [], ruoli={p: "PG", r: "C", 999: "SF"},
                                                                  posizioni={999: "SG,SF,PF"}, nba={**_x, 999: {"sigla": "NYK", "colore": "#006BB6", "eta": 22}})}
    _png = typst.compile(os.path.join(ROOT, "fantabasket-main", "roster.typ"), root="/", format="png", ppi=72, sys_inputs=_ins,
                         font_paths=["/usr/share/fonts/truetype/liberation"], ignore_system_fonts=True)
    ok(_png[:4] == b"\x89PNG", "roster.typ compila con faccia, logo NBA, età e contratto in una bolla; nome lunghissimo compreso")
except ImportError:
    pass

# /assets a una data (v6.21.0): diritti col nome, niente STEPIEN nel passato
ok(RO._diritti_con_nome([{"giocatore_id": r, "pick_numero": 4, "anno_draft": "2026"}])[0]["nome_common"] == "Rook Prova",
   "/assets a una data: i diritti di get_diritti_at col nome")
ok(RO._data_non_valida(datetime(2099, 1, 1, tzinfo=timezone.utc)).startswith("❌") and RO._data_non_valida(None) is None,
   "data nel futuro rifiutata")
# /pdf_roster (v6.20.0): PDF vettoriale per squadra con foto e loghi in miniatura, pagine unite (Typst vero sostituito da typst-py)
try:
    import typst as _typ, tempfile as _tf
    from pypdf import PdfReader
    from PIL import Image as _Im
    _fatte = []
    async def _finto_pdf(team, stagione, as_of=None, formato="png", ppi=288):
        _fatte.append((team["id"], formato))
        f = _tf.NamedTemporaryFile(suffix=".pdf", delete=False); f.close()
        open(f.name, "wb").write(_typ.compile(bytes(f"= {team['id']}", "utf-8"), format="pdf"))
        return f.name
    _v1 = RO._genera_roster_png
    RO._genera_roster_png = _finto_pdf
    _pdfs, _n = asyncio.run(RO.genera_pdf_roster())
    ok(len(_pdfs) == 1 and _n >= 1 and len(PdfReader(_pdfs[0]).pages) == _n == len(_fatte) and all(x[1] == "pdf" for x in _fatte),
       f"/pdf_roster: un PDF, una pagina per squadra con giocatori ({_n})")
    for _x in _pdfs: os.unlink(_x)
    _lim = RO.LIMITE_PDF
    RO.LIMITE_PDF = 1                      # troppo grande: si divide, fino a una squadra per file
    _pdfs, _n = asyncio.run(RO.genera_pdf_roster())
    RO.LIMITE_PDF = _lim
    ok(len(_pdfs) == _n and all(len(PdfReader(x).pages) == 1 for x in _pdfs), f"/pdf_roster: oltre il limite di Telegram si divide in più file ({len(_pdfs)})")
    for _x in _pdfs: os.unlink(_x)
    RO._genera_roster_png = _v1
    # /pdf_assets (v6.21.0): stesso PDF con le pagine di /assets
    _fatte.clear()
    _va = RO._genera_assets_png
    RO._genera_assets_png = _finto_pdf
    _pdfs, _n = asyncio.run(RO.genera_pdf_roster(None, "assets"))
    RO._genera_assets_png = _va
    ok(len(_pdfs) == 1 and len(PdfReader(_pdfs[0]).pages) == _n == len(_fatte) >= 1, f"/pdf_assets: una pagina di asset per squadra ({_n})")
    for _x in _pdfs: os.unlink(_x)
    _f = _tf.NamedTemporaryFile(suffix=".png", delete=False); _f.close()
    _Im.new("RGBA", (520, 380), (200, 50, 50, 255)).save(_f.name)
    _m = RO.miniatura(_f.name, 120, jpeg=True)
    ok(_m != _f.name and _m.endswith(".jpg") and max(_Im.open(_m).size) == 120 and RO.miniatura(_f.name, 120, jpeg=True) == _m,
       "miniatura: foto a 120 pixel in JPEG, in cache")
    ok(RO.miniatura("/nonesiste.png", 64) == "/nonesiste.png", "miniatura di un file che non c'è: il percorso com'era")
    os.unlink(_f.name)
except ImportError:
    pass

# comando
out = []
class M:
    async def reply_text(s, t, **k): out.append((t, k))
    async def reply_photo(s, **k): out.append(("FOTO", k))
async def finto(gid): return "/nonesiste.png"
C.genera_png = finto
up = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=101), effective_message=M())
asyncio.run(C.cmd_carriera(up, types.SimpleNamespace(args=[])))
ok("Uso" in out[-1][0], "/carriera senza nome: istruzioni")
asyncio.run(C.cmd_carriera(up, types.SimpleNamespace(args=["prova"])))
k = out[-1][1].get("reply_markup")
ok(k and {b.callback_data for r_ in k.inline_keyboard for b in r_} >= {f"car:{p}", f"car:{r}"}, "nome non esatto: bottoni coi giocatori simili")
