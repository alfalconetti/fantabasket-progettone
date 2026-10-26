"""
Quintetti: uno per squadra, un giocatore per ruolo (PG, SG, SF, PF, C), nel suo ruolo di roster.
Non si reinseriscono ogni giornata: restano quelli che sono finché qualcuno li cambia.

- Gli admin li caricano: /quintetto_admin SQUADRA con 5 righe, oppure /quintetti_import con tutte
  le squadre (blocchi "Squadra" + 5 righe, il formato dello script da console su Yahoo).
- I GM li cambiano con /quintetto (bottoni) e confermano dal promemoria.
- Promemoria alle 8:00 (Roma) dell'ultimo giorno prima della prima partita della giornata: a ogni
  GM il quintetto, le partite di ogni giocatore nella giornata e i bottoni Confermo / Modifico,
  validi fino alla scadenza.
- Riepilogo agli admin 2 ore prima della scadenza (chi ha confermato, modificato, niente;
  panchine mandate; incompatibilità). Alla scadenza i quintetti si congelano in ipa_formazioni
  (quelli che userà il calcolo) e agli admin va l'elenco di chi non ha mandato la panchina.

- Gli admin possono confermare il quintetto di una squadra prima della scadenza (✅ nell'editor di
  /quintetto_admin SQUADRA), come farebbe il GM.
- Dopo la scadenza gli admin controllano le formazioni su Yahoo: /controlli [N] le elenca tutte con
  ☑️ controllata / ⬜ da controllare e un bottone per squadra (chi e quando, tabella ipa_controlli).
  Una correzione dell'admin alla formazione di una giornata chiusa la segna controllata da sola.

Callback (con la squadra): q:c:<team>:<ruolo> scegli ruolo · q:s:<team>:<ruolo>:<gid> giocatore ·
q:ok:<team>:<giornata> confermo · q:mod:<team>:<giornata> modifico · q:v:<team> torna al quintetto ·
q:ck:<team>:<giornata> controllata sì/no (editor admin) · ck:<giornata>:<team> controllata sì/no
(/controlli) · ck:<giornata>:- aggiorna.
"""
import logging
from datetime import timedelta

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import abbina
import config
import db
from comune import (FAVORE, ROMA, adesso, stati, aperta, chi, e, giornata_in_corso, log, ora, ora_promemoria, partite_squadre_nba,
                    prossima_giornata, testo_partite)

logger = logging.getLogger(__name__)
RUOLI = db.RUOLI
RIEPILOGO_PRIMA = timedelta(hours=2)


# ── lettura del quintetto da testo (admin, import) ─────────────────────────────

def leggi_quintetto(team_id: str, righe: list[str]) -> tuple[dict[str, int], list[str]]:
    """({ruolo: giocatore_id}, errori). Una riga per giocatore, con o senza il ruolo davanti
    ("PG Ja Morant", "Morant"); il ruolo vale quello di roster."""
    s = config.stagione()
    roster = db.roster(team_id, s)
    per_id = {g["id"]: g for g in roster}
    out, errori = {}, []
    for r in [x.strip() for x in righe if x.strip()]:
        r = abbina.RE_NUMERO.sub("", r)
        pezzi = r.split(maxsplit=1)
        ruolo_scritto = pezzi[0].upper().rstrip(":") if pezzi and pezzi[0].upper().rstrip(":") in RUOLI else None
        nome = pezzi[1] if ruolo_scritto and len(pezzi) > 1 else r
        x = abbina.abbina_riga(nome, roster, db.alias(team_id, list(per_id)))
        if not x["certo"]:
            proposte = ", ".join(per_id[c]["nome_common"] for c in x["candidati"]) or "nessuno"
            errori.append(f"«{r}»: non riconosciuto (forse {proposte})")
            continue
        g = per_id[x["scelto"]]
        ruolo = g.get("ruolo") or ruolo_scritto
        if not ruolo:
            errori.append(f"{g['nome_common']}: senza ruolo per la stagione")
            continue
        if ruolo_scritto and g.get("ruolo") and ruolo_scritto != g["ruolo"]:
            errori.append(f"{g['nome_common']}: scritto {ruolo_scritto} ma il suo ruolo è {g['ruolo']}")
            continue
        if ruolo in out:
            errori.append(f"due {ruolo}: {per_id[out[ruolo]]['nome_common']} e {g['nome_common']}")
            continue
        out[ruolo] = g["id"]
    mancano = [x for x in RUOLI if x not in out]
    if mancano and not errori:
        errori.append("manca " + ", ".join(mancano))
    return out, errori


def incompatibilita(team_id: str, q: dict[str, int] | None = None, admin: bool = False,
                    breve: bool = False) -> list[str]:
    """Titolari che non sono più a roster o sono anche in panchina. Il testo cambia per chi legge:
    al GM (se vuoi aggiorna il quintetto), all'admin (cosa fare: avvisare il GM prima della scadenza,
    dopo è un errore della panchina), breve per gli elenchi (/stato, riepilogo)."""
    s = config.stagione()
    q = q if q is not None else db.quintetto(team_id)
    roster = {g["id"]: g for g in db.roster(team_id, s)}
    out = [f"{ruolo} vuoto" for ruolo in RUOLI if not q.get(ruolo)]
    for ruolo, gid in q.items():
        if gid not in roster:
            out.append(f"{ruolo}: il titolare non è più in squadra")
        elif roster[gid].get("ruolo") and roster[gid]["ruolo"] != ruolo:
            out.append(f"{roster[gid]['nome_common']} ora è {roster[gid]['ruolo']}, non {ruolo}")
    # panchine da guardare: quella della prossima giornata (aperta) e, per l'admin, quella della
    # giornata in corso già chiusa (le sue modifiche valgono anche per quella)
    da_vedere = []
    g = prossima_giornata(s)
    if g:
        da_vedere.append((g, False))
    if admin:
        gc = giornata_in_corso(s)
        if gc and db.stato_giornata(s, gc["numero"])["chiusa"] and (not g or gc["numero"] != g["numero"]):
            da_vedere.append((gc, True))
    for gg, chiusa in da_vedere:
        p = db.panchina(s, gg["numero"], team_id)
        if not p:
            continue
        in_panca = {r["giocatore_id"] for r in p["righe"]}
        for ruolo, gid in q.items():
            if gid not in in_panca:
                continue
            nome = roster.get(gid, {}).get("nome_common", gid)
            if breve:
                out.append(f"{nome} titolare ({ruolo}) e in panchina G{gg['numero']}")
            elif not admin:
                out.append(f"{nome} è titolare ({ruolo}) e anche in panchina: se vuoi aggiorna il quintetto ({FAVORE}), "
                           f"altrimenti se ne occupa un admin")
            elif not chiusa:
                out.append(f"{nome} è titolare ({ruolo}) e anche nella panchina della giornata {gg['numero']}: avvisa "
                           f"il GM di togliere {nome} dalla panchina e rimandarla entro la scadenza ({ora(gg['prima_partita'])}). "
                           f"Se non lo fa, nel calcolo {nome} conta da titolare e in panchina quella posizione vale 0 (gli altri non scalano)")
            else:
                out.append(f"{nome} è titolare ({ruolo}) e anche nella panchina della giornata {gg['numero']}, già "
                           f"iniziata: la panchina non si cambia più, è un errore del GM. Nel calcolo {nome} conta da "
                           f"titolare e in panchina quella posizione vale 0 (gli altri non scalano); l'eventuale penalità la decidono gli admin")
    return out


def testo_quintetto(team_id: str, g: dict | None) -> str:
    s = config.stagione()
    q = db.quintetto(team_id)
    roster = {x["id"]: x for x in db.roster(team_id, s)}
    nba = db.squadre_nba_giocatori(list(q.values()))
    partite = partite_squadre_nba(g) if g else {}
    media = (g.get("media") if g.get("media") is not None else g.get("media_file")) if g else None
    righe = []
    st, _ = stati([g for g in q.values() if g])
    for ruolo in RUOLI:
        gid = q.get(ruolo)
        if not gid:
            righe.append(f"<b>{ruolo}</b> —")
            continue
        nome = roster.get(gid, {}).get("nome_common") or f"giocatore {gid} (non più in squadra)"
        riga = f"<b>{ruolo}</b> {e(nome)}{st.get(gid, '')}"
        if g:
            riga += f"\n      {e(testo_partite(nba.get(gid), partite, media))}"
        righe.append(riga)
    return "\n".join(righe)


# ── quintetto coi bottoni (/quintetto dei GM, /quintetto_admin SQUADRA senza righe) ──
# Callback con la squadra: q:c:<team>:<ruolo> · q:s:<team>:<ruolo>:<gid> · q:ok:<team>:<N> ·
# q:mod:<team>:<N> · q:v:<team>. Il GM agisce sulla sua squadra; un admin su qualsiasi, e le sue
# modifiche valgono anche per la formazione della giornata in corso (come /quintetto_admin).

def _nome_admin(update) -> str:
    u = update.effective_user
    return getattr(u, "first_name", None) or getattr(u, "full_name", None) or str(u.id)


def giornata_da_controllare(s: str | None = None) -> dict | None:
    """La giornata in corso se è chiusa (quintetti congelati), se no l'ultima chiusa."""
    s = s or config.stagione()
    g = giornata_in_corso(s)
    if g and db.stato_giornata(s, g["numero"])["chiusa"]:
        return g
    chiuse = [x for x in db.giornate(s) if db.stato_giornata(s, x["numero"])["chiusa"]]
    return chiuse[-1] if chiuse else None


def _tastiera(team_id: str, g: dict | None, admin: bool = False) -> K:
    tasti = [[B(f"✏️ {r}", callback_data=f"q:c:{team_id}:{r}") for r in RUOLI[:3]],
             [B(f"✏️ {r}", callback_data=f"q:c:{team_id}:{r}") for r in RUOLI[3:]]]
    if g and aperta(g):
        tasti.append([B(f"✅ Conferma per la giornata {g['numero']}" + (" (admin)" if admin else ""),
                        callback_data=f"q:ok:{team_id}:{g['numero']}")])
    if admin:
        gc = giornata_da_controllare()
        if gc:
            fatto = team_id in db.controlli(config.stagione(), gc["numero"])
            tasti.append([B(f"↩️ Togli controllata G{gc['numero']}" if fatto else f"☑️ Segna controllata G{gc['numero']}",
                            callback_data=f"q:ck:{team_id}:{gc['numero']}")])
    tasti.append([B("✖️ Chiudi", callback_data=f"q:x:{team_id}")])
    return K(tasti)


def _testo_editor(team_id: str, g: dict | None, admin: bool = False) -> str:
    t = [f"🏀 <b>Quintetto di {e(config.nome(team_id))}</b>" + (" (admin)" if admin else "")]
    if g:
        t.append(f"Giornata {g['numero']} · scadenza {ora(g['prima_partita'])}")
    t += ["", testo_quintetto(team_id, g)]
    inc = incompatibilita(team_id, admin=admin)
    if inc:
        t += ["", "⚠️ " + "\n⚠️ ".join(e(x) for x in inc)]
    if g:
        st = db.conferme(config.stagione(), g["numero"]).get(team_id)
        t += ["", f"Stato: {'✅ confermato' if st and st['stato'] == 'confermato' else '✏️ modificato' if st else 'non ancora confermato'}"]
    if not admin:
        t += ["", f"ℹ️ Aggiornare il quintetto qui {FAVORE}."]
    if admin:
        in_corso = giornata_in_corso()
        if in_corso:
            t.append(f"Le modifiche valgono anche per la giornata in corso ({in_corso['numero']}).")
        gc = giornata_da_controllare()
        if gc:
            c = db.controlli(config.stagione(), gc["numero"]).get(team_id)
            t.append(f"Formazione G{gc['numero']}: " + (f"☑️ controllata da {e(c['da_nome'] or '?')} ({ora(c['quando'])})"
                                                       if c else "⬜ da controllare su Yahoo"))
    return "\n".join(t)


def giornata_comandi(s: str | None = None) -> tuple[dict | None, dict | None]:
    """(prossima giornata, giornata in corso che blocca). Dalla scadenza di una giornata alle 6:00 del
    giorno dopo il suo ultimo giorno NBA (come per le panchine, Luca 20/10) i comandi non lavorano
    ancora per la giornata dopo: prossima = None e blocco = la giornata in corso."""
    import comune
    blocco = comune.panchine_bloccate(s)
    return (None if blocco else prossima_giornata(s)), blocco


def testo_quintetto_bloccato(g: dict) -> str:
    from comune import fine_blocco
    fine = fine_blocco(g)
    return (f"⏳ C'è la giornata {g['numero']} in corso: il quintetto per la giornata successiva si cambia da "
            f"{ora(fine)} in poi. Per correggere la formazione della giornata {g['numero']} scrivi a un admin.")


async def cmd_quintetto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team = config.squadra_del_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("Non risulti GM di nessuna squadra. Admin: /quintetto_admin SQUADRA.")
        return
    g, blocco = giornata_comandi()
    if blocco:
        await update.effective_message.reply_text(
            f"🏀 <b>Quintetto di {e(team['nome'])}</b>\n\n{testo_quintetto(team['id'], blocco)}\n\n"
            + e(testo_quintetto_bloccato(blocco)), parse_mode="HTML")
        return
    await update.effective_message.reply_text(_testo_editor(team["id"], g), parse_mode="HTML",
                                              reply_markup=_tastiera(team["id"], g))


async def cb_quintetto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parti = q.data.split(":")
    azione, team_id = parti[1], parti[2]
    uid = update.effective_user.id
    suo = uid in config.gm_ids(team_id)
    admin = config.is_admin(uid) and not suo
    if not suo and not admin:
        await q.answer("Non è la tua squadra.", show_alert=True)
        return
    team = config.squadra(team_id)
    s = config.stagione()
    g, blocco = giornata_comandi(s)
    if blocco and not admin and azione in ("c", "s", "ok", "mod"):
        # giornata in corso: il GM non cambia né conferma (vale per la successiva solo dalle 6)
        await q.answer(testo_quintetto_bloccato(blocco)[:190], show_alert=True)
        return
    if azione == "ck":
        admin = config.is_admin(uid)
        if not admin:
            await q.answer("Solo admin.", show_alert=True)
            return
        n = int(parti[3])
        from registro import segna_sync
        if team_id in db.controlli(s, n):
            db.togli_controllo(s, n, team_id)
            segna_sync(update.effective_user, "admin", "controllo formazione tolto", squadre=team_id,
                       oggetto=f"formazione G{n}", prima="☑️ controllata", dopo="da controllare")
            await q.answer("Tolto")
        else:
            db.segna_controllo(s, n, team_id, uid, _nome_admin(update))
            await q.answer("Controllata")
            await log(context.bot, f"☑️ Formazione G{n} {e(team['nome'])} controllata da {chi(update)}")
            segna_sync(update.effective_user, "admin", "formazione controllata", squadre=team_id,
                       oggetto=f"formazione G{n}", prima="da controllare", dopo="☑️ controllata")
        await q.edit_message_text(_testo_editor(team_id, g, admin), parse_mode="HTML", reply_markup=_tastiera(team_id, g, admin))
        return
    if azione in ("ok", "mod"):
        n = int(parti[3])
        gg = db.giornata(s, n)
        if not gg or not aperta(gg):
            await q.answer("La scadenza di questa giornata è passata.", show_alert=True)
            return
        if azione == "ok":
            db.conferma(s, n, team_id, "confermato", uid)
            from registro import segna_sync
            segna_sync(update.effective_user, "admin" if admin else "gm",
                       "quintetto confermato" + (" per conto della squadra" if admin else ""), squadre=team_id,
                       oggetto=f"quintetto G{n}", dopo="confermato")
            await q.answer("Confermato")
            await log(context.bot, f"✅ Quintetto G{n} {e(team['nome'])} confermato da {chi(update)}" + (" (admin)" if admin else ""))
            # dopo la conferma il menu si chiude (Luca, 19/10): resta il riepilogo, e come cambiarlo
            await q.edit_message_text(
                f"✅ <b>Quintetto confermato per la giornata {n}</b>" + (f" ({e(team['nome'])}, da admin)" if admin else "")
                + f"\n\n{testo_quintetto(team_id, gg)}\n\n"
                + (f"Per cambiarlo: /quintetto_admin {e(team['nome'])}." if admin else
                   f"Puoi cambiarlo in qualsiasi momento con /quintetto (per la giornata {n} fino a {ora(gg['prima_partita'])})."),
                parse_mode="HTML")
            return
        else:
            await q.answer()
        g = gg
    elif azione == "c":
        ruolo = parti[3]
        roster = [x for x in db.roster(team_id, s) if x.get("ruolo") == ruolo]
        if not roster:
            await q.answer(f"Nessun {ruolo} in squadra.", show_alert=True)
            return
        att = db.quintetto(team_id).get(ruolo)
        st, quando = stati([x["id"] for x in roster])
        import comune
        md = comune.medie([x["id"] for x in roster])
        tasti = [[B(("• " if x["id"] == att else "") + x["nome_common"] + md.get(x["id"], "") + st.get(x["id"], ""),
                    callback_data=f"q:s:{team_id}:{ruolo}:{x['id']}")]
                 for x in roster] + [[B("↩️ Indietro", callback_data=f"q:v:{team_id}")]]
        await q.answer()
        await q.edit_message_text(f"Chi gioca da <b>{ruolo}</b>?" + (f"\n<i>{quando}</i>" if quando else ""),
                                  parse_mode="HTML", reply_markup=K(tasti))
        return
    elif azione == "s":
        ruolo, gid = parti[3], int(parti[4])
        roster = {x["id"]: x for x in db.roster(team_id, s)}
        if gid not in roster or roster[gid].get("ruolo") != ruolo:
            await q.answer("Non è un giocatore di quel ruolo in squadra.", show_alert=True)
            return
        vecchio_q = db.quintetto(team_id)
        nuovo = {**vecchio_q, ruolo: gid}
        db.salva_quintetto(team_id, nuovo, "admin" if admin else "gm", uid)
        from registro import segna_sync
        segna_sync(update.effective_user, "admin" if admin else "gm",
                   "quintetto cambiato" + (" per conto della squadra" if admin else ""), squadre=team_id,
                   giocatore_id=gid, oggetto=f"quintetto, {ruolo}",
                   prima=(db.nomi_giocatori([vecchio_q[ruolo]]).get(vecchio_q[ruolo]) if vecchio_q.get(ruolo) else "vuoto"),
                   dopo=roster[gid]["nome_common"])
        if g:
            db.conferma(s, g["numero"], team_id, "modificato", uid)
        extra = ""
        if admin:
            in_corso = giornata_in_corso(s)
            if in_corso and db.stato_giornata(s, in_corso["numero"])["chiusa"]:
                db.salva_formazione(s, in_corso["numero"], team_id, nuovo)
                db.segna_controllo(s, in_corso["numero"], team_id, uid, _nome_admin(update))
                extra = f" · anche G{in_corso['numero']} in corso (☑️ controllata)"
        await q.answer("Fatto")
        await log(context.bot, f"✏️ Quintetto {e(team['nome'])}: {ruolo} {e(roster[gid]['nome_common'])} ({chi(update)}"
                               + (", admin" if admin else "") + f"){extra}")
    elif azione == "x":
        await q.answer()
        await q.edit_message_text(_testo_editor(team_id, g, admin)
                                  + ("\n\n<i>Per riaprirlo: /quintetto_admin " + e(team["nome"]) + "</i>" if admin
                                     else "\n\n<i>Per riaprirlo: /quintetto</i>"), parse_mode="HTML")
        return
    else:
        await q.answer()
    await q.edit_message_text(_testo_editor(team_id, g, admin), parse_mode="HTML", reply_markup=_tastiera(team_id, g, admin))


# ── admin ──────────────────────────────────────────────────────────────────────

async def cmd_quintetto_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quintetto_admin SQUADRA [GN], sotto 5 righe (con o senza il ruolo davanti).
    Senza GN: cambia il quintetto attuale e, se c'è una giornata in corso, anche la sua formazione
    (quella del calcolo). Con GN (es. G5): corregge solo la formazione della giornata N."""
    import re
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    righe = (msg.text or "").split("\n")
    prima = righe[0].split(maxsplit=1)
    solo_g = None
    if len(prima) > 1:
        m = re.search(r"\s+[Gg](\d{1,2})\s*$", prima[1])
        if m:
            solo_g, prima[1] = int(m.group(1)), prima[1][:m.start()]
    from shared.squadre import cerca_squadra
    team = cerca_squadra(prima[1], config.squadre()) if len(prima) > 1 else None
    if not team:
        await msg.reply_text("Uso: /quintetto_admin SQUADRA (nome o id) nella prima riga, sotto i 5 titolari. "
                             "Con G5 dopo la squadra corregge la formazione della giornata 5.")
        return
    if not [r for r in righe[1:] if r.strip()]:
        in_corso = giornata_in_corso()
        if solo_g and not (in_corso and in_corso["numero"] == solo_g):
            # una giornata chiusa ma non più in corso: coi bottoni si cambierebbe il quintetto di oggi
            await msg.reply_text(f"Per correggere la formazione della giornata {solo_g} scrivi sotto i 5 titolari, una "
                                 f"riga per giocatore:\n/quintetto_admin {e(team['nome'])} G{solo_g}\nPG …\nSG …\nSF …\nPF …\nC …",
                                 parse_mode="HTML")
            return
        # senza righe (anche con il GN della giornata in corso): l'editor coi bottoni; da admin ogni
        # cambio vale anche per la formazione della giornata in corso
        g, _ = giornata_comandi()
        await msg.reply_text(_testo_editor(team["id"], g, admin=True), parse_mode="HTML",
                             reply_markup=_tastiera(team["id"], g, admin=True))
        return
    q, errori = leggi_quintetto(team["id"], righe[1:])
    if errori:
        await msg.reply_text(f"❌ Quintetto di {e(team['nome'])} non salvato:\n• " + "\n• ".join(e(x) for x in errori),
                             parse_mode="HTML")
        return
    s = config.stagione()
    nomi = {x["id"]: x["nome_common"] for x in db.roster(team["id"], s)}
    elenco = ", ".join(f"{r} {nomi.get(q[r], '?')}" for r in RUOLI)
    if solo_g:
        if not db.stato_giornata(s, solo_g)["chiusa"]:
            await msg.reply_text(f"La giornata {solo_g} non è ancora chiusa: cambia il quintetto senza G{solo_g}.")
            return
        db.salva_formazione(s, solo_g, team["id"], q)
        u = update.effective_user
        db.segna_controllo(s, solo_g, team["id"], u.id, _nome_admin(update))
        await msg.reply_text(f"✅ Formazione della giornata {solo_g} di {e(team['nome'])} corretta (☑️ controllata): {e(elenco)}",
                             parse_mode="HTML")
        await log(context.bot, f"✏️ Formazione G{solo_g} {e(team['nome'])} corretta da {chi(update)}: {e(elenco)}")
        from registro import segna_sync
        segna_sync(update.effective_user, "admin", "formazione corretta", squadre=team["id"], oggetto=f"formazione G{solo_g}",
                   dopo=elenco, nota="a giornata chiusa (☑️ controllata)")
        return
    db.salva_quintetto(team["id"], q, "admin", update.effective_user.id)
    g, _ = giornata_comandi()
    if g:
        db.conferma(s, g["numero"], team["id"], "modificato", update.effective_user.id)
    in_corso = giornata_in_corso(s)
    if in_corso and db.stato_giornata(s, in_corso["numero"])["chiusa"]:
        db.salva_formazione(s, in_corso["numero"], team["id"], q)
        u = update.effective_user
        db.segna_controllo(s, in_corso["numero"], team["id"], u.id, _nome_admin(update))
    await msg.reply_text("✅ " + _testo_editor(team["id"], g)
                         + (f"\n\nAggiornata anche la formazione della giornata in corso ({in_corso['numero']})." if in_corso else ""),
                         parse_mode="HTML")
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "quintetto per conto della squadra", squadre=team["id"], oggetto="quintetto",
               dopo=elenco, nota=f"anche la formazione della G{in_corso['numero']} in corso" if in_corso else None)
    await log(context.bot, f"✏️ Quintetto {e(team['nome'])} impostato da {chi(update)} (admin): {e(elenco)}"
                           + (f" · anche G{in_corso['numero']} in corso" if in_corso else ""))


def importa(testo: str) -> tuple[list[str], list[str]]:
    """Blocchi separati da righe vuote: nome o id della squadra (esatti, senza maiuscole e accenti:
    in un import di massa una ricerca tollerante può sbagliare squadra), poi i 5 titolari.
    (salvati, errori)"""
    from shared.squadre import normalizza

    def cerca_squadra(testo, squadre):
        n = normalizza(testo)
        return next((t for t in squadre if n in (normalizza(t["nome"]), normalizza(t["id"]))), None)
    blocchi, cur = [], []
    for r in testo.splitlines():
        if r.strip():
            cur.append(r.strip())
        elif cur:
            blocchi.append(cur)
            cur = []
    if cur:
        blocchi.append(cur)
    ok, errori = [], []
    for b in blocchi:
        team = cerca_squadra(b[0], config.squadre())
        if not team:
            errori.append(f"«{b[0]}»: squadra non trovata")
            continue
        q, err = leggi_quintetto(team["id"], b[1:])
        if err:
            errori.append(f"{team['nome']}: " + "; ".join(err))
            continue
        db.salva_quintetto(team["id"], q, "import")
        ok.append(team["nome"])
    return ok, errori


async def cmd_quintetti_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quintetti_import con sotto (o in un file .txt allegato) tutte le squadre."""
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    testo = "\n".join((msg.text or msg.caption or "").split("\n")[1:])
    doc = msg.document or (msg.reply_to_message.document if msg.reply_to_message else None)
    if doc:
        testo = bytes(await (await doc.get_file()).download_as_bytearray()).decode("utf-8-sig", errors="replace")
    if not testo.strip():
        await msg.reply_text("Uso: /quintetti_import e sotto, per ogni squadra, il nome nella prima riga e i 5 titolari; "
                             "squadre separate da una riga vuota. Va bene anche un file .txt con didascalia /quintetti_import.")
        return
    ok, errori = importa(testo)
    t = f"✅ Quintetti salvati: {len(ok)}" + (f"\n{e(', '.join(ok))}" if ok else "")
    if errori:
        t += "\n\n❌ Non salvati:\n• " + "\n• ".join(e(x) for x in errori)
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, t, "quintetti-import")
    await log(context.bot, f"📥 /quintetti_import di {chi(update)}: {len(ok)} salvati, {len(errori)} errori")
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "quintetti importati", oggetto=f"{len(ok)} squadre",
               dopo=", ".join(ok)[:500] or "nessuno", nota=f"{len(errori)} errori" if errori else None)


def testo_stato(g: dict) -> str:
    s = config.stagione()
    conf = db.conferme(s, g["numero"])
    panche = db.panchine(s, g["numero"])
    righe = [f"📋 <b>Giornata {g['numero']}</b> · scadenza {ora(g['prima_partita'])}", ""]
    nessuna_conferma, senza_panca = [], []
    chiusa = db.stato_giornata(s, g["numero"])["chiusa"]
    ctrl = db.controlli(s, g["numero"]) if chiusa else {}
    for t in config.squadre():
        c = conf.get(t["id"])
        stato_q = "✅" if c and c["stato"] == "confermato" else "✏️" if c else "—"
        p = panche.get(t["id"])
        inc = incompatibilita(t["id"], breve=True)
        righe.append(f"{stato_q} quintetto · {'🪑' if p else '❌'} panchina"
                     + ((" · ☑️" if t["id"] in ctrl else " · ⬜") if chiusa else "") + f" · {e(t['nome'])}"
                     + (f" ⚠️ {e('; '.join(inc))}" if inc else ""))
        if not c:
            nessuna_conferma.append(t["nome"])
        if not p:
            senza_panca.append(t["nome"])
    righe += ["", "✅ confermato · ✏️ modificato · — niente (quintetto da controllare su Yahoo)"
              + (" · ☑️ formazione controllata da un admin · ⬜ da controllare (/controlli)" if chiusa else "")]
    if nessuna_conferma:
        righe += ["", f"<b>Quintetti da controllare ({len(nessuna_conferma)})</b>: {e(', '.join(nessuna_conferma))}"]
    if senza_panca:
        righe += [f"<b>Panchine mancanti ({len(senza_panca)})</b>: {e(', '.join(senza_panca))}"]
    return "\n".join(righe)


def md_stato(g: dict) -> str:
    """/stato in Markdown (v24): la stessa situazione in una tabella, più leggibile del messaggio."""
    s = config.stagione()
    conf, panche = db.conferme(s, g["numero"]), db.panchine(s, g["numero"])
    chiusa = db.stato_giornata(s, g["numero"])["chiusa"]
    ctrl = db.controlli(s, g["numero"]) if chiusa else {}
    md = lambda x: str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")
    righe = [f"# Stato della giornata {g['numero']}", "",
             f"Scadenza: {ora(g['prima_partita'])} · {'chiusa (formazioni congelate)' if chiusa else 'aperta'} · "
             f"estratto il {adesso().astimezone(ROMA):%d/%m/%Y %H:%M}", "",
             "| Squadra | Quintetto | Panchina | " + ("Formazione | " if chiusa else "") + "Problemi |",
             "|---|---|---|" + ("---|" if chiusa else "") + "---|"]
    for t in config.squadre():
        c = conf.get(t["id"])
        p = panche.get(t["id"])
        stato_q = "✅ confermato" if c and c["stato"] == "confermato" else "✏️ modificato" if c else "— da controllare"
        panca = ("❌ non mandata" if not p else ("⏰ in ritardo" if p.get("in_ritardo") else "🪑 mandata")
                 + (f" ({ora(p.get('inviata'))})" if p.get("inviata") else ""))
        cella_c = ""
        if chiusa:
            x = ctrl.get(t["id"])
            cella_c = (f"☑️ {md(x.get('da_nome') or '?')}" if x else "⬜ da controllare") + " | "
        righe.append(f"| {md(t['nome'])} | {stato_q} | {md(panca)} | {cella_c}{md('; '.join(incompatibilita(t['id'], breve=True)))} |")
    righe += ["", f"Quintetti non confermati: {sum(1 for t in config.squadre() if t['id'] not in conf)} · "
                  f"panchine mancanti: {sum(1 for t in config.squadre() if t['id'] not in panche)}"]
    return "\n".join(righe) + "\n"


def testo_quintetti(n: int | None = None) -> str:
    """Tutti i quintetti, una riga per squadra: quelli attuali, o con N le formazioni congelate
    della giornata N (quelle del calcolo)."""
    s = config.stagione()
    titolo = (f"🏀 <b>Formazioni della giornata {n}</b> (congelate alla scadenza)" if n
              else "🏀 <b>Quintetti attuali</b>")
    righe = [titolo, ""]
    for t in config.squadre():
        q = db.formazione(s, n, t["id"]) if n else db.quintetto(t["id"])
        rosa = {x["id"] for x in db.roster(t["id"], s)}
        nomi = db.nomi_giocatori([g for g in q.values() if g])
        pezzi = []
        for ruolo in RUOLI:
            gid = q.get(ruolo)
            nome = e(nomi.get(gid, "?")) if gid else "—"
            pezzi.append(f"{ruolo} {nome}" + (" ⚠️" if gid and gid not in rosa else ""))
        if len(righe) > 2:
            righe.append("")                     # una riga vuota tra una squadra e l'altra (Luca, 26/10)
        righe.append(f"<b>{e(t['nome'])}</b>: " + " · ".join(pezzi))
    righe += ["", "⚠️ non più in squadra · — ruolo vuoto"]
    return "\n".join(righe)


async def cmd_quintetti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quintetti [N] (admin): tutti i quintetti, una riga per squadra."""
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    if n and not db.stato_giornata(config.stagione(), n)["chiusa"]:
        await update.effective_message.reply_text(f"La giornata {n} non è ancora chiusa: i quintetti attuali con /quintetti.")
        return
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, testo_quintetti(n), f"quintetti-G{n}" if n else "quintetti")


def testo_controlli(g: dict, con_formazioni: bool = True) -> tuple[str, K]:
    """Le formazioni congelate di una giornata chiusa, da controllare su Yahoo: ☑️ / ⬜ e chi."""
    s, n = config.stagione(), g["numero"]
    ctrl, conf = db.controlli(s, n), db.conferme(s, n)
    squadre = config.squadre()
    righe = [f"🔍 <b>Controllo formazioni G{n}</b> su Yahoo · {len([t for t in squadre if t['id'] in ctrl])}/{len(squadre)} fatte", ""]
    for t in squadre:
        c, cf = ctrl.get(t["id"]), conf.get(t["id"])
        gm = "✅" if cf and cf["stato"] == "confermato" else "✏️" if cf else "—"
        riga = f"{'☑️' if c else '⬜'} <b>{e(t['nome'])}</b> (GM {gm})"
        if c:
            riga += f" <i>{e(c['da_nome'] or '?')} {c['quando'].astimezone(ROMA):%d/%m %H:%M}</i>"
        if con_formazioni:
            f = db.formazione(s, n, t["id"])
            nomi = db.nomi_giocatori([x for x in f.values() if x])
            riga += "\n    " + " · ".join(f"{r} {e(nomi.get(f.get(r), '—')) if f.get(r) else '—'}" for r in RUOLI)
        righe.append(riga)
    righe += ["", "Tocca una squadra per segnarla controllata (o toglierlo). Se correggi una formazione con "
                  f"/quintetto_admin SQUADRA G{n} si segna da sola. GM: ✅ confermato · ✏️ modificato · — niente."]
    tasti = [B(("☑️ " if t["id"] in ctrl else "⬜ ") + t["nome"], callback_data=f"ck:{n}:{t['id']}") for t in squadre]
    kb = [tasti[i:i + 2] for i in range(0, len(tasti), 2)] + [[B("🔄 Aggiorna", callback_data=f"ck:{n}:-")]]
    testo = "\n".join(righe)
    if con_formazioni and len(testo) > 3900:
        return testo_controlli(g, con_formazioni=False)[0] + f"\n<i>Formazioni: /quintetti {n}</i>", K(kb)
    return testo, K(kb)


async def cmd_controlli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/controlli [N] (admin): formazioni della giornata chiusa da controllare su Yahoo."""
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    s = config.stagione()
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    g = db.giornata(s, n) if n else giornata_da_controllare(s)
    if not g or not db.stato_giornata(s, g["numero"])["chiusa"]:
        await update.effective_message.reply_text("Nessuna giornata chiusa da controllare" + (f" (la {n} non è chiusa)." if n else "."))
        return
    testo, kb = testo_controlli(g)
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_controlli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = update.effective_user.id
    if not config.is_admin(uid):
        await q.answer("Solo admin.", show_alert=True)
        return
    _, n, team_id = q.data.split(":")
    s, n = config.stagione(), int(n)
    g = db.giornata(s, n)
    if team_id != "-":
        from registro import segna_sync
        if team_id in db.controlli(s, n):
            db.togli_controllo(s, n, team_id)
            segna_sync(update.effective_user, "admin", "controllo formazione tolto", squadre=team_id,
                       oggetto=f"formazione G{n}", prima="☑️ controllata", dopo="da controllare")
            await q.answer("Tolto")
        else:
            db.segna_controllo(s, n, team_id, uid, _nome_admin(update))
            await q.answer("Controllata")
            await log(context.bot, f"☑️ Formazione G{n} {e(config.nome(team_id))} controllata da {chi(update)}")
            segna_sync(update.effective_user, "admin", "formazione controllata", squadre=team_id,
                       oggetto=f"formazione G{n}", prima="da controllare", dopo="☑️ controllata")
    else:
        await q.answer()
    testo, kb = testo_controlli(g)
    try:
        await q.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
    except Exception as err:                       # "message is not modified" su 🔄 senza novità
        logger.info("Controlli: %s", err)


async def cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stato [N]: conferme dei quintetti e panchine di una giornata (la prossima se manca N)."""
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    if n:
        g = db.giornata(config.stagione(), n)
    else:                                           # giornata in corso fino alle 6: quella
        g, blocco = giornata_comandi()
        g = blocco or g
    if not g:
        await update.effective_message.reply_text("Nessuna giornata.")
        return
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, testo_stato(g), f"stato-G{g['numero']}")
    import io
    await context.bot.send_document(chat_id=update.effective_chat.id,                 # la tabella (v24)
                                    document=io.BytesIO(md_stato(g).encode("utf-8")),
                                    filename=f"stato-G{g['numero']}-{adesso().astimezone(ROMA):%Y%m%d-%H%M}.md",
                                    caption=f"📋 Stato della giornata {g['numero']} in tabella")


# ── job: promemoria, riepilogo, chiusura ───────────────────────────────────────

def promemoria(t: dict, g: dict) -> tuple[str, K]:
    """Il promemoria di una squadra per la giornata g (testo e bottoni)."""
    testo = (f"🏀 <b>Giornata {g['numero']}</b> · formazione entro <b>{ora(g['prima_partita'])}</b>\n\n"
             f"Il tuo quintetto ({e(t['nome'])}), con le partite di ognuno:\n\n{testo_quintetto(t['id'], g)}")
    inc = incompatibilita(t["id"])
    if inc:
        testo += "\n\n⚠️ " + "\n⚠️ ".join(e(x) for x in inc)
    testo += (f"\n\nVa bene così o vuoi cambiarlo? Confermarlo o aggiornarlo qui {FAVORE}. "
               "Puoi cambiarlo in qualsiasi momento con /quintetto, anche dopo averlo confermato.\n"
               "La panchina invece sì: mandamela qui, 5 giocatori, uno per riga.")
    tasti = K([[B("✅ Confermo", callback_data=f"q:ok:{t['id']}:{g['numero']}"),
                B("✏️ Modifico", callback_data=f"q:mod:{t['id']}:{g['numero']}")]])
    return testo, tasti


async def manda_promemoria(bot, g: dict) -> int:
    inviati = 0
    for t in config.squadre():
        testo, tasti = promemoria(t, g)
        for uid in config.gm_ids(t["id"]):
            try:
                await bot.send_message(chat_id=uid, text=testo, parse_mode="HTML", reply_markup=tasti)
                inviati += 1
            except Exception as err:          # GM che non ha mai scritto al bot
                logger.info("Promemoria a %s: %s", uid, err)
    return inviati


def ceduti_alla_scadenza(s: str, g: dict, panche: dict) -> tuple[list, list]:
    """([(squadra, [nomi])] panchinari, [(squadra, [nomi])] titolari) che alla scadenza non erano più della
    squadra, dal registro dei movimenti (shared/rosa.py). I panchinari nel calcolo escono e gli altri scalano."""
    from shared import rosa
    scad = g.get("prima_partita")
    out_p, out_q = [], []
    for t in config.squadre():
        p = panche.get(t["id"])
        righe = (p["righe"] if p and isinstance(p["righe"], list) else []) if p else []
        ids_p = [r.get("giocatore_id") for r in righe if r.get("giocatore_id")]
        ids_q = [v for v in db.formazione(s, g["numero"], t["id"]).values() if v]
        cp = rosa.ceduti(db.q, t["id"], ids_p, scad)
        cq = rosa.ceduti(db.q, t["id"], ids_q, scad)
        nomi = db.nomi_giocatori(list(cp | cq))
        if cp:
            out_p.append((t["nome"], [nomi.get(x, str(x)) for x in ids_p if x in cp]))
        if cq:
            out_q.append((t["nome"], [nomi.get(x, str(x)) for x in ids_q if x in cq]))
    return out_p, out_q


async def job_giornate(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 5 minuti: per le giornate aperte promemoria, riepilogo agli admin e chiusura."""
    bot = context.bot
    s = config.stagione()
    ora_ = adesso()
    for g in db.giornate(s):
        scad = g.get("prima_partita")
        if not scad:
            continue
        st = db.stato_giornata(s, g["numero"])
        if st["chiusa"]:
            continue
        if ora_ >= scad:
            db.congela_quintetti(s, g["numero"], [t["id"] for t in config.squadre()])
            db.congela_ruoli_panchine(s, g["numero"])                 # i ruoli dei panchinari per la FADD
            db.segna_stato(s, g["numero"], "chiusa")
            panche = db.panchine(s, g["numero"])
            mancanti = [t["nome"] for t in config.squadre() if t["id"] not in panche]
            try:
                ced_p, ced_q = ceduti_alla_scadenza(s, g, panche)
            except Exception as err:
                logger.warning("Ceduti alla scadenza: %s", err)
                ced_p, ced_q = [], []
            if config.gruppo_admin():
                try:
                    await bot.send_message(chat_id=config.gruppo_admin(), parse_mode="HTML", text=(
                        f"⏰ <b>Giornata {g['numero']} chiusa</b>: quintetti congelati (si correggono anche a giornata "
                        f"in corso con /quintetto_admin)."
                        + (f"\n❌ Senza panchina ({len(mancanti)}): {e(', '.join(mancanti))}" if mancanti else "\n✅ Tutte le panchine arrivate.")
                        + ("\n\n⚠️ <b>Panchine con giocatori non più in squadra</b> (escono dalla panchina, gli altri "
                           "scalano; penalità: decidete voi):\n" + "\n".join(f"• {e(n)}: {e(', '.join(x))}" for n, x in ced_p)
                           if ced_p else "")
                        + ("\n\n⚠️ <b>Titolari non più in squadra</b> (nel calcolo contano finché non li correggete da "
                           "Yahoo con /quintetto_admin):\n" + "\n".join(f"• {e(n)}: {e(', '.join(x))}" for n, x in ced_q)
                           if ced_q else "")))
                except Exception as err:
                    logger.warning("Chiusura al gruppo admin: %s", err)
            from registro import segna_sync
            segna_sync(None, "sistema", "giornata chiusa", oggetto=f"giornata {g['numero']}", dopo="quintetti congelati",
                       nota=(f"senza panchina: {', '.join(mancanti)}" if mancanti else "tutte le panchine arrivate")
                       + (f"; panchine con ceduti: {len(ced_p)}" if ced_p else ""))
            await log(bot, f"⏰ G{g['numero']} chiusa: quintetti congelati, {len(mancanti)} panchine mancanti"
                           + (f", {len(ced_p)} panchine con ceduti" if ced_p else ""))
            continue
        p = ora_promemoria(g)
        if not st["promemoria"] and p and ora_ >= p:
            db.segna_stato(s, g["numero"], "promemoria")
            n = await manda_promemoria(bot, g)
            await log(bot, f"📨 Promemoria G{g['numero']}: {n} messaggi ai GM")
        if not st["riepilogo"] and ora_ >= scad - RIEPILOGO_PRIMA:
            db.segna_stato(s, g["numero"], "riepilogo")
            if config.gruppo_admin():
                from shared.messaggi import manda_lungo
                try:
                    await manda_lungo(bot, config.gruppo_admin(), testo_stato(g), f"stato-G{g['numero']}")
                except Exception as err:
                    logger.warning("Riepilogo al gruppo admin: %s", err)


async def cmd_dev_promemoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dev_promemoria [SQUADRA]: il promemoria della prossima giornata, mandato solo al dev
    (la sua squadra, o quella indicata). Prima riga: quando partirà davvero."""
    if not (config.dev_id() and update.effective_user.id == config.dev_id()):
        return
    from shared.squadre import cerca_squadra
    t = (cerca_squadra(" ".join(context.args), config.squadre()) if context.args
         else config.squadra_del_gm(update.effective_user.id)) or config.squadre()[0]
    g = prossima_giornata()
    if not g:
        await update.effective_message.reply_text("Nessuna giornata aperta.")
        return
    testo, tasti = promemoria(t, g)
    await update.effective_message.reply_text(
        f"<i>Anteprima per {e(t['nome'])}: partirà {ora(ora_promemoria(g))} a {len(config.gm_ids(t['id']))} GM. "
        f"I bottoni funzionano davvero.</i>\n\n" + testo, parse_mode="HTML", reply_markup=tasti)


def get_handlers() -> list:
    from telegram.ext import MessageHandler, filters
    return [
        CommandHandler("dev_promemoria", cmd_dev_promemoria),
        CommandHandler("quintetto", cmd_quintetto),
        CommandHandler("quintetto_admin", cmd_quintetto_admin),
        CommandHandler("quintetti_import", cmd_quintetti_import),
        MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/quintetti_import"), cmd_quintetti_import),
        CommandHandler("stato", cmd_stato),
        CommandHandler("quintetti", cmd_quintetti),
        CommandHandler("controlli", cmd_controlli),
        CallbackQueryHandler(cb_quintetto, pattern=r"^q:"),
        CallbackQueryHandler(cb_controlli, pattern=r"^ck:\d+:[\w-]+$"),
    ]
