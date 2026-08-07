"""
Parser per trade in formato testuale.

Formato supportato:

  TRADE

  GM_A cede:
  Giocatore 25x2
  1st round pick 2027 by GM_X
  2nd round pick 2028 by GM_Y
  Diritti di Nome Rookie

  GM_B cede:
  Altro Giocatore 10x1

  # Per trade a 3+ squadre, sezioni riceve opzionali:
  GM_A riceve:
  ...

Regole di parsing:
- Giocatore: riga con suffisso NxM (es. "Julius Randle 29x1")
- Pick: "1st/2nd round pick ANNO by GMNOME"
- Pick corrente: "16th pick" (anno corrente dal DB)
- Diritti: "Diritti di NOME"
"""
import re
import unicodedata
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── normalizzazione ───────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


# ── risoluzione nomi GM ───────────────────────────────────────────────────────

def _trova_team(nome_raw: str, tutti_team: list) -> dict | None:
    """Fuzzy match su gm_nome e nome squadra."""
    import difflib
    nome_n = _norm(nome_raw)
    candidati = {}
    for t in tutti_team:
        for campo in [t.get("gm_nome", ""), t.get("nome", "")]:
            if campo:
                candidati[_norm(campo)] = t
    # Exact
    if nome_n in candidati:
        return candidati[nome_n]
    # Fuzzy
    match = difflib.get_close_matches(nome_n, candidati.keys(), n=1, cutoff=0.7)
    return candidati[match[0]] if match else None


# ── risoluzione giocatori su DB ───────────────────────────────────────────────

def _trova_giocatore_db(nome_raw: str) -> tuple[int | None, str | None]:
    """
    Cerca il giocatore in PostgreSQL per nome_norm.
    Restituisce (giocatore_id, nome_common) o (None, None).
    """
    import database as _db
    import difflib
    nome_n = _norm(nome_raw)
    rows = _db.cerca_giocatori(nome_n)
    if not rows:
        return None, None
    if len(rows) == 1:
        return rows[0]["id"], rows[0]["nome_common"]
    # Più match: prendi il più simile
    nomi = [_norm(r["nome_common"]) for r in rows]
    match = difflib.get_close_matches(nome_n, nomi, n=1, cutoff=0.6)
    if match:
        r = next(r for r in rows if _norm(r["nome_common"]) == match[0])
        return r["id"], r["nome_common"]
    return rows[0]["id"], rows[0]["nome_common"]  # primo risultato


# ── parsing singola riga ──────────────────────────────────────────────────────

@dataclass
class ParsedItem:
    tipo: str               # giocatore | pick | diritti
    raw: str                # riga originale
    # giocatore
    nome_raw: str  = ""
    importo: int   = 0
    anni: int      = 0
    giocatore_id: int | None = None
    nome_resolved: str = ""
    # pick
    round: int     = 0
    anno: str      = ""
    by_raw: str    = ""
    by_team_id: str = ""
    pick_id: int | None = None
    # errori
    errori: list   = field(default_factory=list)


_RE_GIOCATORE = re.compile(r'^(.+?)\s+(\d+)x(\d+)\s*$', re.IGNORECASE)
_RE_PICK      = re.compile(r'^(1st|2nd)\s+round\s+pick\s+(\d{4})\s+by\s+(.+)$', re.IGNORECASE)
_RE_PICK_N    = re.compile(r'^(\d+)(?:st|nd|rd|th)\s+pick\s*$', re.IGNORECASE)
_RE_DIRITTI   = re.compile(r'^diritti\s+di\s+(.+)$', re.IGNORECASE)


def _parse_riga(riga: str, tutti_team: list, stagione: str) -> ParsedItem | None:
    """Parsea una singola riga asset. Restituisce None se la riga va ignorata."""
    r = riga.strip()
    if not r:
        return None

    import database as _db

    # Diritti
    m = _RE_DIRITTI.match(r)
    if m:
        nome_r = m.group(1).strip()
        gid, nome_res = _trova_giocatore_db(nome_r)
        item = ParsedItem(tipo="diritti", raw=r, nome_raw=nome_r,
                          giocatore_id=gid, nome_resolved=nome_res or nome_r)
        if not gid:
            item.errori.append(f"Giocatore non trovato: '{nome_r}'")
        return item

    # Pick Nth (draft corrente)
    m = _RE_PICK_N.match(r)
    if m:
        pos = int(m.group(1))
        item = ParsedItem(tipo="pick", raw=r, round=1, anno=stagione, by_raw=f"posizione {pos}")
        # Cerca pick nel DB con posizione = pos
        # Per ora la segniamo come non risolta — da gestire separatamente
        item.errori.append(f"Pick draft corrente ({pos}a scelta) — verifica manuale nel DB")
        return item

    # Pick 1st/2nd
    m = _RE_PICK.match(r)
    if m:
        rnd    = 1 if m.group(1).lower() == "1st" else 2
        anno   = m.group(2)
        by_raw = m.group(3).strip()
        team_by = _trova_team(by_raw, tutti_team)
        item = ParsedItem(tipo="pick", raw=r, round=rnd, anno=anno, by_raw=by_raw)
        if not team_by:
            item.errori.append(f"GM/squadra non trovato: '{by_raw}'")
            return item
        item.by_team_id = team_by["id"]
        # Cerca la pick nel DB
        picks = _db.get_pick_team(team_by["id"])
        match_pick = next(
            (p for p in picks if str(p["anno"]) == anno and p["round"] == rnd), None
        )
        if match_pick:
            item.pick_id = match_pick["id"]
        else:
            item.errori.append(
                f"Pick non trovata nel DB: {rnd}° giro {anno} di {team_by['nome']}"
            )
        return item

    # Giocatore (NxM alla fine)
    m = _RE_GIOCATORE.match(r)
    if m:
        nome_r  = m.group(1).strip()
        importo = int(m.group(2))
        anni    = int(m.group(3))
        gid, nome_res = _trova_giocatore_db(nome_r)
        item = ParsedItem(tipo="giocatore", raw=r, nome_raw=nome_r,
                          importo=importo, anni=anni,
                          giocatore_id=gid, nome_resolved=nome_res or nome_r)
        if not gid:
            item.errori.append(f"Giocatore non trovato: '{nome_r}'")
        return item

    # Riga non riconosciuta
    item = ParsedItem(tipo="sconosciuto", raw=r)
    item.errori.append(f"Riga non riconosciuta: '{r}'")
    return item


# ── parsing testo completo ────────────────────────────────────────────────────

@dataclass
class SezioneGM:
    team_id: str
    team_nome: str
    cede: list = field(default_factory=list)   # list[ParsedItem]
    riceve: list = field(default_factory=list)  # list[ParsedItem]


def parsa_trade(testo: str, stagione: str, tutti_team: list) -> tuple[list[SezioneGM], list[str]]:
    """
    Parsea il testo di una trade.
    Restituisce (sezioni, errori_globali).
    """
    errori = []
    sezioni: dict[str, SezioneGM] = {}  # team_id → SezioneGM
    ordine_squadre: list[str] = []

    # Rimuovi TRADE keyword e normalizza a capo
    righe = testo.strip().splitlines()
    righe = [r for r in righe if r.strip().upper() != "TRADE"]

    sezione_corrente: SezioneGM | None = None
    tipo_corrente: str = ""  # "cede" | "riceve"

    _RE_SEZIONE = re.compile(r'^(.+?)\s+(cede|riceve)\s*:\s*$', re.IGNORECASE)

    for riga in righe:
        r = riga.strip()
        if not r:
            continue

        # Nuova sezione GM cede/riceve
        m = _RE_SEZIONE.match(r)
        if m:
            gm_raw    = m.group(1).strip()
            tipo_sez  = m.group(2).lower()
            team      = _trova_team(gm_raw, tutti_team)
            if not team:
                errori.append(f"GM/squadra non trovato: '{gm_raw}'")
                sezione_corrente = None
                continue
            tid = team["id"]
            if tid not in sezioni:
                sezioni[tid] = SezioneGM(team_id=tid, team_nome=team["nome"])
                ordine_squadre.append(tid)
            sezione_corrente = sezioni[tid]
            tipo_corrente = tipo_sez
            continue

        if sezione_corrente is None:
            continue

        item = _parse_riga(r, tutti_team, stagione)
        if item is None:
            continue
        if item.tipo == "sconosciuto":
            errori.extend(item.errori)
            continue
        if tipo_corrente == "cede":
            sezione_corrente.cede.append(item)
        else:
            sezione_corrente.riceve.append(item)

    # Per trade a 2 squadre senza sezioni "riceve": inferisci dai cede
    squadre = [sezioni[tid] for tid in ordine_squadre]
    if len(squadre) == 2:
        if not squadre[0].riceve and not squadre[1].riceve:
            squadre[0].riceve = squadre[1].cede[:]
            squadre[1].riceve = squadre[0].cede[:]
    elif len(squadre) > 2:
        # Per trade multi-squadra senza "riceve" espliciti, segnala
        for sq in squadre:
            if not sq.riceve:
                errori.append(
                    f"{sq.team_nome}: trade a più squadre richiede sezioni 'riceve' esplicite"
                )

    # Raccogli errori item
    for sq in squadre:
        for item in sq.cede + sq.riceve:
            for e in item.errori:
                errori.append(f"[{sq.team_nome}] {e}")

    return squadre, errori


# ── creazione bozza da parse ──────────────────────────────────────────────────

def crea_trade_da_parse(squadre: list[SezioneGM], stagione: str, proposta_da: str) -> int:
    """
    Crea la bozza nel DB partendo dalle sezioni parsate.
    Restituisce il trade_id.
    """
    import database as _db

    n_squadre = len(squadre)
    trade_id = _db.crea_trade_bozza(proposta_da, n_squadre, stagione)

    for i, sq in enumerate(squadre):
        _db.aggiungi_squadra_trade(trade_id, sq.team_id, i + 1)

    # Determina i destinatari: usa le sezioni "riceve" per sapere team_id_a
    # Costruiamo mappa: (giocatore_id/pick_id/team_id_da) → team_id_a
    for sq in squadre:
        team_a_map: dict = {}
        # Per ogni altra squadra, guarda cosa riceve di questo team
        for altra in squadre:
            if altra.team_id == sq.team_id:
                continue
            for item in altra.riceve:
                # Se questo item corrisponde a qualcosa che sq cede
                if item.tipo == "giocatore" and item.giocatore_id:
                    team_a_map[("g", item.giocatore_id)] = altra.team_id
                elif item.tipo == "pick" and item.pick_id:
                    team_a_map[("p", item.pick_id)] = altra.team_id
                elif item.tipo == "diritti" and item.giocatore_id:
                    team_a_map[("d", item.giocatore_id)] = altra.team_id

        for item in sq.cede:
            if item.tipo == "giocatore" and item.giocatore_id:
                team_a = team_a_map.get(("g", item.giocatore_id), "?")
                _db.aggiungi_item_trade(trade_id, "giocatore", sq.team_id, team_a,
                                        giocatore_id=item.giocatore_id)
            elif item.tipo == "pick" and item.pick_id:
                team_a = team_a_map.get(("p", item.pick_id), "?")
                _db.aggiungi_item_trade(trade_id, "pick", sq.team_id, team_a,
                                        pick_id=item.pick_id)
            elif item.tipo == "diritti" and item.giocatore_id:
                team_a = team_a_map.get(("d", item.giocatore_id), "?")
                _db.aggiungi_item_trade(trade_id, "diritti", sq.team_id, team_a,
                                        giocatore_id=item.giocatore_id)

    return trade_id


# ── formattazione output standard ────────────────────────────────────────────

def formatta_trade(squadre: list[SezioneGM]) -> str:
    """Produce il testo della trade nel formato standard della lega."""
    righe = []

    def _label(item: ParsedItem) -> str:
        if item.tipo == "giocatore":
            nome = item.nome_resolved or item.nome_raw
            return f"{nome} {item.importo}x{item.anni}"
        if item.tipo == "pick":
            rnd  = "1st" if item.round == 1 else "2nd"
            return f"{rnd} round pick {item.anno} by {item.by_raw}"
        if item.tipo == "diritti":
            return f"Diritti di {item.nome_resolved or item.nome_raw}"
        return item.raw

    if len(squadre) == 2:
        # Formato compatto: solo sezioni "cede"
        for sq in squadre:
            righe.append(f"<b>{sq.team_nome} cede:</b>")
            for item in sq.cede:
                righe.append(f"  {_label(item)}")
            righe.append("")
    else:
        # Formato esteso: cede + riceve
        for sq in squadre:
            righe.append(f"<b>{sq.team_nome} cede:</b>")
            for item in sq.cede:
                righe.append(f"  {_label(item)}")
            righe.append("")
        for sq in squadre:
            righe.append(f"<b>{sq.team_nome} riceve:</b>")
            for item in sq.riceve:
                righe.append(f"  {_label(item)}")
            righe.append("")

    return "\n".join(righe).strip()
