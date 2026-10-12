"""
Comandi admin: chi è admin, come firmarsi nei log e la conferma degli admin quando
un'operazione (annullare un'offerta, riaprire un'asta) manda il cap di una squadra in negativo.
Usato da admin.py e dai moduli admin_*.py.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import teams as tm
import utils


def is_admin(user_id: int) -> bool:
    return user_id in utils.get_admin_ids()


def _admin_label(user) -> str:
    """Costruisce 'Nome (@username)' o 'Nome' se l'username manca."""
    nome = user.first_name or "Admin"
    if user.username:
        return f"{nome} (@{user.username})"
    return nome


# ── conferma degli admin quando un'operazione manda il cap in negativo ──────────

async def _richiedi_conferma_cap_negativo(context, asta: dict, ore: int,
                                           admin_group_id: int, admin_label: str,
                                           cap_disp: int, cap_virt: int, cap_post: int,
                                           callback_prefix: str):
    """
    Invia al gruppo admin un warning con bottone di conferma per operazione
    che porterebbe il cap virtuale in negativo.
    callback_prefix: 'riapri_cap' o 'annulla_off_cap'
    """
    team_id = asta["offerente_team_id"]
    team_data = tm.get_team_by_id(team_id)
    team_nome = team_data["nome"] if team_data else team_id
    deficit = cap_post - cap_disp

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Confermo, procedi",
            callback_data=f"{callback_prefix}:{asta['id']}:{ore}"
        ),
        InlineKeyboardButton("❌ Annulla", callback_data="admin_noop"),
    ]])
    await context.bot.send_message(
        chat_id=admin_group_id,
        text=(
            f"⚠️ <b>Attenzione — cap virtuale negativo</b>\n\n"
            f"L'operazione richiesta da <b>{admin_label}</b> su <b>{asta['giocatore']}</b> "
            f"porterebbe <b>{team_nome}</b> a cap virtuale negativo:\n"
            f"Cap disponibile: {cap_disp}M\n"
            f"Cap virtuale attuale: {cap_virt}M\n"
            f"Cap virtuale dopo: <b>{cap_post}M (+{deficit}M oltre il limite)</b>\n\n"
            f"Confermare per procedere comunque."
        ),
        parse_mode="HTML",
        reply_markup=kb,
    )
