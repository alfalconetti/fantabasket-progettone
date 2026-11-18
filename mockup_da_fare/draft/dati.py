"""Dati finti del mockup del tabellone del draft (bozza del 18/11, in verticale, un'immagine per giro).
Uso: python3 dati.py → anteprima_2_colonne.png e anteprima_3_colonne.png"""
import json, os, sys, typst
QUI = os.path.dirname(os.path.abspath(__file__))
nomi = ["Tibur", "Pelicancer", "Brooklyn Bari", "Murgia Bulls", "Salento Suns", "Gargano Hawks", "Levante Lakers", "Trulli Thunder",
        "Molfetta Magic", "Adriatico Heat", "Taranto Twolves", "Lecce Kings", "Polignano Pistons", "Ostuni Nets", "Bitonto Bucks",
        "Monopoli Mavs", "Altamura Jazz", "Fasano Raptors", "Matera Grizzlies", "Barletta Celtics", "Trani Knicks", "Andria Spurs",
        "Foggia Rockets", "Brindisi Warriors"]
col = ["#C8102E", "#1B6FB8", "#2E7D32", "#B5179E", "#F57C00", "#00897B", "#5D4037", "#6A1B9A", "#0277BD", "#AD1457", "#455A64", "#827717",
       "#D84315", "#283593", "#00695C", "#8E24AA", "#1565C0", "#C62828", "#4E342E", "#2E7D32", "#EF6C00", "#37474F", "#6D4C41", "#0D47A1"]
# ordine del primo giro dopo lottery e penalità (indici nella lista)
ordine = [1, 4, 0, 3, 2, 5, 6, 8, 7, 9, 11, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
scambi = {2: 20, 7: 0, 15: 4, 21: 9}
sanz = {7: "↓1 per penalità (era 8ª)", 8: ""}
gioc = [("Marcus Delano", "PG · Duke"), ("Ilya Petrenko", "C · Real Madrid"), ("Jaylen Okafor", "SF · Kentucky"), ("Tre Whitfield", "PF · Arizona"),
        ("Sam Albright", "SG · Gonzaga"), ("Kofi Mensah", "C · Kansas")]
def scala(n):
    for a, b, v in ((1, 1, 12), (2, 3, 10), (4, 5, 8), (6, 10, 5), (11, 24, 3), (25, 30, 2), (31, 48, 1)):
        if a <= n <= b: return f"{v}M ×2"
def pick(n, i, fatte):
    di = scambi.get(i)
    st = "fatta" if n <= fatte else ("ora" if n == fatte + 1 else "dopo")
    g = gioc[n - 1] if st == "fatta" else ("", "")
    return {"n": n, "squadra": nomi[di] if di is not None else nomi[i], "colore": col[di] if di is not None else col[i],
            "via": nomi[i] if di is not None else "", "sanz": sanz.get(i, "") if n <= 24 else "", "stato": st, "gioc": g[0], "info": g[1], "scala": scala(n)}
fatte = 6
primo = [pick(k + 1, i, fatte) for k, i in enumerate(ordine)]
secondo = [pick(k + 25, i, fatte) for k, i in enumerate(ordine)]
ora = primo[fatte]
for p in primo + secondo:
    p["sigla"] = "".join(w[0] for w in p["squadra"].split()[:2]).upper()
base = {"anno": "2027", "note": "«via»: la pick era di quella squadra ed è stata scambiata. In basso a destra la rookie scale della pick (importo del primo anno × anni). Le 1st vanno firmate, se no il giocatore va free agent."}
dd = {"1": {**base, "giro": "Primo giro", "sotto": "6 scelte fatte su 24", "ora": {"pick": f"Pick {ora['n']}", "squadra": ora["squadra"], "scade": "sceglie entro le 21:40"}, "pick": primo},
      "2": {**base, "giro": "Secondo giro", "sotto": "dopo il primo giro · 0 scelte fatte su 24", "ora": None, "pick": secondo}}
for col in (2, 3):
    v = {**dd["1"], "col": col}
    open(os.path.join(QUI, f"anteprima_{col}_colonne.png"), "wb").write(typst.compile(os.path.join(QUI, "draft.typ"), root="/", format="png", ppi=170, font_paths=["/usr/share/fonts"], sys_inputs={"dati": json.dumps(v, ensure_ascii=False)}))
