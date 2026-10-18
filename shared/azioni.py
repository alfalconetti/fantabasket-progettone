"""
Registro delle azioni (v6.0.0, accountability; specifica approvata da Luca il 19/10). Non è il
«registro unico» dei movimenti (transazioni): quello dice cosa si è mosso, questo chi ha fatto cosa.

Ogni azione che cambia qualcosa, in qualsiasi bot, lascia una riga in `registro_azioni` (database
condiviso): chi l'ha fatta, in che veste, cosa, su quale squadra e giocatore, com'era prima e com'è
dopo. Le azioni da admin e da dev vanno anche sul canale log del bot, in un formato unico; quelle
dei GM e dei job solo nel registro (niente rumore). Si consulta con /registro (bot principale): gli
admin vedono tutto, un GM le righe della sua squadra.

Vesti:
  gm       flussi dei GM (anche un admin che agisce da GM, dal menu normale)
  admin    pannello e comandi admin
  dev      comandi dev (giocatori creati o modificati, sync, broadcast, passaggi di stagione rifatti)
  sistema  job automatici (estrazioni, scadenze, calcolo)
La veste la dice il flusso che chiama, mai un «è admin?» (regola: dal menu normale niente superpoteri).

Il registro non deve mai far fallire un'azione: si scrive dopo che l'azione è riuscita, e un errore
qui finisce solo nel log del processo.

Nessuna dipendenza dai bot: riceve q (la funzione di query del bot, q(sql, params, one=, many=)).
"""
import html
import json
import logging

logger = logging.getLogger(__name__)

VESTI = ("gm", "admin", "dev", "sistema")
SUL_LOG = ("admin", "dev")              # le vesti che vanno anche sul canale log
NOMI_BOT = {"main": "bot principale", "aste": "bot aste", "louca": "loucabot", "ipa": "IPanchinari"}
_migrato: set = set()


def migra(q) -> None:
    q("""CREATE TABLE IF NOT EXISTS registro_azioni (
            id           BIGSERIAL PRIMARY KEY,
            quando       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            bot          TEXT NOT NULL,
            chi_id       BIGINT,
            chi_nome     TEXT,
            veste        TEXT NOT NULL CHECK (veste IN ('gm', 'admin', 'dev', 'sistema')),
            azione       TEXT NOT NULL,
            squadre      TEXT[] NOT NULL DEFAULT '{}',
            giocatore_id INT,
            oggetto      TEXT,
            prima        TEXT,
            dopo         TEXT,
            nota         TEXT,
            dettagli     JSONB)""")
    q("CREATE INDEX IF NOT EXISTS idx_registro_quando ON registro_azioni (quando DESC)")
    q("CREATE INDEX IF NOT EXISTS idx_registro_squadre ON registro_azioni USING GIN (squadre)")
    q("CREATE INDEX IF NOT EXISTS idx_registro_chi ON registro_azioni (chi_id)")
    q("CREATE INDEX IF NOT EXISTS idx_registro_giocatore ON registro_azioni (giocatore_id)")


def _pronto(q) -> None:
    """migra() una volta per processo. Se due bot partono insieme, il CREATE TABLE IF NOT EXISTS
    dell'uno può fallire mentre l'altro crea la tabella: se a quel punto la tabella c'è, va bene."""
    if id(q) in _migrato:
        return
    try:
        migra(q)
    except Exception:
        if not (q("SELECT to_regclass('registro_azioni') AS t", one=True) or {}).get("t"):
            raise
    _migrato.add(id(q))


def chi(user) -> tuple[int | None, str | None]:
    """(id, nome) di un utente Telegram: «Nome (@username)»."""
    if user is None:
        return None, None
    nome = getattr(user, "full_name", None) or getattr(user, "first_name", None) or str(getattr(user, "id", "?"))
    if getattr(user, "username", None):
        nome += f" (@{user.username})"
    return getattr(user, "id", None), nome


def _testo(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, (dict, list)):
        return json.dumps(x, ensure_ascii=False, default=str)
    return str(x)


def registra(q, bot: str, user, veste: str, azione: str, squadre=(), giocatore_id: int | None = None,
             oggetto=None, prima=None, dopo=None, nota=None, dettagli: dict | None = None) -> dict | None:
    """Scrive la riga. Non solleva mai: se il registro non è raggiungibile, None (e un avviso nel log)."""
    try:
        if veste not in VESTI:
            raise ValueError(f"veste sconosciuta: {veste}")
        _pronto(q)
        chi_id, chi_nome = user if isinstance(user, tuple) else chi(user)
        sq = [s for s in ([squadre] if isinstance(squadre, str) else list(squadre or [])) if s]
        return q("""INSERT INTO registro_azioni (bot, chi_id, chi_nome, veste, azione, squadre, giocatore_id,
                                                oggetto, prima, dopo, nota, dettagli)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                 (bot, chi_id, chi_nome, veste, azione, sq, giocatore_id, _testo(oggetto), _testo(prima), _testo(dopo),
                  _testo(nota), json.dumps(dettagli, ensure_ascii=False, default=str) if dettagli else None), one=True)
    except Exception as err:                     # il registro non deve mai far fallire l'azione
        logger.warning("Registro azioni (%s %s): %s", bot, azione, err)
        return None


def riga_log(r: dict, nomi_squadre=None) -> str:
    """La riga per il canale log (HTML), nel formato unico:
    🛠 admin Nome (@user) · azione · Squadra
    oggetto: prima → dopo · nota"""
    def e(x) -> str:                             # una riga di log resta corta (Telegram: 4096 caratteri)
        x = str(x)
        return html.escape(x if len(x) <= 800 else x[:800] + "…", quote=False)
    icona = "🧰" if r["veste"] == "dev" else "🛠"
    sq = " · ".join(e(nomi_squadre(s) if nomi_squadre else s) for s in (r.get("squadre") or []))
    testa = f"{icona} {r['veste']} {e(r.get('chi_nome') or '?')} · <b>{e(r['azione'])}</b>" + (f" · {sq}" if sq else "")
    corpo = e(r["oggetto"]) if r.get("oggetto") else ""
    if r.get("prima") is not None or r.get("dopo") is not None:
        corpo += (": " if corpo else "") + f"{e(r.get('prima') if r.get('prima') is not None else '—')} → " \
                                           f"<b>{e(r.get('dopo') if r.get('dopo') is not None else '—')}</b>"
    if r.get("nota"):
        corpo += (" · " if corpo else "") + f"<i>{e(r['nota'])}</i>"
    return testa + (f"\n{corpo}" if corpo else "")


async def azione(q, tg_bot, chat_log, bot: str, user, veste: str, azione_: str, nomi_squadre=None,
                 nel_registro: bool = True, **campi) -> dict | None:
    """registra() e, per admin e dev, la riga sul canale log del bot. Non solleva mai.
    nel_registro=False: solo la riga sul log (il riassunto di un'azione in blocco, le cui righe
    sono già nel registro una per una)."""
    r = registra(q, bot, user, veste, azione_, **campi) if nel_registro else None
    if veste in SUL_LOG and tg_bot is not None and chat_log:
        riga = r or {"veste": veste, "chi_nome": (user if isinstance(user, tuple) else chi(user))[1],
                     "azione": azione_, **{k: _testo(v) for k, v in campi.items() if k in ("oggetto", "prima", "dopo", "nota")},
                     "squadre": [campi["squadre"]] if isinstance(campi.get("squadre"), str) else list(campi.get("squadre") or [])}
        try:
            await tg_bot.send_message(chat_id=chat_log, text=riga_log(riga, nomi_squadre), parse_mode="HTML",
                                      disable_web_page_preview=True)
        except Exception as err:
            logger.warning("Riga del registro sul canale log: %s", err)
    return r


def cerca(q, squadra: str | None = None, giocatore_id: int | None = None, chi_id: int | None = None,
          chi_testo: str | None = None, bot: str | None = None, azione_: str | None = None, veste: str | None = None,
          giorni: int | None = None, limite: int = 500) -> list[dict]:
    """Le righe del registro coi filtri dati (tutti facoltativi), dalla più recente."""
    _pronto(q)
    dove, par = [], []
    if squadra:
        dove.append("%s = ANY(squadre)"); par.append(squadra)
    if giocatore_id:
        dove.append("giocatore_id = %s"); par.append(giocatore_id)
    if chi_id:
        dove.append("chi_id = %s"); par.append(chi_id)
    if chi_testo:
        dove.append("chi_nome ILIKE %s"); par.append(f"%{chi_testo}%")
    if bot:
        dove.append("bot = %s"); par.append(bot)
    if azione_:
        dove.append("azione ILIKE %s"); par.append(f"%{azione_}%")
    if veste:
        dove.append("veste = %s"); par.append(veste)
    if giorni:
        dove.append("quando >= NOW() - (%s || ' days')::interval"); par.append(str(int(giorni)))
    sql = "SELECT * FROM registro_azioni" + (" WHERE " + " AND ".join(dove) if dove else "") + " ORDER BY quando DESC, id DESC LIMIT %s"
    par.append(int(limite))
    return q(sql, tuple(par), many=True) or []
