"""
Playoff, passo 1 (v7.10.0, Luca 15/11): dalla regular season ai playoff, fino al primo turno in calendario.

1. Alla convalida dell'ultima giornata di regular season (il numero più alto del calendario) il bot scrive al gruppo
   admin che la regular season è finita e che per i playoff serve /set_fase (bot principale), che controlla
   anche che ci sia il calendario dei playoff (shared/playoff_base.problemi_passaggio).
2. Dopo il cambio di fase (job_passaggio, ogni minuto, legge la fase da globals.json): congela tutte le giornate di
   regular season tranne l'ultima, calcola i seed (6 per conference, dall'ordine della classifica: vittorie, Quasi
   Cup, scontri diretti, media, differenza) e manda al gruppo admin la BOZZA: il tabellone e le posizioni, con gli
   spareggi decisi.
3. /set_seed SQUADRA N (admin): la squadra al seed N della sua conference, scambiata con chi c'era (anche con una
   squadra fuori dalle prime 6); il bot rimanda la bozza. Le scelte a mano restano anche dopo i ricalcoli.
4. ✅ Conferma (basta un admin): il tabellone sul canale principale, «soggetto a cambiamenti fino alle 15 del giorno
   dopo l'ultima notte di regular season in caso di correzioni».
5. Alle 15 (orari.blocco_playoff) di quel giorno, se confermato (job_blocco): congela l'ultima giornata di regular
   season, ricalcola i seed (le scelte a mano restano), aggiorna il tabellone sul canale se è cambiato qualcosa,
   blocca i seed, crea le serie del primo turno e la giornata P1 in calendario (lega_giornate, tipo playoff, dalle
   date di /importa_playoff) con le gare 1 (in casa la meglio classificata). Da lì le giornate P entrano in
   calendario una alla volta (passo 2: serie e turni).

/playoff: il tabellone (playoff.typ, a piramide sul giallo), in ogni momento: prima dei playoff «se finisse oggi».
Tabelle: lega_playoff (stato della stagione: bozza → confermato → bloccato), lega_seed, lega_serie.
"""
import asyncio
import html
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import classifica as C
import config
import db
from shared import codici_giornata as CG
from shared import playoff_base as PB
from shared import regole

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playoff.typ")
QUANTE = 6                                    # per conference (regolamento): 1 e 2 aspettano, 3–6 e 4–5 al primo turno
TURNI = {1: "Primo turno", 2: "Semifinali di conference", 3: "Finale di conference", 4: "Finale"}
PRIMO_TURNO = (("4-5", 4, 5), ("3-6", 3, 6))
TEMPI = {"read_timeout": 60, "write_timeout": 60, "connect_timeout": 30}
e = lambda x: html.escape(str(x), quote=False)


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_playoff (
              stagione      TEXT PRIMARY KEY,
              stato         TEXT NOT NULL DEFAULT 'bozza',      -- bozza / confermato / bloccato
              bozza_chat    BIGINT,
              bozza_msg     BIGINT,
              canale_chat   BIGINT,
              canale_msg    BIGINT,
              confermato    TIMESTAMPTZ,
              confermato_da TEXT,
              bloccato      TIMESTAMPTZ,
              creato        TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    # v7.11.0 (passo 2): la campione, quando finisce la finale
    db.q("ALTER TABLE lega_playoff ADD COLUMN IF NOT EXISTS campione TEXT")
    db.q("ALTER TABLE lega_playoff ADD COLUMN IF NOT EXISTS finito TIMESTAMPTZ")
    db.q("""CREATE TABLE IF NOT EXISTS lega_seed (
              stagione   TEXT NOT NULL,
              conference TEXT NOT NULL,
              seed       INT  NOT NULL,
              team       TEXT NOT NULL,
              manuale    BOOLEAN NOT NULL DEFAULT FALSE,       -- /set_seed: resta anche dopo i ricalcoli
              PRIMARY KEY (stagione, conference, seed))""")
    db.q("""CREATE TABLE IF NOT EXISTS lega_serie (
              id         SERIAL PRIMARY KEY,
              stagione   TEXT NOT NULL,
              turno      INT  NOT NULL,                       -- 1 primo turno … 4 finale
              conference TEXT NOT NULL DEFAULT '',            -- '' per la finale
              slot       TEXT NOT NULL,                       -- 4-5, 3-6, 1, 2, cf, f
              alta       TEXT NOT NULL,                       -- la meglio classificata (in casa in gara 1, 3, 5, 7)
              bassa      TEXT NOT NULL,
              seed_alta  INT,
              seed_bassa INT,
              al_meglio  INT  NOT NULL,
              vinte_alta INT  NOT NULL DEFAULT 0,
              vinte_bassa INT NOT NULL DEFAULT 0,
              vincente   TEXT,
              inizio     INT,                                 -- la giornata (numero G) della gara 1
              UNIQUE (stagione, turno, conference, slot))""")
    db.q("""CREATE TABLE IF NOT EXISTS lega_avvisi_playoff (
              stagione TEXT NOT NULL,
              chiave   TEXT NOT NULL,                         -- un avviso al gruppo admin una volta sola
              quando   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (stagione, chiave))""")


def _una_volta(s: str, chiave: str) -> bool:
    """True la prima volta (e la segna)."""
    migra()
    r = db.q("INSERT INTO lega_avvisi_playoff (stagione, chiave) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING chiave",
             (s, chiave), one=True)
    return bool(r)


# ── conference e seed ──────────────────────────────────────────────────────────

def conferenze() -> list[str]:
    """I nomi delle conference nell'ordine di divisions.json: la prima va sopra nel tabellone."""
    path = os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json")), "divisions.json")
    try:
        nomi = list((json.load(open(path, encoding="utf-8")).get("conference") or {}).keys())
    except Exception:
        nomi = []
    return nomi or sorted(set(C.conference().values()))


def classifica_conference(s: str) -> dict[str, list[dict]]:
    """{conference: righe della classifica nell'ordine (vittorie, Quasi Cup, scontri diretti, media, differenza)}."""
    righe, _ = C.calcola(s)
    conf = C.conference()
    out = {c: [] for c in conferenze()}
    for r in righe:
        c = conf.get(r["team"])
        if c in out:
            out[c].append(r)
    return out


def seed_calcolati(s: str) -> dict[str, list[str]]:
    return {c: [r["team"] for r in rr[:QUANTE]] for c, rr in classifica_conference(s).items()}


def seed_salvati(s: str) -> dict[str, dict[int, dict]]:
    migra()
    out = {c: {} for c in conferenze()}
    for r in db.q("SELECT * FROM lega_seed WHERE stagione = %s", (s,), many=True) or []:
        out.setdefault(r["conference"], {})[r["seed"]] = r
    return out


def seed(s: str) -> dict[str, list[str]]:
    """I seed in uso: quelli salvati (dalla bozza in poi), se no quelli della classifica di adesso."""
    sv = seed_salvati(s)
    if any(sv.values()):
        return {c: [sv[c][k]["team"] for k in sorted(sv[c])] for c in sv}
    return seed_calcolati(s)


def aggiorna_seed(s: str) -> list[str]:
    """Ricalcola dalla classifica tenendo le scelte a mano; salva. Restituisce i cambi (testo)."""
    migra()
    vecchi = seed_salvati(s)
    calc = classifica_conference(s)
    cambi = []
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for c, rr in calc.items():
                ordine = [r["team"] for r in rr]
                fissi = {k: v["team"] for k, v in vecchi.get(c, {}).items() if v["manuale"]}
                liberi = [t for t in ordine if t not in fissi.values()]
                nuovi = {}
                for k in range(1, QUANTE + 1):
                    nuovi[k] = fissi.get(k) or (liberi.pop(0) if liberi else None)
                for k, t in nuovi.items():
                    if t is None:
                        continue
                    prima = (vecchi.get(c, {}).get(k) or {}).get("team")
                    if prima and prima != t:
                        cambi.append(f"{c} {k}ª: {config.nome(prima)} → {config.nome(t)}")
                    cur.execute("""INSERT INTO lega_seed (stagione, conference, seed, team, manuale) VALUES (%s, %s, %s, %s, %s)
                                   ON CONFLICT (stagione, conference, seed) DO UPDATE SET team = EXCLUDED.team,
                                     manuale = EXCLUDED.manuale""", (s, c, k, t, k in fissi))
    return cambi


def imposta_seed(s: str, team: str, n: int) -> str:
    """/set_seed: la squadra al seed n della sua conference, scambiata con chi c'era. Restituisce il testo dell'esito."""
    conf = C.conference().get(team)
    if not conf:
        raise ValueError(f"{config.nome(team)} non è in nessuna conference (config/divisions.json)")
    if not 1 <= n <= QUANTE:
        raise ValueError(f"il seed va da 1 a {QUANTE}")
    if (stato(s) or {}).get("stato") == "bloccato":
        raise ValueError("il tabellone è già bloccato")
    sv = seed_salvati(s).get(conf, {})
    dove = next((k for k, v in sv.items() if v["team"] == team), None)
    chi = (sv.get(n) or {}).get("team")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO lega_seed (stagione, conference, seed, team, manuale) VALUES (%s, %s, %s, %s, TRUE)
                           ON CONFLICT (stagione, conference, seed) DO UPDATE SET team = EXCLUDED.team, manuale = TRUE""",
                        (s, conf, n, team))
            if dove and chi and dove != n:
                cur.execute("UPDATE lega_seed SET team = %s, manuale = TRUE WHERE stagione = %s AND conference = %s AND seed = %s",
                            (chi, s, conf, dove))
    if chi == team:
        return f"{config.nome(team)} era già {n}ª in {conf}"
    if dove:
        return f"{config.nome(team)} {n}ª in {conf}, {config.nome(chi)} {dove}ª"
    return f"{config.nome(team)} {n}ª in {conf}" + (f", {config.nome(chi)} fuori dai playoff" if chi else "")


def spareggi(rr: list[dict]) -> list[str]:
    """Le squadre a pari record nelle prime 7 di una conference (dove lo spareggio decide qualcosa) e come si è deciso."""
    out, i = [], 0
    top = rr[:QUANTE + 1]
    while i < len(top):
        j = i
        while j + 1 < len(top) and (top[j + 1]["w"], top[j + 1]["l"]) == (top[i]["w"], top[i]["l"]):
            j += 1
        if j > i:
            gruppo = top[i:j + 1]
            nomi = ", ".join(f"{config.nome(r['team'])} {k + i + 1}ª" for k, r in enumerate(gruppo))
            come = ("la vincitrice della Quasi Cup davanti, poi scontri diretti, media, differenza"
                    if any(r.get("cup_tb") for r in gruppo) else "scontri diretti, poi media punti, poi differenza")
            out.append(f"a {gruppo[0]['w']}-{gruppo[0]['l']}: {nomi} ({come})")
        i = j + 1
    return out


# ── stato ──────────────────────────────────────────────────────────────────────

def stato(s: str) -> dict | None:
    migra()
    return db.q("SELECT * FROM lega_playoff WHERE stagione = %s", (s,), one=True)


def _salva_stato(s: str, **campi) -> None:
    migra()
    db.q("INSERT INTO lega_playoff (stagione) VALUES (%s) ON CONFLICT DO NOTHING", (s,))
    for k, v in campi.items():
        db.q(f"UPDATE lega_playoff SET {k} = %s WHERE stagione = %s", (v, s))


def ora_blocco(s: str) -> datetime | None:
    """Le 15 (orari.blocco_playoff) del giorno dopo l'ultima notte di regular season."""
    u = CG.ultima_rs(s)
    g = db.giornata(s, u) if u else None
    if not g:
        return None
    return datetime.combine(g["al"] + timedelta(days=1), regole.orario("blocco_playoff"), ROMA)


def serie_al_meglio(turno: int) -> int:
    return int(regole.valore(f"playoff_serie_{turno}"))


# ── tabellone (immagine) ───────────────────────────────────────────────────────

def _squadra(t: str, k: int | None) -> dict:
    from shared import quasi_cup as QC
    return {**QC._squadra(t), "seed": str(k) if k else ""}


def _punti(x) -> str:
    return f"{float(x):.2f}".replace(".", ",") if x is not None else ""


def _gare(s: str, x: dict) -> tuple[list[dict], bool, str]:
    """Le gare di una serie per playoff.typ, se è in corso, e la nota (prossima gara o chi passa)."""
    u = CG.ultima_rs(s) or 0
    pp = db.q("""SELECT p.giornata, p.casa, p.trasferta, g.dal, g.al, g.prima_partita FROM lega_partite p
                 JOIN lega_giornate g ON g.stagione = p.stagione AND g.numero = p.giornata
                 WHERE p.stagione = %s AND g.tipo = 'playoff' AND p.giornata >= %s
                   AND ((p.casa = %s AND p.trasferta = %s) OR (p.casa = %s AND p.trasferta = %s))
                 ORDER BY p.giornata""", (s, x["inizio"] or 0, x["alta"], x["bassa"], x["bassa"], x["alta"]), many=True) or []
    gare, live, nota = [], False, ""
    adesso = datetime.now(timezone.utc)
    for i, p in enumerate(pp, 1):
        r = db.q("""SELECT * FROM lega_risultati WHERE stagione = %s AND giornata = %s AND casa = %s
                    AND convalidato IS NOT NULL""", (s, p["giornata"], p["casa"]), one=True)
        prov = None
        if not r:
            lc = db.q("SELECT risultati FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, p["giornata"]), one=True)
            rr = (lc["risultati"] if isinstance(lc["risultati"], list) else json.loads(lc["risultati"])) if lc else []
            prov = next((y for y in rr if y.get("casa") == p["casa"]), None)
        y = r or prov
        alta_casa = p["casa"] == x["alta"]
        pa = pb = v = ""
        if y:
            pc, pt = _punti(y.get("punti_casa")), _punti(y.get("punti_trasferta"))
            pa, pb = (pc, pt) if alta_casa else (pt, pc)
            if r:
                vince = r["casa"] if r["vince"] == "casa" else r["trasferta"]
                v = "a" if vince == x["alta"] else "b"
        iniziata = bool(p["prima_partita"] and p["prima_partita"] <= adesso)
        if not r and iniziata:
            live = True
        if r:
            casa = f"in casa {config.nome(p['casa'])}"
        elif iniziata:
            casa = "in corso"
        else:
            casa = f"{p['dal']:%d/%m} · in casa {config.nome(p['casa'])}"
        gare.append({"n": i, "p": f"P{p['giornata'] - u}", "casa": casa, "pa": pa, "pb": pb, "v": v})
        if not r:
            nota = f"gara {i} · P{p['giornata'] - u} · {p['dal']:%d/%m}–{p['al']:%d/%m}"
    if x["vincente"]:
        a, b = x["vinte_alta"], x["vinte_bassa"]
        nota = (f"{'vince' if x['turno'] == 4 else 'passa'} {config.nome(x['vincente'])} {max(a, b)}-{min(a, b)}")
    elif not nota:
        nota = f"al meglio delle {x['al_meglio']}"
    return gare, live, nota


def _serie_tab(s: str, x: dict) -> dict:
    gare, live, nota = _gare(s, x)
    return {"tipo": "serie", "a": _squadra(x["alta"], x["seed_alta"]), "b": _squadra(x["bassa"], x["seed_bassa"]),
            "va": x["vinte_alta"], "vb": x["vinte_bassa"], "nota": nota, "gare": gare, "live": live,
            "fine": bool(x["vincente"])}


def _finale_tab(s: str, x: dict) -> dict:
    """La finale: sotto ogni nome il piazzamento nella sua conference («1ª Ovest»)."""
    d = _serie_tab(s, x)
    conf = C.conference()
    for k, t, sd in (("a", x["alta"], x["seed_alta"]), ("b", x["bassa"], x["seed_bassa"])):
        d[k]["conf"] = (f"{sd}ª " if sd else "") + (conf.get(t) or "")
    return d


def dati_tabellone(s: str) -> dict:
    """Il JSON per playoff.typ nello stato di adesso: seed, serie con le gare, finale e campione."""
    st = stato(s)
    sd = seed(s)
    tutte = serie(s)
    per = {(r["turno"], r["conference"], r["slot"]): r for r in tutte}
    imp = db.q("SELECT numero_p, dal, al FROM lega_giornate_playoff WHERE stagione = %s ORDER BY numero_p", (s,), many=True) or []
    u = CG.ultima_rs(s) or 0
    p1 = imp[0] if imp else None
    confs = conferenze()

    def blocco(c: str) -> dict:
        tt = sd.get(c, [])
        get = lambda k: _squadra(tt[k - 1], k) if len(tt) >= k else {"nome": "—", "sigla": "?", "colore": "#BBBBBB", "logo": "", "seed": str(k)}
        r1 = []
        for slot, a, b in PRIMO_TURNO:
            x = per.get((1, c, slot))
            if x:
                r1.append(_serie_tab(s, x))
            else:
                nota = ("da P1" + (f" (G{u + 1}) · {p1['dal']:%d/%m}" if p1 else "") + f" · in casa {get(a)['nome']}")
                r1.append({"tipo": "serie", "a": get(a), "b": get(b), "va": 0, "vb": 0, "nota": nota, "gare": [], "fine": False})
        r2 = []
        for slot, k, chi, tit in (("1", 1, "vincente 4 – 5", "semifinale 1"), ("2", 2, "vincente 3 – 6", "semifinale 2")):
            x = per.get((2, c, slot))
            r2.append({**_serie_tab(s, x), "titolo": tit} if x else
                      {"tipo": "attesa", "a": get(k), "b": chi, "titolo": tit, "nota": "aspetta dal primo turno"})
        x = per.get((3, c, "cf"))
        r3 = (_serie_tab(s, x) if x else
              {"tipo": "attesa", "a": "vincente semifinale 1", "b": "vincente semifinale 2", "nota": "finale di conference"})
        return {"nome": f"Conference {c}", "t1": get(1), "t2": get(2), "r1": r1, "r2": r2, "r3": r3}
    blocchi = [blocco(c) for c in confs[:2]] + [blocco("")] * (2 - len(confs[:2]))
    fx = per.get((4, "", "f"))
    stt = (st or {}).get("stato")
    righe, giocate = C.calcola(s)
    campione = (st or {}).get("campione")
    if not st:
        fase, adesso = f"Se la regular season finisse oggi · dopo {giocate} giornate convalidate", "Proiezione"
    elif stt == "bozza":
        fase, adesso = "Bozza: da confermare dagli admin", "Bozza"
    elif stt == "confermato":
        b = ora_blocco(s)
        fase = ("Tabellone confermato · può cambiare fino alle " + (f"{b:%H:%M} del {b:%d/%m}" if b else "15") +
                " in caso di correzioni")
        adesso = "Confermato"
    elif campione:
        fase, adesso = f"Campione: {config.nome(campione)}", "Campione"
    else:
        t = max((x["turno"] for x in tutte), default=1)
        n = ultima_p(s)
        adesso = TURNI[t] if t != 2 else "Semifinali"
        fase = TURNI[t] + (f" · {_nome_p(s, n)} (G{n})" if n else "")
        gn = db.giornata(s, n) if n else None
        if gn:
            fase += f", {gn['dal']:%d/%m}–{gn['al']:%d/%m}"
    m = [serie_al_meglio(k) for k in (1, 2, 3, 4)]
    nota_meglio = (f"Primo turno al meglio delle {m[0]}, semifinali di conference delle {m[1]}, finali di conference delle "
                   f"{m[2]}, finale delle {m[3]}")
    a = int(s)
    return {"anno": f"{a}-{(a + 1) % 100:02d}", "fase": fase, "adesso": adesso,
            "finale_nota": f"al meglio delle {m[3]}", "ovest": blocchi[0], "est": blocchi[1],
            "conf_sopra": (confs + ["", ""])[0], "conf_sotto": (confs + ["", ""])[1],   # i nomi di divisions.json
            "finale": _finale_tab(s, fx) if fx else None,
            "campione": _squadra(campione, None) if campione else None,
            "regole_nota": (f"{nota_meglio} · in casa in gara 1, 3, 5 e 7 la meglio classificata · bonus casa "
                            f"{regole.bonus_casa(playoff=True):g} · ogni partita è una giornata P (P1 = G{u + 1}) · un turno "
                            f"inizia quando tutte le serie del turno prima sono finite · bordo rosso: partita in corso")}


def immagine(d: dict) -> bytes:
    import typst
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(TEMPLATE, root="/", format="png", ppi=150, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})


# ── la bozza agli admin ────────────────────────────────────────────────────────

def testo_bozza(s: str) -> str:
    st = stato(s) or {}
    sv = seed_salvati(s)
    cc = classifica_conference(s)
    rec = {r["team"]: r for rr in cc.values() for r in rr}
    righe = [f"🏆 <b>Playoff {s}: {'bozza del tabellone' if st.get('stato') == 'bozza' else 'tabellone'}</b>", ""]
    for c in conferenze():
        righe.append(f"<b>Conference {e(c)}</b>")
        for k in range(1, QUANTE + 1):
            x = sv.get(c, {}).get(k)
            if not x:
                continue
            r = rec.get(x["team"], {})
            righe.append(f"{k}. {e(config.nome(x['team']))} ({r.get('w', '?')}-{r.get('l', '?')})"
                         + (" ✋ <i>a mano</i>" if x["manuale"] else "") + (" 🏆" if r.get("cup_tb") else ""))
        dentro = {v["team"] for v in sv.get(c, {}).values()}
        fuori = [r for r in cc.get(c, []) if r["team"] not in dentro][:2]
        if fuori:
            righe.append("<i>fuori: " + ", ".join(f"{e(config.nome(r['team']))} ({r['w']}-{r['l']})" for r in fuori) + "</i>")
        for sp in spareggi(cc.get(c, [])):
            righe.append(f"⚖️ <i>{e(sp)}</i>")
        righe.append("")
    b = ora_blocco(s)
    righe += ["Primo turno: 3–6 e 4–5 (in casa in gara 1 la meglio classificata); 1 e 2 aspettano.",
              "Per cambiare: <code>/set_seed SQUADRA N</code> (scambia con chi c'è al seed N, anche con una squadra fuori).",
              (f"Il tabellone si blocca alle {b:%H:%M} del {b:%d/%m} (dopo le ultime correzioni della regular season): "
               "allora entra in calendario la P1." if b else "")]
    return "\n".join(x for x in righe if x is not None)


def _tasti(s: str):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
    st = stato(s) or {}
    if st.get("stato") != "bozza":
        return None
    return K([[B("✅ Conferma e pubblica sul canale", callback_data=f"po:ok:{s}")]])


async def manda_bozza(bot, s: str) -> None:
    """La bozza (o il tabellone aggiornato) al gruppo admin: un messaggio nuovo ogni volta, l'ultimo coi bottoni."""
    gruppo = config.gruppo_admin()
    if not gruppo:
        return
    png = await asyncio.to_thread(immagine, dati_tabellone(s))
    m = await bot.send_photo(chat_id=gruppo, photo=png, caption=f"🏆 Playoff {s}", **TEMPI)
    t = await bot.send_message(chat_id=gruppo, text=testo_bozza(s)[:4000], parse_mode="HTML", reply_markup=_tasti(s))
    st = stato(s) or {}
    if st.get("bozza_msg") and st.get("bozza_chat"):          # i bottoni solo sull'ultima
        try:
            await bot.edit_message_reply_markup(chat_id=st["bozza_chat"], message_id=st["bozza_msg"], reply_markup=None)
        except Exception:
            pass
    _salva_stato(s, bozza_chat=gruppo, bozza_msg=t.message_id)


async def _pubblica_canale(bot, s: str, aggiornato: bool = False) -> str:
    canale = config.globali().get("main_channel_id")
    if not canale:
        return "canale principale non configurato"
    png = await asyncio.to_thread(immagine, dati_tabellone(s))
    st = stato(s) or {}
    b = ora_blocco(s)
    n = ultima_p(s) if st.get("stato") == "bloccato" else None
    u = CG.ultima_rs(s) or 0
    if st.get("campione"):
        cap = f"🏆 <b>Playoff {s}</b>: {e(config.nome(st['campione']))} campione!"
    elif st.get("stato") == "bloccato" and n and n > u + 1:
        cap = f"🏆 <b>Playoff {s}</b>: il tabellone aggiornato · prossima {_nome_p(s, n)} (G{n})."
    elif st.get("stato") == "bloccato":
        cap = f"🏆 <b>Playoff {s}</b>: il tabellone definitivo. Si parte con la P1."
    else:
        cap = (f"🏆 <b>Playoff {s}</b>: il tabellone" + (" aggiornato" if aggiornato else "") +
               (f". <i>Soggetto a cambiamenti fino alle {b:%H:%M} del {b:%d/%m} in caso di correzioni.</i>" if b else ""))
    if st.get("canale_msg"):
        from telegram import InputMediaPhoto
        try:
            await bot.edit_message_media(chat_id=st["canale_chat"], message_id=st["canale_msg"],
                                         media=InputMediaPhoto(png, caption=cap, parse_mode="HTML"), **TEMPI)
            return "tabellone aggiornato sul canale"
        except Exception as err:
            if "not modified" in str(err).lower():
                return "tabellone già aggiornato sul canale"
            logger.info("Playoff: tabellone non modificabile (%s), ne mando uno nuovo", err)
    m = await bot.send_photo(chat_id=canale, photo=png, caption=cap, parse_mode="HTML", **TEMPI)
    _salva_stato(s, canale_chat=canale, canale_msg=m.message_id)
    return "tabellone sul canale"


# ── i passaggi ─────────────────────────────────────────────────────────────────

async def fine_regular_season(bot, s: str, n: int) -> str:
    """Dalla convalida (handlers_risultati): se n è l'ultima giornata di regular season, l'avviso agli admin."""
    if n != CG.ultima_rs(s) or CG.in_playoff():
        return ""
    if not _una_volta(s, "rs_finita"):
        return ""
    gruppo = config.gruppo_admin()
    if gruppo:
        mancano = PB.problemi_passaggio(s)
        await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=(
            f"🏁 <b>Regular season finita</b>: la G{n} era l'ultima.\n\nPer andare ai playoff serve il cambio di fase "
            "(/set_fase nel bot principale, «🏆 Playoff»): poi qui arriva la bozza del tabellone da confermare."
            + (("\n\n⚠️ Prima: " + "; ".join(e(x) for x in mancano) + ".") if mancano else "")))
    return "avviso di fine regular season agli admin"


def congela_regular_season(s: str, anche_ultima: bool = False) -> list[int]:
    """Il cambio di fase congela tutte le giornate di regular season, tranne l'ultima (fino alle 15 del giorno dopo)."""
    import congelamento as CO
    CO.migra()
    u = CG.ultima_rs(s)
    fatte = []
    for g in db.giornate(s):
        if g.get("tipo", "regular") != "regular" or (g["numero"] == u and not anche_ultima):
            continue
        db.q("""INSERT INTO lega_congelamento (stagione, giornata, congelata, da) VALUES (%s, %s, TRUE, NULL)
                ON CONFLICT (stagione, giornata) DO UPDATE SET congelata = TRUE, quando = NOW()""", (s, g["numero"]))
        fatte.append(g["numero"])
    return fatte


async def avvia(bot, s: str) -> str:
    """Il passaggio ai playoff, una volta: congelamento, seed, bozza agli admin."""
    if stato(s):
        return ""
    mancano = PB.problemi_passaggio(s)
    if mancano:
        if _una_volta(s, "fase_senza_rs"):
            gruppo = config.gruppo_admin()
            if gruppo:
                await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=(
                    "⚠️ <b>Fase playoff, ma non si può ancora partire</b>: " + "; ".join(e(x) for x in mancano) +
                    ". La bozza del tabellone arriva da sola appena è tutto pronto."))
        return "playoff: in attesa (" + "; ".join(mancano) + ")"
    congelate = congela_regular_season(s)
    _salva_stato(s, stato="bozza")
    aggiorna_seed(s)
    from registro import segna_sync
    segna_sync(None, "sistema", "playoff: bozza del tabellone", oggetto=f"stagione {s}",
               nota=f"congelate {len(congelate)} giornate di regular season (l'ultima resta aperta fino al blocco)")
    await manda_bozza(bot, s)
    return f"playoff: bozza agli admin, {len(congelate)} giornate congelate"


async def conferma(bot, s: str, user) -> str:
    st = stato(s) or {}
    chi = (getattr(user, "full_name", None) or str(getattr(user, "id", "?"))) if user else "?"
    if st.get("stato") != "bozza":
        return "già confermato"
    _salva_stato(s, stato="confermato", confermato=datetime.now(timezone.utc), confermato_da=chi)
    esito = await _pubblica_canale(bot, s)
    from registro import segna_sync
    segna_sync(user, "admin", "playoff: tabellone confermato", oggetto=f"stagione {s}")
    b = ora_blocco(s)
    if b and datetime.now(timezone.utc) >= b:
        esito += "; " + await blocca(bot, s)
    return esito


def crea_primo_turno(s: str) -> list[dict]:
    """Le serie del primo turno e la P1 in calendario con le gare 1 (in casa la meglio classificata)."""
    u = CG.ultima_rs(s)
    p1 = db.q("SELECT * FROM lega_giornate_playoff WHERE stagione = %s AND numero_p = 1", (s,), one=True)
    if u is None or not p1:
        raise ValueError("manca il calendario dei playoff (P1)")
    n = u + 1
    sd = seed(s)
    serie = []
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO lega_giornate (stagione, numero, tipo, dal, al, media_file) VALUES (%s, %s, 'playoff', %s, %s, %s)
                           ON CONFLICT (stagione, numero) DO UPDATE SET tipo = 'playoff', dal = EXCLUDED.dal, al = EXCLUDED.al,
                             media_file = EXCLUDED.media_file""", (s, n, p1["dal"], p1["al"], p1["media_file"]))
            cur.execute("DELETE FROM lega_partite WHERE stagione = %s AND giornata = %s", (s, n))
            for c, tt in sd.items():
                for slot, a, b in PRIMO_TURNO:
                    if len(tt) < b:
                        continue
                    cur.execute("""INSERT INTO lega_serie (stagione, turno, conference, slot, alta, bassa, seed_alta, seed_bassa,
                                     al_meglio, inizio) VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s, %s)
                                   ON CONFLICT (stagione, turno, conference, slot) DO UPDATE SET alta = EXCLUDED.alta,
                                     bassa = EXCLUDED.bassa, seed_alta = EXCLUDED.seed_alta, seed_bassa = EXCLUDED.seed_bassa,
                                     al_meglio = EXCLUDED.al_meglio, inizio = EXCLUDED.inizio""",
                                (s, c, slot, tt[a - 1], tt[b - 1], a, b, serie_al_meglio(1), n))
                    cur.execute("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, %s, %s)",
                                (s, n, tt[a - 1], tt[b - 1]))
                    serie.append({"conference": c, "slot": slot, "alta": tt[a - 1], "bassa": tt[b - 1]})
    import calendario
    calendario.ricalcola(s)                              # prima partita e squadre a media della P1
    return serie


async def blocca(bot, s: str) -> str:
    """Alle 15: ultima giornata di regular season congelata, seed ricalcolati (le scelte a mano restano) e bloccati,
    primo turno e P1 in calendario."""
    st = stato(s) or {}
    if st.get("stato") != "confermato":
        return ""
    congela_regular_season(s, anche_ultima=True)
    cambi = aggiorna_seed(s)
    serie = crea_primo_turno(s)
    _salva_stato(s, stato="bloccato", bloccato=datetime.now(timezone.utc))
    esito = await _pubblica_canale(bot, s, aggiornato=bool(cambi))
    gruppo = config.gruppo_admin()
    u = CG.ultima_rs(s)
    if gruppo:
        await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=(
            f"🔒 <b>Tabellone dei playoff bloccato</b>: la regular season è tutta congelata, il primo turno è in calendario "
            f"(P1 = G{u + 1}: {len(serie)} serie, gare 1)."
            + (("\n\nCambiati dalle correzioni: " + "; ".join(e(x) for x in cambi) + ".") if cambi else "")))
    from registro import segna_sync
    segna_sync(None, "sistema", "playoff: tabellone bloccato", oggetto=f"stagione {s}",
               nota=f"P1 = G{u + 1}, {len(serie)} serie" + (f"; cambi: {'; '.join(cambi)}" if cambi else ""))
    import foglio                                        # v7.15.0: il foglio Playoff con la P1
    ef = await foglio.aggiorna_playoff(s)
    return esito + f"; primo turno in calendario (P1 = G{u + 1})" + (f"; {ef}" if ef else "")


async def job_passaggio(context) -> None:
    """Ogni minuto: fase playoff senza bozza → avvia; confermato e passate le 15 → blocca; bozza non confermata alle 15
    → un promemoria agli admin."""
    if not CG.in_playoff():
        return
    s = config.stagione()
    try:
        st = stato(s)
        if not st:
            await avvia(context.bot, s)
            return
        b = ora_blocco(s)
        if not b or datetime.now(timezone.utc) < b:
            return
        if st["stato"] == "confermato":
            await blocca(context.bot, s)
        elif st["stato"] == "bloccato":
            await promemoria_convalida(context.bot, s)
        elif st["stato"] == "bozza" and _una_volta(s, "bozza_non_confermata"):
            gruppo = config.gruppo_admin()
            if gruppo:
                await context.bot.send_message(chat_id=gruppo, text=(
                    "⏰ Il tabellone dei playoff non è ancora confermato: la P1 entra in calendario solo dopo la conferma."))
    except Exception:
        logger.exception("Playoff: passaggio")


# ── passo 2: serie, turni, una giornata P alla volta ───────────────────────────
# Dopo ogni convalida di una giornata P (handlers_risultati → dopo_convalida): le serie si ricontano dai risultati
# convalidati (rifare una convalida le ricalcola da capo), poi la giornata dopo entra in calendario con le gare
# delle serie ancora aperte. Un turno nuovo parte quando tutte le serie del turno prima sono finite (anche prima
# del previsto). In casa la meglio classificata in gara 1, 3, 5 e 7 (regolamento: «il miglior record»): nella
# conference il seed più alto, in finale la posizione nella classifica generale della regular season.

def vinte_per_passare(al_meglio: int) -> int:
    return al_meglio // 2 + 1


def serie(s: str) -> list[dict]:
    migra()
    return db.q("SELECT * FROM lega_serie WHERE stagione = %s ORDER BY turno, conference, slot", (s,), many=True) or []


def _risultati_p(s: str) -> list[dict]:
    """I risultati convalidati delle giornate P, in ordine."""
    return db.q("""SELECT r.* FROM lega_risultati r JOIN lega_giornate g ON g.stagione = r.stagione AND g.numero = r.giornata
                   WHERE r.stagione = %s AND g.tipo = 'playoff' AND r.convalidato IS NOT NULL
                   ORDER BY r.giornata""", (s,), many=True) or []


def _della_serie(x: dict, r: dict) -> bool:
    return r["giornata"] >= (x["inizio"] or 0) and {r["casa"], r["trasferta"]} == {x["alta"], x["bassa"]}


def aggiorna_serie(s: str) -> list[dict]:
    """Ricontare le vittorie di ogni serie dai risultati convalidati. Restituisce le serie appena finite."""
    ris = _risultati_p(s)
    finite = []
    for x in serie(s):
        va = vb = 0
        for r in ris:
            if not _della_serie(x, r):
                continue
            chi = r["casa"] if r["vince"] == "casa" else r["trasferta"]
            if va >= vinte_per_passare(x["al_meglio"]) or vb >= vinte_per_passare(x["al_meglio"]):
                break                                   # serie già chiusa: un risultato in più non conta
            if chi == x["alta"]:
                va += 1
            elif chi == x["bassa"]:
                vb += 1
        serve = vinte_per_passare(x["al_meglio"])
        vincente = x["alta"] if va >= serve else x["bassa"] if vb >= serve else None
        if (va, vb, vincente) != (x["vinte_alta"], x["vinte_bassa"], x["vincente"]):
            db.q("UPDATE lega_serie SET vinte_alta = %s, vinte_bassa = %s, vincente = %s WHERE id = %s",
                 (va, vb, vincente, x["id"]))
            if vincente and not x["vincente"]:
                finite.append({**x, "vinte_alta": va, "vinte_bassa": vb, "vincente": vincente})
    return finite


def posto_generale(s: str) -> dict[str, int]:
    """La posizione nella classifica generale della regular season (1 = la migliore)."""
    righe, _ = C.calcola(s)
    return {r["team"]: i for i, r in enumerate(righe, 1)}


def _seed_di(s: str, team: str) -> int | None:
    for c, tt in seed(s).items():
        if team in tt:
            return tt.index(team) + 1
    return None


def _nuove_serie(s: str, turno: int, n: int) -> list[dict]:
    """Le serie del turno (2, 3 o 4) dalle vincenti del turno prima; inizio = la giornata n."""
    vinc = {(x["conference"], x["slot"]): x["vincente"] for x in serie(s) if x["turno"] == turno - 1}
    sd = seed(s)
    coppie = []                                         # (conference, slot, squadra, squadra)
    if turno == 2:
        for c, tt in sd.items():
            if len(tt) >= QUANTE:
                coppie += [(c, "1", tt[0], vinc.get((c, "4-5"))), (c, "2", tt[1], vinc.get((c, "3-6")))]
    elif turno == 3:
        for c in sd:
            coppie.append((c, "cf", vinc.get((c, "1")), vinc.get((c, "2"))))
    else:
        cc = conferenze()[:2]
        coppie.append(("", "f", vinc.get((cc[0], "cf")), vinc.get((cc[1], "cf"))))
    posto = posto_generale(s) if turno == 4 else {}
    out = []
    for c, slot, a, b in coppie:
        if not a or not b:
            raise ValueError(f"turno {turno}: manca una vincente ({c or 'finale'} {slot})")
        sa, sb = _seed_di(s, a), _seed_di(s, b)
        if turno == 4:
            meglio_a = posto.get(a, 99) < posto.get(b, 99)
        else:
            meglio_a = (sa or 99) < (sb or 99)
        alta, bassa = (a, b) if meglio_a else (b, a)
        out.append({"conference": c, "slot": slot, "alta": alta, "bassa": bassa,
                    "seed_alta": sa if meglio_a else sb, "seed_bassa": sb if meglio_a else sa})
    for x in out:
        db.q("""INSERT INTO lega_serie (stagione, turno, conference, slot, alta, bassa, seed_alta, seed_bassa, al_meglio, inizio)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (stagione, turno, conference, slot) DO UPDATE SET alta = EXCLUDED.alta, bassa = EXCLUDED.bassa,
                  seed_alta = EXCLUDED.seed_alta, seed_bassa = EXCLUDED.seed_bassa, al_meglio = EXCLUDED.al_meglio,
                  inizio = EXCLUDED.inizio, vinte_alta = 0, vinte_bassa = 0, vincente = NULL""",
             (s, turno, x["conference"], x["slot"], x["alta"], x["bassa"], x["seed_alta"], x["seed_bassa"],
              serie_al_meglio(turno), n))
    return out


def gare_della_giornata(s: str, n: int) -> dict:
    """Cosa si gioca nella giornata n (la prossima giornata P): {turno, partite [(casa, trasferta)], nuovo_turno,
    campione}. Crea le serie del turno nuovo quando serve; toglie quelle nate per la giornata n da un calcolo che una
    convalida rifatta ha cambiato."""
    aggiorna_serie(s)
    db.q("DELETE FROM lega_serie WHERE stagione = %s AND inizio >= %s AND turno > 1", (s, n))
    tutte = [x for x in serie(s) if (x["inizio"] or 0) < n]
    if not tutte:
        raise ValueError("nessuna serie: il primo turno non è ancora in calendario")
    t = max(x["turno"] for x in tutte)
    aperte = [x for x in tutte if x["turno"] == t and not x["vincente"]]
    if aperte:
        partite = []
        for x in aperte:
            gara = x["vinte_alta"] + x["vinte_bassa"] + 1
            partite.append((x["alta"], x["bassa"]) if gara % 2 else (x["bassa"], x["alta"]))
        return {"turno": t, "partite": partite, "nuovo_turno": False, "campione": None}
    if t >= 4:
        f = next(x for x in tutte if x["turno"] == 4)
        return {"turno": 4, "partite": [], "nuovo_turno": False, "campione": f["vincente"]}
    nuove = _nuove_serie(s, t + 1, n)
    return {"turno": t + 1, "partite": [(x["alta"], x["bassa"]) for x in nuove], "nuovo_turno": True, "campione": None}


def _scrivi_giornata(s: str, n: int, partite: list[tuple[str, str]]) -> None:
    """La giornata n (tipo playoff) in calendario, con le date di /importa_playoff, e le sue partite."""
    k = n - CG.ultima_rs(s)
    p = db.q("SELECT * FROM lega_giornate_playoff WHERE stagione = %s AND numero_p = %s", (s, k), one=True)
    if not p:
        raise ValueError(f"manca la data della P{k} nel calendario dei playoff (/importa_playoff)")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO lega_giornate (stagione, numero, tipo, dal, al, media_file) VALUES (%s, %s, 'playoff', %s, %s, %s)
                           ON CONFLICT (stagione, numero) DO UPDATE SET tipo = 'playoff', dal = EXCLUDED.dal, al = EXCLUDED.al,
                             media_file = EXCLUDED.media_file""", (s, n, p["dal"], p["al"], p["media_file"]))
            cur.execute("DELETE FROM lega_partite WHERE stagione = %s AND giornata = %s", (s, n))
            for casa, tr in partite:
                cur.execute("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, %s, %s)",
                            (s, n, casa, tr))
    import calendario
    calendario.ricalcola(s)


def _partite_in_calendario(s: str, n: int) -> list[tuple[str, str]]:
    return sorted((r["casa"], r["trasferta"]) for r in
                  db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s", (s, n), many=True) or [])


def ultima_p(s: str) -> int | None:
    r = db.q("SELECT MAX(numero) AS n FROM lega_giornate WHERE stagione = %s AND tipo = 'playoff'", (s,), one=True)
    return r["n"] if r else None


def _iniziata(s: str, n: int) -> bool:
    g = db.giornata(s, n)
    return bool(g and g.get("prima_partita") and g["prima_partita"] <= datetime.now(timezone.utc))


def _convalidata(s: str, n: int) -> bool:
    r = db.q("SELECT stato FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, n), one=True)
    return bool(r and r["stato"] == "convalidata")


def _nome_p(s: str, n: int) -> str:
    return f"P{n - (CG.ultima_rs(s) or 0)}"


def testo_partite(s: str, partite: list[tuple[str, str]]) -> str:
    righe = []
    for casa, tr in partite:
        x = next((x for x in serie(s) if {x["alta"], x["bassa"]} == {casa, tr} and not x["vincente"]), None)
        gara = (x["vinte_alta"] + x["vinte_bassa"] + 1) if x else 1
        stato_ = ""
        if x:
            a, b = x["vinte_alta"], x["vinte_bassa"]
            stato_ = (f" · {config.nome(x['alta'])} {a}-{b}" if a > b else f" · {config.nome(x['bassa'])} {b}-{a}"
                      if b > a else f" · {a}-{b}")
        righe.append(f"• gara {gara}: <b>{e(config.nome(casa))}</b> – {e(config.nome(tr))}{stato_}")
    return "\n".join(righe)


async def dopo_convalida(bot, s: str, n: int, prima: dict | None = None) -> str:
    """Dalla convalida di una giornata P: serie ricontate, la giornata dopo in calendario (o la campione), tabellone
    aggiornato sul canale. prima: {casa: {vince, …}} della convalida precedente (live._esiti), se c'era.
    Se la giornata dopo è già iniziata o convalidata non si tocca: le serie si ricontano e, se la convalida rifatta
    ha cambiato un vincitore, lo si dice agli admin."""
    g = db.giornata(s, n)
    if not g or g.get("tipo") != "playoff":
        return ""
    gruppo = config.gruppo_admin()
    dopo = n + 1
    gia = db.giornata(s, dopo)
    gia_p = bool(gia and gia.get("tipo") == "playoff")
    esiti = []
    if gia_p and (_iniziata(s, dopo) or _convalidata(s, dopo)):
        finite = aggiorna_serie(s)
        import live
        ora_ = live._esiti(s, n)
        cambiati = [c for c, v in (prima or {}).items() if v.get("vince") != (ora_.get(c) or {}).get("vince")]
        if prima is not None and cambiati and gruppo:
            await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=(
                f"⚠️ <b>Playoff</b>: la {_nome_p(s, n)} convalidata di nuovo cambia chi vince "
                + ", ".join(f"{e(config.nome(c))} – {e(config.nome(prima[c].get('trasferta') or '?'))}" for c in cambiati)
                + f", ma la {_nome_p(s, dopo)} è già iniziata: le serie sono ricontate, le partite già in calendario "
                  "restano. Controllate /playoff e decidete voi come sistemare."))
            esiti.append(f"⚠️ {_nome_p(s, dopo)} già iniziata: partite non cambiate, avvisati gli admin")
            from registro import segna_sync                # v7.13.0: resta traccia anche nel registro
            segna_sync(None, "sistema", "playoff: giornata già iniziata non cambiata", oggetto=f"{_nome_p(s, dopo)} (G{dopo})",
                       nota=f"la {_nome_p(s, n)} convalidata di nuovo cambia chi vince "
                            + ", ".join(f"{config.nome(c)} – {config.nome(prima[c].get('trasferta') or '?')}" for c in cambiati)
                            + "; avvisati gli admin")
    else:
        finite = aggiorna_serie(s)
        try:
            cosa = gare_della_giornata(s, dopo)
        except ValueError as err:
            if gruppo:
                await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=f"⚠️ <b>Playoff</b>: {e(err)}.")
            return f"playoff: {err}"
        if cosa["campione"]:
            if gia_p:
                db.q("DELETE FROM lega_partite WHERE stagione = %s AND giornata = %s", (s, dopo))
                db.q("DELETE FROM lega_giornate WHERE stagione = %s AND numero = %s", (s, dopo))
            esiti.append(await _campione(bot, s, cosa["campione"]))
        elif gia_p and _partite_in_calendario(s, dopo) == sorted(cosa["partite"]):
            esiti.append(f"{_nome_p(s, dopo)} già in calendario")
        else:
            try:
                _scrivi_giornata(s, dopo, cosa["partite"])
            except ValueError as err:
                if gruppo:
                    await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=f"⚠️ <b>Playoff</b>: {e(err)}.")
                return f"playoff: {err}"
            esiti.append(f"{_nome_p(s, dopo)} in calendario" + (" (partite cambiate)" if gia_p else ""))
            gd = db.giornata(s, dopo)
            if gruppo:
                titolo = (f"🏁 Si apre il turno: <b>{TURNI[cosa['turno']].lower()}</b>.\n" if cosa["nuovo_turno"] else "")
                await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=(
                    titolo + f"📅 <b>{_nome_p(s, dopo)} (G{dopo})</b>" + (" <i>(partite cambiate)</i>" if gia_p else "")
                    + f" · {gd['dal']:%d/%m}–{gd['al']:%d/%m}\n" + testo_partite(s, cosa["partite"])))
            from registro import segna_sync
            segna_sync(None, "sistema", "playoff: giornata in calendario" + (" (partite cambiate)" if gia_p else ""),
                       oggetto=f"{_nome_p(s, dopo)} (G{dopo})",
                       dopo="; ".join(f"{config.nome(c)} – {config.nome(t)}" for c, t in cosa["partite"]),
                       nota=(f"dopo la convalida della {_nome_p(s, n)}" + (" rifatta" if gia_p else "")
                             + (f"; si apre il turno: {TURNI[cosa['turno']].lower()}" if cosa["nuovo_turno"] else "")))
    for x in finite:
        perde = x["bassa"] if x["vincente"] == x["alta"] else x["alta"]
        esiti.append(f"{config.nome(x['vincente'])} batte {config.nome(perde)} "
                     f"{max(x['vinte_alta'], x['vinte_bassa'])}-{min(x['vinte_alta'], x['vinte_bassa'])}")
    try:
        esiti.append(await _pubblica_canale(bot, s, aggiornato=True))
    except Exception as err:
        logger.warning("Playoff: tabellone sul canale dopo la G%s: %s", n, err)
    import foglio                                        # v7.15.0: il foglio Playoff, a parte dal Calendario
    ef = await foglio.aggiorna_playoff(s)
    if ef:
        esiti.append(ef)
    return "playoff: " + "; ".join(esiti)


async def _campione(bot, s: str, team: str) -> str:
    st = stato(s) or {}
    if st.get("campione") == team:
        return f"{config.nome(team)} campione"
    _salva_stato(s, campione=team, finito=datetime.now(timezone.utc))
    from registro import segna_sync
    segna_sync(None, "sistema", "playoff: campione", oggetto=config.nome(team), nota=f"stagione {s}")
    canale = config.globali().get("main_channel_id")
    testo = f"🏆 <b>{e(config.nome(team))}</b> vince i playoff {s}-{(int(s) + 1) % 100:02d}! Complimenti 🎉"
    for chat in (canale, config.gruppo_admin()):
        if chat:
            try:
                await bot.send_message(chat_id=chat, text=testo, parse_mode="HTML")
            except Exception as err:
                logger.warning("Playoff: messaggio della campione a %s: %s", chat, err)
    return f"{config.nome(team)} campione"


async def promemoria_convalida(bot, s: str) -> None:
    """Dal job di ogni minuto: se l'ultima giornata P è finita e non è convalidata e la data della prossima è già
    arrivata, una volta sola un avviso agli admin (la giornata dopo entra in calendario solo con la convalida)."""
    n = ultima_p(s)
    st = stato(s) or {}
    if not n or st.get("campione") or _convalidata(s, n):
        return
    u = CG.ultima_rs(s) or 0
    p = db.q("SELECT dal FROM lega_giornate_playoff WHERE stagione = %s AND numero_p = %s", (s, n - u + 1), one=True)
    oggi = datetime.now(ROMA)
    if not p or oggi.date() < p["dal"] or oggi.hour < 12:
        return
    if _una_volta(s, f"convalida_{n}"):
        gruppo = config.gruppo_admin()
        if gruppo:
            await bot.send_message(chat_id=gruppo, parse_mode="HTML", text=(
                f"⏰ <b>Playoff</b>: la {_nome_p(s, n)} (G{n}) non è ancora convalidata e la {_nome_p(s, n + 1)} parte oggi. "
                "La giornata dopo entra in calendario (e IPanchinari chiede le formazioni) solo con la convalida."))


def titoli_live(g: dict, d: dict, risultati: list[dict]) -> None:
    """Nel JSON di live.typ (stessi campi della Quasi Cup): «P3 · Giornata 41» e sopra ogni partita la serie
    («GARA 2 · OVEST 4–5 · 1-0»)."""
    s = g["stagione"] if "stagione" in g else config.stagione()
    n = g["numero"]
    d["titolo"] = f"{_nome_p(s, n)} · Giornata {n}"
    tutte = serie(s)
    for p, x in zip(d.get("partite") or [], risultati):     # stesso ordine: una scheda per risultato
        sr = next((y for y in tutte if {y["alta"], y["bassa"]} == {x["casa"], x["trasferta"]} and (y["inizio"] or 0) <= n), None)
        if not sr:
            continue
        prima = db.q("""SELECT COUNT(*) AS c FROM lega_partite p JOIN lega_giornate gg ON gg.stagione = p.stagione
                          AND gg.numero = p.giornata WHERE p.stagione = %s AND gg.tipo = 'playoff' AND p.giornata >= %s
                          AND p.giornata < %s AND ((p.casa = %s AND p.trasferta = %s) OR (p.casa = %s AND p.trasferta = %s))""",
                     (s, sr["inizio"] or 0, n, sr["alta"], sr["bassa"], sr["bassa"], sr["alta"]), one=True)["c"]
        dove = "FINALE" if sr["turno"] == 4 else f"{sr['conference'].upper()} " + {"cf": "FINALE CONF.", "1": "SEMIF. 1",
                                                                                   "2": "SEMIF. 2"}.get(sr["slot"], sr["slot"].replace("-", "–"))
        p["titolo"] = f"GARA {prima + 1} · {dove}"


# ── comandi ────────────────────────────────────────────────────────────────────

async def cmd_playoff(update, context):
    msg = update.effective_message
    s = config.stagione()
    d = await asyncio.to_thread(dati_tabellone, s)
    png = await asyncio.to_thread(immagine, d)
    await msg.reply_photo(png, caption=f"🏆 Playoff {d['anno']} · {d['fase']}", **TEMPI)


async def cmd_set_seed(update, context):
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    s = config.stagione()
    st = stato(s) or {}
    if st.get("stato") not in ("bozza", "confermato"):
        await msg.reply_text("I seed si cambiano solo dopo il passaggio ai playoff e prima del blocco del tabellone"
                             + (" (il tabellone è già bloccato)." if st.get("stato") == "bloccato" else "."))
        return
    args = list(context.args or [])
    if len(args) < 2 or not args[-1].isdigit():
        from shared import esempi as ES
        await msg.reply_text(f"Uso: /set_seed SQUADRA N (es. /set_seed {ES.squadra()} 3): la squadra al seed N della sua conference, "
                             "scambiata con chi c'è.")
        return
    from partita import leggi_argomenti
    sq, _n, err = leggi_argomenti(args[:-1], config.squadre())
    if err or len(sq) != 1:
        await msg.reply_text(f"❌ {err or 'una squadra sola'}")
        return
    try:
        esito = imposta_seed(s, sq[0]["id"], int(args[-1]))
    except ValueError as err:
        await msg.reply_text(f"❌ {err}")
        return
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "playoff: seed cambiato", oggetto=esito)
    await msg.reply_text(f"✅ {esito}")
    await manda_bozza(context.bot, s)
    if st.get("stato") == "confermato":
        await _pubblica_canale(context.bot, s, aggiornato=True)


async def cb_playoff(update, context):
    q = update.callback_query
    if not config.is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.")
        return
    await q.answer()
    s = q.data.split(":")[2]
    chi = q.from_user.full_name or str(q.from_user.id)
    esito = await conferma(context.bot, s, q.from_user)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await q.message.reply_text(f"✅ Tabellone confermato da {chi}: {esito}.")


def get_handlers() -> list:
    from telegram.ext import CallbackQueryHandler, CommandHandler
    return [CommandHandler("playoff", cmd_playoff, block=False), CommandHandler("set_seed", cmd_set_seed),
            CallbackQueryHandler(cb_playoff, pattern=r"^po:ok:\d+$")]
