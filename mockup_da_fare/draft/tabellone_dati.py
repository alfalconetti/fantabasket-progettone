import json, typst
sq = [("Tibur Eagles", "Andrea", "#1B5E20"), ("Pelicancer", "Leo", "#1B6FB8"), ("Brooklyn Bari", "Brownie", "#2E7D32"), ("Murgia Bulls", "Matteo", "#B5179E"),
      ("Salento Suns", "Geva", "#F57C00"), ("Gargano Hawks", "Henry", "#00897B"), ("Levante Lakers", "GobKor", "#5D4037"), ("Trulli Thunder", "MarcG", "#6A1B9A"),
      ("Molfetta Magic", "Derial", "#0277BD"), ("Adriatico Heat", "Kolera", "#AD1457"), ("Taranto Twolves", "Alan", "#455A64"), ("Lecce Kings", "Birra", "#827717"),
      ("Polignano Pistons", "Calamo", "#D84315"), ("Ostuni Nets", "A&D", "#283593"), ("Bitonto Bucks", "Erminio", "#00695C"), ("Monopoli Mavs", "Mathias", "#8E24AA"),
      ("Altamura Jazz", "Luca", "#1565C0"), ("Fasano Raptors", "Delfino", "#C62828"), ("Matera Grizzlies", "Enzo", "#4E342E"), ("Barletta Celtics", "Antonio", "#2E7D32"),
      ("Trani Knicks", "Diego", "#EF6C00"), ("Andria Spurs", "Pedro Leon", "#37474F"), ("Foggia Rockets", "Flavio", "#6D4C41"), ("Brindisi Warriors", "Paris", "#0D47A1")]
gioc = ["Cam Boozer", "AJ Dybantsa", "Caleb Wilson", "Darryn Peterson", "Keaton Wagler", "Darius Acuff Jr.", "Mikel Brown Jr.", "Kingston Flemings",
        "Yaxel Lendeborg", "Brayden Burries", "Nate Ament", "Morez Johnson Jr.", "Aday Mara", "Hannes Steinbach", "Allen Graves", "Ebuka Okorie",
        "Bennett Stirtz", "Labaron Philon Jr.", "Daylin Swain", "Karim Lopez", "Christian Anderson Jr.", "Jayden Quantaince", "Cameron Carr", "Chris Cenac Jr."]
# (chi sceglie, di chi era, sanzione, protezione)
riga = [(0, None, "", ""), (1, None, "", "protetta 1-4"), (2, None, "", ""), (3, None, "", ""), (4, 5, "", ""), (0, None, "", ""), (6, None, "", ""),
        (7, None, "", ""), (0, 8, "", ""), (8, None, "", ""), (9, None, "", ""), (10, 11, "", ""), (12, None, "−1 per penalità (era 12ª)", ""),
        (13, None, "−1 per penalità (era 13ª)", ""), (14, None, "", ""), (15, 16, "", ""), (6, 17, "", ""), (19, 15, "", ""), (18, None, "−1 per penalità (era 18ª)", ""),
        (19, 20, "", ""), (10, None, "", ""), (19, None, "", ""), (21, 22, "", ""), (23, 21, "", "")]
def scala(n):
    for a, b, v in ((1, 1, 12), (2, 3, 10), (4, 5, 8), (6, 10, 5), (11, 24, 3)):
        if a <= n <= b: return f"firmato {v}M ×2"
def build(fatte):
    out = []
    for k, (i, da, sz, pr) in enumerate(riga):
        n = k + 1
        st = "fatta" if n <= fatte else ("ora" if n == fatte + 1 else "dopo")
        t = sq[i]
        out.append({"n": n, "squadra": t[0], "gm": t[1], "colore": t[2], "via": sq[da][0] if da is not None else "", "sanz": sz, "prot": pr,
                    "stato": st, "gioc": gioc[k] if st == "fatta" else "", "scala": scala(n) if st == "fatta" else scala(n).replace("firmato ", "scala "),
                    "sigla": "".join(w[0] for w in t[0].split()[:2]).upper()})
    return out
note = "«via»: la pick era di quella squadra ed è stata scambiata · 🛡 la protezione è scattata e la pick è rimasta a chi l'aveva ceduta · in rosso le discese per le penalità · le 1st si firmano alla rookie scale della posizione, le 2nd diventano diritti"
for nome, fatte, ora in (("corso", 6, {"pick": "Pick 7", "squadra": "Levante Lakers", "stato": "GM GobKor · nome da approvare dagli admin"}), ("fine", 24, None)):
    d = {"anno": "2026", "giro": "Primo giro", "sotto": f"{min(fatte, 24)} scelte fatte su 24", "ora": ora, "pick": build(fatte), "note": note, "col": 2}
    open(f"tab_{nome}.png", "wb").write(typst.compile("tabellone.typ", root="/", format="png", ppi=150, sys_inputs={"dati": json.dumps(d, ensure_ascii=False)}))
