import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.21.0 (Luca, 21/11): roster, assets, pick, pick_lega, carriera, team_diff, trova_trade, penalita e i PDF del bot
principale anche in loucabot (vista.py, codice del main da MAIN_DIR); nei gruppi risponde loucabot, il main in privato."""
import asyncio, os, types
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
os.environ["MAIN_DIR"] = os.path.join(os.path.dirname(os.getcwd()), "fantabasket-main")
import db, config
db.init_db()
import vista
hs = vista.get_handlers()
cmds = {c for h in hs for c in getattr(h, "commands", ())}
ok(cmds == set(vista.COMANDI), f"loucabot: tutte le viste del main {sorted(cmds)}")
import handlers as H
ok(callable(getattr(H, "cmd_classifica", None)) or hasattr(H, "get_handlers"), "il modulo handlers di loucabot resta quello di loucabot")
import database as MDB
MDB.init_db(); MDB.migrate_db()
S = config.stagione()
for r in MDB._q("SELECT id FROM giocatori WHERE nome_common LIKE 'Vista %%'", many=True) or []:
    MDB._q("DELETE FROM transazioni WHERE giocatore_id = %s", (r["id"],)); MDB._q("DELETE FROM contratti WHERE giocatore_id = %s", (r["id"],))
    MDB._q("DELETE FROM giocatori WHERE id = %s", (r["id"],))
gid = MDB._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('Vista Uno','Vista Uno','vista uno') RETURNING id")
cid = MDB._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team01',7,2,%s,'normale') RETURNING id", (gid, S))
MDB._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,'team01',%s,%s)", (gid, S, cid))


class Msg:
    def __init__(s): s.out = []
    async def reply_text(s, t, **k): s.out.append(("testo", t)); return s
    async def reply_photo(s, photo=None, caption=None, **k): s.out.append(("foto", caption)); return s
    async def reply_document(s, document=None, **k): s.out.append(("doc", k.get("filename"))); return s
    async def reply_media_group(s, media, **k): s.out.append(("album", len(media))); return [s]
    async def delete(s): pass
    async def edit_text(s, *a, **k): pass


class Bot:
    async def send_chat_action(self, *a, **k): pass
    async def send_message(self, **k): pass


def comando(nome, args, gruppo=True):
    m = Msg()
    h = next(h for h in hs if nome in getattr(h, "commands", ()))
    u = types.SimpleNamespace(effective_message=m, message=m, effective_user=types.SimpleNamespace(id=101, first_name="GM", username=None, full_name="GM"),
                              effective_chat=types.SimpleNamespace(id=-100 if gruppo else 101, type="group" if gruppo else "private"))
    asyncio.run(h.callback(u, types.SimpleNamespace(args=args, bot=Bot(), user_data={}, chat_data={}, bot_data={})))
    return m.out


for nome, args, tipo in (("roster", ["Alfa"], "foto"), ("assets", ["Alfa"], "foto"), ("roster", [], "foto"),
                         ("pick_lega", [], "foto"), ("carriera", ["Vista", "Uno"], "foto"), ("team_diff", ["Alfa"], "testo"),
                         ("penalita", ["Alfa"], "testo"), ("penalita", [], "testo")):
    out = comando(nome, args)
    ok(any(k == tipo for k, _ in out) and not any("❌" in (t or "") or "non trovat" in (t or "") for k, t in out if k == "testo"),
       f"/{nome} {' '.join(args)} nel gruppo, da loucabot: {[(k, (t or '')[:60]) for k, t in out][:3]}")
out = comando("pick", ["Alfa", "1", str(int(S) + 1)])
ok(out and out[0][0] in ("testo", "foto"), f"/pick: risponde {out[:1]}")
out = comando("trova_trade", ["Vista", "Uno"])
ok(out and out[0][0] == "testo", f"/trova_trade: risponde {out[:1]}")
out = comando("penalita", [], gruppo=False)
ok(out and "Penalità di" in out[0][1], "/penalita in loucabot: da vedere, niente pannello admin né revoche")

# il main: le viste solo in privato, niente menu dei gruppi, fuori dal menu del gruppo admin
_sys.path.insert(0, os.environ["MAIN_DIR"])
import importlib.util
spec = importlib.util.spec_from_file_location("comandi_main", os.path.join(os.environ["MAIN_DIR"], "comandi.py"))
CM = importlib.util.module_from_spec(spec); spec.loader.exec_module(CM)
L = CM.liste_comandi("regular-season-fa")
ok(L["group"] == [] and CM.VISTE <= {c.command for c in L["gm"]} | {"penalita"}, "main: niente menu nei gruppi, le viste restano nel menu privato")
import ast
src = open(os.path.join(os.environ["MAIN_DIR"], "bot.py")).read()
ok(all(f"_solo_privato_viste({n}())" in src for n in ("roster_handlers", "pick_handlers", "carriera_handlers", "team_diff_handlers",
                                                       "trova_trade_handlers", "penalita_handlers")), "main: le viste solo in privato")
from telegram.ext import CommandHandler, filters
spec = importlib.util.spec_from_file_location("bot_main_viste", os.path.join(os.environ["MAIN_DIR"], "bot.py"))
_ns = {}
exec(compile(ast.Module(body=[n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_solo_privato_viste"], type_ignores=[]), "bot.py", "exec"), _ns)
_sys.modules["comandi"] = CM
_h = _ns["_solo_privato_viste"]([CommandHandler("roster", lambda u, c: None), CommandHandler("menu", lambda u, c: None)])
_upd = lambda tipo: types.SimpleNamespace(effective_chat=types.SimpleNamespace(type=tipo))
ok(_h[0].filters.check_update is not None and repr(_h[0].filters) != repr(_h[1].filters), "main: /roster col filtro privato, /menu no")
MDB._q("DELETE FROM transazioni WHERE giocatore_id = %s", (gid,)); MDB._q("DELETE FROM contratti WHERE giocatore_id = %s", (gid,))
MDB._q("DELETE FROM giocatori WHERE id = %s", (gid,))
