"""
CLI di servizio per lo yahoo-router (da lanciare dentro il container).

  python3 cli.py auth    → bootstrap OAuth (una volta sola)
  python3 cli.py teams   → elenca le squadre di tutte le leghe configurate
"""
import asyncio
import sys

import yahoo_client as yc


async def cmd_auth():
    print("\n1. Apri questo link nel browser e fai login con l'account Yahoo della lega:\n")
    print(yc.auth_url())
    print("\n2. Autorizza l'app e copia il codice che Yahoo ti mostra.\n")
    code = input("Codice: ").strip()
    await yc.exchange_code(code)
    print(f"\n✅ Token salvato in {yc.TOKEN_PATH}")


async def cmd_teams():
    for lid in yc.league_ids():
        lg = await yc.get_league_teams(lid)
        print(f"\n=== {lg['name']}  ({lg['league_key']}, stagione {lg['season']})")
        for t in lg["teams"]:
            comm = "  [commissioner]" if t["is_commissioner"] else ""
            print(f"  {t['team_id']:>2}  {t['name']:<30} {t['manager'] or '-'}{comm}")


COMANDI = {"auth": cmd_auth, "teams": cmd_teams}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMANDI:
        print(__doc__)
        sys.exit(1)
    asyncio.run(COMANDI[sys.argv[1]]())
