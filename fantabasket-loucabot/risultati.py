"""
Calcolo definitivo di una giornata: dai quintetti congelati e dalle panchine di IPanchinari
(ipa_formazioni, ipa_panchine) ai risultati, con le regole di calcolo.py.

- calcola(stagione, n): punteggi di tutti i giocatori schierati, FADD, esito di ogni partita,
  avvisi per gli admin. Non scrive niente.
- griglia(c): il tab "Calcolo GN" del foglio di controllo: una riga per giocatore coi fantapunti
  di ogni notte, la media, gli status, e formule che rifanno il conto del bot (punteggio, totali,
  supplementari, vincitore), più il riquadro dei risultati in cima. Deve dare gli stessi numeri del
  bot: lo verifica tests/louca/louca_risultati.py ricalcolando il foglio con LibreOffice.
- salva_calcolo / convalida: lega_calcoli (la proposta da convalidare) e, alla convalida,
  lega_risultati (quello che va sul foglio Calendario).
"""
import json
import logging
from datetime import timedelta

import calcolo
import config
import db

logger = logging.getLogger(__name__)
RUOLI = ("PG", "SG", "SF", "PF", "C")
BONUS = {"regular": 3, "playoff": 5}


# ── dati di IPanchinari (stesso database) ──────────────────────────────────────

def _c_e(tabella: str) -> bool:
    return bool(db.q("SELECT to_regclass(%s) AS t", (tabella,), one=True)["t"])


def giornata_chiusa(stagione: str, n: int) -> bool:
    """IPanchinari ha congelato i quintetti della giornata (la scadenza è passata)."""
    if not _c_e("ipa_stato_giornata"):
        return False
    r = db.q("SELECT chiusa FROM ipa_stato_giornata WHERE stagione = %s AND giornata = %s", (stagione, n), one=True)
    return bool(r and r["chiusa"])


def schieramenti(stagione: str, n: int) -> dict[str, dict]:
    """{team_id: {quintetto: [{ruolo, gid}], panchina: [{gid, ruolo, testo}]}} della giornata."""
    out: dict[str, dict] = {}
    if _c_e("ipa_formazioni"):
        for r in db.q("SELECT team_id, ruolo, giocatore_id FROM ipa_formazioni WHERE stagione = %s AND giornata = %s",
                      (stagione, n), many=True) or []:
            out.setdefault(r["team_id"], {"quintetto": {}, "panchina": None})["quintetto"][r["ruolo"]] = r["giocatore_id"]
    if _c_e("ipa_panchine"):
        for r in db.q("SELECT team_id, righe FROM ipa_panchine WHERE stagione = %s AND giornata = %s",
                      (stagione, n), many=True) or []:
            righe = r["righe"] if isinstance(r["righe"], list) else json.loads(r["righe"])
            out.setdefault(r["team_id"], {"quintetto": {}, "panchina": None})["panchina"] = righe
    return out


def _giocatori(ids: list[int], stagione: str) -> dict[int, dict]:
    if not ids:
        return {}
    righe = db.q("""SELECT g.id, g.nome_common, g.espn_id, r.ruolo FROM giocatori g
                    LEFT JOIN ruolo_attuale r ON r.giocatore_id = g.id AND r.stagione = %s
                    WHERE g.id = ANY(%s)""", (stagione, list(ids)), many=True) or []
    return {r["id"]: r for r in righe}


# ── calcolo ────────────────────────────────────────────────────────────────────

def _riga(gid, ruolo, gioc: dict, posto: str) -> dict:
    x = gioc.get(gid) or {}
    return {"gid": gid, "atleta": x.get("espn_id"), "ruolo": ruolo or x.get("ruolo"), "posto": posto,
            "nome": x.get("nome_common") or ("—" if not gid else f"giocatore {gid}")}


def schieramenti_attuali(stagione: str, n: int) -> dict[str, dict]:
    """Per la prova: i quintetti di adesso (ipa_quintetto) e le panchine mandate per la giornata n."""
    out = {t: {"quintetto": {}, "panchina": None} for t in [s["id"] for s in config.squadre()]}
    if _c_e("ipa_quintetto"):
        for r in db.q("SELECT team_id, ruolo, giocatore_id FROM ipa_quintetto", many=True) or []:
            out.setdefault(r["team_id"], {"quintetto": {}, "panchina": None})["quintetto"][r["ruolo"]] = r["giocatore_id"]
    for t, s in schieramenti(stagione, n).items():
        out.setdefault(t, {"quintetto": {}, "panchina": None})["panchina"] = s["panchina"]
    return out


def calcola(stagione: str, n: int, g: dict | None = None, sch: dict | None = None, stagione_nba: str | None = None,
            partite: list | None = None) -> dict:
    """Con g, sch e stagione_nba (solo /dev_prova_calcolo): una giornata finta, sulle partite NBA di
    altri giorni e con gli schieramenti indicati; le medie dalla stagione NBA di quei giorni."""
    stagione_nba = stagione_nba or stagione
    g = g or db.giornata(stagione, n)
    if not g:
        raise ValueError(f"giornata {n} non trovata")
    partite = partite if partite is not None else db.partite_giornata(stagione, n)
    sch = sch if sch is not None else schieramenti(stagione, n)
    ids = set()
    for s in sch.values():
        ids |= {x for x in s["quintetto"].values() if x}
        ids |= {r.get("giocatore_id") for r in (s["panchina"] or []) if r.get("giocatore_id")}
    gioc = _giocatori(list(ids), stagione)
    avvisi: list[str] = []
    squadre: dict[str, dict] = {}
    for p in partite:
        for t in (p["casa"], p["trasferta"]):
            s = sch.get(t, {"quintetto": {}, "panchina": None})
            q = [_riga(s["quintetto"].get(r), r, gioc, f"Q-{r}") for r in RUOLI]
            b = [_riga(x.get("giocatore_id"), x.get("ruolo"), gioc, f"P{i}") for i, x in enumerate(s["panchina"] or [], 1)]
            nome = config.nome(t)
            vuoti = [x["posto"] for x in q if not x["gid"]]
            if vuoti:
                avvisi.append(f"{nome}: quintetto incompleto ({', '.join(vuoti)}): 0 in quei ruoli")
            if s["panchina"] is None:
                avvisi.append(f"{nome}: panchina non mandata, si gioca senza supplementari (penalità: decidono gli admin)")
            senza = [x["nome"] for x in q + b if x["gid"] and not x["atleta"]]
            if senza:
                avvisi.append(f"{nome}: senza id ESPN, contano 0: {', '.join(senza)} (/espn_abbina)")
            squadre[t] = {"quintetto": q, "panchina": b}
    atleti = [x["atleta"] for s in squadre.values() for x in s["quintetto"] + s["panchina"] if x["atleta"]]
    punti = calcolo.punteggio_giocatori(stagione_nba, g, atleti)
    bonus = BONUS.get(g.get("tipo") or "regular", 3)
    risultati = []
    for p in partite:
        sc = calcolo.punteggio_squadra(g, squadre[p["casa"]]["quintetto"], squadre[p["casa"]]["panchina"], punti)
        st = calcolo.punteggio_squadra(g, squadre[p["trasferta"]]["quintetto"], squadre[p["trasferta"]]["panchina"], punti)
        for t, s in ((p["casa"], sc), (p["trasferta"], st)):
            avvisi += [f"{config.nome(t)}: {a}" for a in s["avvisi"]]
        es = calcolo.esito(sc, st, bonus)
        risultati.append({"casa": p["casa"], "trasferta": p["trasferta"], "sc": sc, "st": st, "esito": es,
                          "punti_casa": es["regolamentari"][0], "punti_trasferta": es["regolamentari"][1],
                          "supp_casa": es["punti_supplementari"][0] if es["punti_supplementari"] else None,
                          "supp_trasferta": es["punti_supplementari"][1] if es["punti_supplementari"] else None,
                          "supplementari": es["supplementari"], "vince": es["vince"]})
    return {"stagione": stagione, "giornata": g, "bonus": bonus, "squadre": squadre, "punti": punti,
            "risultati": risultati, "avvisi": avvisi, "dettaglio": _dettaglio(stagione_nba, g, atleti)}


def _dettaglio(stagione: str, g: dict, atleti: list[str]) -> dict:
    """Per il foglio: fantapunti di ogni notte (solo le partite che contano), media della stagione,
    status di ogni notte (lo snapshot che conta, o quello deciso da un admin)."""
    giorni = [g["dal"] + timedelta(days=i) for i in range((g["al"] - g["dal"]).days + 1)]
    notti: dict[str, dict] = {}
    for r in db.tabellini_atleti(atleti, g["dal"], g["al"]):
        if calcolo.conta(r):
            notti.setdefault(r["atleta"], {})[r["data_et"]] = float(r["fp"])
    medie = db.medie_stagione(atleti, stagione, g["dal"])
    stati = db.infortuni(atleti, giorni)
    con_snap = db.giorni_con_snapshot(giorni)
    decisi = db.status_validi(stagione, g["numero"], atleti)
    status = {}
    for a in atleti:
        if a in decisi:
            status[a] = {d: (decisi[a] or "sano") + " (admin)" for d in giorni}
        else:
            status[a] = {d: (stati.get((a, d)) or "sano") if d in con_snap else "—" for d in giorni}
    return {"giorni": giorni, "notti": notti, "medie": {a: m["media"] for a, m in medie.items()}, "status": status}


# ── testo per il gruppo admin ──────────────────────────────────────────────────

def _n(x) -> str:
    return f"{x:.2f}".replace(".", ",")


def testo(c: dict, versione: int = 1) -> str:
    import html
    e = html.escape
    g = c["giornata"]
    righe = [f"📊 <b>Giornata {g['numero']} calcolata</b>" + (f" (ricalcolo {versione - 1})" if versione > 1 else "")
             + f" · notti {g['dal']:%d/%m}–{g['al']:%d/%m}", ""]
    for r in c["risultati"]:
        casa, tr = config.nome(r["casa"]), config.nome(r["trasferta"])
        v = casa if r["vince"] == "casa" else tr
        riga = f"{e(casa)} <b>{_n(r['punti_casa'])}</b> – <b>{_n(r['punti_trasferta'])}</b> {e(tr)}"
        if r["supplementari"]:
            riga += f" · {r['supplementari']} suppl. {_n(r['supp_casa'])}–{_n(r['supp_trasferta'])}"
        riga += f" → <b>{e(v)}</b>"
        fadd = [s["fadd"] for s in (r["sc"], r["st"]) if s["fadd"]]
        for f in fadd:
            riga += f"\n   ↪️ FADD: esce {e(f['esce']['nome'])}, entra {e(f['entra']['nome'])}"
        righe.append(riga)
    if c["avvisi"]:
        righe += ["", "⚠️ " + "\n⚠️ ".join(e(a) for a in c["avvisi"])]
    righe += ["", f"Controlla il tab «Calcolo G{g['numero']}» del foglio di calcolo, poi convalida. "
                  "Per correggere: /set_valid_status, /quintetto_admin SQUADRA GN, /panchina_admin SQUADRA GN "
                  "(su IPanchinari), poi 🔄 Ricalcola."]
    return "\n".join(righe)


# ── foglio "Calcolo GN" ────────────────────────────────────────────────────────

BLU, NERO, VERDE = "#0000ff", "#000000", "#008000"
SF_TESTA, SF_PART, SF_PANCA, SF_FADD, SF_TOT, SF_PARAM = "#1f3864", "#d9e1f2", "#f2f2f2", "#fce4d6", "#e2efda", "#fff2cc"


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def griglia(c: dict) -> dict:
    """{righe, sfondi, testi, pesi, formati, congela}: matrici della stessa forma per il gas."""
    g = c["giornata"]
    det = c["dettaglio"]
    giorni = det["giorni"]
    nd = len(giorni)
    # colonne
    COL = ["Squadra", "Posto", "Ruolo", "Giocatore", "NBA"] + [f"Notte {d:%d/%m}" for d in giorni] + \
          ["Media stagione", "Squadra NBA a media?"] + [f"Status {d:%d/%m}" for d in giorni] + \
          ["Indisponibile?", "Punteggio", "Come", "In campo", "Ordine suppl.", "Note"]
    W = len(COL)
    iN0 = 5                       # prima notte
    iMED, iAM = iN0 + nd, iN0 + nd + 1
    iS0 = iAM + 1
    iIND = iS0 + nd
    iPUN, iCOME, iCAMPO, iORD = iIND + 1, iIND + 2, iIND + 3, iIND + 4
    L = {k: _col(v) for k, v in dict(N0=iN0, NN=iN0 + nd - 1, MED=iMED, AM=iAM, IND=iIND, PUN=iPUN, CAMPO=iCAMPO,
                                      ORD=iORD).items()}
    righe, sf, tx, pe, fo = [], [], [], [], []

    def nuova(valori=None, sfondo="", colore=NERO, peso="normal", formato=""):
        v = list(valori or []) + [""] * (W - len(valori or []))
        righe.append(v[:W])
        sf.append([sfondo] * W)
        tx.append([colore] * W)
        pe.append([peso] * W)
        fo.append([formato] * W)
        return len(righe)                      # numero di riga (1 = prima)

    nuova([f"Calcolo giornata {g['numero']} · stagione {c['stagione']} · notti {g['dal']:%d/%m}–{g['al']:%d/%m}"], peso="bold")
    r_par = nuova(["Bonus casa", c["bonus"], "Scarto minimo", calcolo.SCARTO,
                   "Dati del bot in blu, formule in nero: il foglio rifà i conti del bot. Le correzioni si fanno dal bot "
                   "(/set_valid_status, quintetto e panchina della giornata), poi Ricalcola: il tab si riscrive."])
    for i in (1, 3):
        sf[-1][i], tx[-1][i] = SF_PARAM, BLU
    BON, SCA = f"$B${r_par}", f"$D${r_par}"
    nuova()
    np = len(c["risultati"])
    nuova(["Partita", "Casa", "Punti casa", "Trasferta", "Punti trasferta", "Suppl.", "Punti suppl. casa",
                   "Punti suppl. trasferta", "Vince"], sfondo=SF_TESTA, colore="#ffffff", peso="bold")
    righe_ris = [nuova() for _ in range(np)]
    nuova()
    nuova(COL, sfondo=SF_TESTA, colore="#ffffff", peso="bold")
    r_testa = len(righe)
    for k, (r, rr) in enumerate(zip(c["risultati"], righe_ris), 1):
        casa, tr = config.nome(r["casa"]), config.nome(r["trasferta"])
        nuova([f"Partita {k}: {casa} (casa) – {tr}"], sfondo=SF_PART, peso="bold")
        blocchi = {}
        for t, s in ((r["casa"], r["sc"]), (r["trasferta"], r["st"])):
            nome_t = config.nome(t)
            fadd = s["fadd"]
            esce = fadd["esce"]["atleta"] if fadd else None
            entra = fadd["entra"]["atleta"] if fadd else None
            in_campo = {x.get("atleta") for x in s["titolari"]}
            ordine = {x.get("atleta"): i for i, x in enumerate(s["panchina"], 1) if x.get("atleta")}
            prima = len(righe) + 1
            for x in c["squadre"][t]["quintetto"] + c["squadre"][t]["panchina"]:
                a = x["atleta"]
                p = c["punti"].get(a, {"fp": 0.0, "come": "zero", "nota": "senza id ESPN" if x["gid"] else "vuoto"})
                # le due colonne che la formula del punteggio usa, come le ha usate il bot:
                # a media = la sua squadra non ha giocato (media, o 0 perché indisponibile)
                zero_indisp = p["come"] == "zero" and p.get("nota", "").startswith("indisponibile")
                a_media = p["come"] == "media" or zero_indisp
                indisp = zero_indisp or (a is not None and a == esce)
                nota = p.get("nota", "")
                if a and a == esce:
                    nota = f"FADD: esce ({fadd['motivo']}), entra {fadd['entra']['nome']}. " + nota
                if a and a == entra:
                    nota = f"FADD: entra al posto di {fadd['esce']['nome']}. " + nota
                riga_n = len(righe) + 1
                notti = [det["notti"].get(a, {}).get(d, "") if a else "" for d in giorni]
                stati = [det["status"].get(a, {}).get(d, "—") if a else "—" for d in giorni]
                nba = p.get("squadra") or ""
                rn = f"{L['N0']}{riga_n}:{L['NN']}{riga_n}"
                punteggio = (f'=IF(COUNT({rn})>0,ROUND(AVERAGE({rn}),2),'
                             f'IF(AND({L["AM"]}{riga_n}="sì",{L["IND"]}{riga_n}="no"),{L["MED"]}{riga_n},0))')
                come = (f'=IF(COUNT({rn})>0,"partite",IF(AND({L["AM"]}{riga_n}="sì",{L["IND"]}{riga_n}="no"),"media","0"))')
                valori = [nome_t, x["posto"], x["ruolo"] or "", x["nome"], nba] + notti + \
                         [det["medie"].get(a, 0.0) if a else 0.0, "sì" if a_media else "no"] + stati + \
                         ["sì" if indisp else "no", punteggio, come,
                          "sì" if a in in_campo and a else "no", ordine.get(a, "") if a else "", nota.strip()]
                fondo = SF_FADD if (a and a in (esce, entra)) else (SF_PANCA if x["posto"].startswith("P") else "")
                nuova(valori, sfondo=fondo, colore=BLU)
                for i in (iPUN, iCOME):
                    tx[-1][i] = NERO
                pe[-1][iPUN] = "bold"
                for i in list(range(iN0, iN0 + nd)) + [iMED, iPUN]:
                    fo[-1][i] = "0.00"
            blocchi[t] = (prima, len(righe))
        (c1, c2), (t1, t2) = blocchi[r["casa"]], blocchi[r["trasferta"]]
        P, Q, O = L["PUN"], L["CAMPO"], L["ORD"]
        nuova()
        r_tot = nuova(["", "", "", "Totale in campo", casa, f'=SUMIFS({P}{c1}:{P}{c2},{Q}{c1}:{Q}{c2},"sì")', "", tr,
                       f'=SUMIFS({P}{t1}:{P}{t2},{Q}{t1}:{Q}{t2},"sì")'], sfondo=SF_TOT, peso="bold", formato="0.00")
        r_reg = nuova(["", "", "", "Regolamentari (bonus casa alla squadra di casa)", "", f"=F{r_tot}+{BON}", "", "",
                       f"=I{r_tot}", "Scarto", f"=F{len(righe) + 1}-I{len(righe) + 1}"], sfondo=SF_TOT, peso="bold",
                      formato="0.00")
        nuova(["", "", "", "Supplementari: un panchinaro a testa alla volta, in ordine"], peso="bold")
        nuova(["", "", "", "Suppl.", f"+ {casa}", f"Tot. {casa}", "", f"+ {tr}", f"Tot. {tr}", "Scarto", "Decide?"],
              peso="bold")
        prima_s = len(righe) + 1
        for k2 in range(1, 6):
            rr_ = len(righe) + 1
            gia = f"ABS($K${r_reg})>={SCA}" if k2 == 1 else f'OR(ABS($K${r_reg})>={SCA},COUNTIF(K{prima_s}:K{rr_ - 1},"sì")>0)'
            nuova(["", "", "", k2, f"=SUMIFS({P}{c1}:{P}{c2},{O}{c1}:{O}{c2},{k2})",
                   (f"=F{r_reg}+E{rr_}" if k2 == 1 else f"=F{rr_ - 1}+E{rr_}"), "",
                   f"=SUMIFS({P}{t1}:{P}{t2},{O}{t1}:{O}{t2},{k2})",
                   (f"=I{r_reg}+H{rr_}" if k2 == 1 else f"=I{rr_ - 1}+H{rr_}"),
                   f"=F{rr_}-I{rr_}", f'=IF({gia},"",IF(ABS(J{rr_})>={SCA},"sì",""))'], formato="0.00")
        ultima_s = len(righe)
        r_es = len(righe) + 1
        nuova(["", "", "", "Risultato", "Vince",
               f'=IF(ABS(K{r_reg})>={SCA},IF(K{r_reg}>0,"{casa}","{tr}"),IFERROR(IF(INDEX(J{prima_s}:J{ultima_s},'
               f'MATCH("sì",K{prima_s}:K{ultima_s},0))>0,"{casa}","{tr}"),"{tr}"))', "", "Suppl.",
               f'=IF(ABS(K{r_reg})>={SCA},0,IFERROR(MATCH("sì",K{prima_s}:K{ultima_s},0),5))',
               "pari anche dopo tutta la panchina: vince la squadra in trasferta"], sfondo=SF_TOT, peso="bold")
        nuova()
        # riquadro dei risultati in cima
        i_r = rr - 1
        righe[i_r][:9] = [k, casa, f"=F{r_reg}", tr, f"=I{r_reg}", f"=I{r_es}",
                          f'=IF(F{rr}=0,"",INDEX(F{prima_s}:F{ultima_s},F{rr})-C{rr})',
                          f'=IF(F{rr}=0,"",INDEX(I{prima_s}:I{ultima_s},F{rr})-E{rr})', f"=F{r_es}"]
        for i in (2, 4, 6, 7):
            fo[i_r][i] = "0.00"
        for i in (2, 4, 5, 6, 7, 8):
            tx[i_r][i] = VERDE
    return {"righe": righe, "sfondi": sf, "testi": tx, "pesi": pe, "formati": fo,
            "congela": {"righe": r_testa, "colonne": 4}, "nome": f"Calcolo G{g['numero']}",
            "colonne": {"punteggio": iPUN}}


def payload_foglio(gr: dict) -> dict:
    """Il payload per il gas: i formati numerici diventano intervalli (colonne contigue con lo
    stesso formato, riga per riga accorpate per colonna)."""
    formati = []
    fo = gr["formati"]
    for j in range(len(fo[0])):
        i = 0
        while i < len(fo):
            if fo[i][j]:
                k = i
                while k + 1 < len(fo) and fo[k + 1][j] == fo[i][j]:
                    k += 1
                formati.append({"range": f"{_col(j)}{i + 1}:{_col(j)}{k + 1}", "formato": fo[i][j]})
                i = k + 1
            else:
                i += 1
    return {"action": "calcolo", "nome": gr["nome"], "righe": gr["righe"], "sfondi": gr["sfondi"], "testi": gr["testi"],
            "pesi": gr["pesi"], "formati": formati, "congela": gr["congela"]}


async def scrivi_foglio(c: dict, manda=None) -> str:
    """Scrive il tab "Calcolo GN"; restituisce una riga di esito."""
    import foglio
    if not manda and not foglio.configurato():
        return "foglio di calcolo non configurato (GAS_ROUTER_URL)"
    try:
        r = await foglio.manda_gas("calcolo", payload_foglio(griglia(c)), manda)
    except Exception as err:
        logger.warning("Foglio di calcolo: %s", err)
        return f"⚠️ tab Calcolo G{c['giornata']['numero']} non scritto ({type(err).__name__}: {str(err)[:150]})"
    if r.get("error"):
        return f"⚠️ tab Calcolo G{c['giornata']['numero']} non scritto: {str(r['error'])[:200]}"
    return f"tab «{r.get('tab')}» scritto ({r.get('righe')} righe)"


# ── stato del calcolo e convalida ──────────────────────────────────────────────

def risultati_json(c: dict) -> list[dict]:
    return [{k: r[k] for k in ("casa", "trasferta", "punti_casa", "punti_trasferta", "supp_casa", "supp_trasferta",
                               "supplementari", "vince")} for r in c["risultati"]]


def salva_calcolo(c: dict) -> int:
    """La proposta da convalidare (sostituisce la precedente). Restituisce la versione."""
    g = c["giornata"]
    r = db.q("""INSERT INTO lega_calcoli (stagione, giornata, risultati, avvisi) VALUES (%s, %s, %s, %s)
                ON CONFLICT (stagione, giornata) DO UPDATE SET risultati = EXCLUDED.risultati, avvisi = EXCLUDED.avvisi,
                  versione = lega_calcoli.versione + 1, calcolato = NOW(), stato = 'da_convalidare', messaggio = NULL
                RETURNING versione""", (c["stagione"], g["numero"], json.dumps(risultati_json(c)), json.dumps(c["avvisi"])),
             one=True)
    return r["versione"]


def convalida(stagione: str, n: int, da: int) -> list[dict]:
    """Scrive lega_risultati dalla proposta e la segna convalidata. Restituisce i risultati."""
    lc = db.q("SELECT * FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (stagione, n), one=True)
    ris = lc["risultati"] if isinstance(lc["risultati"], list) else json.loads(lc["risultati"])
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lega_risultati WHERE stagione = %s AND giornata = %s", (stagione, n))
            for r in ris:
                cur.execute("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta,
                                 supp_casa, supp_trasferta, vince, convalidato) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                            (stagione, n, r["casa"], r["trasferta"], r["punti_casa"], r["punti_trasferta"],
                             r["supp_casa"], r["supp_trasferta"], r["vince"]))
            cur.execute("UPDATE lega_calcoli SET stato = 'convalidata', convalidato = NOW(), convalidato_da = %s "
                        "WHERE stagione = %s AND giornata = %s", (da, stagione, n))
    return ris
