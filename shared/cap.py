"""
Cap e slot di una squadra: un'implementazione sola per i due bot (v3.12.0).

Prima ogni bot aveva la sua copia delle stesse query (bot principale: database.py, bot
aste: pg_client.py) e una regola nuova andava ricordata in due posti. Ora entrambi chiamano
queste funzioni, passando la propria funzione di query `q(sql, params, one=, many=)`, come
per `shared/ruoli_core.py`.

Regole:
  - anni residui = anni_originali − (stagione − stagione_firma), rookie compresi;
    0 o meno = x0, contratto finito;
  - pesa sul cap un contratto attivo in corso, oppure un x0 dichiarato RFA (rfa_dichiarati);
    con la DPE della stagione pesa l'importo ridotto (prima e dopo la deadline);
  - occupa uno slot un contratto attivo in corso (gli x0 no, RFA compresi), tranne chi ha
    una DPE approvata prima della deadline (regolamento: la DPE dopo la deadline non libera
    lo slot, dà un cambio ruolo);
  - cap occupato = contratti che pesano + impatto dei tagli (spalmature) della stagione.
"""

# frammenti SQL sul contratto `c`; ognuno prende un parametro: la stagione
SQL_IN_CORSO = "(c.anni_originali - (%s::int - c.stagione_firma::int)) >= 1"
SQL_RFA = ("EXISTS (SELECT 1 FROM rfa_dichiarati rd WHERE rd.contratto_id = c.id "
           "AND rd.stagione = %s AND rd.stato = 'attiva')")
SQL_IMPORTO = ("COALESCE((SELECT d.importo_dpe FROM dpe d WHERE d.giocatore_id = c.giocatore_id "
               "AND d.team_id = c.team_id AND d.stagione = %s), c.importo)")
SQL_DPE_LIBERA_SLOT = ("EXISTS (SELECT 1 FROM dpe d WHERE d.giocatore_id = c.giocatore_id "
                       "AND d.team_id = c.team_id AND d.stagione = %s AND d.pre_deadline)")

# Il bot aste può girare su un database in cui il bot principale non ha ancora creato
# rfa_dichiarati (v3.11): in quel caso nessun x0 è RFA, con lo stesso numero di parametri.
_SQL_RFA_ASSENTE = "(%s IS NULL AND FALSE)"
_rfa_presente: dict = {}


def anni_residui(contratto: dict, stagione) -> int:
    """Anni residui di un contratto nella stagione data (0 o meno = finito, x0)."""
    return int(contratto["anni_originali"]) - (int(stagione) - int(contratto["stagione_firma"]))


def tabella_rfa(q) -> bool:
    """La tabella rfa_dichiarati esiste (una volta trovata non si richiede più)."""
    chiave = id(q)
    if not _rfa_presente.get(chiave):
        r = q("SELECT to_regclass('public.rfa_dichiarati') IS NOT NULL AS c", one=True)
        if not (r and r["c"]):
            return False
        _rfa_presente[chiave] = True
    return True


def sql_rfa(q) -> str:
    """Condizione "x0 dichiarato RFA" (parametro: stagione)."""
    return SQL_RFA if tabella_rfa(q) else _SQL_RFA_ASSENTE


def sql_pesa_cap(q) -> str:
    """Condizione "pesa sul cap" (parametri: stagione, stagione)."""
    return f"({SQL_IN_CORSO} OR {sql_rfa(q)})"


SQL_OCCUPA_SLOT = f"({SQL_IN_CORSO} AND NOT {SQL_DPE_LIBERA_SLOT})"   # parametri: stagione, stagione


def cap_contratti(q, team_id: str, stagione) -> int:
    """Somma dei contratti che pesano sul cap, con la DPE ridotta."""
    s = str(stagione)
    r = q(f"""SELECT COALESCE(SUM({SQL_IMPORTO}), 0) AS tot FROM contratti c
              WHERE c.team_id = %s AND c.attivo AND {sql_pesa_cap(q)}""",
          (s, team_id, s, s), one=True)
    return int(r["tot"]) if r else 0


def impatto_taglio(q, team_id: str, stagione) -> int:
    """Spalmature dei tagli che pesano nella stagione."""
    r = q("SELECT COALESCE(SUM(importo), 0) AS tot FROM impatto_taglio WHERE team_id = %s AND stagione = %s",
          (team_id, str(stagione)), one=True)
    return int(r["tot"]) if r else 0


def cap_occupato(q, team_id: str, stagione) -> int:
    return cap_contratti(q, team_id, stagione) + impatto_taglio(q, team_id, stagione)


def giocatori_in_slot(q, team_id: str, stagione) -> int:
    """Quanti giocatori della squadra occupano uno slot."""
    s = str(stagione)
    r = q(f"SELECT count(*) AS n FROM contratti c WHERE c.team_id = %s AND c.attivo AND {SQL_OCCUPA_SLOT}",
          (team_id, s, s), one=True)
    return int(r["n"]) if r else 0


def peso_cap(q, giocatore_id: int, stagione) -> int:
    """Quanto pesa sul cap il contratto attivo del giocatore (0 se non pesa o non c'è)."""
    s = str(stagione)
    r = q(f"""SELECT {SQL_IMPORTO} AS imp, {sql_pesa_cap(q)} AS pesa
              FROM contratti c WHERE c.giocatore_id = %s AND c.attivo""",
          (s, s, s, giocatore_id), one=True)
    return int(r["imp"]) if r and r["pesa"] else 0


def occupa_slot(q, giocatore_id: int, stagione) -> bool:
    """Il contratto attivo del giocatore occupa uno slot nella sua squadra."""
    s = str(stagione)
    r = q(f"SELECT {SQL_OCCUPA_SLOT} AS occ FROM contratti c WHERE c.giocatore_id = %s AND c.attivo",
          (s, s, giocatore_id), one=True)
    return bool(r and r["occ"])


def colonne_roster(q) -> str:
    """Colonne da aggiungere a una query di roster su `contratti c` (parametri, in ordine:
    stagione ×5): importo effettivo (con la DPE), pesa sul cap, occupa uno slot."""
    return (f"{SQL_IMPORTO} AS importo_effettivo, {sql_pesa_cap(q)} AS pesa_cap, "
            f"{SQL_OCCUPA_SLOT} AS occupa_slot")
