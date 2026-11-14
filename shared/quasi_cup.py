"""
Quasi NBA Cup (v7.9.0, Luca 14/11): la coppa d'inizio stagione, dentro il campionato.

Regole (decise con Luca il 14/11):
- qualificazione: le giornate dal 30/10 al 27/11 (anche quella a cavallo del 27; date in settings.json, v7.9.1); per ogni squadra conta il suo
  miglior punteggio di giornata (i punti regolamentari dei risultati convalidati: bonus casa compreso, senza
  supplementari). Passano le prime 4; a pari miglior punteggio conta il secondo, poi il terzo, e così via;
- Q1, semifinali: nella prima giornata che inizia dopo il 27/11, 1ª–4ª e 2ª–3ª; Q2, finale: nella giornata dopo.
  Si giocano come una partita normale (risultati.calcola + calcolo.esito): in casa la meglio classificata, col
  bonus casa della regular season, 5 punti di scarto, supplementari con la panchina, pari → vince chi è fuori casa.
  Formazioni: quelle della giornata G della stessa settimana. I punti della G non cambiano;
- premio: un cambio ruolo in più, di un tipo apposta ('cup', uno a stagione: bot principale, handlers/cambi_ruolo.py),
  e la vittoria di ogni spareggio per il seed in regular season (per quando ci saranno i playoff: MIGRATION).

Codici delle partite: G la regular season (il default), Q la Cup (Q1, Q2), P i playoff (quando ci saranno).

Qui i dati e l'immagine, in comune tra loucabot (calcolo, live, convalida: cup.py) e il bot principale (/quasi_cup).
Tabelle (le crea crea(), chiamata da tutti e due i bot all'avvio):
- lega_cup: i risultati convalidati di Q1 e Q2 (stessa forma di lega_risultati, con `turno` al posto della giornata);
- lega_cup_live: il messaggio della Cup sul canale principale per ogni turno e gli ultimi risultati live.
"""
import json
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from shared import lettura as L
from shared.numeri import testo as tp

ROMA = ZoneInfo("Europe/Rome")
# le date della qualificazione sono in settings.json (cup_inizio_giorno/mese, cup_fine_giorno/mese: /impostazioni),
# nell'anno in cui inizia la stagione; default 30/10 – 27/11 (v7.9.1)
QUALIFICATE = 4                # il tabellone è semifinali + finale: sempre 4
IN_CLASSIFICA = 8              # le squadre nell'immagine (Luca, 14/11)
TURNI = {1: "Semifinali", 2: "Finale"}
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quasi_cup.typ")


def crea(q) -> None:
    q("""CREATE TABLE IF NOT EXISTS lega_cup (
            stagione         TEXT NOT NULL,
            turno            INT  NOT NULL,                     -- 1 semifinali (Q1), 2 finale (Q2)
            giornata         INT  NOT NULL,                     -- la giornata G della stessa settimana
            casa             TEXT NOT NULL,
            trasferta        TEXT NOT NULL,
            punti_casa       NUMERIC(7,2),                      -- regolamentari, bonus casa compreso
            punti_trasferta  NUMERIC(7,2),
            supp_casa        NUMERIC(7,2),
            supp_trasferta   NUMERIC(7,2),
            vince            TEXT,                              -- casa / trasferta
            convalidato      TIMESTAMPTZ,
            PRIMARY KEY (stagione, turno, casa))""")
    q("""CREATE TABLE IF NOT EXISTS lega_cup_live (
            stagione    TEXT NOT NULL,
            turno       INT  NOT NULL,
            chat_id     BIGINT,
            message_id  BIGINT,
            risultati   JSONB,                                  -- gli ultimi del live (stessa forma di lega_cup)
            aggiornato  TIMESTAMPTZ,
            chiuso      TIMESTAMPTZ,                            -- turno convalidato: il messaggio è definitivo
            PRIMARY KEY (stagione, turno))""")


def finestra(s: str) -> tuple[date, date]:
    from shared import regole
    return regole.cup_qualificazione(int(s))


# ── calendario ─────────────────────────────────────────────────────────────────

def giornate(s: str) -> dict:
    """{qual: [giornate della qualificazione], q1: giornata delle semifinali | None, q2: della finale | None}."""
    dal, al = finestra(s)
    gg = L.q("SELECT * FROM lega_giornate WHERE stagione = %s AND tipo = 'regular' ORDER BY numero", (s,), many=True) or []
    qual = [g for g in gg if g["dal"] <= al and g["al"] >= dal]
    dopo = [g for g in gg if g["dal"] > al]
    return {"qual": qual, "q1": dopo[0] if dopo else None, "q2": dopo[1] if len(dopo) > 1 else None}


def turno_di(s: str, n: int, info: dict | None = None) -> int | None:
    """Il turno della Cup (1, 2) che si gioca nella giornata G n, se c'è."""
    info = info or giornate(s)
    for t, k in ((1, "q1"), (2, "q2")):
        if info[k] and info[k]["numero"] == n:
            return t
    return None


# ── qualificazione ─────────────────────────────────────────────────────────────

def classifica(s: str, info: dict | None = None) -> list[dict]:
    """Tutte le squadre, in ordine: [{team, punteggi: [(punti, giornata), …] dal più alto}]. Solo i risultati convalidati."""
    info = info or giornate(s)
    nn = [g["numero"] for g in info["qual"]]
    per = {t["id"]: [] for t in L.squadre()}
    if nn:
        for r in L.q("""SELECT giornata, casa, trasferta, punti_casa, punti_trasferta FROM lega_risultati
                        WHERE stagione = %s AND giornata = ANY(%s) AND convalidato IS NOT NULL""", (s, nn), many=True) or []:
            for t, p in ((r["casa"], r["punti_casa"]), (r["trasferta"], r["punti_trasferta"])):
                if p is not None:
                    per.setdefault(t, []).append((float(p), r["giornata"]))
    lungo = max([len(v) for v in per.values()] + [0])
    ordine = list(per)

    def chiave(t):
        pp = sorted((p for p, _ in per[t]), reverse=True)
        return [-p for p in pp] + [float("inf")] * (lungo - len(pp)) + [ordine.index(t)]
    return [{"team": t, "punteggi": sorted(per[t], key=lambda x: (-x[0], x[1]))} for t in sorted(per, key=chiave)]


def convalidate(s: str, nn: list[int]) -> set[int]:
    if not nn:
        return set()
    return {r["giornata"] for r in L.q("SELECT DISTINCT giornata FROM lega_risultati WHERE stagione = %s AND giornata = ANY(%s) "
                                       "AND convalidato IS NOT NULL", (s, nn), many=True) or []}


def qualificazione_chiusa(s: str, info: dict | None = None) -> bool:
    """Tutte le giornate della qualificazione convalidate (e finite)."""
    info = info or giornate(s)
    nn = [g["numero"] for g in info["qual"]]
    return bool(nn) and convalidate(s, nn) == set(nn)


# ── turni ──────────────────────────────────────────────────────────────────────

def risultati_cup(s: str, turno: int) -> list[dict]:
    return L.q("SELECT * FROM lega_cup WHERE stagione = %s AND turno = %s AND convalidato IS NOT NULL ORDER BY punti_casa DESC",
               (s, turno), many=True) or []


def vincente(r: dict) -> str:
    return r["casa"] if r["vince"] == "casa" else r["trasferta"]


def abbinamenti(s: str, turno: int, info: dict | None = None) -> list[tuple[str, str]]:
    """[(casa, trasferta)] del turno, in casa la meglio classificata. Semifinali: dalla classifica (quelle salvate se il
    turno è già convalidato); finale: le vincenti delle semifinali convalidate, se no nessuna."""
    info = info or giornate(s)
    salvati = risultati_cup(s, turno)
    if salvati:
        return _ordina_sf([(r["casa"], r["trasferta"]) for r in salvati], s, info)
    cl = [x["team"] for x in classifica(s, info)]
    if turno == 1:
        if len(cl) < QUALIFICATE:
            return []
        return [(cl[0], cl[3]), (cl[1], cl[2])]
    sf = risultati_cup(s, 1)
    if len(sf) < 2:
        return []
    a, b = sorted((vincente(r) for r in sf), key=cl.index)
    return [(a, b)]


def _ordina_sf(coppie: list[tuple[str, str]], s: str, info: dict) -> list[tuple[str, str]]:
    """La semifinale della prima classificata per prima (SF1)."""
    cl = [x["team"] for x in classifica(s, info)]
    return sorted(coppie, key=lambda c: min(cl.index(c[0]) if c[0] in cl else 99, cl.index(c[1]) if c[1] in cl else 99))


def live(s: str, turno: int) -> dict | None:
    r = L.q("SELECT * FROM lega_cup_live WHERE stagione = %s AND turno = %s", (s, turno), one=True)
    if r and isinstance(r.get("risultati"), str):
        r["risultati"] = json.loads(r["risultati"])
    return r


def campione(s: str) -> str | None:
    """La vincitrice della Cup della stagione (finale convalidata), se c'è."""
    f = risultati_cup(s, 2)
    return vincente(f[0]) if f else None


# ── immagine ───────────────────────────────────────────────────────────────────

def _sigla(nome: str) -> str:
    parole = [p for p in nome.replace("-", " ").split() if p[:1].isalnum()]
    return "".join(p[0] for p in parole[:2]).upper() or nome[:2].upper()


def _squadra(t: str) -> dict:
    from shared.rendimento import colore_squadra
    sq = L.squadra(t) or {"id": t, "nome": t}
    return {"id": t, "nome": sq.get("nome", t), "sigla": _sigla(sq.get("nome", t)), "colore": colore_squadra(sq), "logo": L.logo(t)}


def _quando(g: dict | None, turno: int) -> str:
    if not g:
        return f"Q{turno} · calendario da fare"
    return f"Q{turno} · G{g['numero']} · {g['dal']:%d/%m}–{g['al']:%d/%m}"


def _righe_partita(coppia: tuple[str, str], seed: dict, ris: dict | None) -> list[dict]:
    out = []
    for lato, t in (("casa", coppia[0]), ("trasferta", coppia[1])):
        x = {**_squadra(t), "seed": f"{seed[t]}ª" if t in seed else "", "punti": "", "supp": "", "avanti": False}
        if ris:
            x["punti"] = tp(ris[f"punti_{lato}"])
            if ris.get(f"supp_{lato}") is not None:
                x["supp"] = f"+{tp(ris[f'supp_{lato}'])} supp."
            x["avanti"] = ris.get("vince") == lato
        out.append(x)
    return out


def dati(s: str, ora: datetime | None = None) -> dict:
    """Tutto quello che va nell'immagine, nella fase di adesso."""
    ora = ora or datetime.now(timezone.utc)
    oggi = ora.astimezone(ROMA).date()
    info = giornate(s)
    dal, al = finestra(s)
    cl = classifica(s, info)
    chiusa = qualificazione_chiusa(s, info) and oggi > al
    seed = {x["team"]: i + 1 for i, x in enumerate(cl[:QUALIFICATE])}
    # fase
    lv = {t: live(s, t) for t in (1, 2)}
    fatti = {t: risultati_cup(s, t) for t in (1, 2)}

    def iniziato(t: int) -> bool:
        g = info["q1" if t == 1 else "q2"]
        return bool(lv[t] and lv[t].get("message_id")) or bool(g and g.get("prima_partita") and g["prima_partita"] <= ora)

    agg = lambda t: (f" · aggiornata alle {lv[t]['aggiornato'].astimezone(ROMA):%H:%M}"
                     if lv[t] and lv[t].get("aggiornato") and not fatti[t] else "")
    vinc = campione(s)
    if vinc:
        fase = f"{L.nome(vinc)} vince la Quasi NBA Cup!"
    elif fatti[1] and iniziato(2):
        fase = f"Finale in corso · {_quando(info['q2'], 2)}{agg(2)}"
    elif fatti[1]:
        fase = f"Finaliste decise: finale nella {_quando(info['q2'], 2)}"
    elif iniziato(1) and chiusa:
        fase = f"Semifinali in corso · {_quando(info['q1'], 1)}{agg(1)}"
    elif chiusa:
        fase = f"Qualificate le prime 4: semifinali nella {_quando(info['q1'], 1)}"
    elif oggi < dal:
        fase = f"La qualificazione inizia il {dal:%d/%m}: conta il miglior punteggio di giornata fino al {al:%d/%m}"
    elif oggi <= al:
        manca = (al - oggi).days
        fase = (f"Fase di qualificazione: mancano {manca} giorni (fino al {al:%d/%m}), poi semifinali e finale" if manca > 1 else
                f"Fase di qualificazione: {'ultimo giorno' if manca == 0 else 'manca un giorno'} (fino al {al:%d/%m})")
    else:
        fase = "Qualificazione finita: si aspetta la convalida dell'ultima giornata"
    # record
    tutti = [(p, x["team"]) for x in cl for p, _g in x["punteggi"]]
    chip = None
    if tutti:
        p, t = max(tutti, key=lambda z: z[0])
        chip = {"t": "Record della Cup", "v": f"{L.nome(t)} · {tp(p)}"}
    # qualificazione
    righe = []
    for i, x in enumerate(cl[:IN_CLASSIFICA]):
        pp = x["punteggi"]
        gdate = {g["numero"]: g for g in info["qual"]}
        dove = (f"G{pp[0][1]} · {gdate[pp[0][1]]['dal']:%d/%m}" if pp and pp[0][1] in gdate else "nessuna giornata convalidata")
        righe.append({**_squadra(x["team"]), "max": tp(pp[0][0]) if pp else "–", "dove": dove,
                      "secondo": tp(pp[1][0]) if len(pp) > 1 else "–"})
    # semifinali
    coppie = abbinamenti(s, 1, info)
    semi = []
    for k, cp in enumerate(coppie):
        ris, badge = None, ""
        if fatti[1]:
            ris = next((r for r in fatti[1] if r["casa"] == cp[0]), None)
            badge = "FINITA" if ris else ""
        elif lv[1] and lv[1].get("risultati") and chiusa:
            ris = next((r for r in lv[1]["risultati"] if r["casa"] == cp[0]), None)
            badge = "LIVE" if ris else ""
        semi.append({"titolo": f"Semifinale {k + 1}", "quando": _quando(info["q1"], 1), "badge": badge,
                     "righe": _righe_partita(cp, seed, ris)})
    # finale
    fin = {"quando": _quando(info["q2"], 2), "badge": "", "righe": [], "campione": None}
    fc = abbinamenti(s, 2, info)
    if fc:
        ris = None
        if fatti[2]:
            ris = fatti[2][0]
            fin["badge"] = "FINITA"
        elif lv[2] and lv[2].get("risultati"):
            ris = next((r for r in lv[2]["risultati"] if r["casa"] == fc[0][0]), None)
            fin["badge"] = "LIVE" if ris else ""
        seed_f = {t: seed.get(t) for t in fc[0] if seed.get(t)}
        fin["righe"] = _righe_partita(fc[0], seed_f, ris)
    if vinc:
        fin["campione"] = _squadra(vinc)
    giornate_q = [g["numero"] for g in info["qual"]]
    return {
        "anno": s, "fase": fase, "chip": chip,
        "tab_nota": "le qualificate" if chiusa else "se finisse oggi",
        "semi": semi, "finale": fin,
        "q_titoli": ["Qualificate", "Eliminate"] if chiusa else ["Dentro, se finisse oggi", "Inseguono"],
        "classifica": righe,
        "finestra": (f"giornate dal {dal:%d/%m} al {al:%d/%m} (anche quella a cavallo del {al:%d}): "
                     + (f"G{giornate_q[0]}–G{giornate_q[-1]}" if giornate_q else "calendario da fare")),
    }


def immagine(d: dict) -> bytes:
    import typst
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(TEMPLATE, root="/", format="png", ppi=170, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})


def didascalia(d: dict, ora: datetime | None = None) -> str:
    import html
    ora = ora or datetime.now(timezone.utc)
    return f"🏅 <b>Quasi NBA Cup {html.escape(d['anno'])}</b> · {html.escape(d['fase'])}"


async def cmd_quasi_cup(update, context):
    """/quasi_cup (loucabot e bot principale): l'immagine della fase di adesso, coi dati già salvati (live compreso)."""
    import asyncio
    d = await asyncio.to_thread(dati, L.stagione())
    png = await asyncio.to_thread(immagine, d)
    await update.effective_message.reply_photo(png, caption=didascalia(d), parse_mode="HTML",
                                               read_timeout=60, write_timeout=60, connect_timeout=30)
