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
db.q("TRUNCATE ipa_quintetto, ipa_alias, ipa_cessioni, ipa_panchine, ipa_bozze, ipa_conferme, ipa_formazioni, ipa_stato_giornata, "
     "lega_giornate, nba_tabellini, nba_partite, nba_atleti, nba_status")
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
qb = premi(101, f"q:s:team01:PG:{gids['Walter Clayton Jr.']}")
ok(db.quintetto("team01")["PG"] == gids["Walter Clayton Jr."] and db.conferme(S, 2)["team01"]["stato"] == "modificato",
   "quintetto cambiato dal GM: segnato come modificato")
ok(premi(101, f"q:s:team01:PG:{gids['Devin Booker']}").risposte[-1].startswith("Non è un giocatore di quel ruolo"), "ruolo sbagliato rifiutato")
premi(101, "q:ok:team01:2")
ok(premi(102, "q:ok:team01:2").risposte[-1] == "Non è la tua squadra.", "il GM di un'altra squadra non tocca il quintetto")
ok(db.conferme(S, 2)["team01"]["stato"] == "confermato", "Confermo dal promemoria")
ok(premi(101, "q:ok:team01:1").risposte[-1] == "La scadenza di questa giornata è passata.", "bottone di una giornata scaduta: rifiutato")

# ── stato ESPN (nba_status di loucabot) nei builder, nell'anteprima e nel quintetto ──
db.q("INSERT INTO nba_status (atleta, nome, squadra, stato) VALUES (%s, 'Kevon Looney', 'NOP', 'Out'), (%s, 'Devin Booker', 'PHX', 'Day-To-Day')",
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
   and not any(b.startswith("q:ok") for b in bottoni(k["reply_markup"])), "quintetto_admin senza righe: bottoni, parte dall'attuale")
premi(900, f"q:s:team01:PG:{gids['Walter Clayton Jr.']}")
ok(db.quintetto("team01")["PG"] == gids["Walter Clayton Jr."] and db.formazione(S, 1, "team01")["PG"] == gids["Walter Clayton Jr."],
   "admin coi bottoni a giornata in corso: aggiorna anche la formazione")
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

# pulizia
ids = list(gids.values())
db.q("DELETE FROM cambi_ruolo WHERE giocatore_id = ANY(%s)", (ids,))
db.q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (ids,))
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (ids,))
db.q("TRUNCATE ipa_quintetto, ipa_alias, ipa_cessioni, ipa_panchine, ipa_bozze, ipa_conferme, ipa_formazioni, ipa_stato_giornata, "
     "lega_giornate, nba_tabellini, nba_partite, nba_atleti, nba_status")
_ = date
