import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types, os, sys
import database as db, settings
db.init_db(); db.migrate_db()
sent=[]
class Bot:
    async def send_message(self, **k): sent.append((k.get("chat_id"), k.get("text","").replace("\n"," | ")))
class Msg:
    def __init__(s): s.text_html="msg"; s.reply_markup=None
    async def reply_text(s,t,**k): sent.append(("reply", t))
class Q:
    def __init__(s,data,uid): s.data=data; s.from_user=types.SimpleNamespace(id=uid,first_name=f"U{uid}",username=None); s.message=Msg(); s.ans=None; s.t=None; s.kb=None
    async def answer(s,*a,**k):
        if s.ans is not None: raise RuntimeError("doppio answer")
        s.ans=(a,k)
    async def edit_message_text(s,t=None,**k): s.t=t; s.kb=k.get("reply_markup")
    async def edit_message_reply_markup(s,**k): s.kb=k.get("reply_markup")
ud={}
async def go(cb, data, uid):
    q=Q(data,uid); upd=types.SimpleNamespace(callback_query=q, effective_user=q.from_user, effective_message=q.message)
    r=await cb(upd, types.SimpleNamespace(bot=Bot(), user_data=ud, args=[])); q.ret=r; return q
def kbt(q): return [b.callback_data for r in (q.kb.inline_keyboard if q.kb else []) for b in r]

# seed
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni RESTART IDENTITY CASCADE")
G={}
for t in ["team01","team02","team03","team04"]:
    for k in range(10):
        n=f"{t}_p{k}"
        gid=db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n))
        db._q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,10,2,'2026','normale')",(gid,t))
        G[n]=gid
    for anno in range(2027,2033):
        for rnd in (1,2):
            db._q("INSERT INTO pick (proprietario_orig,proprietario_att,anno,round) VALUES (%s,%s,%s,%s)",(t,t,str(anno),rnd))
rk=db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('rook','Rook','rook') RETURNING id")
db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team03',2,40,'2026')",(rk,))
rk2=db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('rook2','Rook2','rook2') RETURNING id")
db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team03',2,41,'2026')",(rk2,))
def pick(t,anno,rnd): return db._qval("SELECT id FROM pick WHERE proprietario_orig=%s AND anno=%s AND round=%s",(t,str(anno),rnd))

import handlers.trade as T
from validators.trade import valida_trade
async def main():
    ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
    # builder 3 team by GM 101
    q=await go(T.cb_n_squadre,"trade_n:3",101); tid=ud["trade_id"]
    q=await go(T.cb_seleziona_squadra,"trade_sq:team02",101)
    q=await go(T.cb_seleziona_squadra,"trade_sq:team02",101); ok(q.ret==T.TRADE_SELEZIONA_SQUADRE and ud["trade_squadre_ordine"]==["team01","team02"],"doppio tap squadra ignorato")
    q=await go(T.cb_seleziona_squadra,"trade_sq:team03",101); ok(q.ret==T.TRADE_ASSET_MENU,"3 squadre → asset")
    await go(T.cb_toggle_giocatore,f"trade_gi:{tid}:team01:{G['team01_p0']}",101)
    await go(T.cb_squadra_confermata.__wrapped__ if hasattr(T.cb_squadra_confermata,'__wrapped__') else T.cb_asset_menu, f"trade_am:ok:{tid}:team01",101)
    await go(T.cb_toggle_pick,f"trade_pi:{tid}:team02:{pick('team02',2028,2)}",101)
    await go(T.cb_asset_menu,f"trade_am:ok:{tid}:team02",101)
    rid=db._qval("SELECT id FROM rookie WHERE giocatore_id=%s",(rk,)); rid2=db._qval("SELECT id FROM rookie WHERE giocatore_id=%s",(rk2,))
    q=await go(T.cb_toggle_diritti,f"trade_di:{tid}:team03:{rid}",101); ok(q.ret==T.TRADE_ASSET_DIRITTI,"diritti: resta nello stato diritti")
    q=await go(T.cb_toggle_diritti,f"trade_di:{tid}:team03:{rid2}",101); ok(len([i for i in db.get_items_trade(tid) if i['tipo']=='diritti'])==2,"secondo diritto aggiunto")
    q=await go(T.cb_toggle_diritti,f"trade_di:{tid}:team03:{rid2}",101)
    q=await go(T.cb_asset_menu,f"trade_am:ok:{tid}:team03",101); ok(q.ret==T.TRADE_ASSEGNA_DEST,"chiede destinatari")
    # assign: items order team01 player, team02 pick, team03 diritti
    for _ in range(3):
        it=ud["trade_item_da_assegnare"]; i=db.get_item_trade(it)
        dest={"team01":"team02","team02":"team03","team03":"team01"}[i["team_id_da"]]
        q=await go(T.cb_assegna_dest,f"trade_dest:{it}:{i['team_id_da']}",101) # invalid self
        ok(q.ret==T.TRADE_ASSEGNA_DEST and db.get_item_trade(it)["team_id_a"]=="?","dest = se stessa rifiutato")
        q=await go(T.cb_assegna_dest,f"trade_dest:{it}:{dest}",101)
    ok(q.ret==T.TRADE_RIEPILOGO and "Validazione OK" in q.t, "riepilogo 3 squadre valido")
    # editor: add asset → '?' → done chiede destinatario
    q=await go(T.cb_edit_back,f"edit_back:{tid}",101)
    q=await go(T.cb_edit_tipo,f"edit_tipo:g:{tid}:team02",101)
    gadd=G['team02_p1']; ok(any(f":?:{gadd}" in c for c in kbt(q)),"editor 3 squadre: destinatario '?'")
    q=await go(T.cb_edit_item,f"edit_item:g:{tid}:team02:?:{gadd}",101)
    ok(valida_trade(tid)[0] is False and any("manca la squadra" in e for e in valida_trade(tid)[1]),"validatore blocca '?'")
    q=await go(T.cb_edit_done,f"edit_done:{tid}",101); ok(q.ret==T.TRADE_ASSEGNA_DEST,"Fatto → assegna destinatario")
    it=ud["trade_item_da_assegnare"]; q=await go(T.cb_assegna_dest,f"trade_dest:{it}:team01",101)
    ok(q.ret==T.TRADE_RIEPILOGO and "Validazione OK" in q.t,"dopo assegnazione valida")
    # altro GM non può eliminare/modificare
    q=await go(T.cb_trade_del,f"trade_del:{tid}",102); ok(db.get_trade(tid) is not None,"altro GM non elimina la bozza")
    q=await go(T.cb_send_trade,f"trade_send:gm:{tid}",102); ok(db.get_trade(tid)["stato"]=="bozza","altro GM non invia la bozza")
    # proponi
    sent.clear()
    q=await go(T.cb_send_trade,f"trade_send:gm:{tid}",101); ok(db.get_trade(tid)["stato"]=="proposta","proposta ai GM")
    ok({c for c,_ in sent}=={102,103},"voto chiesto a Beta e Gamma")
    q=await go(T.cb_trade_del,f"trade_del:{tid}",101); ok(db.get_trade(tid) is not None,"vecchio 'Elimina' non cancella trade in voto")
    q=await go(T.cb_edit_rm,f"edit_rm:{tid}:{it}",101); ok(db.get_item_trade(it) is not None,"vecchio 'modifica' non tocca trade in voto")
    q=await go(T.cb_voto_gm,f"trade_voto:si:{tid}:team04",104); ok("non deve votare" in (q.t or ""),"squadra estranea non vota")
    sent.clear(); q=await go(T.cb_voto_gm,f"trade_voto:si:{tid}:team02",102)
    ok(any(c==101 and "Beta</b> ha accettato" in t for c,t in sent),"proponente avvisato del voto di Beta")
    sent.clear()
    import handlers.trade as TT
    q=await go(T.cb_rifiuta_conf,f"trade_rifiuta_conf:{tid}:team03:no",103)
    ok(db.get_trade(tid)["stato"]=="rifiutata_gm" and {c for c,_ in sent}>={101,102} and 103 not in {c for c,_ in sent},"rifiuto Gamma avvisato a Alfa e Beta")
    # clone and admin path
    q=await go(T.cb_my_trades,f"mt:c:{tid}",101); nuovo=db._qval("SELECT max(id) FROM trade")
    q=await go(T.cb_send_trade,f"trade_send:admin:{nuovo}",101); ok(db.get_trade(nuovo)["stato"]=="in_approvazione","clone mandato agli admin")
    sent.clear(); q=await go(T.cb_admin_trade,f"trade_admin:ok:{nuovo}",900)
    ok(db.get_trade(nuovo)["stato"]=="approvata","approvata ed eseguita")
    ok(db.get_contratto_attivo(G['team01_p0'])["team_id"]=="team02" and db.get_contratto_attivo(gadd)["team_id"]=="team01","giocatori spostati")
    ok(db.get_pick(pick('team02',2028,2))["proprietario_att"]=="team03","pick spostata")
    ok(db._qval("SELECT team_id FROM rookie WHERE giocatore_id=%s",(rk,))=="team01","diritti spostati")
    ok({c for c,_ in sent}>={101,102,103,-1},"tutti avvisati + canale")
    ref=db.get_trade(nuovo)["trade_ref"]
    # annulla_trade_admin
    sent.clear(); msg=Msg(); upd=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900,first_name="Adm"),effective_message=msg,effective_chat=types.SimpleNamespace(type="private"),message=msg)
    await T.cmd_annulla_trade_admin(upd, types.SimpleNamespace(bot=Bot(),args=[ref],user_data={}))
    ok(db.get_trade(nuovo)["stato"]=="annullata" and db.get_contratto_attivo(G['team01_p0'])["team_id"]=="team01","rollback ok")
    ok({c for c,_ in sent if c!="reply"}>={101,102,103},"annullamento avvisato a tutte le squadre (niente crash)")
    # scrivi_trade with '?' in old bozza
    t2=db.crea_trade_bozza("team01",3,"2026")
    for o,t in enumerate(["team01","team02","team03"],1): db.aggiungi_squadra_trade(t2,t,o)
    db.aggiungi_item_trade(t2,"giocatore","team01","?",giocatore_id=G['team01_p5'])
    db._q("UPDATE trade SET stato='in_approvazione', validazione_ok=TRUE WHERE id=%s",(t2,))
    q=await go(T.cb_admin_trade,f"trade_admin:ok:{t2}",900)
    ok(db.get_trade(t2)["stato"]=="in_approvazione" and db.get_contratto_attivo(G['team01_p5'])["team_id"]=="team01","'?' bloccato in esecuzione")
    v=valida_trade(t2)[1]; ok(any("non cede e non riceve" in e for e in v),"squadra senza asset segnalata")
    # parser
    from handlers.trade_parser import parsa_trade
    import teams as tm
    txt="TRADE\n\nAlfa cede:\nteam01_p7 10x2\n\nBeta cede:\nteam02_p7 10x2\n\nGamma cede:\nteam03_p7 10x2\n\nAlfa riceve:\nteam02_p7 10x2\n\nBeta riceve:\nteam03_p7 10x2\n"
    sq,err=parsa_trade(txt,"2026",tm.get_all_teams()); ok(any("nessuna squadra lo riceve" in e for e in err),"parser: ceduto senza riceve")
    txt2=txt+"Gamma riceve:\nteam01_p7 10x2\nteam04_p1 10x2\n"
    sq,err=parsa_trade(txt2,"2026",tm.get_all_teams()); ok(any("nessuna squadra lo cede" in e for e in err) and not any("nessuna squadra lo riceve" in e for e in err),"parser: ricevuto senza cede")
    txt3=txt+"Gamma riceve:\nteam01_p7 10x2\n"
    sq,err=parsa_trade(txt3,"2026",tm.get_all_teams()); ok(not err,f"parser: 3 squadre corretta {err}")
asyncio.run(main())
