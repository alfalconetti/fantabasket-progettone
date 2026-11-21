"""Ordine dei comandi nel menu «/» di Telegram (v7.19.0, proposta approvata da Luca il 21/11).

Telegram li mostra nell'ordine della lista passata a set_my_commands; prima era l'ordine in cui erano stati
aggiunti (nel bot principale /menu dopo /watch_soglia). Ogni bot definisce le sue liste come prima (gm, admin =
gm + i suoi, dev = admin + i suoi) e poi le passa qui:
- `ordina(lista, ordine)`: prima i comandi nell'ordine dato, poi gli altri come erano (un comando nuovo non
  previsto finisce in fondo, non sparisce);
- `admin_in_cima(gm, admin, cima)`: per gli admin prima i comandi admin (con `cima` per primi), poi quelli dei GM.
"""


def ordina(lista: list, ordine: list[str]) -> list:
    pos = {c: i for i, c in enumerate(ordine)}
    return sorted(lista, key=lambda b: (pos.get(b.command, len(ordine)), 0))


def admin_in_cima(gm: list, admin: list, cima: tuple = ("admin_menu", "guida_admin")) -> list:
    """`admin` è gm + i comandi admin: diventa comandi admin (quelli in `cima` per primi) + gm."""
    nomi_gm = {b.command for b in gm}
    solo_admin = [b for b in admin if b.command not in nomi_gm]
    return ordina(solo_admin, list(cima)) + list(gm)
