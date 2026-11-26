import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types, json, os
import database as db, settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
def setfase(f):
    g=json.load(open(os.environ["GLOBALS_PATH"])); g["fase"]=f; json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
def g(n): return db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n.lower()))
def firma(gid,t,imp,anni):
    c=db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,%s,'2026','normale') RETURNING id",(gid,t,imp,anni))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,'2026',%s)",(gid,t,c))
G={}
for i in range(12): G[i]=g(f"p{i}"); firma(G[i],"team01",1 if i<5 else 4,1)
sent=[]
class Bot:
    async def send_message(self,**k): sent.append(k.get("text",""))
class Q:
    def __init__(s,d,uid=101): s.data=d; s.from_user=types.SimpleNamespace(id=uid, username="adm", first_name="Adm"); s.t=None
    async def answer(s,*a,**k): pass
    async def edit_message_text(s,t,**k): s.t=t
import handlers.tagli as T
async def taglia(gid):
    q=Q(f"taglia_ok:{gid}"); u=types.SimpleNamespace(callback_query=q,effective_user=q.from_user)
    await T.cb_conferma_taglio(u, types.SimpleNamespace(bot=Bot())); return q.t
async def main():
    setfase("offseason-fa")
    for i in range(3): await taglia(G[i])
    ok(db.get_tagli_gratuiti_usati("team01","2026")==3, "3 tagli 1x1 gratuiti")
    t=await taglia(G[3])
    imp=db._q("SELECT stagione,importo FROM impatto_taglio WHERE giocatore_id=%s",(G[3],),many=True)
    ok("tagliato" in t and [ (r["stagione"],r["importo"]) for r in imp]==[("2026",1)], f"4° 1x1: consentito con spalmatura 1x1 {[(r['stagione'],r['importo']) for r in imp]}")
    ok(db.get_tagli_gratuiti_usati("team01","2026")==3, "il 4° non conta come gratuito")
    setfase("regular-season-fa")   # roster ora 8? 12-4 = 8 → sotto 10
    t=await taglia(G[6]); ok("sotto il minimo" in t and db.get_contratto_attivo(G[6]), "RS: taglio bloccato sotto i 10")
    setfase("offseason-fa")
    # decadimento ritiro: spalmate di altre squadre tolte
    x=g("Ret"); firma(x,"team02",10,2)
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team01',%s,'2025','2026',3),('team01',%s,'2025','2027',2)",(x,x))
    from handlers.decadimento import applica_decadimento, cmd_ritiro_fa
    await applica_decadimento(Bot(),"team02",x,"ritiro","adm")
    ok(db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(x,))==0 and any("spalmature" in s for s in sent), "ritiro: tolte anche le spalmature di team01")
    y=g("Cam"); firma(y,"team02",5,1)
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team01',%s,'2025','2026',3)",(y,))
    await applica_decadimento(Bot(),"team02",y,"altro","adm")
    ok(db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(y,))==1, "motivo 'altro' (Cam Thomas): spalmate di altri restano")
    # ritiro_fa
    z=g("Free Ret"); db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team03',%s,'2025','2026',4),('team03',%s,'2025','2025',4)",(z,z))
    out=[]
    class M:
        async def reply_text(s,t,**k): out.append(t)
    upd=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900),effective_message=M())
    await cmd_ritiro_fa(upd, types.SimpleNamespace(args=["Free","Ret"],bot=Bot()))
    ok(db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(z,))==1 and "−4M" in out[-1], "/ritiro_fa: tolta la stagione corrente e future, storico 2025 resta")
    # rookie slot
    for i in range(7): firma(g(f"fill{i}"),"team01",1,2)   # team01: 8 + 7 = 15
    rk=g("Rook"); rid=db._qval("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team01',2,40,'2026') RETURNING id",(rk,))
    from handlers.rookie import esegui_attivazione, AttivazioneNonEseguibile
    try: esegui_attivazione(rid,"team01",1,2); ok(False,"rookie con roster pieno")
    except AttivazioneNonEseguibile as e: ok("Roster pieno" in str(e), "attivazione diritti bloccata a roster pieno")
    # registra_firma anni
    import handlers.admin_panel as A
    out.clear()
    upd=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900),effective_message=M(),effective_chat=types.SimpleNamespace(type="private"))
    await A.cmd_registra_firma(upd, types.SimpleNamespace(args=["team02","25","1","Nobody"],bot=Bot()))
    ok("anni non validi" in out[-1], "/registra_firma 25M x1 rifiutato")
asyncio.run(main())

# ── Cam Thomas exception
async def cam_thomas():
    from handlers.decadimento import applica_decadimento
    import handlers.admin_panel as A
    ct=g("Cam Thomas"); firma(ct,"team03",12,2)
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team02',%s,'2025','2026',3)",(ct,))
    await applica_decadimento(Bot(),"team03",ct,"cam_thomas","adm")
    ok(db.get_contratto_attivo(ct) is None and db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(ct,))==1,
       "Cam Thomas: contratto chiuso gratis, spalmature degli altri restano")
    ok(db.minimo_cam_thomas(ct,"team03")==12 and db.minimo_cam_thomas(ct,"team02") is None, "minimo 12M solo per la squadra che l'ha fatto decadere")
    out=[]
    class M:
        async def reply_text(s,t,**k): out.append(t)
    u=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900,first_name="Adm",username=None),effective_message=M(),effective_chat=types.SimpleNamespace(type="private"))
    await A.cmd_registra_firma(u, types.SimpleNamespace(args=["team03","8","1","Cam","Thomas"],bot=Bot()))
    ok("almeno il contratto precedente" in out[-1] and db.get_contratto_attivo(ct) is None, "/registra_firma a 8M rifiutato (minimo 12)")
    await A.cmd_registra_firma(u, types.SimpleNamespace(args=["team03","12","1","Cam","Thomas"],bot=Bot()))
    ok(db.get_contratto_attivo(ct) is not None, "/registra_firma a 12M accettato")
asyncio.run(cam_thomas())

# v7.29.3 (Luca, 26/11): «rifirmato include anche riottenuto via trade»: da chi l'ha fatto decadere vale il contratto
# di allora (il massimo tra i due) per un anno, per cap e trade; per gli altri il suo
async def cam_thomas_trade():
    from handlers.decadimento import applica_decadimento
    from validators.trade import avvisi_cam_thomas, _cap_post_team
    from datetime import datetime, timedelta
    kp = g("Kevin Porter Jr."); firma(kp, "team06", 10, 2)
    await applica_decadimento(Bot(), "team06", kp, "cam_thomas", "adm")
    firma(kp, "team07", 4, 1)
    c = db.get_contratto_attivo(kp)
    cap7 = db.cap_occupato_team("team07", "2026")
    ok(db.peso_cap_giocatore(kp, "2026") == 4 and db.peso_cap_in(kp, "2026", "team06") == 10
       and db.peso_cap_in(kp, "2026", "team08") == 4, "KPJ da Derial vale 4; verso Leo 10, verso altri 4")
    items = [{"tipo": "giocatore", "giocatore_id": kp, "team_id_da": "team07", "team_id_a": "team06", "nome_common": "Kevin Porter Jr."}]
    prima6, dopo6 = _cap_post_team("team06", items, "2026")
    prima7, dopo7 = _cap_post_team("team07", items, "2026")
    ok(dopo6 - prima6 == 10 and prima7 - dopo7 == 4, f"trade: +10 a Leo, −4 a Derial ({dopo6 - prima6}, {prima7 - dopo7})")
    av = avvisi_cam_thomas(items, "2026")
    ok(len(av) == 1 and "vale 10M (non 4M)" in av[0], f"avviso nella trade {av}")
    ok(not avvisi_cam_thomas([{**items[0], "team_id_da": "team06", "team_id_a": "team08"}], "2026"), "verso un altro: nessun avviso")
    # eseguita: da Leo pesa 10, nel roster 10 (anche alla data), poi da un altro di nuovo 4
    db._q("UPDATE contratti SET team_id = 'team06' WHERE id = %s", (c["id"],))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,team_id_a,stagione,contratto_id) VALUES ('traded',%s,'team07','team06','2026',%s)", (kp, c["id"]))
    r6 = {r["giocatore_id"]: r for r in db.get_roster_team("team06")}
    ra = {r["giocatore_id"]: r for r in db.get_roster_team_at("team06", (datetime.now() + timedelta(minutes=1)).isoformat())}
    ok(db.peso_cap_giocatore(kp, "2026") == 10 and r6[kp]["importo"] == 10 and r6[kp]["importo_originale"] == 4
       and ra[kp]["importo"] == 10, "da Leo: cap, roster e roster alla data a 10")
    db._q("UPDATE contratti SET team_id = 'team08' WHERE id = %s", (c["id"],))
    ok(db.peso_cap_giocatore(kp, "2026") == 4 and db.cap_occupato_team("team07", "2026") == cap7 - 4, "da un altro di nuovo 4")
    db._q("UPDATE transazioni SET timestamp = NOW() - INTERVAL '13 months' WHERE giocatore_id = %s AND tipo = 'decadimento'", (kp,))
    ok(db.peso_cap_in(kp, "2026", "team06") == 4, "dopo un anno dal decadimento vale il suo contratto anche da Leo")
asyncio.run(cam_thomas_trade())


# ── v7.19.0: correggere la causa di un decadimento (Luca, 20/11: Altro invece di Cam Thomas)
async def correzione():
    import handlers.decadimento as D
    db._q("DELETE FROM registro_azioni WHERE azione = 'causa del decadimento corretta'")
    ok(D.causa_da_nota("Decadimento: ✂ Cam Thomas exception") == "cam_thomas" and D.causa_da_nota("Decadimento: 📝 Altro") == "altro"
       and D.causa_da_nota("Decadimento: 🌍 Firma in altra lega") == "altra_lega", "la causa dalla nota, anche scritta a mano senza la variante dell'emoji")
    ok(D.cambio_causa("ritiro", "cam_thomas") and D.cambio_causa("altro", "altro") and not D.cambio_causa("altro", "ritiro")
       and not D.cambio_causa("ritiro", "altra_lega"), "da ritiro o altra lega non si torna a una causa che lascia le spalmature")
    y = db._qval("SELECT id FROM giocatori WHERE nome_common = 'Cam'")
    tid = db._qval("SELECT id FROM transazioni WHERE tipo = 'decadimento' AND giocatore_id = %s", (y,))
    q = Q("decor:l", uid=900)
    await D.cb_dec_correggi(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=Bot()))
    ok("Correggi la causa" in q.t, "pannello: l'elenco dei decadimenti recenti")
    q = Q(f"decor:m:{tid}:cam_thomas", uid=900)
    await D.cb_dec_correggi(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=Bot()))
    ok("contratto di prima" in q.t, "conferma: dice che varrà il minimo della Cam Thomas")
    sent.clear()
    q = Q(f"decor:ok:{tid}:cam_thomas", uid=900)
    await D.cb_dec_correggi(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=Bot()))
    ok("Causa corretta" in q.t and db.minimo_cam_thomas(y, "team02") == 5
       and db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s", (y,)) == 1
       and any("Correzione" in s and "Cam Thomas" in s for s in sent),
       "Altro → Cam Thomas: vale il minimo per rifirmarlo, le spalmature restano, messaggio sul canale")
    esito = await D.applica_correzione(Bot(), tid, "ritiro", "adm", user=q.from_user)
    ok("Causa corretta" in esito and db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s", (y,)) == 0,
       "Cam Thomas → Ritiro: tolte anche le spalmature di team01")
    esito = await D.applica_correzione(Bot(), tid, "altro", "adm")
    ok(esito.startswith("❌") and "Ritiro" in db._qval("SELECT note FROM transazioni WHERE id = %s", (tid,)),
       "Ritiro → Altro: rifiutato, la causa resta")
    _n = db._qval("SELECT count(*) FROM registro_azioni WHERE azione = 'causa del decadimento corretta' AND giocatore_id = %s", (y,))
    ok(_n == 2, f"due righe nel registro ({_n})")
asyncio.run(correzione())
