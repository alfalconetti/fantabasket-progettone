import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.36.0: /archivia_calcolo, l'archivio del foglio di controllo del calcolo a fine stagione: solo dopo la finale,
anteprima e conferma, i tab copiati in un file nuovo e tolti, una volta per stagione; finché la stagione prima non è
archiviata i tab della nuova non si scrivono (non sovrascrivono «Calcolo G1» vecchio)."""
import asyncio, json, types
import db, config, foglio
import archivio_calcolo as AC
import playoff as PO
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db(); AC.migra(); PO.migra()
S = config.stagione()
db.q("TRUNCATE lega_calcoli, lega_archivio_calcolo, lega_playoff")
for n in (1, 2, 3):
    db.q("INSERT INTO lega_calcoli (stagione, giornata, stato, risultati) VALUES (%s, %s, 'convalidata', '[]')", (S, n))
ok(AC.stagione_da_archiviare() == S, "la stagione dei tab: quella coi calcoli non ancora archiviata")
t, kb = AC.anteprima(S)
ok(kb is None and "Non ancora" in t and "nessun tabellone" in t, "prima della fine dei playoff: niente bottone")
db.q("INSERT INTO lega_playoff (stagione, stato) VALUES (%s, 'bloccato')", (S,))
ok(AC.anteprima(S)[1] is None, "finale non convalidata: ancora no")
db.q("UPDATE lega_playoff SET campione = 'team01' WHERE stagione = %s", (S,))
t, kb = AC.anteprima(S)
ok(kb and f"arc:ok:{S}" in str([b.callback_data for r in kb.inline_keyboard for b in r]) and AC.nome_archivio(S) in t
   and "G1, G2, G3" in t, "dopo la finale: anteprima coi tab e il nome dell'archivio, bottone")

# la stagione dopo: finché la vecchia non è archiviata, i tab nuovi non si scrivono
S2 = str(int(S) + 1)
ok(AC.blocco_tab(S2) and "/archivia_calcolo" in AC.blocco_tab(S2) and AC.blocco_tab(S) is None,
   "stagione nuova con la vecchia non archiviata: il tab «Calcolo G1» non si scrive")
_g = json.load(open(config.GLOBALS_PATH))
json.dump({**_g, "stagione_corrente": S2}, open(config.GLOBALS_PATH, "w"))
r = asyncio.run(foglio.manda_gas("calcolo", {"action": "calcolo", "nome": "Calcolo G1", "righe": [[1]]}))
ok("archivia_calcolo" in (r.get("error") or ""), "e manda_gas lo rifiuta senza chiamare il gas")
json.dump(_g, open(config.GLOBALS_PATH, "w"))

# conferma col bottone: il gas copia e toglie; una volta sola
mandati = []
async def _finto(endpoint, payload, manda=None):
    mandati.append((endpoint, payload)); return {"ok": True, "copiati": 3, "tolti": 3, "url": "https://docs.google.com/x"}
_vero = foglio.manda_gas
foglio.manda_gas = _finto
class Q:
    def __init__(s, data, uid=900):
        s.data, s.alert, s.testo = data, None, None
        s.from_user = types.SimpleNamespace(id=uid, full_name="Admin")
    async def answer(s, t=None, show_alert=False): s.alert = t
    async def edit_message_text(s, t, **k): s.testo = t
class Bot:
    async def send_message(s, *a, **k): pass
def premi(data, uid=900):
    q = Q(data, uid); asyncio.run(AC.cb_archivio(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=Bot()))); return q
ok(premi(f"arc:ok:{S}", 101).alert == "Solo admin.", "solo admin")
q = premi(f"arc:ok:{S}")
ok(mandati and mandati[0][0] == "calcolo_archivia" and mandati[0][1]["azzera"] and mandati[0][1]["archivio"] == AC.nome_archivio(S)
   and "archiviato" in q.testo and "docs.google.com" in q.testo, "conferma: il gas archivia e azzera, il link all'archivio")
ok(db.q("SELECT tab, url FROM lega_archivio_calcolo WHERE stagione = %s", (S,), one=True) == {"tab": 3, "url": "https://docs.google.com/x"}
   and AC.stagione_da_archiviare() is None and AC.blocco_tab(S2) is None, "segnata: niente più da archiviare, la stagione nuova scrive")
ok("Non più valido" in (premi(f"arc:ok:{S}").alert or ""), "doppio tocco: una volta sola")
mandati.clear()
async def _errore(endpoint, payload, manda=None): return {"error": "Copiati 1 tab su 3"}
foglio.manda_gas = _errore
db.q("DELETE FROM lega_archivio_calcolo")
q = premi(f"arc:ok:{S}")
ok("non riuscito" in q.testo and AC.stagione_da_archiviare() == S, "errore del gas: non segnata, si può rifare")
foglio.manda_gas = _vero
db.q("TRUNCATE lega_calcoli, lega_archivio_calcolo, lega_playoff")
