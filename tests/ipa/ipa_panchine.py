import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""IPanchinari: panchina da messaggio con soprannomi (abbinamento, bottoni, alias ricordati,
pubblicazione sul canale solo con le righe del GM, aggiornamento, scadenza), quintetti (admin,
import, /quintetto coi bottoni, conferma, incompatibilità), promemoria, riepilogo e chiusura."""
import asyncio, importlib.util, json, os, types
from datetime import date, datetime, timedelta, timezone
import config, db, comune, panchine as P, quintetti as Q, soprannomi as SO, cessioni as CE

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

# tabelle di loucabot (giornate, partite NBA) e del bot principale (roster) nello stesso DB
spec = importlib.util.spec_from_file_location("louca_db", os.path.join(ROOT, "fantabasket-loucabot", "db.py"))
ldb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ldb); ldb.init_db()
db.init_db()
db.q("TRUNCATE ipa_quintetto, ipa_alias, ipa_cessioni, ipa_panchine, ipa_bozze, ipa_conferme, ipa_formazioni, ipa_stato_giornata, ipa_controlli, "
     "lega_giornate, nba_tabellini, nba_partite, nba_atleti, nba_infortuni")
G = json.load(open(config.GLOBALS_PATH)); G["canale_panchinari_id"] = -500; json.dump(G, open(config.GLOBALS_PATH, "w"))

S = config.stagione()
gids = {}
NOMI_PROVA = ["Ja Morant", "Dominick Barlow", "Walter Clayton Jr.", "Nique Clifford", "Kevon Looney", "Jalen Brunson",
              "Devin Booker", "Mikal Bridges", "Grant Williams", "Mark Williams", "Josh Hart"]
vecchi = [r["id"] for r in db.q("SELECT id FROM giocatori WHERE nome_bref = ANY(%s) AND espn_id LIKE '9%%'", (NOMI_PROVA,), many=True) or []]
if vecchi:   # avanzi di una prova interrotta
    db.q("DELETE FROM cambi_ruolo WHERE giocatore_id = ANY(%s)", (vecchi,))
    db.q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (vecchi,))
    db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (vecchi,))
def giocatore(nome, team, ruolo, espn=None, squadra=None):
    gid = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
               (nome, nome, nome.lower(), espn), one=True)["id"]
    db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, %s, 5, 2, %s, 'normale')",
         (gid, team, S))
    db.q("INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_a, stagione, tipo) VALUES (%s, %s, %s, %s, 'iniziale')", (gid, team, ruolo, S))
    if espn:
        db.q("INSERT INTO nba_atleti (atleta, nome, squadra) VALUES (%s, %s, %s)", (espn, nome, squadra))
    gids[nome] = gid
    return gid
for n, r, sq in [("Ja Morant", "PG", "MEM"), ("Dominick Barlow", "PF", "ATL"), ("Walter Clayton Jr.", "PG", "UTA"),
                 ("Nique Clifford", "SG", "SAC"), ("Kevon Looney", "C", "NOP"), ("Jalen Brunson", "PG", "NYK"),
                 ("Devin Booker", "SG", "PHX"), ("Mikal Bridges", "SF", "NYK"), ("Grant Williams", "PF", "CHA"),
                 ("Mark Williams", "C", "PHX"), ("Josh Hart", "SF", "NYK")]:
    giocatore(n, "team01", r, espn=f"9{len(gids)}", squadra=sq)
giocatore("Altro Tizio", "team02", "PG")

ora_ = datetime.now(timezone.utc)
def giornata(n, scad, dal, al, media=None):
    db.q("INSERT INTO lega_giornate (stagione, numero, dal, al, prima_partita, media) VALUES (%s, %s, %s, %s, %s, %s)",
         (S, n, dal, al, scad, media))
d1 = (ora_ + timedelta(days=2)).date()
giornata(1, ora_ - timedelta(hours=1), d1 - timedelta(days=5), d1 - timedelta(days=4), [])
giornata(2, ora_ + timedelta(days=2), d1, d1 + timedelta(days=1), ["ATL"])
for i, (casa, tr, d) in enumerate([("NYK", "BOS", d1), ("MEM", "NYK", d1 + timedelta(days=1)), ("PHX", "SAC", d1)]):
    ldb.salva_partite_nba([{"espn_id": f"p{i}", "stagione": S, "tipo": 2, "data_et": d, "casa": casa, "trasferta": tr,
                            "inizio": datetime(d.year, d.month, d.day, 23, 0, tzinfo=timezone.utc), "stato": "STATUS_SCHEDULED"}])

# ── finto Telegram ──
class Msg:
    def __init__(s, testo=""):
        s.text, s.caption, s.document, s.reply_to_message, s.risposte = testo, None, None, None, []
    async def reply_text(s, t, **k): s.risposte.append((t, k))
class Bot:
    def __init__(s): s.mandati, s.n, s.testi = [], 1000, {}
    async def send_message(s, chat_id, text, **k):
        s.n += 1; s.mandati.append({"chat_id": chat_id, "text": text, "id": s.n, **k}); s.testi[(chat_id, s.n)] = text
        return types.SimpleNamespace(message_id=s.n)
    async def edit_message_text(s, chat_id, message_id, text, **k):
        if getattr(s, "rotto", False): raise RuntimeError("Bad Request: message to edit not found")
        if s.testi[(chat_id, message_id)] == text: raise RuntimeError("Bad Request: message is not modified")
        s.testi[(chat_id, message_id)] = text
        s.mandati.append({"chat_id": chat_id, "text": text, "id": message_id, "modifica": True})
    async def send_document(s, **k): pass
BOT = Bot()
CTX = types.SimpleNamespace(bot=BOT, args=[], job_queue=None)
def upd(uid, msg=None, cb=None):
    u = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid, full_name=f"U{uid}"),
                              effective_chat=types.SimpleNamespace(id=uid), effective_message=msg, callback_query=None)
    if cb:
        q = types.SimpleNamespace(data=cb, risposte=[], testi=[])
        async def answer(t=None, show_alert=False): q.risposte.append(t)
        async def edit(t, **k): q.testi.append((t, k))
        q.answer, q.edit_message_text = answer, edit
        u.callback_query = q
    return u
def manda(uid, testo):
    m = Msg(testo); asyncio.run(P.msg_panchina(upd(uid, m), CTX)); return m
def premi(uid, data):
    u = upd(uid, cb=data); asyncio.run((P.cb_panchina if data.startswith("pb:") else Q.cb_quintetto)(u, CTX)); return u.callback_query
def bottoni(k):
    return [b.callback_data for riga in k.inline_keyboard for b in riga]

# ── abbinamento: casi reali ──
import abbina as A
_r = [{"id": i, "nome_common": n} for i, n in enumerate(["Herbert Jones", "Jalen Williams", "Jalen Brunson", "Ja Morant"], 1)]
ok(all(A.abbina_riga(x, _r)["scelto"] == 1 for x in ("Herbet", "Herbet il muro", "Herb")),
   "nome di battesimo da solo, scritto male o accorciato (Herbet, Herb): riconosciuto se è di uno solo")
ok(A.abbina_riga("Jalen", _r)["scelto"] is None and len(A.abbina_riga("Jalen", _r)["candidati"]) == 2,
   "nome di battesimo di due giocatori: si chiede")

# ── quintetti dall'admin ──
qq, err = Q.leggi_quintetto("team01", ["PG Brunson", "SG Booker", "SF Bridges", "PF Grant Williams", "C Mark Williams"])
ok(not err and qq == {"PG": gids["Jalen Brunson"], "SG": gids["Devin Booker"], "SF": gids["Mikal Bridges"],
                      "PF": gids["Grant Williams"], "C": gids["Mark Williams"]}, f"quintetto da testo con i ruoli {err}")
_, err = Q.leggi_quintetto("team01", ["SG Brunson", "Booker", "Bridges", "Grant Williams", "Mark Williams"])
ok(any("ruolo è PG" in x for x in err), "ruolo scritto diverso da quello di roster: errore")
_, err = Q.leggi_quintetto("team01", ["Brunson", "Morant", "Bridges", "Grant Williams", "Mark Williams"])
ok(any("due PG" in x for x in err) and any("manca SG" in x for x in err) is False, f"due giocatori nello stesso ruolo: errore {err}")
salvati, errori = Q.importa("Alfa\nPG Brunson\nSG Booker\nSF Bridges\nPF Grant Williams\nC Mark Williams\n\nZeta\nPG Uno\n")
ok(salvati == ["Alfa"] and any("Zeta" in x for x in errori) and db.quintetto("team01") == qq, "import di più squadre: salva le buone, segnala le altre")

# ── panchina con i soprannomi ──
TESTO = """No Buffalo Brownies

Ja the sniper Morant
Dominik Arcade Boy Barlow
Walter White Clayton jr
Nique il califfo Clifford
Kevon the champ Looney"""
m = manda(101, TESTO)
t, k = m.risposte[0]
ok("giornata 2" in t and "Ja the sniper Morant → <b>Ja Morant</b>" in t and "Dominick Barlow" in t and "No Buffalo Brownies" in t,
   "anteprima al GM: per la prossima giornata aperta, con i nomi veri e il titolo")
bid = int(bottoni(k["reply_markup"])[-2].split(":")[2])
ok(f"pb:ok:{bid}" in bottoni(k["reply_markup"]), "tutte le righe riconosciute: si può pubblicare")
ok(premi(102, f"pb:ok:{bid}").risposte == ["Non è la tua squadra."], "il GM di un'altra squadra non può confermare")
premi(111, f"pb:ok:{bid}")                                   # il secondo GM della squadra sì
canale = [x for x in BOT.mandati if x["chat_id"] == -500]
ok(len(canale) == 1 and canale[0]["text"].startswith("<b>Alfa</b>") and "Dominik Arcade Boy Barlow" in canale[0]["text"] and "Dominick Barlow" not in canale[0]["text"]
   and "<i>No Buffalo Brownies</i>" in canale[0]["text"] and "Alfa" in canale[0]["text"],
   f"sul canale solo le righe del GM (niente nomi veri) e il titolo: {canale[0]['text'] if canale else ''}")
ok("<i>✍️ GM · inserita " in canale[0]["text"] and " alle " in canale[0]["text"], "sul canale: inserita dal GM, giorno e ora")
p = db.panchina(S, 2, "team01")
ok([r["giocatore_id"] for r in p["righe"]] == [gids[n] for n in ("Ja Morant", "Dominick Barlow", "Walter Clayton Jr.",
                                                                    "Nique Clifford", "Kevon Looney")], "panchina salvata in ordine coi giocatori veri")

m = manda(101, "Ja Morant\nBarlow\nClayton\nClifford")
ok("5 giocatori, mai meno" in m.risposte[0][0] and "pb:" not in str(m.risposte[0][1]), "4 righe: rifiutata, la panchina è sempre di 5")

# ── soprannome sconosciuto: si sceglie coi bottoni e si ricorda ──
m = manda(101, "Lo Sceriffo\nBarlow\nClayton\nClifford\nLooney")
t, k = m.risposte[0]
bid = int(bottoni(k["reply_markup"])[0].split(":")[2])
ok("❓" in t and f"pb:ok:{bid}" not in bottoni(k["reply_markup"]), "riga non riconosciuta: da scegliere, niente Pubblica")
ok(f"pb:t:{bid}:0" in bottoni(k["reply_markup"]), "riga senza candidati: bottone per scegliere dalla rosa già nell'anteprima")
qb = premi(101, f"pb:r:{bid}:0")
ok(any(f"pb:s:{bid}:0:{gids['Josh Hart']}" == b for b in bottoni(qb.testi[-1][1]["reply_markup"])), "bottoni con la rosa")
premi(101, f"pb:s:{bid}:0:{gids['Josh Hart']}")
premi(101, f"pb:ok:{bid}")
canale = [x for x in BOT.mandati if x["chat_id"] == -500]
ok(len(canale) == 2 and canale[1].get("modifica") and canale[1]["id"] == canale[0]["id"] and "🔁" in canale[1]["text"],
   "rimandata: modifica il messaggio di prima sul canale, niente messaggio nuovo")
ok("✍️ GM · 🔁 ultima modifica " in canale[1]["text"] and "aggiornata" not in canale[1]["text"],
   "aggiornata: solo in fondo, 🔁 e ora dell'ultima modifica (niente riga in più in cima)")
m = manda(101, "lo sceriffo!\nBarlow\nClayton\nClifford\nLooney")
ok("lo sceriffo! → <b>Josh Hart</b>" in m.risposte[0][0], "la volta dopo il soprannome si riconosce da solo (alias)")

# ── dubbio tra più candidati: bottoni diretti nell'anteprima ──
m = manda(101, "Williams il primo\nBarlow\nClayton\nClifford\nLooney")
t, k = m.risposte[0]
bid = int(bottoni(k["reply_markup"])[0].split(":")[2])
ok({f"pb:s:{bid}:0:{gids['Grant Williams']}", f"pb:s:{bid}:0:{gids['Mark Williams']}"} <= set(bottoni(k["reply_markup"])),
   "riga dubbia: i candidati sono già bottoni nell'anteprima")
qb = premi(101, f"pb:s:{bid}:0:{gids['Grant Williams']}")
ok("Williams il primo → <b>Grant Williams</b>" in qb.testi[-1][0], "un tocco e la riga è risolta")
db.chiudi_bozza(bid)

# ── titolare in panchina (solo avviso: fa fede Yahoo), doppioni (bloccano) ──
m = manda(101, "Brunson\nBarlow\nBarlow il bis\nClifford\nLooney")
t, k = m.risposte[0]
ok("due volte" in t and not any(b.startswith("pb:ok") for b in bottoni(k["reply_markup"])), "doppione: niente Pubblica")
m = manda(101, "Brunson\nBarlow\nClayton\nClifford\nLooney")
t, k = m.risposte[0]
bid = int(bottoni(k["reply_markup"])[0].split(":")[2])
ok("risulta nel tuo quintetto (PG)" in t and "ci pensa" not in t and "se ne occupa un admin" in t
   and f"pb:ok:{bid}" in bottoni(k["reply_markup"]), "titolare in panchina: solo un avviso, si pubblica lo stesso")
BOT.mandati.clear()
premi(101, f"pb:ok:{bid}")
ok(any(x["chat_id"] == -3 and "titolare nel quintetto del bot" in x["text"] for x in BOT.mandati)
   and any(x["chat_id"] == -500 for x in BOT.mandati), "pubblicata, e l'avviso arriva sul canale log")
m = manda(101, "Brunson\nBarlow\nClayton\nClifford\nLooney")
bid = int(bottoni(m.risposte[0][1]["reply_markup"])[0].split(":")[2])
BOT.mandati.clear(); BOT.rotto = True
premi(101, f"pb:ok:{bid}")
BOT.rotto = False
nuovi = [x for x in BOT.mandati if x["chat_id"] == -500]
ok(len(nuovi) == 1 and not nuovi[0].get("modifica") and db.q("SELECT messaggio_canale FROM ipa_panchine WHERE team_id='team01' ORDER BY inviata DESC LIMIT 1", one=True)["messaggio_canale"] == nuovi[0]["id"],
   "messaggio vecchio cancellato a mano: ne esce uno nuovo, e il bot si segna quello")

# ── incompatibilità quintetto/panchina e /quintetto ──
db.salva_panchina(S, 2, "team01", None, [{"giocatore_id": gids["Ja Morant"], "testo": "Ja"}])
ok(any("anche in panchina" in x for x in Q.incompatibilita("team01", {**qq, "PG": gids["Ja Morant"]})),
   "titolare che è anche in panchina: segnalato")
qb = premi(101, "q:c:team01:PG")
ok(set(bottoni(qb.testi[-1][1]["reply_markup"])) >= {f"q:s:team01:PG:{gids['Ja Morant']}", f"q:s:team01:PG:{gids['Walter Clayton Jr.']}"}
   and f"q:s:team01:PG:{gids['Devin Booker']}" not in bottoni(qb.testi[-1][1]["reply_markup"]), "cambio PG: solo i PG della squadra")
from shared import azioni as _A; _A.migra(db.q); db.q("DELETE FROM registro_azioni WHERE bot = 'ipa'")
qb = premi(101, f"q:s:team01:PG:{gids['Walter Clayton Jr.']}")
ok(db.quintetto("team01")["PG"] == gids["Walter Clayton Jr."] and db.conferme(S, 2)["team01"]["stato"] == "modificato",
   "quintetto cambiato dal GM: segnato come modificato")
ok(premi(101, f"q:s:team01:PG:{gids['Devin Booker']}").risposte[-1].startswith("Non è un giocatore di quel ruolo"), "ruolo sbagliato rifiutato")
premi(101, "q:ok:team01:2")
ok(premi(102, "q:ok:team01:2").risposte[-1] == "Non è la tua squadra.", "il GM di un'altra squadra non tocca il quintetto")
ok(db.conferme(S, 2)["team01"]["stato"] == "confermato", "Confermo dal promemoria")
_reg = db.q("SELECT veste, azione, squadre, dopo, chi_id FROM registro_azioni WHERE bot = 'ipa' ORDER BY id", many=True)
ok([(r["veste"], r["azione"], r["squadre"]) for r in _reg] == [("gm", "quintetto cambiato", ["team01"]), ("gm", "quintetto confermato", ["team01"])]
   and _reg[0]["dopo"] == "Walter Clayton Jr." and _reg[0]["chi_id"] == 101,
   f"registro IPanchinari: cambio e conferma del GM, sulla sua squadra {_reg}")
ok(premi(101, "q:ok:team01:1").risposte[-1] == "La scadenza di questa giornata è passata.", "bottone di una giornata scaduta: rifiutato")

# ── stato ESPN (ultimo snapshot di nba_infortuni di loucabot) nei builder, nell'anteprima e nel quintetto ──
db.q("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, preso) VALUES (CURRENT_DATE - 3, %s, 'Kevon Looney', 'NOP', 'Day-To-Day', NOW() - INTERVAL '3 days')",
     (db.q("SELECT espn_id FROM giocatori WHERE id = %s", (gids["Kevon Looney"],), one=True)["espn_id"],))   # snapshot vecchio: non conta
db.q("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato) VALUES (CURRENT_DATE, %s, 'Kevon Looney', 'NOP', 'Out'), (CURRENT_DATE, %s, 'Devin Booker', 'PHX', 'Day-To-Day')",
     (db.q("SELECT espn_id FROM giocatori WHERE id = %s", (gids["Kevon Looney"],), one=True)["espn_id"],
      db.q("SELECT espn_id FROM giocatori WHERE id = %s", (gids["Devin Booker"],), one=True)["espn_id"]))
m = manda(101, "Ja Morant\nBarlow\nClifford\nLooney\nBrunson")
ok("→ <b>Kevon Looney</b> 🔴 Out" in m.risposte[0][0] and "Infortunati da ESPN, aggiornati" in m.risposte[0][0],
   "anteprima: stato ESPN accanto al giocatore, con l'ora dell'aggiornamento")
db.chiudi_bozza(int(bottoni(m.risposte[0][1]["reply_markup"])[-2].split(":")[2]))
qb = premi(101, "q:c:team01:SG")
ok(any("Devin Booker 🟡 Day-To-Day" in b.text for riga in qb.testi[-1][1]["reply_markup"].inline_keyboard for b in riga),
   "scelta del quintetto: stato nei bottoni")
ok("Devin Booker</b>" not in Q.testo_quintetto("team01", None) and "Devin Booker 🟡 Day-To-Day" in Q.testo_quintetto("team01", None),
   "quintetto (promemoria, /quintetto): stato accanto al titolare")

# ── builder coi bottoni ──
m = Msg(); asyncio.run(P.cmd_build_panchina(upd(101, m), CTX))
t, k = m.risposte[0]
tasti = bottoni(k["reply_markup"])
bid = int(tasti[0].split(":")[2])
tit = set(db.quintetto("team01").values())
proposti = {int(x.split(":")[3]) for x in tasti if x.startswith("pb:b:")}
ok(proposti and not (proposti & tit) and gids["Josh Hart"] in proposti, "builder: solo giocatori della squadra non nel quintetto")
ok(any("Kevon Looney (C) 🔴 Out" in b.text for riga in k["reply_markup"].inline_keyboard for b in riga),
   "builder: stato ESPN nei bottoni")
qb = premi(101, f"pb:b:{bid}:{gids['Josh Hart']}")
ok(f"pb:b:{bid}:{gids['Josh Hart']}" not in bottoni(qb.testi[-1][1]["reply_markup"]) and "1. Josh Hart" in qb.testi[-1][0],
   "builder: il giocatore scelto non si ripropone")
premi(101, f"pb:b:{bid}:{gids['Kevon Looney']}")
qb = premi(101, f"pb:u:{bid}")
ok("Kevon Looney" not in qb.testi[-1][0], "builder: togli l'ultimo")
qb = premi(101, f"pb:b:{bid}:{gids['Ja Morant']}")
ok(not any(x.startswith("pb:bv") or x.startswith("pb:ok") for x in bottoni(qb.testi[-1][1]["reply_markup"])),
   "builder: niente anteprima né Pubblica prima del quinto")
premi(101, f"pb:b:{bid}:{gids['Dominick Barlow']}"); premi(101, f"pb:b:{bid}:{gids['Nique Clifford']}")
qb = premi(101, f"pb:b:{bid}:{gids['Kevon Looney']}")
ok(f"pb:ok:{bid}" in bottoni(qb.testi[-1][1]["reply_markup"]) and "2. Ja Morant → <b>Ja Morant</b>" in qb.testi[-1][0],
   "builder: al quinto l'anteprima con Pubblica, come per il messaggio")
BOT.mandati.clear(); premi(101, f"pb:ok:{bid}")
ok(any(x["chat_id"] == -500 and "1. Josh Hart\n2. Ja Morant" in x["text"] for x in BOT.mandati), "builder: sul canale i nomi dei giocatori")
ok("josh hart" not in db.alias("team01"), "il nome vero non diventa un soprannome")

# ── CAI mode dal builder: titolo e soprannomi ──
m = Msg(); asyncio.run(P.cmd_build_panchina(upd(101, m), CTX))
bid = int(bottoni(m.risposte[0][1]["reply_markup"])[0].split(":")[2])
CINQUE = ["Josh Hart", "Kevon Looney", "Ja Morant", "Dominick Barlow", "Nique Clifford"]
for n in CINQUE:
    qb = premi(101, f"pb:b:{bid}:{gids[n]}")
ok(f"pb:cai:{bid}" in bottoni(qb.testi[-1][1]["reply_markup"]), "anteprima del builder: bottone CAI mode")
qb = premi(101, f"pb:cai:{bid}")
ok("titolo" in qb.testi[-1][0], "CAI mode: prima chiede il titolo")
m = manda(101, "La panca dei sogni")
ok("Soprannome per <b>Josh Hart</b> (1/5)" in m.risposte[-1][0], "poi il soprannome di ognuno, in ordine")
m = manda(101, "Lo Sceriffo bis")
ok("Kevon Looney</b> (2/5)" in m.risposte[-1][0], "avanti al prossimo")
qb = premi(101, f"pb:cs:{bid}")
ok("Ja Morant</b> (3/5)" in qb.testi[-1][0], "salta: al prossimo")
qb = premi(101, f"pb:cf:{bid}")
ok("1. Lo Sceriffo bis → <b>Josh Hart</b>" in qb.testi[-1][0] and "2. Kevon Looney → <b>Kevon Looney</b>" in qb.testi[-1][0]
   and "La panca dei sogni" in qb.testi[-1][0], "fine: anteprima con titolo e soprannomi")
BOT.mandati.clear(); premi(101, f"pb:ok:{bid}")
ok(any(x["chat_id"] == -500 and "<i>La panca dei sogni</i>" in x["text"] and "1. Lo Sceriffo bis" in x["text"]
       and "Josh Hart" not in x["text"] for x in BOT.mandati), "sul canale titolo e soprannomi, non i nomi")
ok(db.alias("team01").get("lo sceriffo bis") == gids["Josh Hart"], "il soprannome della CAI mode si impara")
m = Msg(); asyncio.run(P.cmd_build_panchina(upd(101, m), CTX))
bid = int(bottoni(m.risposte[0][1]["reply_markup"])[0].split(":")[2])
for n in CINQUE:
    premi(101, f"pb:b:{bid}:{gids[n]}")
premi(101, f"pb:cai:{bid}")
m = manda(101, "Ja the sniper Morant\nBarlow\nClayton\nClifford\nLooney")
ok("Panchina di Alfa" in m.risposte[-1][0] and "Ja Morant" in m.risposte[-1][0] and db.bozza(bid)["chiusa"],
   "CAI mode lasciata a metà: un messaggio di più righe è una panchina nuova")

# ── testo con le partite ──
tq = Q.testo_quintetto("team01", db.giornata(S, 2))
ok("NYK: " in tq and "vs BOS" in tq and "@ MEM" in tq and "PHX: " in tq and "CHA: " in tq, f"partite di ogni titolare nella giornata\n{tq}")

# ── /report_formazioni: quintetti e panchine di tutte le squadre, coi problemi ──
import report as RP
md = RP.report(db.giornata(S, 2))
ok(md.startswith(f"# Formazioni della giornata 2 — stagione {S}") and "aperta: quintetti di adesso" in md
   and "squadre NBA a media: ATL" in md, "report: intestazione (giornata aperta, quintetti di adesso, squadre a media)")
ok("| Beta |" in md and "❌ non mandata" in md and "Panchine mancanti: **" in md, "report: panchine mancanti nel riepilogo")
ok("| Kevon Looney | C | NOP | — | 🔴 Out |" in md and "🟡 Day-To-Day | da seguire" in md, "report: stato degli infortunati accanto al giocatore")
ok("@ MEM" in md and "vs BOS" in md, "report: partite della giornata di ogni giocatore")
ok("nessuna partita: media" in md, "report: squadra NBA senza partite (media)")
ok("**posto vuoto: 0 punti**" in md or "senza id ESPN" in md, "report: posti vuoti o senza id ESPN segnalati")
ok(RP.scegli_giornata(None)["numero"] == 2 and RP.scegli_giornata(1)["numero"] == 1, "report: senza N la prossima giornata")
class _B:
    def __init__(s): s.doc = []
    async def send_document(s, chat_id, document, filename, caption=None, **k): s.doc.append((filename, document.getvalue()))
_bb = _B()
_ctx = types.SimpleNamespace(bot=_bb, args=["2"])
_u = lambda uid: types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_chat=types.SimpleNamespace(id=uid),
                                       effective_message=Msg())
asyncio.run(RP.cmd_report_formazioni(_u(101), _ctx))
_adm = int(config.admin_ids()[0])
asyncio.run(RP.cmd_report_formazioni(_u(_adm), _ctx))
ok(len(_bb.doc) == 1 and _bb.doc[0][0].startswith("formazioni-G2-") and b"## Riepilogo" in _bb.doc[0][1],
   "/report_formazioni N: solo admin, file .md")

# ── chiusura: panchinari ceduti prima della scadenza, al gruppo admin (penalità) ──
db.q("DELETE FROM transazioni WHERE note = 'prova ceduti'")
for _tipo, _da, _a, _quando in [("signed", None, "team01", ora_ - timedelta(days=30)), ("trade", "team01", "team02", ora_)]:
    db.q("INSERT INTO transazioni (tipo, oggetto, giocatore_id, team_id_da, team_id_a, stagione, timestamp, note) "
         "VALUES (%s, 'giocatore', %s, %s, %s, %s, %s, 'prova ceduti')", (_tipo, gids["Kevon Looney"], _da, _a, S, _quando))
_cp, _cq = Q.ceduti_alla_scadenza(S, db.giornata(S, 2), db.panchine(S, 2))
ok(_cp == [("Alfa", ["Kevon Looney"])] and _cq == [], "chiusura: panchinario ceduto prima della scadenza trovato (per il gruppo admin)")
_cp, _ = Q.ceduti_alla_scadenza(S, {**db.giornata(S, 2), "prima_partita": ora_ - timedelta(hours=1)}, db.panchine(S, 2))
ok(_cp == [], "ceduto dopo la scadenza: non segnalato (conta per la vecchia squadra)")
db.q("DELETE FROM transazioni WHERE note = 'prova ceduti'")

# ── orario del promemoria ──
roma = comune.ROMA
notte = {"prima_partita": datetime(2026, 10, 21, 1, 0, tzinfo=roma)}
pomeriggio = {"prima_partita": datetime(2026, 12, 25, 18, 0, tzinfo=roma)}
ok(comune.ora_promemoria(notte) == datetime(2026, 10, 20, 8, 0, tzinfo=roma) and
   comune.ora_promemoria(pomeriggio) == datetime(2026, 12, 25, 8, 0, tzinfo=roma),
   "promemoria: le 8 del giorno prima se si gioca di notte, della mattina stessa se si gioca nel pomeriggio")

# ── job: chiusura della G1 (scaduta), promemoria e riepilogo della G2 ──
BOT.mandati.clear()
asyncio.run(Q.job_giornate(CTX))
ok(db.stato_giornata(S, 1)["chiusa"] and db.formazione(S, 1, "team01")["PG"] == gids["Walter Clayton Jr."]
   and any("Giornata 1 chiusa" in x["text"] and "Beta" in x["text"] for x in BOT.mandati),
   "scadenza passata: quintetti congelati, panchine mancanti agli admin")
ok("**chiusa**: formazioni congelate" in RP.report(db.giornata(S, 1)), "report di una giornata chiusa: le formazioni congelate")
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE numero = 2", (datetime.now(timezone.utc) + timedelta(hours=1),))
BOT.mandati.clear()
asyncio.run(Q.job_giornate(CTX))
prom = [x for x in BOT.mandati if x["chat_id"] in (101, 111)]
ok(len(prom) == 2 and "q:ok:team01:2" in bottoni(prom[0]["reply_markup"]) and "vs BOS" in prom[0]["text"],
   "promemoria a tutti i GM della squadra con partite e Confermo/Modifico")
ok(any(x["chat_id"] == -2 and "Panchine mancanti" in x["text"] for x in BOT.mandati), "riepilogo agli admin prima della scadenza")
BOT.mandati.clear()
asyncio.run(Q.job_giornate(CTX))
ok(not BOT.mandati, "promemoria e riepilogo una volta sola")

# ── admin: quintetto cambiato a giornata in corso, formazione di una giornata precisa ──
db.q("UPDATE lega_giornate SET al = %s WHERE numero = 1", (date.today() + timedelta(days=1),))
def admin(testo):
    m = Msg(testo); asyncio.run(Q.cmd_quintetto_admin(upd(900, m), CTX)); return m.risposte[-1][0]
r = admin("/quintetto_admin Alfa\nMorant\nBooker\nBridges\nGrant Williams\nMark Williams")
ok(db.formazione(S, 1, "team01")["PG"] == gids["Ja Morant"] and db.quintetto("team01")["PG"] == gids["Ja Morant"]
   and "giornata in corso (1)" in r, "admin a giornata in corso: cambia quintetto e formazione della giornata")
r = admin("/quintetto_admin Alfa G1\nBrunson\nBooker\nBridges\nGrant Williams\nMark Williams")
ok(db.formazione(S, 1, "team01")["PG"] == gids["Jalen Brunson"] and db.quintetto("team01")["PG"] == gids["Ja Morant"],
   "con G1: corregge solo la formazione della giornata 1")
ok("non è ancora chiusa" in admin("/quintetto_admin Alfa G2\nBrunson\nBooker\nBridges\nGrant Williams\nMark Williams"),
   "G di una giornata non chiusa: rifiutato")
_m = Msg("/quintetto_admin Alfa G1"); asyncio.run(Q.cmd_quintetto_admin(upd(900, _m), CTX))
ok("✏️ PG" in str([b.text for r_ in _m.risposte[-1][1]["reply_markup"].inline_keyboard for b in r_])
   and "manca" not in _m.risposte[-1][0], "con G1 della giornata in corso e senza righe: l'editor coi bottoni, non «manca PG…»")

# ── /quintetti: una riga per squadra ──
m = Msg("/quintetti"); CTX.args = []; asyncio.run(Q.cmd_quintetti(upd(900, m), CTX))
tq = Q.testo_quintetti()
ok("<b>Alfa</b>: PG Ja Morant · SG Devin Booker · SF Mikal Bridges · PF Grant Williams · C Mark Williams" in tq
   and "<b>Beta</b>: PG — · SG —" in tq, f"/quintetti: una riga per squadra coi nomi interi\n{tq[:300]}")
ok("<b>Alfa</b>: PG Jalen Brunson" in Q.testo_quintetti(1), "/quintetti 1: la formazione congelata della giornata 1")
m = Msg("/quintetti 2"); CTX.args = ["2"]; asyncio.run(Q.cmd_quintetti(upd(900, m), CTX)); CTX.args = []
ok("non è ancora chiusa" in m.risposte[-1][0], "/quintetti N di una giornata non chiusa: rifiutato")
m = Msg("/quintetti"); asyncio.run(Q.cmd_quintetti(upd(101, m), CTX))
ok(m.risposte[-1][0] == "⛔ Solo admin.", "/quintetti solo admin")

# ── admin coi bottoni: quintetto (parte da quello attuale) e panchina di un'altra squadra ──
m = Msg("/quintetto_admin Alfa"); asyncio.run(Q.cmd_quintetto_admin(upd(900, m), CTX))
t, k = m.risposte[-1]
ok("(admin)" in t and "Ja Morant" in t and "q:c:team01:SG" in bottoni(k["reply_markup"])
   , "quintetto_admin senza righe: bottoni, parte dall'attuale")
premi(900, f"q:s:team01:PG:{gids['Walter Clayton Jr.']}")
ok(db.quintetto("team01")["PG"] == gids["Walter Clayton Jr."] and db.formazione(S, 1, "team01")["PG"] == gids["Walter Clayton Jr."],
   "admin coi bottoni a giornata in corso: aggiorna anche la formazione")
m = Msg("/panchina_admin Alfa"); asyncio.run(P.cmd_panchina_admin(upd(900, m), CTX))
ok("giornata 1" in m.risposte[-1][0] and "correzione (giornata chiusa)" in m.risposte[-1][0],
   "admin a giornata 1 in corso: /panchina_admin SQUADRA corregge la giornata 1, non la successiva " + m.risposte[-1][0][:80])
m = Msg("/build_panchina"); asyncio.run(P.cmd_build_panchina(upd(101, m), CTX))
ok("non accetto panchine" in m.risposte[-1][0] and "giornata 1 in corso" in m.risposte[-1][0],
   "GM a giornata 1 in corso: niente panchine per la giornata dopo (fino alle 6 del giorno in cui comincia) " + m.risposte[-1][0])
import comune as _CO
_blocco = _CO.panchine_bloccate; _CO.panchine_bloccate = lambda *a, **k: None       # come la mattina dopo
m = Msg("/panchina_admin Alfa"); asyncio.run(P.cmd_panchina_admin(upd(900, m), CTX))
t, k = m.risposte[-1]
bid = int(bottoni(k["reply_markup"])[0].split(":")[2])
ok("Panchina di Alfa" in t and db.bozza(bid)["fonte"] == "admin" and any(b.startswith(f"pb:b:{bid}:") for b in bottoni(k["reply_markup"])),
   "panchina_admin senza righe: builder per conto della squadra")
db.chiudi_bozza(bid)
m = Msg("/panchina_admin Alfa\nJa Morant\nBarlow\nClifford\nLooney\nBrunson"); asyncio.run(P.cmd_panchina_admin(upd(900, m), CTX))
bid = int(bottoni(m.risposte[-1][1]["reply_markup"])[-2].split(":")[2])
BOT.mandati.clear(); premi(900, f"pb:ok:{bid}")
ok(any(x["chat_id"] == -500 and "✍️ admin U900 · 🔁 ultima modifica" in x["text"] for x in BOT.mandati),
   "panchina inserita da un admin: sul canale quale admin")
# le prove che seguono mandano panchine con la giornata 1 in corso: si resta «la mattina dopo»

# ── soprannomi: vederli, cancellarli, seguono il giocatore ──
m = Msg("/soprannomi"); CTX.args = []; asyncio.run(SO.cmd_soprannomi(upd(101, m), CTX))
t, k = m.risposte[-1]
ok("<b>Josh Hart</b>: " in t and "«lo sceriffo»" in t and "«ja the sniper morant»" in t, "/soprannomi: quelli della squadra, per giocatore")
id_sc = next(a["id"] for a in db.alias_giocatori([gids["Josh Hart"]]) if a["alias"] == "lo sceriffo")
ok(f"so:d:team01:{id_sc}:0" in bottoni(k["reply_markup"]), "un bottone 🗑 per soprannome")
ok(any(b.text == "🗑 lo sceriffo → Josh Hart" for riga in k["reply_markup"].inline_keyboard for b in riga),
   "nel bottone il nome intero del giocatore (con gli omonimi il cognome non basta)")
ok(premi(102, f"so:d:team01:{id_sc}:0").risposte == ["Non è la tua squadra."], "il GM di un'altra squadra non cancella")
m = Msg("/soprannomi Alfa"); CTX.args = ["Alfa"]; asyncio.run(SO.cmd_soprannomi(upd(102, m), CTX)); CTX.args = []
ok("«lo sceriffo»" in m.risposte[-1][0] and m.risposte[-1][1]["reply_markup"] is None and "🗑" not in m.risposte[-1][0],
   "un GM guarda i soprannomi di un'altra squadra: solo testo, niente bottoni")
ok(SO.somiglianza("lo sceriffo", "Josh Hart") < SO.SOGLIA_SOSPETTI and SO.somiglianza("hart", "Josh Hart") == 1
   and SO.somiglianza("sga", "Shai Gilgeous-Alexander") == 1 and SO.somiglianza("ja morant", "Ja Morant") == 1,
   "somiglianza: «lo sceriffo» sospetto, cognome e iniziali no")
class MsgD(Msg):
    async def reply_document(s, document, filename, **k): s.risposte.append((document.read().decode(), {"file": filename}))
m = MsgD("/soprannomi tutti"); CTX.args = ["tutti"]; asyncio.run(SO.cmd_soprannomi(upd(900, m), CTX))
testo_t, file_t = m.risposte[0][0], m.risposte[1]
ok("sospetti" in testo_t and "«lo sceriffo» → Josh Hart" in testo_t and file_t[1]["file"] == "soprannomi.md"
   and file_t[0].index("lo sceriffo") < file_t[0].index("ja the sniper morant") if "ja the sniper morant" in file_t[0] else False,
   "/soprannomi tutti (admin): i sospetti nel messaggio, tutti nel file dal più sospetto")
m = Msg("/soprannomi tutti"); asyncio.run(SO.cmd_soprannomi(upd(101, m), CTX)); CTX.args = []
ok("solo per gli admin" in m.risposte[-1][0], "/soprannomi tutti: solo admin")
BOT.mandati.clear()
u = upd(101, cb=f"so:d:team01:{id_sc}:0"); asyncio.run(SO.cb_soprannomi(u, CTX))
ok("lo sceriffo" not in db.alias("team01") and "«lo sceriffo»" not in u.callback_query.testi[-1][0]
   and any(x["chat_id"] == -3 and "cancellato" in x["text"] for x in BOT.mandati), "cancellato: sparisce, riga sul log")
# Josh Hart (in panchina G2) e Mikal Bridges (SF nel quintetto e nella formazione G1 in corso) passano a Beta
db.salva_panchina(S, 2, "team01", None, [{"giocatore_id": gids[n], "testo": n} for n in CINQUE])
db.q("UPDATE contratti SET team_id = 'team02' WHERE giocatore_id = ANY(%s) AND attivo", ([gids["Josh Hart"], gids["Mikal Bridges"]],))
ok(db.alias("team02", [x["id"] for x in db.roster("team02", S)]).get("lo sceriffo bis") == gids["Josh Hart"]
   and "lo sceriffo bis" not in db.alias("team01", [x["id"] for x in db.roster("team01", S)]),
   "dopo la trade il soprannome vale per la squadra nuova, non più per la vecchia")
m = Msg("/soprannomi"); asyncio.run(SO.cmd_soprannomi(upd(102, m), CTX))
ok("«lo sceriffo bis» <i>(da Alfa)</i>" in m.risposte[-1][0], "/soprannomi della squadra nuova: ereditati, con chi li ha scritti")
BOT.mandati.clear()
n_avvisi = asyncio.run(CE.controlla(BOT))
gm = [x for x in BOT.mandati if x["chat_id"] == 101]
hart = next((x["text"] for x in gm if "Josh Hart" in x["text"]), "")
bridges = next((x["text"] for x in gm if "Mikal Bridges" in x["text"]), "")
ok(n_avvisi == 2 and "ora è di <b>Beta</b>" in hart and "panchina della giornata 2: rimandala" in hart,
   f"cessione di un panchinaro: avviso al GM, va rimandata la panchina\n{hart}")
ok("quintetto del bot (SF)" in bridges and "favore agli admin" in bridges and "giornata 1 in corso (SF)" in bridges,
   f"cessione di un titolare: quintetto (non obbligatorio) e giornata in corso\n{bridges}")
ok(any(x["chat_id"] == 111 for x in BOT.mandati) and sum(x["chat_id"] == -3 and "Cessione" in x["text"] for x in BOT.mandati) == 2,
   "a tutti i GM della squadra e sul canale log")
BOT.mandati.clear()
ok(asyncio.run(CE.controlla(BOT)) == 0 and not BOT.mandati, "avvisati una volta sola")
db.q("UPDATE contratti SET team_id = 'team01' WHERE giocatore_id = %s AND attivo", (gids["Josh Hart"],))
asyncio.run(CE.controlla(BOT))
db.q("UPDATE contratti SET team_id = 'team02' WHERE giocatore_id = %s AND attivo", (gids["Josh Hart"],))
ok(asyncio.run(CE.controlla(BOT)) == 1, "tornato e ceduto di nuovo: nuovo avviso")
m = Msg(); asyncio.run(P.cmd_panchina(upd(101, m), CTX))
ok("Josh Hart (non più in squadra: rimandala)" in m.risposte[-1][0], "/panchina: il ceduto si vede")
db.q("UPDATE contratti SET team_id = 'team01' WHERE giocatore_id = ANY(%s) AND attivo", ([gids["Josh Hart"], gids["Mikal Bridges"]],))

# ── righe duplicate ("prova" ×5): rifiutata ──
m = manda(101, "prova\nprova\nprova\nprova\nprova")
ok("Righe duplicate: «prova»" in m.risposte[0][0] and "pb:" not in str(m.risposte[0][1]), "righe uguali: rifiutata, righe duplicate")
m = manda(101, "Morant\nBarlow\nClifford\nlo Sceriffo!\nLO SCERIFFO")
ok("Righe duplicate" in m.risposte[0][0], "duplicate anche con maiuscole e punteggiatura diverse")

# ── canale cambiato: /ripubblica_panchine ──
import json as _json
G = _json.load(open(config.GLOBALS_PATH)); G["canale_panchinari_id"] = -600; _json.dump(G, open(config.GLOBALS_PATH, "w"))
P.PAUSA_CANALE = 0
BOT.mandati.clear()
m = Msg("/ripubblica_panchine"); CTX.args = []; asyncio.run(P.cmd_ripubblica_panchine(upd(900, m), CTX))
nuovo = [x for x in BOT.mandati if x["chat_id"] == -600]
p2 = db.panchina(S, 2, "team01")
ok(len(nuovo) == len(db.panchine(S, 2)) >= 1 and "<b>Alfa</b> · giornata 2" in nuovo[0]["text"] and "✍️ " in nuovo[0]["text"]
   and p2["messaggio_canale"] == nuovo[0]["id"] and p2["canale_id"] == -600,
   "ripubblicate sul canale nuovo, con chi e quando; il bot si segna i messaggi nuovi")
ok(any(x["chat_id"] == 900 and "Ripubblicate" in x["text"] for x in BOT.mandati), "a fine lavoro avvisa chi l'ha chiesto")
m = manda(101, "Ja Morant\nBarlow\nClifford\nLooney\nBrunson")
bid = int(bottoni(m.risposte[0][1]["reply_markup"])[-2].split(":")[2])
BOT.mandati.clear(); premi(101, f"pb:ok:{bid}")
ok([x.get("modifica") for x in BOT.mandati if x["chat_id"] in (-500, -600)] == [True]
   and any(x["chat_id"] == -600 and x["id"] == p2["messaggio_canale"] for x in BOT.mandati),
   "dopo: la modifica va sul messaggio del canale nuovo, il vecchio canale non si tocca")
db.q("UPDATE ipa_panchine SET canale_id = -500 WHERE team_id = 'team01'")       # come se fosse del canale vecchio
m = manda(101, "Ja Morant\nBarlow\nClifford\nLooney\nHart")
bid = int(bottoni(m.risposte[0][1]["reply_markup"])[-2].split(":")[2])
BOT.mandati.clear(); premi(101, f"pb:ok:{bid}")
ok([(x["chat_id"], bool(x.get("modifica"))) for x in BOT.mandati if x["chat_id"] in (-500, -600)] == [(-600, False)],
   "messaggio di un altro canale: non si modifica (potrebbe essere di un'altra squadra), se ne manda uno nuovo")
G["canale_panchinari_id"] = -500; _json.dump(G, open(config.GLOBALS_PATH, "w"))

# ── scadenza passata mentre si conferma ──
m = manda(101, "Ja Morant\nBarlow\nClayton\nClifford\nLooney")
bid = int(bottoni(m.risposte[0][1]["reply_markup"])[0].split(":")[2])
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE numero = 2", (datetime.now(timezone.utc) - timedelta(minutes=1),))
qb = premi(101, f"pb:ok:{bid}")
ok(qb.risposte[-1] == "La scadenza è passata." and "non è stata pubblicata" in qb.testi[-1][0], "scaduta durante la conferma: non si pubblica")

# ── chiusura: i ruoli dei panchinari si congelano; correzione a giornata chiusa ──
asyncio.run(Q.job_giornate(CTX))
p2 = db.panchina(S, 2, "team01")
ok(db.stato_giornata(S, 2)["chiusa"] and p2 and all(r.get("ruolo") for r in p2["righe"]),
   f"alla scadenza i ruoli dei panchinari si scrivono nella panchina (per la FADD) {p2['righe'] if p2 else ''}")
m = Msg("/panchina_admin Alfa G2\nJa Morant\nBarlow\nClifford\nLooney\nBrunson"); asyncio.run(P.cmd_panchina_admin(upd(900, m), CTX))
t, k = m.risposte[-1]
bid = int(bottoni(k["reply_markup"])[-2].split(":")[2])
ok("correzione (giornata chiusa)" in t and f"pb:ok:{bid}" in bottoni(k["reply_markup"]), "/panchina_admin SQUADRA G2: correzione di una giornata chiusa")
BOT.mandati.clear(); qb = premi(900, f"pb:ok:{bid}")
p2 = db.panchina(S, 2, "team01")
ok([r["giocatore_id"] for r in p2["righe"]][-1] == gids["Jalen Brunson"] and all(r.get("ruolo") for r in p2["righe"])
   and "/ricalcola 2" in qb.testi[-1][0] and any("/ricalcola 2" in x["text"] for x in BOT.mandati if x["chat_id"] == -3),
   "correzione pubblicata anche a scadenza passata, ruoli congelati, invito a ricalcolare (al GM e sul log)")
m = Msg("/panchina_admin Alfa G9\nJa Morant\nBarlow\nClifford\nLooney\nBrunson"); asyncio.run(P.cmd_panchina_admin(upd(900, m), CTX))
ok("non trovata" in m.risposte[-1][0] or "non è ancora chiusa" in m.risposte[-1][0], "G di una giornata non chiusa o inesistente: rifiutato")

# ── conferma dell'admin e controllo delle formazioni dopo la scadenza ──
aperta_g = {"numero": 3, "prima_partita": datetime.now(timezone.utc) + timedelta(days=3)}
ok(f"q:ok:team02:3" in bottoni(Q._tastiera("team02", aperta_g, admin=True)), "l'admin può confermare il quintetto di una squadra")
_gc = Q.giornata_da_controllare()
NC = _gc["numero"] if _gc else None
ok(NC and db.stato_giornata(S, NC)["chiusa"] and Q.giornata_in_corso()["numero"] == NC, "da controllare: la giornata in corso chiusa")
ok(f"q:ck:team02:{NC}" in bottoni(Q._tastiera("team02", None, admin=True)), "editor admin: ☑️ Segna controllata")
m = Msg(); u = upd(900, m); asyncio.run(Q.cmd_controlli(u, CTX))
t, k = m.risposte[-1]
ok(f"Controllo formazioni G{NC}" in t and "⬜ <b>Beta</b>" in t and f"ck:{NC}:team02" in bottoni(k["reply_markup"]), "/controlli: le formazioni da controllare")
uq = upd(101, cb=f"ck:{NC}:team02"); asyncio.run(Q.cb_controlli(uq, CTX))
ok(uq.callback_query.risposte == ["Solo admin."] and "team02" not in db.controlli(S, NC), "controllo: solo admin")
uq = upd(900, cb=f"ck:{NC}:team02"); uq.effective_user.first_name = "Luca"; asyncio.run(Q.cb_controlli(uq, CTX))
c2 = db.controlli(S, NC).get("team02")
ok(c2 and c2["da_nome"] == "Luca" and "☑️ <b>Beta</b>" in uq.callback_query.testi[-1][0],
   "tocco: Beta controllata da Luca")
uq = upd(900, cb=f"ck:{NC}:team02"); asyncio.run(Q.cb_controlli(uq, CTX))
ok("team02" not in db.controlli(S, NC), "secondo tocco: tolto")
m = Msg("/quintetto_admin Alfa G2\nJalen Brunson\nBooker\nBridges\nGrant Williams\nMark Williams"); asyncio.run(Q.cmd_quintetto_admin(upd(900, m), CTX))
ok("team01" in db.controlli(S, 2) and "controllata" in m.risposte[-1][0], "correzione della formazione G2: controllata da sola")
m = Msg(); u = upd(900, m); CTX.args = ["2"]; asyncio.run(Q.cmd_stato(u, CTX)); CTX.args = []
ok(any("☑️ · Alfa" in x["text"] for x in BOT.mandati[-3:]) or "☑️ · Alfa" in str(m.risposte), "/stato 2: ☑️ accanto a chi è controllato")

# ── v24: il quintetto si chiude dopo la conferma, avvisi per l'admin, /stato in tabella, panchine a giornata in corso ──
import comune as CO
from datetime import datetime as _dt, time as _tm
# a questo punto le giornate 1 e 2 sono chiuse: una giornata 3 aperta
giornata(3, CO.adesso() + timedelta(days=2), d1 + timedelta(days=4), d1 + timedelta(days=5), [])
qc = premi(101, "q:ok:team01:3")
ok(qc.testi and "Quintetto confermato per la giornata 3" in qc.testi[-1][0] and not qc.testi[-1][1].get("reply_markup")
   and "/quintetto" in qc.testi[-1][0], "Confermo: il menu si chiude, resta il riepilogo con /quintetto per cambiarlo")
ok("in qualsiasi momento con /quintetto" in Q.promemoria(config.squadra("team01"), db.giornata(S, 3))[0],
   "promemoria: si può cambiare in qualsiasi momento con /quintetto")
ok(f"q:x:team01" in bottoni(Q._tastiera("team01", db.giornata(S, 3))), "editor del quintetto: ✖️ Chiudi")
qx = premi(101, "q:x:team01")
ok(qx.testi and not qx.testi[-1][1].get("reply_markup") and "/quintetto" in qx.testi[-1][0], "✖️ Chiudi: senza bottoni, dice come riaprirlo")
tit = db.quintetto("team01")["SG"]
db.salva_panchina(S, 3, "team01", None, [{"giocatore_id": tit, "testo": "x"}])
nome_t = db.nomi_giocatori([tit])[tit]
gm_t, adm_t, br_t = (Q.incompatibilita("team01"), Q.incompatibilita("team01", admin=True),
                     Q.incompatibilita("team01", breve=True))
ok(any("se vuoi aggiorna il quintetto" in x for x in gm_t), "al GM: se vuoi aggiorna il quintetto")
ok(any(f"avvisa il GM di togliere {nome_t} dalla panchina" in x and "entro la scadenza" in x for x in adm_t)
   and not any("se vuoi aggiorna" in x for x in adm_t), "all'admin: avvisa il GM di cambiare la panchina entro la scadenza " + str(adm_t))
ok(any(f"{nome_t} titolare (SG) e in panchina G3" == x for x in br_t), "negli elenchi: la versione breve")
_gc = Q.giornata_in_corso(S)
db.salva_panchina(S, _gc["numero"], "team01", None, [{"giocatore_id": tit, "testo": "x"}])
adm_t = Q.incompatibilita("team01", admin=True)
ok(any("già iniziata" in x and "penalità" in x for x in adm_t), "giornata già iniziata: è un errore, gli altri scalano, penalità agli admin")
mdx = Q.md_stato(db.giornata(S, 3))
ok("| Squadra | Quintetto | Panchina | Problemi |" in mdx and "| Alfa |" in mdx and "in panchina G3" in mdx, "/stato in Markdown: tabella")
m = Msg("/stato"); CTX.args = []
docs = []
async def _doc(**k): docs.append(k)
BOT.send_document = _doc
asyncio.run(Q.cmd_stato(upd(900, m), CTX))
ok(docs and docs[-1]["filename"].startswith("stato-G3-") and docs[-1]["filename"].endswith(".md"), "/stato manda anche il file .md")
g1 = dict(db.giornata(S, 1))
_vere = CO.db.giornate; CO.db.giornate = lambda *_a, **_k: [g1]
fine = _dt.combine(g1["al"] + timedelta(days=1), _tm(6, 0), tzinfo=CO.ROMA)
ok(_blocco(S, fine - timedelta(minutes=1))["numero"] == 1 and _blocco(S, fine + timedelta(minutes=1)) is None
   and _blocco(S, CO.scadenza(g1) - timedelta(minutes=1)) is None,
   "panchine bloccate dalla scadenza alle 6 del giorno dopo l'ultimo giorno NBA della giornata")
CO.db.giornate = _vere

# ── v26: /edit — ordine, cambi e soprannomi della panchina già mandata ──
_vb = CO.panchine_bloccate; CO.panchine_bloccate = lambda *a, **k: None
_p5 = ["Dominick Barlow", "Walter Clayton Jr.", "Nique Clifford", "Kevon Looney", "Josh Hart"]
_p5 = [n for n in _p5 if db.q("SELECT 1 FROM contratti WHERE giocatore_id=%s AND team_id='team01'", (gids[n],), one=True)]
_p5 += [n for n in ["Grant Williams", "Mark Williams", "Jalen Brunson", "Devin Booker"] if n not in _p5][:5 - len(_p5)]
db.salva_panchina(S, 3, "team01", "Titolo", [{"giocatore_id": gids[n], "testo": ("Il Barlow" if i == 0 else n)}
                                             for i, n in enumerate(_p5)])
m = Msg("/edit"); CTX.args = []
asyncio.run(P.cmd_edit(upd(101, m), CTX))
t, k = m.risposte[-1]
bid = int(next(x for x in bottoni(k["reply_markup"]) if x.startswith("pb:ok:")).split(":")[2])
ok("🛠" in t and "1. Il Barlow → <b>" in t and all(f"pb:{a}:{bid}:0" in bottoni(k["reply_markup"]) for a in ("n", "su", "gi", "sw")),
   "/edit: la panchina mandata, ogni riga con ✏️ ⬆️ ⬇️ 🔄")
rig = lambda: P.db.bozza(bid)["dati"]["righe"]
ok(premi(101, f"pb:su:{bid}:0").risposte == ["È già il primo."], "⬆️ sul primo: niente")
premi(101, f"pb:gi:{bid}:0")
ok([r["scelto"] for r in rig()][:2] == [gids[_p5[1]], gids[_p5[0]]] and rig()[1]["testo"] == "Il Barlow", "⬇️: scende di uno, col suo soprannome")
qs = premi(101, f"pb:sw:{bid}:1")
bs = bottoni(qs.testi[-1][1]["reply_markup"])
fuori = next(n for n in NOMI_PROVA if n not in _p5 and db.q("SELECT 1 FROM contratti WHERE giocatore_id=%s AND team_id='team01'", (gids[n],), one=True))
ok(f"pb:sp:{bid}:1:{gids[_p5[3]]}" in bs and f"pb:sp:{bid}:1:{gids[fuori]}" in bs, "🔄: gli altri panchinari e chi non è in panchina")
premi(101, f"pb:sp:{bid}:1:{gids[_p5[3]]}")
ok(rig()[1]["scelto"] == gids[_p5[3]] and rig()[3]["scelto"] == gids[_p5[0]] and rig()[3]["testo"] == "Il Barlow",
   "🔄 con uno in panchina: si scambiano il posto, il soprannome segue il giocatore")
premi(101, f"pb:sp:{bid}:3:{gids[fuori]}")
ok(rig()[3]["scelto"] == gids[fuori] and rig()[3]["testo"] == fuori and gids[_p5[0]] not in [r["scelto"] for r in rig()],
   "🔄 con uno fuori: entra al suo posto, col nome vero")
qn = premi(101, f"pb:n:{bid}:0")
ok("Soprannome per" in qn.testi[-1][0] and f"pb:cn:{bid}" in bottoni(qn.testi[-1][1]["reply_markup"]), "✏️: chiede il soprannome")
mm = manda(101, "El Mago")
ok(rig()[0]["testo"] == "El Mago" and "🛠" in mm.risposte[-1][0], "il soprannome scritto torna all'editor")
premi(101, f"pb:n:{bid}:0"); premi(101, f"pb:cn:{bid}")
ok(rig()[0]["testo"] == P.db.nomi_giocatori([rig()[0]["scelto"]])[rig()[0]["scelto"]], "♻️ Nome vero")
premi(101, f"pb:n:{bid}:1"); premi(101, f"pb:cs:{bid}")
ok(P.db.bozza(bid)["dati"].get("cai_passo") is None and not P.db.bozza(bid)["dati"].get("cai_singolo"), "↩️ dal soprannome: niente cambia")
BOT.mandati.clear(); premi(101, f"pb:ok:{bid}")
pp = db.panchina(S, 3, "team01")
ok([r["giocatore_id"] for r in pp["righe"]] == [r["scelto"] for r in rig()] and pp["titolo"] == "Titolo"
   and any("🔁 ultima modifica" in x["text"] for x in BOT.mandati), "✅ Pubblica: salvata col titolo, sul canale come modifica")
m = Msg("/edit"); asyncio.run(P.cmd_edit(upd(102, m), CTX))
ok("non c'è ancora una panchina" in m.risposte[-1][0], "/edit senza panchina mandata: lo dice")
CO.panchine_bloccate = lambda *a, **k: db.giornata(S, 3)
m = Msg("/edit"); asyncio.run(P.cmd_edit(upd(101, m), CTX))
ok("🛠" not in m.risposte[-1][0], "/edit a giornata in corso: rifiutato")
# admin a giornata in corso (Luca, 20/10): /edit SQUADRA e /panchina_admin SQUADRA correggono quella in corso
_chiusa = db.stato_giornata(S, 3)["chiusa"]
if not _chiusa:
    db.q("INSERT INTO ipa_stato_giornata (stagione, giornata, chiusa) VALUES (%s, 3, NOW()) "
         "ON CONFLICT (stagione, giornata) DO UPDATE SET chiusa = NOW()", (S,))
m = Msg("/edit Alfa"); CTX.args = ["Alfa"]; asyncio.run(P.cmd_edit(upd(900, m), CTX)); CTX.args = []
ok("🛠" in m.risposte[-1][0] and "correzione (giornata chiusa)" in m.risposte[-1][0], "admin: /edit SQUADRA a giornata in corso corregge quella")
m = Msg("/panchina_admin Alfa"); asyncio.run(P.cmd_panchina_admin(upd(900, m), CTX))
ok("correzione (giornata chiusa)" in m.risposte[-1][0] and "non accetto" not in m.risposte[-1][0],
   "admin: /panchina_admin SQUADRA a giornata in corso apre la correzione")
m = Msg("/edit"); asyncio.run(P.cmd_edit(upd(101, m), CTX))
ok("non accetto panchine" in m.risposte[-1][0], "il GM resta bloccato")
# giornata in corso fino alle 6: il quintetto non lavora ancora per la giornata dopo (Luca, 20/10)
m = Msg("/quintetto"); asyncio.run(Q.cmd_quintetto(upd(101, m), CTX))
ok("giornata 3 in corso" in m.risposte[-1][0] and not m.risposte[-1][1].get("reply_markup"), "/quintetto a giornata in corso: niente bottoni, dice da quando")
ok(premi(101, "q:c:team01:PG").risposte and "in corso" in (premi(101, "q:c:team01:PG").risposte[-1] or ""), "bottoni vecchi del GM: bloccati")
_m = Msg("/quintetto_admin Alfa"); asyncio.run(Q.cmd_quintetto_admin(upd(900, _m), CTX))
_bs = [b.callback_data for r_ in _m.risposte[-1][1]["reply_markup"].inline_keyboard for b in r_]
ok(any(x.startswith("q:c:team01") for x in _bs) and not any(x.startswith("q:ok:") for x in _bs),
   "admin a giornata in corso: editor sì (vale per la formazione in corso), niente Conferma della giornata dopo")
CO.panchine_bloccate = _vb

# pulizia
ids = list(gids.values())
db.q("DELETE FROM cambi_ruolo WHERE giocatore_id = ANY(%s)", (ids,))
db.q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (ids,))
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (ids,))
db.q("TRUNCATE ipa_quintetto, ipa_alias, ipa_cessioni, ipa_panchine, ipa_bozze, ipa_conferme, ipa_formazioni, ipa_stato_giornata, ipa_controlli, "
     "lega_giornate, nba_tabellini, nba_partite, nba_atleti, nba_infortuni")
_ = date
