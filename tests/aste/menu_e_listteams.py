import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types, json, os
from datetime import datetime, timezone, timedelta
import database as db, pg_client as pg, utils
pg.init_pg(); db.init_db()
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
def setg(**kw):
    g=json.load(open(os.environ["GLOBALS_PATH"])); g.update(kw); json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
from comandi import liste_comandi
nomi=lambda l:[c.command for c in l]
l=liste_comandi("regular-season-deadline", False, False)
ok("nuova_fa" not in nomi(l["gm"]) and "offri" not in nomi(l["gm"]) and "me" in nomi(l["gm"]), "deadline senza aste: niente comandi di offerta per i GM")
l=liste_comandi("regular-season-fa", True, True)
ok({"nuova_fa","lista_fa","offri","offerta"} <= set(nomi(l["gm"])) and "apri_asta" in nomi(l["admin"]) and "nuova_rfa" not in nomi(l["admin"]), "RS con FA aperta: comandi FA, niente RFA")
l=liste_comandi("offseason-rfa", False, True)
ok("offri" in nomi(l["gm"]) and "nuova_fa" not in nomi(l["gm"]) and "nuova_rfa" in nomi(l["admin"]), "fase RFA: si offre, niente FA, nuova_rfa agli admin")
ok(set(nomi(l["dev"])) >= set(nomi(l["admin"])) >= set(nomi(l["gm"])) and "set_fase" not in nomi(l["admin"]), "dev ⊇ admin ⊇ GM, niente set_fase nel menu")
ok(nomi(l["gruppi"])==["team","listteams"], "gruppi: solo team e listteams")
# /listteams
for i in range(16):
    gid=pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(f"x{i}",f"x{i}",f"x{i}"),one=True)["id"]
    c=pg.q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team02',10,1,'2026','normale') RETURNING id",(gid,),one=True)["id"]
    pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,'team02','2026',%s)",(gid,c))
pg.q("UPDATE contratti SET importo=1 WHERE id > 15")    # team02: 15x10 + 1 = 151M, 16 giocatori
setg(fase="offseason-fa")
out=[]
class M:
    async def reply_text(s,t,**k): out.append(t)
import handlers.admin as A
asyncio.run(A.listteams(types.SimpleNamespace(effective_message=M(),effective_user=types.SimpleNamespace(id=1)), types.SimpleNamespace(args=[])))
t="".join(out); riga=[r for r in t.splitlines() if "team02" in r][0]
print("   ", riga)
ok("151/165M" in riga and "sopra 150 in RS" in riga and "16/15" in riga and "negativo" in riga, "riga compatta con tetto, avviso RS e negativo")
ok("disponibili" not in t and "(15-" not in t, "niente più 'disponibili' e conti tipo (15-1)")
