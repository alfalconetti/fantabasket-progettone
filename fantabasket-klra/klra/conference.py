"""
Conference alternative (v2, Luca 06/11, mockup approvato): si scelgono le squadre della prima conference (le altre
vanno nella seconda); ogni squadra prende **a caso** il posto di una squadra della sua conference nel calendario già
estratto (niente nuova estrazione), e l'accoppiamento resta salvato. Si combinano col sistema di punteggio: due livelli
separati, ognuno ha la sua conference attiva (di default le ufficiali, config/divisions.json).

Le partite del calendario permutato le legge il codice di loucabot al posto di lega_partite (motore.in_conference):
ogni sfida nuova si ricalcola da zero, perché bonus casa e supplementari dipendono dall'avversario.
Si scrive solo nel database klra.
"""
import json
import random

import db
from klra import basi


def _divisioni():
    import os
    path = os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json")), "divisions.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def ufficiali() -> dict[str, list[str]]:
    """{nome della conference: [squadre]} delle conference vere, nell'ordine di divisions.json."""
    d = _divisioni()
    out = {}
    for nome, divs in (d.get("conference") or {}).items():
        out[nome] = sorted(t for t, dv in (d.get("team_div") or {}).items() if dv in divs)
    return out


def nomi() -> list[str]:
    return list(ufficiali())


def configurate() -> bool:
    u = ufficiali()
    return len(u) == 2 and all(u.values())


def mappa_nuova(squadre_a: list[str], rnd: random.Random | None = None) -> dict[str, str]:
    """Ogni squadra prende a caso il posto di una squadra della sua conference (nuova) nel calendario vero."""
    rnd = rnd or random.SystemRandom()
    u = ufficiali()
    na, nb = nomi()
    tutte = sorted(u[na] + u[nb])
    nuove_a = sorted(squadre_a)
    nuove_b = [t for t in tutte if t not in nuove_a]
    posti_a, posti_b = list(u[na]), list(u[nb])
    rnd.shuffle(posti_a)
    rnd.shuffle(posti_b)
    return {**dict(zip(nuove_a, posti_a)), **dict(zip(nuove_b, posti_b))}


def appartenenza(conf: dict) -> dict[str, str]:
    """{squadra: nome della conference} per le conference alternative."""
    na, nb = nomi()
    a = set(conf["squadre_a"] if isinstance(conf["squadre_a"], list) else json.loads(conf["squadre_a"]))
    return {t: (na if t in a else nb) for x in ufficiali().values() for t in x}


def _mappa(conf: dict) -> dict:
    return conf["mappa"] if isinstance(conf["mappa"], dict) else json.loads(conf["mappa"])


def partite_json(conf: dict, stagione: str) -> str:
    """Le partite del calendario vero con le squadre al posto loro: chi ha preso il posto di X gioca le partite di X.
    Da chiamare FUORI da in_conference (legge lega_partite vera)."""
    inv = {posto: t for t, posto in _mappa(conf).items()}
    righe = db.q("SELECT id, stagione, giornata, casa, trasferta FROM lega_partite WHERE stagione = %s", (stagione,), many=True) or []
    return json.dumps([{**r, "casa": inv.get(r["casa"], r["casa"]), "trasferta": inv.get(r["trasferta"], r["trasferta"])} for r in righe])


def tutte() -> list[dict]:
    return basi.q("SELECT * FROM klra_conference ORDER BY lower(nome)", many=True) or []


def per_id(cid) -> dict | None:
    try:
        return basi.q("SELECT * FROM klra_conference WHERE id = %s", (int(cid),), one=True)
    except (TypeError, ValueError):
        return None


def per_nome(nome: str) -> dict | None:
    return basi.q("SELECT * FROM klra_conference WHERE lower(nome) = lower(%s)", (nome.strip(),), one=True)


def attiva(uid: int) -> dict | None:
    """La conference alternativa scelta (None = le ufficiali)."""
    return basi.q("""SELECT c.* FROM klra_scelte s JOIN klra_conference c ON c.id = s.conference_id WHERE s.user_id = %s""",
                  (uid,), one=True)


def scegli(uid: int, cid: int | None) -> None:
    from klra import sistemi as SI
    basi.q("""INSERT INTO klra_scelte (user_id, sistema_id, conference_id) VALUES (%s, %s, %s)
              ON CONFLICT (user_id) DO UPDATE SET conference_id = EXCLUDED.conference_id""",
           (uid, SI.attivo(uid)["id"], cid))


def nome_valido(nome: str) -> str | None:
    import re
    nome = (nome or "").strip()
    if not 2 <= len(nome) <= 30:
        return "Il nome va da 2 a 30 caratteri."
    if nome.startswith("/") or not re.search(r"\w", nome):
        return "Il nome deve avere almeno una lettera o una cifra e non iniziare con «/»."
    if per_nome(nome) or nome.lower() in ("ufficiali", "ufficiale"):
        return f"Ci sono già delle conference che si chiamano «{nome}»."
    return None


def crea(nome: str, uid: int, autore_nome: str, squadre_a: list[str]) -> dict:
    return basi.q("""INSERT INTO klra_conference (nome, autore, autore_nome, squadre_a, mappa) VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                  (nome.strip(), uid, autore_nome, json.dumps(sorted(squadre_a)), json.dumps(mappa_nuova(squadre_a))), one=True)


def puo_modificare(c: dict, uid: int) -> bool:
    return bool(c) and c.get("autore") == uid


def aggiorna(cid: int, uid: int, squadre_a: list[str]) -> bool:
    c = per_id(cid)
    if not puo_modificare(c, uid):
        return False
    basi.q("UPDATE klra_conference SET squadre_a = %s, mappa = %s, modificato = NOW() WHERE id = %s",
           (json.dumps(sorted(squadre_a)), json.dumps(mappa_nuova(squadre_a)), cid))
    return True
