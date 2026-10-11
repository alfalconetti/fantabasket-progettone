import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types, json, os
import database as db, settings
db.init_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
g=json.load(open(os.environ["GLOBALS_PATH"])); g["fase"]="regular-season-fa"; json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
def gioc(n,t,imp):
    gid=db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n.lower()))
    c=db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,2,'2026','normale') RETURNING id",(gid,t,imp))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,'2026',%s)",(gid,t,c)); return gid
klay=gioc("Klay","team01",20); altro=gioc("Altro","team02",5)
for i in range(12): gioc(f"a{i}","team01",1); gioc(f"b{i}","team02",1)
db._q("INSERT INTO dpe (giocatore_id,team_id,stagione,importo_originale,importo_dpe) VALUES (%s,'team01','2026',20,15)",(klay,))
t=db.crea_trade_bozza("team01",2,"2026"); db.aggiungi_squadra_trade(t,"team01",1); db.aggiungi_squadra_trade(t,"team02",2)
db.aggiungi_item_trade(t,"giocatore","team01","team02",giocatore_id=klay); db.aggiungi_item_trade(t,"giocatore","team02","team01",giocatore_id=altro)
from validators.trade import _cap_post_team
items=db.get_items_trade(t)
c1,p1=_cap_post_team("team01",items,"2026"); c2,p2=_cap_post_team("team02",items,"2026")
ok(p1==c1-15+5 and p2==c2-5+15, f"validazione: Klay pesa 15 (DPE) per entrambe ({c2}→{p2})")
import handlers.trade as T
db._q("UPDATE trade SET stato='in_approvazione' WHERE id=%s",(t,))
T._scrivi_trade(t,"TRADE-2026-001","adm")
ok(db._qval("SELECT team_id FROM dpe WHERE giocatore_id=%s",(klay,))=="team02", "dopo la trade la DPE è dei Lakers")
ok(db.cap_occupato_team("team02","2026")==p2, f"cap reale team02 = validato ({db.cap_occupato_team('team02','2026')})")
ok(any(r["ha_dpe"] for r in db.get_roster_team("team02") if r["giocatore_id"]==klay), "roster team02: Klay con DPE (slot libero)")
T._scrivi_trade(t,"TRADE-2026-001",None,inverti=True)
ok(db._qval("SELECT team_id FROM dpe WHERE giocatore_id=%s",(klay,))=="team01", "annullamento: la DPE torna a team01")
# taglio che rompe i ruoli in RS
import handlers.tagli as TG, validators.ruoli as VR
VR_orig=VR.deficit_team
VR.deficit_team=lambda team,st,togli=(),**k: 1 if togli else 0
team=__import__("teams").get_team_by_id("team01")
try:
    TG._valuta_taglio(team, db._qval("SELECT id FROM giocatori WHERE nome_common='a0'")); ok(False,"taglio con ruoli scoperti")
except TG.TaglioNonEseguibile as e:
    ok("minimi dei ruoli" in str(e), "RS: taglio che scopre i ruoli bloccato")
VR.deficit_team=lambda team,st,togli=(),**k: 0
v=TG._valuta_taglio(team, db._qval("SELECT id FROM giocatori WHERE nome_common='a0'"))
ok(v["rate"] or v["gratuito"], "RS: taglio che non scopre i ruoli consentito")
