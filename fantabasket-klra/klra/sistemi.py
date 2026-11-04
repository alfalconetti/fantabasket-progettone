"""
I sistemi di punteggio nel database klra: elenco, scelta di ognuno, creazione, modifica, bozze dell'editor.

Regole (Luca, 04/11): l'Ufficiale c'è sempre e segue settings.json; un sistema nuovo nasce sempre come copia di un
altro (qualsiasi); **solo chi l'ha creato** lo modifica, gli altri lo modificano facendone una copia; nessun limite
di numero. Ognuno ha il suo sistema «attivo» (di default l'Ufficiale).
"""
import json
import re

from klra import basi
from klra import regole as KR


def tutti() -> list[dict]:
    return basi.q("SELECT * FROM klra_sistemi ORDER BY ufficiale DESC, predefinito IS NULL, lower(nome)", many=True) or []


def per_id(sid) -> dict | None:
    try:
        return basi.q("SELECT * FROM klra_sistemi WHERE id = %s", (int(sid),), one=True)
    except (TypeError, ValueError):
        return None


def per_nome(nome: str) -> dict | None:
    return basi.q("SELECT * FROM klra_sistemi WHERE lower(nome) = lower(%s)", (nome.strip(),), one=True)


def ufficiale() -> dict:
    return basi.q("SELECT * FROM klra_sistemi WHERE ufficiale", one=True)


def attivo(uid: int) -> dict:
    r = basi.q("""SELECT s.* FROM klra_scelte c JOIN klra_sistemi s ON s.id = c.sistema_id WHERE c.user_id = %s""", (uid,), one=True)
    return r or ufficiale()


def scegli(uid: int, sid: int) -> None:
    basi.q("""INSERT INTO klra_scelte (user_id, sistema_id) VALUES (%s, %s)
              ON CONFLICT (user_id) DO UPDATE SET sistema_id = EXCLUDED.sistema_id, scelto = NOW()""", (uid, sid))


def parametri(s: dict) -> dict:
    from klra import motore
    return motore.parametri(s)


def nome_valido(nome: str) -> str | None:
    """None se va bene, se no il motivo."""
    nome = (nome or "").strip()
    if not 2 <= len(nome) <= 30:
        return "Il nome va da 2 a 30 caratteri."
    if nome.startswith("/") or not re.search(r"\w", nome):
        return "Il nome deve avere almeno una lettera o una cifra e non iniziare con «/»."
    if re.fullmatch(r"[Gg]?\d+|20\d\d", nome):
        return "Un nome fatto solo di numeri si confonde con la giornata: aggiungi una parola."
    if per_nome(nome):
        return f"C'è già un sistema che si chiama «{nome}»."
    return None


def crea(nome: str, uid: int, autore_nome: str, p: dict, base_id: int | None) -> dict:
    return basi.q("""INSERT INTO klra_sistemi (nome, autore, autore_nome, parametri, base_id) VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                  (nome.strip(), uid, autore_nome, json.dumps(KR.completa(p)), base_id), one=True)


def puo_modificare(s: dict, uid: int) -> bool:
    return bool(s) and not s["ufficiale"] and not s.get("predefinito") and s.get("autore") == uid


def aggiorna(sid: int, uid: int, p: dict) -> bool:
    s = per_id(sid)
    if not puo_modificare(s, uid):
        return False
    basi.q("UPDATE klra_sistemi SET parametri = %s, modificato = NOW() WHERE id = %s", (json.dumps(KR.completa(p)), sid))
    return True


# ── bozze dell'editor (restano se si chiude a metà) ──

def bozza(uid: int) -> dict | None:
    r = basi.q("SELECT * FROM klra_bozze WHERE user_id = %s", (uid,), one=True)
    if r and not isinstance(r["parametri"], dict):
        r["parametri"] = json.loads(r["parametri"])
    return r


def apri_bozza(uid: int, base: dict, modifica: bool) -> dict:
    basi.q("""INSERT INTO klra_bozze (user_id, base_id, parametri, modifica_id) VALUES (%s, %s, %s, %s)
              ON CONFLICT (user_id) DO UPDATE SET base_id = EXCLUDED.base_id, parametri = EXCLUDED.parametri,
                modifica_id = EXCLUDED.modifica_id, aggiornata = NOW()""",
           (uid, base["id"], json.dumps(parametri(base)), base["id"] if modifica else None))
    return bozza(uid)


def salva_bozza(uid: int, p: dict) -> None:
    basi.q("UPDATE klra_bozze SET parametri = %s, aggiornata = NOW() WHERE user_id = %s", (json.dumps(p), uid))


def butta_bozza(uid: int) -> None:
    basi.q("DELETE FROM klra_bozze WHERE user_id = %s", (uid,))


def trova_in_args(args: list[str]) -> tuple[dict | None, list[str]]:
    """Un nome di sistema dentro gli argomenti (anche di più parole): (sistema, argomenti rimasti)."""
    parole = [a for a in args]
    low = [a.lower() for a in parole]
    for s in sorted(tutti(), key=lambda x: -len(x["nome"])):
        nn = s["nome"].lower().split()
        for i in range(len(low) - len(nn) + 1):
            if low[i:i + len(nn)] == nn:
                return s, parole[:i] + parole[i + len(nn):]
    return None, parole
