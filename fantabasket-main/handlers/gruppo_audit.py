"""
Gruppo admin di audit (v7.29.0, Luca 24-25/11): il gruppo admin principale si riempiva di «papiri» e ci si perdeva
quello che conta. Nel gruppo di audit vanno l'anti-tanking, i job periodici (controlli dei tabellini, sincronizzazione,
chiusura delle giornate e riepiloghi di IPanchinari, backup settimanale, diritti in scadenza, spalmature) e il
dettaglio di tutti i punteggi del calcolo; nel principale restano trade, convalida (in breve, con gli 0 da controllare
e le partite close) e le richieste dei GM che aspettano una decisione.

/gruppo_audit [LINK] (admin), scritto DENTRO il gruppo nuovo: salva in globals.json l'id del gruppo
(audit_group_id) e, se c'è, il link d'invito (audit_group_link), che compare nel pannello admin e nel messaggio
della convalida. In privato, senza argomenti: com'è impostato. Finché non è impostato, tutto resta nel gruppo admin.
"""
import html

import settings


def link() -> str | None:
    return settings.load_globals().get("audit_group_link")


def riga_link(testo: str = "Gruppo di audit") -> str:
    l = link()
    return f'<a href="{html.escape(l)}">{html.escape(testo)}</a>' if l else ""


async def cmd_gruppo_audit(update, context):
    msg, chat = update.effective_message, update.effective_chat
    if update.effective_user.id not in [int(a) for a in settings.admin_ids()]:
        await msg.reply_text("⛔ Solo admin.")
        return
    g = settings.load_globals()
    if chat.type == "private":
        if g.get("audit_group_id"):
            await msg.reply_text(f"🗂 Gruppo di audit: <code>{g['audit_group_id']}</code>"
                                 + (f"\nLink: {html.escape(g['audit_group_link'])}" if g.get("audit_group_link") else "\nLink: non impostato")
                                 + "\n\nPer cambiarlo: /gruppo_audit [LINK] scritto dentro il gruppo.", parse_mode="HTML")
        else:
            await msg.reply_text("🗂 Gruppo di audit non impostato: tutto va nel gruppo admin.\n\n"
                                 "I bot escono dai gruppi che non conoscono: aggiungi me al gruppo nuovo, esco e ti "
                                 "scrivo qui il suo id; mettilo in globals.json come \"audit_group_id\", poi aggiungi me, "
                                 "loucabot e IPanchinari e scrivi lì /gruppo_audit https://t.me/+… (il link d'invito).")
        return
    if chat.id == g.get("admin_group_id"):
        await msg.reply_text("❌ Questo è il gruppo admin principale: il comando va scritto nel gruppo di audit.")
        return
    l = (context.args or [None])[0]
    if l and not l.startswith(("https://t.me/", "http://t.me/", "t.me/")):
        await msg.reply_text("❌ Il link d'invito deve essere del tipo https://t.me/+…")
        return
    g["audit_group_id"] = chat.id
    if l:
        g["audit_group_link"] = l if l.startswith("http") else "https://" + l
    settings.save_globals(g)
    from handlers.registro import segna_sync
    segna_sync(update.effective_user, "admin", "gruppo di audit impostato", oggetto=str(chat.id), dopo=g.get("audit_group_link") or "")
    await msg.reply_text("✅ Questo è il gruppo di audit: qui arrivano anti-tanking, job periodici e il dettaglio dei punteggi."
                         + ("" if g.get("audit_group_link") else "\nManca il link d'invito: /gruppo_audit https://t.me/+…")
                         + "\nGli altri bot lo leggono al prossimo messaggio, senza riavvio.")


def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [CommandHandler("gruppo_audit", cmd_gruppo_audit)]
