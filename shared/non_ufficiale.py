"""Il gancio per klra (sistemi di punteggio alternativi) nel codice comune (v7.20.1, Luca 21/11: «klra copia quasi
speculare di loucabot, a parte i sistemi»).

klra usa i comandi di loucabot e quelli in comune (`/rendimento`, `/confronto`, `/rendimento_situazione`,
`/rendimento_team`, la Quasi Cup…) dentro `klra.motore.contesto`. Lì imposta queste ContextVar; fuori (bot principale,
loucabot) sono vuote e tutto funziona come prima:
- `fp(riga)`: i fantapunti di una partita (un tabellino con le statistiche); col sistema, rifatti coi suoi pesi e bonus;
- `fm_bref(riga)`: la fantamedia di una stagione di Basketball-Reference (le medie a partita); col sistema, coi suoi
  pesi; i bonus per partita non si possono calcolare dalle medie → `nota_bref()` lo dice, solo se il sistema ne ha;
- `marca(d)`: i dati di un'immagine con striscia rossa e filigrana NON UFFICIALE (i template le leggono);
- `chiave()`: da aggiungere alle cache che dipendono dal sistema.
"""
import contextvars

_ETICHETTA = contextvars.ContextVar("nu_etichetta", default=None)    # testo della striscia (None: ufficiale)
_FP = contextvars.ContextVar("nu_fp", default=None)                  # funzione(riga) -> fantapunti
_FM = contextvars.ContextVar("nu_fm_bref", default=None)             # funzione(riga bref) -> fantamedia
_NOTA_BREF = contextvars.ContextVar("nu_nota_bref", default="")
_CHIAVE = contextvars.ContextVar("nu_chiave", default="")


class sistema:
    """with non_ufficiale.sistema(etichetta, fp=…, fm_bref=…, nota_bref=…, chiave=…): dentro, il codice comune usa il sistema."""
    def __init__(self, etichetta: str, fp=None, fm_bref=None, nota_bref: str = "", chiave: str = ""):
        self.v = (etichetta, fp, fm_bref, nota_bref, chiave)

    def __enter__(self):
        self.t = [c.set(x) for c, x in zip((_ETICHETTA, _FP, _FM, _NOTA_BREF, _CHIAVE), self.v)]
        return self

    def __exit__(self, *a):
        for c, t in zip((_ETICHETTA, _FP, _FM, _NOTA_BREF, _CHIAVE), self.t):
            c.reset(t)
        return False


def attivo() -> bool:
    return _ETICHETTA.get() is not None


def fp(r: dict) -> float:
    f = _FP.get()
    return float(f(r)) if f else float(r.get("fp") or 0)


def fm_bref(r: dict) -> float:
    f = _FM.get()
    return float(f(r)) if f else float(r.get("fantamedia") or 0)


def nota_bref() -> str:
    return _NOTA_BREF.get() if attivo() else ""


def chiave() -> str:
    return _CHIAVE.get()


def marca(d: dict) -> dict:
    e = _ETICHETTA.get()
    return {**d, "filigrana": "NON UFFICIALE", "striscia": e} if e else d
