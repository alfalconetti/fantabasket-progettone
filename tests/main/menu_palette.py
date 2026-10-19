import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v6.1.0 (Luca, 19/10): menu a bottoni sempre con ← o ✖️ Chiudi; /palette che funziona davvero e testo
sempre leggibile; /my_team senza i colori finti; /team_diff nei gruppi. La DPE su un 1x1 resta una DPE (v6.1.2)."""
import asyncio, json, os, types
import database as db, settings, teams as tm
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
P = os.environ["GLOBALS_PATH"]
def fase(f):
    g = json.load(open(P)); g["fase"] = f; json.dump(g, open(P, "w"))
fase("regular-season-fa")
GM = 101                                   # GM di team01 (Alfa)
cb = lambda k: [b.callback_data for r in k.inline_keyboard for b in r] if k else []
mandati = []
class Bot:
    async def send_message(self, **k): mandati.append(k)
class Msg:
    def __init__(s): s.risposte, s.text, s.photo, s.cancellato = [], "x", None, False
    async def reply_text(s, t, **k): s.risposte.append((t, k)); return s
    async def reply_photo(s, **k): s.risposte.append(("FOTO", k)); return s
    async def delete(s): s.cancellato = True
class Q:
    def __init__(s, data, uid=GM):
        s.data, s.from_user, s.message, s.testi, s.risposte = data, types.SimpleNamespace(id=uid, first_name="U", username=None, full_name="U"), Msg(), [], []
    async def answer(s, *a, **k): s.risposte.append(a[0] if a else None)
    async def edit_message_text(s, t, **k): s.testi.append((t, k))
    async def edit_message_reply_markup(s, **k): s.testi.append(("MARKUP", k))
def premi(f, data, uid=GM, ud=None):
    q = Q(data, uid)
    u = types.SimpleNamespace(callback_query=q, effective_user=q.from_user, effective_message=q.message,
                              effective_chat=types.SimpleNamespace(id=uid, type="private"))
    ctx = types.SimpleNamespace(bot=Bot(), user_data=ud if ud is not None else {}, args=[], application=None)
    r = asyncio.run(f(u, ctx)); q.ret = r; return q
def comando(f, uid=GM, args=(), ud=None, testo="x"):
    m = Msg(); m.text = testo
    u = types.SimpleNamespace(callback_query=None, effective_user=types.SimpleNamespace(id=uid, first_name="U", username=None, full_name="U"),
                              effective_message=m, effective_chat=types.SimpleNamespace(id=uid, type="private"))
    ctx = types.SimpleNamespace(bot=Bot(), user_data=ud if ud is not None else {}, args=list(args), application=None)
    r = asyncio.run(f(u, ctx)); m.ret = r; return m

# ── navigazione ──
from handlers import menu as ME, nav, trade_liste as TL, trade_comune as TC, admin_panel as AP
ok("nav:x" in cb(ME._kb_menu_principale("regular-season-fa", "team01")), "/menu: ✖️ Chiudi")
ok("nav:x" in cb(AP._kb_admin_home()), "/admin_menu: ✖️ Chiudi")
q = premi(nav.cb_chiudi, "nav:x")
ok(q.message.cancellato, "✖️ Chiudi: il messaggio sparisce")
q = premi(ME.cb_menu, "menu:trade_bozze")
ok(q.testi and "menu:trade" in cb(q.testi[-1][1]["reply_markup"]) and not q.message.risposte,
   "📝 Bozze dal menu: al posto del menu (non sotto), con ← Trade")
q = premi(TL.cb_my_trades, "mt:l")
ok("menu:trade" in cb(q.testi[-1][1]["reply_markup"]) and "nav:x" in cb(q.testi[-1][1]["reply_markup"]),
   "📂 Le mie trade: ← Trade e ✖️ Chiudi (prima non si tornava indietro)")
ok({"trade_x:menu", "trade_x"} <= set(cb(TC._kb_n_squadre())), "nuova trade: ← Trade e ✖️ Annulla")
ok("trade_x" in cb(TC._kb_asset_menu(1, "team01")) and "trade_x" in cb(TC._kb_squadre([])), "builder: ✖️ Annulla in ogni schermata")
tid = db.crea_trade_bozza("team01", 2, "2026")
ud = {"trade_id": tid, "trade_squadre_ordine": ["team01"]}
q = premi(TC.cb_annulla_trade, "trade_x", ud=ud)
ok(db.get_trade(tid)["stato"] == "annullata" and "trade_id" not in ud and q.ret == -1 and "annullata" in q.testi[-1][0],
   "✖️ Annulla: la bozza a metà si annulla e la conversazione finisce")
for f, data in ((ME.cb_menu, "menu:tagli"), (ME.cb_menu, "menu:rookie"), (ME.cb_menu, "menu:dpe")):
    q = premi(f, data)
    ok(q.testi and "menu:home" in cb(q.testi[-1][1].get("reply_markup")), f"{data}: al posto del menu, con 🏠 Menu")
from handlers import stagione as ST
fase("offseason-rinnovi")
t, k = ST._testo_rinnovi(tm.get_team_by_id("team01"), None)
ok({"menu:home", "nav:x"} <= set(cb(k)), "rinnovi rookie (GM): 🏠 Menu e ✖️ Chiudi anche senza rookie")
t, k = ST._testo_rfa(tm.get_team_by_id("team01"), "team01")
ok({"sga:scegli:rfa", "adm:home"} <= set(cb(k)), "RFA (admin): ← Squadre e ← Menu admin")
fase("regular-season-fa")
from handlers import impostazioni as IM
ok({"adm:home", "nav:x"} <= set(cb(IM.home()[1])), "/settings: ← Menu admin e ✖️ Chiudi")

# ── /team_diff nei gruppi ──
from comandi import liste_comandi
ok("team_diff" in [c.command for c in liste_comandi("regular-season-fa")["group"]], "/team_diff nel menu comandi dei gruppi")

# ── /my_team ──
from handlers import myteam as MT
m = comando(MT.cmd_my_team)
k = m.risposte[-1][1]["reply_markup"]
ok(cb(k) == ["myt:nome", "myt:gm_nome", "myt:x"] and "/palette" in m.risposte[-1][0],
   "/my_team: nome squadra, nome GM, Chiudi; i colori rimandano a /palette (quelli di qui non facevano niente)")
ud = {}
q = premi(MT.cb_scegli_campo, "myt:nome", ud=ud)
ok(q.ret == MT.INSERISCI_VALORE and "myt:home" in cb(q.testi[-1][1]["reply_markup"]), "/my_team: mentre scrivi c'è ← Indietro")
m = comando(MT.ricevi_valore, ud=ud, testo="Alfa Nuova")
ok(tm.get_team_by_id("team01")["nome"] == "Alfa Nuova", "/my_team: nome cambiato sulla squadra di chi scrive")
tm.set_campo_team("team01", "nome", "Alfa")

# ── /palette ──
from handlers import palette as PA, roster as RO
ok(PA.normalizza_hex("1a237e") == "#1A237E" and PA.normalizza_hex("#abc") == "#AABBCC" and PA.normalizza_hex("blu") is None,
   "palette: hex anche senza # e in tre cifre")
ok(RO.input_colori({"colore_header": "#FFEB3B"})[RO.input_colori({"colore_header": "#FFEB3B"}).index("--input") + 1] and
   "text_on_header=#1a1a1a" in RO.input_colori({"colore_header": "#FFEB3B"})
   and "text_on_header=#f0f0f0" in RO.input_colori({"colore_header": "#1A237E"}),
   "intestazione chiara → testo scuro, scura → testo chiaro (prima sempre bianco)")
ok("text_on_riga1=#f0f0f0" in RO.input_colori({"colore_riga1": "#101820"}) and
   "text_on_dark=#f0f0f0" in RO.input_colori({}), "righe scure → testo chiaro")
eff = RO.colori_effettivi({"colore_header": "#000000"})
ok(eff["riga1"] == "#bfbfbf" and eff["riga2"] == "#ffffff" and eff["dark"] == "#000000", f"colori automatici come Typst {eff}")
ok(PA._valore({}, "colore_riga1").startswith("automatico (#") and PA._valore({"colore_riga1": "#123456"}, "colore_riga1") == "#123456",
   "il menu mostra il colore vero: scelto o automatico (prima default finti)")
generati = []
async def finto_png(team, stagione):
    generati.append(dict(team)); open("/tmp/_pal.png", "wb").write(b"x"); return "/tmp/_pal.png"
RO._genera_roster_png = finto_png; RO._genera_assets_png = finto_png
ud = {}
m = comando(PA.cmd_palette, ud=ud)
ok(m.ret == PA.PAL_MENU and "pal_annulla" in cb(m.risposte[-1][1]["reply_markup"]), "/palette: menu con ✖️ Chiudi senza salvare")
q = premi(PA.cb_pal_campo, "pal_campo:colore_pick", ud=ud)
ok(q.ret == PA.PAL_ATTENDI_HEX and {"pal_auto:colore_pick", "pal_back"} <= set(cb(q.testi[-1][1]["reply_markup"])),
   "scelta del colore: ♻️ Automatico e ← Indietro")
m = comando(PA.msg_pal_hex, ud=ud, testo="ffeb3b")
ok(m.ret == PA.PAL_ANTEPRIMA and generati[-1]["colore_pick"] == "#FFEB3B" and m.risposte[-1][0] == "FOTO",
   "anteprima col colore nuovo (per le pick: assets)")
q = premi(PA.cb_pal_ok, "pal_ok:colore_pick", ud=ud)
ok(ud["pal_pendenti"] == {"colore_pick": "#FFEB3B"} and q.ret == PA.PAL_MENU, "✅ Usa questo: da salvare")
tm.set_campo_team("team01", "colore_riga2", "#EEEEEE")
q = premi(PA.cb_pal_auto, "pal_auto:colore_riga2", ud=ud)
q = premi(PA.cb_pal_salva, "pal_salva", ud=ud)
t1 = tm.get_team_by_id("team01")
ok(t1.get("colore_pick") == "#FFEB3B" and "colore_riga2" not in t1 and q.ret == -1, "💾 Salva: colore scritto, «automatico» toglie il campo")
ok(db._qval("SELECT count(*) FROM registro_azioni WHERE azione = 'palette della squadra'") >= 1, "palette nel registro")
tm.set_campo_team("team01", "colore_pick", "")

# ── DPE su un 1x1: resta una DPE normale (v6.1.2: non è un decadimento, a fine stagione l'x0 può andare RFA) ──
from handlers import dpe as DP
def gioc(n, imp, anni):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES "
                 "(%s,'team01',%s,%s,'2026','normale') RETURNING id", (gid, imp, anni))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,'team01','2026',%s)", (gid, c))
    return gid
uno = gioc("Unoxuno", 1, 1)
err, esito = asyncio.run(DP.applica_dpe(Bot(), uno, "team01", "Adm", da_admin=True))
d = db.get_dpe_attiva(uno, "2026")
ok(not err and db.get_contratto_attivo(uno) and d and d["importo_dpe"] == 0
   and db._qval("SELECT count(*) FROM transazioni WHERE giocatore_id=%s AND tipo='decadimento'", (uno,)) == 0,
   "DPE su un 1x1: DPE normale (0M, contratto ancora attivo), niente decadimento")
ok(not hasattr(db, "_migra_dpe_1x1") and not hasattr(DP, "dpe_come_decadimento"), "niente conversione DPE 1x1 → decadimento")
_ = settings
