import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Registro unico (v3.10.0): pick e diritti in transazioni, storico ricostruito, vista
movimenti_giocatori, roster_attuale dai contratti, controllo di coerenza."""
from datetime import datetime, timezone, timedelta
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
Z=timezone.utc; T0=datetime(2026,7,25,20,tzinfo=Z); G=lambda d,m=0: T0+timedelta(days=d,minutes=m)
def gioc(n,t,ts=T0,imp=5):
    gid=db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n.lower()))
    if t:
        c=db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,2,'2026','normale') RETURNING id",(gid,t,imp))
        db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp,note) VALUES ('signed',%s,%s,'2026',%s,%s,'migrazione iniziale')",(gid,t,c,ts))
    return gid
def pick(orig,att,anno="2028",r=1): return db._qval("INSERT INTO pick (proprietario_orig,proprietario_att,anno,round) VALUES (%s,%s,%s,%s) RETURNING id",(orig,att,anno,r))
def trade(ref,stato,quando,agg=None):
    t=db._qval("INSERT INTO trade (trade_ref,stagione,stato,n_squadre,proposta_da,approvata_at,aggiornato) VALUES (%s,'2026',%s,2,'team01',%s,%s) RETURNING id",(ref,stato,quando,agg or quando)); return t
def item(t,tipo,da,a,gid=None,pid=None): db._q("INSERT INTO trade_items (trade_id,tipo,giocatore_id,pick_id,team_id_da,team_id_a) VALUES (%s,%s,%s,%s,%s,%s)",(t,tipo,gid,pid,da,a))
def tx(gid,da,a,quando,t,nota=None): db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,team_id_a,stagione,trade_id,timestamp,note) VALUES ('traded',%s,%s,%s,'2026',%s,%s,%s)",(gid,da,a,t,quando,nota))

jokic=gioc("Jokic","team21")                      # id 1: quello a cui erano agganciati i tagli pre-bot
g1=gioc("Uno","team01"); g2=gioc("Due","team02"); gioc("Taglio","team05")
rk=gioc("Rookie Due",None); db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team01',2,40,'2026')",(rk,))
rk2=gioc("Da Attivare",None); db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team03',2,41,'2026')",(rk2,))
p1=pick("team01","team02"); p2=pick("team03","team03","2029"); p3=pick("team02","team03","2030"); p4=pick("team05","team06","2031")  # p4 passata di mano prima del bot
# taglio pre-bot "agganciato" a Jokic
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione,gratuito,note,timestamp) VALUES ('cut',%s,'team08','2026',TRUE,'Taglio gratuito registrato manualmente — avvenuto pre-bot',%s)",(jokic,G(60)))
# TA: approvata, P1 team01→team02
ta=trade("TRADE-2026-001","approvata",G(1)); item(ta,"pick","team01","team02",pid=p1)
# TB: sole pick, risulta annullata senza movimenti (eseguita e annullata): P2 resta a team03
tb=trade("TRADE-2026-002","annullata",G(2),G(2,5)); item(tb,"pick","team03","team04",pid=p2)
# TC: annullata con /annulla_trade_admin: Uno team01→team02 e ritorno, diritti Rookie Due team01→team02 e ritorno
tc=trade("TRADE-2026-003","annullata",G(3),G(3,10)); item(tc,"giocatore","team01","team02",gid=g1); item(tc,"diritti","team01","team02",gid=rk)
tx(g1,"team01","team02",G(3),tc); tx(g1,"team02","team01",G(3,10),tc,"ANNULLAMENTO TRADE-2026-003")
# TD: eseguita ma rimasta "annullata" (vecchio /annulla_trade_admin rotto): Due team02→team03, P3 team02→team03
td=trade("TRADE-2026-004","annullata",G(4)); item(td,"giocatore","team02","team03",gid=g2); item(td,"pick","team02","team03",pid=p3)
tx(g2,"team02","team03",G(4),td); db._q("UPDATE contratti SET team_id='team03' WHERE giocatore_id=%s",(g2,))
ok(len(db.get_roster_team_at("team21",G(61).isoformat()))==0, "prima: Jokic sparisce dal roster di team21 (taglio pre-bot agganciato a lui)")

db._migra_registro_unico()
ok(db._qval("SELECT oggetto FROM transazioni WHERE tipo='cut' AND team_id_da='team08'")=="squadra"
   and db.get_tagli_gratuiti_usati("team08","2026")==1, "taglio pre-bot: evento di squadra, conta ancora come taglio gratuito")
ok([r["giocatore_id"] for r in db.get_roster_team_at("team21",G(61).isoformat())]==[jokic], "dopo: Jokic di nuovo nel roster di team21")
ok(db._qval("SELECT stato FROM trade WHERE id=%s",(td,))=="approvata" and db._qval("SELECT stato FROM trade WHERE id=%s",(tc,))=="annullata",
   "trade eseguita ma segnata annullata → approvata; quella annullata davvero resta annullata")
ok(db.storico_pick_diritti_presente(), "storico di pick e diritti creato")
at=lambda team,d,m=0: {p["id"] for p in db.get_pick_at(team,G(d,m).isoformat())}
ok(p1 in at("team01",0,30) and p1 in at("team02",1,30) and p1 not in at("team01",1,30), "P1: team01 prima della trade, team02 dopo")
ok(p2 in at("team04",2,1) and p2 in at("team03",2,6) and p2 in at("team03",1), "P2 (trade di sole pick annullata): team04 tra esecuzione e annullamento, poi team03")
ok(p3 in at("team02",3) and p3 in at("team03",5), "P3 (trade rimessa approvata): team02 → team03")
ok(p4 in at("team06",0,30), "P4 passata di mano prima del bot: all'avvio del registro è di team06")
dat=lambda team,d,m=0: {r["giocatore_id"] for r in db.get_diritti_at(team,G(d,m).isoformat())}
ok(rk in dat("team02",3,5) and rk in dat("team01",3,15) and rk in dat("team01",2), "diritti: ceduti e tornati con l'annullamento")
ok(db.controlli_coerenza()==[], "controllo di coerenza pulito dopo la migrazione")
n=db._qval("SELECT count(*) FROM transazioni")
db._migra_registro_unico(); ok(db._qval("SELECT count(*) FROM transazioni")==n, "migrazione rilanciata: nessuna riga in più")

# da qui il registro si aggiorna da solo
import handlers.trade as T
import handlers.trade_esegui as TE   # v3.13.0: trade.py spezzato
te=db.crea_trade_bozza("team02",2,"2026"); db.aggiungi_squadra_trade(te,"team02",1); db.aggiungi_squadra_trade(te,"team01",2)
db.aggiungi_item_trade(te,"pick","team02","team01",pick_id=p1); db.aggiungi_item_trade(te,"diritti","team01","team02",giocatore_id=rk)
db._q("UPDATE trade SET stato='in_approvazione' WHERE id=%s",(te,))
TE._scrivi_trade(te,"TRADE-2026-005","adm")
ok(db._qval("SELECT count(*) FROM transazioni WHERE trade_id=%s AND oggetto IN ('pick','diritti')",(te,))==2, "trade nuova: movimento della pick e dei diritti nel registro")
ok(db.controlli_coerenza()==[], "coerenza dopo la trade")
from handlers import team_diff as TD
ora=datetime.now(Z)
ok(TD._motivo_asset("pick",p1,ora-timedelta(hours=1),ora+timedelta(minutes=1),"?")=="Trade", "team_diff: la pick entra 'Trade'")
TE._scrivi_trade(te,"TRADE-2026-005",None,inverti=True)
ok(p1 in {p["id"] for p in db.get_pick_at("team02",(datetime.now(Z)+timedelta(seconds=1)).isoformat())}, "annullamento: la pick torna a team02 anche nello storico")
ok(TD._motivo_asset("pick",p1,ora-timedelta(hours=1),datetime.now(Z)+timedelta(minutes=1),"?")=="Trade annullata", "team_diff: 'Trade annullata'")
# attivazione e scadenza
import handlers.rookie as R
rid=db._qval("SELECT id FROM rookie WHERE giocatore_id=%s",(rk2,))
prima=datetime.now(Z)
R.esegui_attivazione(rid,"team03",1,2)
ok(db._qval("SELECT tipo FROM transazioni WHERE oggetto='diritti' AND giocatore_id=%s ORDER BY timestamp DESC, id DESC LIMIT 1",(rk2,))=="rookie_firma"
   and rk2 in {r["giocatore_id"] for r in db.get_diritti_at("team03",prima.isoformat())}
   and not db.get_diritti_at("team03",(datetime.now(Z)+timedelta(seconds=1)).isoformat()), "attivazione: i diritti si chiudono nel registro (prima c'erano)")
db.scadi_diritti_anno(2026)
ok(db._qval("SELECT tipo FROM transazioni WHERE oggetto='diritti' AND giocatore_id=%s ORDER BY timestamp DESC, id DESC LIMIT 1",(rk,))=="rookie_diritti_scaduti", "scadenza: movimento 'rookie_diritti_scaduti'")
ok(db.controlli_coerenza()==[], "coerenza dopo attivazione e scadenza")
# roster_attuale = contratti attivi (chi è tagliato non c'è più)
tg=db._qval("SELECT id FROM giocatori WHERE nome_common='Taglio'")
db._q("UPDATE contratti SET attivo=FALSE WHERE giocatore_id=%s",(tg,))
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione) VALUES ('cut',%s,'team05','2026')",(tg,))
ok(not db._q("SELECT 1 FROM roster_attuale WHERE giocatore_id=%s",(tg,),one=True), "roster_attuale: il tagliato non c'è più (prima restava nella squadra)")
# il controllo trova le modifiche fatte a mano
db._q("UPDATE contratti SET team_id='team09' WHERE giocatore_id=%s",(g1,)); db._q("UPDATE pick SET proprietario_att='team09' WHERE id=%s",(p4,))
pr=db.controlli_coerenza()
ok(any("Uno" in p for p in pr) and any("2031" in p for p in pr), f"controllo: contratto e pick spostati a mano segnalati ({len(pr)})")
# ricostruzione forzata con dati incoerenti: niente viene toccato
n=db._qval("SELECT count(*) FROM transazioni")
try:
    db.crea_storico_pick_diritti(forza=True); ok(False,"ricostruzione con dati incoerenti doveva fermarsi")
except db.StoricoNonCoerente:
    ok(db._qval("SELECT count(*) FROM transazioni")==n, "dati incoerenti: ricostruzione fermata, registro intatto")
