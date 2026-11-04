"""
PDF delle partite (v6.22.0, Luca 04/11), per tutti:
- /pdf_giornata [N]: prima pagina coi risultati della giornata, poi le 12 partite una per pagina come /partita
  (senza numero la giornata di /partita);
- /pdf_partite [SQUADRA] [STAGIONE]: tutte le /partita di una squadra nella stagione finora, in ordine di giornata,
  playoff compresi quando ci saranno (senza squadra la tua, senza stagione quella in corso).

Le pagine sono partita.typ in PDF (vettoriale), con foto e loghi in miniatura (shared/miniature: con le immagini
intere un PDF supera i 50 MB che Telegram accetta dai bot), unite con pypdf; oltre i 45 MB in più file.
"""
import asyncio
import html
import io
import json
import logging
from datetime import datetime, timezone

import config
import db
import partita as PA

logger = logging.getLogger(__name__)
LIMITE = 45 * 1024 * 1024
_IN_CORSO = {"si": False}


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _piccole(d: dict) -> dict:
    """Le stesse informazioni di /partita, con foto e loghi in miniatura."""
    from shared.miniature import miniatura
    d = json.loads(json.dumps(d, default=str))
    for sq in d.get("squadre", []):
        if sq.get("logo"):
            sq["logo"] = miniatura(sq["logo"], 256)
        for r in sq.get("righe", []):
            if r.get("foto"):
                r["foto"] = miniatura(r["foto"], 120, jpeg=True)
    return d


def pagina(d: dict) -> bytes:
    import typst
    return typst.compile(PA.TEMPLATE, root="/", format="pdf", sys_inputs={"dati": json.dumps(_piccole(d), ensure_ascii=False)})


def prima_pagina(titolo: str, sotto: str, righe: list[dict]) -> bytes:
    """La pagina dei risultati: una riga per partita, in grassetto chi vince (o è avanti)."""
    import typst
    corpo = {"titolo": titolo, "sotto": sotto, "righe": righe}
    src = '''#let d = json(bytes(sys.inputs.at("dati")))
#set page(width: 520pt, height: auto, margin: 18pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 10pt)
#text(18pt, weight: "bold", fill: rgb("#39007D"))[#d.titolo] \\
#text(9pt, fill: rgb("#6B6480"))[#d.sotto]
#v(10pt)
#table(columns: (auto, 1fr, auto, auto, auto, 1fr), stroke: (x, y) => (bottom: 0.5pt + rgb("#D6C8F5")), inset: 6pt,
  align: (center, right, right, center, left, left),
  ..d.righe.map(r => (text(fill: rgb("#6B6480"))[#r.k], text(weight: if r.vince == "casa" { "bold" } else { "regular" })[#r.casa],
    text(weight: if r.vince == "casa" { "bold" } else { "regular" })[#r.pc], [–],
    text(weight: if r.vince == "trasferta" { "bold" } else { "regular" })[#r.pt],
    text(weight: if r.vince == "trasferta" { "bold" } else { "regular" })[#r.trasferta])).flatten())
'''
    return typst.compile(src.encode("utf-8"), root="/", format="pdf", sys_inputs={"dati": json.dumps(corpo, ensure_ascii=False)})


def unisci(pagine: list[bytes]) -> list[bytes]:
    """Le pagine in uno o più PDF sotto il limite di Telegram."""
    from pypdf import PdfReader, PdfWriter
    parti = 1
    while True:
        passo = max(1, -(-len(pagine) // parti))
        out = []
        for i in range(0, len(pagine), passo):
            w = PdfWriter()
            for p in pagine[i:i + passo]:
                w.append(PdfReader(io.BytesIO(p)))
            w.compress_identical_objects(remove_identicals=True)
            b = io.BytesIO()
            w.write(b)
            out.append(b.getvalue())
        if all(len(x) <= LIMITE for x in out) or passo == 1:
            return out
        parti += 1


def _riga(k, d: dict) -> dict:
    a, b = d["squadre"]
    return {"k": str(k), "casa": a["nome"], "trasferta": b["nome"], "pc": a["punti"], "pt": b["punti"],
            "vince": a["lato"] if a.get("vince") else (b["lato"] if b.get("vince") else "")}


def pdf_giornata(s: str, n: int, ora: datetime | None = None) -> list[bytes]:
    g = db.giornata(s, n)
    if not g:
        raise ValueError(f"la giornata {n} non c'è")
    ora = ora or datetime.now(timezone.utc)
    dd = [PA.dati(s, n, p["casa"], p["trasferta"], ora) for p in db.partite_giornata(s, n)]
    if not dd:
        raise ValueError(f"nella giornata {n} non ci sono partite")
    stato = dd[0]["stato"]
    sotto = f"{g['dal']:%d/%m} – {g['al']:%d/%m} · " + {"convalidata": "risultati convalidati", "calcolata": "calcolata, da convalidare",
                                                          "in corso": "in corso: punteggi provvisori", "da giocare": "da giocare"}.get(stato, stato)
    prima = prima_pagina(f"Giornata {n}", sotto, [_riga(i, x) for i, x in enumerate(dd, 1)])
    return unisci([prima] + [pagina(x) for x in dd])


def pdf_partite(s: str, team_id: str, ora: datetime | None = None) -> tuple[list[bytes], int]:
    """Tutte le partite di una squadra nella stagione, delle giornate già iniziate."""
    ora = ora or datetime.now(timezone.utc)
    pagine = []
    for g in db.giornate(s):
        if not g.get("prima_partita") or g["prima_partita"] > ora:
            continue
        p = db.partita_squadra(s, g["numero"], team_id)
        if p:
            pagine.append(pagina(PA.dati(s, g["numero"], p["casa"], p["trasferta"], ora)))
    return (unisci(pagine) if pagine else []), len(pagine)


async def _manda(msg, pdfs: list[bytes], nome: str, didascalia: str) -> None:
    for i, b in enumerate(pdfs, 1):
        parte = f" ({i}/{len(pdfs)})" if len(pdfs) > 1 else ""
        await msg.reply_document(document=io.BytesIO(b), filename=f"{nome}{'_' + str(i) if len(pdfs) > 1 else ''}.pdf",
                                 caption=didascalia + parte)


async def cmd_pdf_giornata(update, context):
    msg = update.effective_message
    s = config.stagione()
    arg = next((a.lstrip("Gg") for a in (context.args or []) if a.lstrip("Gg").isdigit()), None)
    g = db.giornata(s, int(arg)) if arg else PA.giornata_di_default(s)
    if not g:
        await msg.reply_text("Nessuna giornata da mostrare." if not arg else f"La giornata {arg} non c'è.")
        return
    if _IN_CORSO["si"]:
        await msg.reply_text("⏳ Sto già preparando un PDF: riprova tra un minuto.")
        return
    _IN_CORSO["si"] = True
    try:
        await msg.reply_text(f"⏳ Preparo il PDF della giornata {g['numero']}: ci vuole qualche secondo…")
        pdfs = await asyncio.to_thread(pdf_giornata, s, g["numero"])
        await _manda(msg, pdfs, f"giornata_{g['numero']}", f"📄 Giornata {g['numero']}: risultati e le partite")
    except Exception as err:
        logger.exception("PDF giornata")
        await msg.reply_text(f"❌ PDF non riuscito: {e(str(err))[:200]}")
    finally:
        _IN_CORSO["si"] = False


async def cmd_pdf_partite(update, context):
    import re
    from shared.squadre import cerca_squadra
    msg = update.effective_message
    args = list(context.args or [])
    s = next((a for a in args if re.fullmatch(r"20\d\d", a)), None) or config.stagione()
    resto = " ".join(a for a in args if a != s).strip()
    sq = cerca_squadra(resto, config.squadre()) if resto else config.squadra_del_gm(update.effective_user.id)
    if not sq:
        await msg.reply_text(f"Squadra non trovata: «{e(resto)}»." if resto else "Uso: /pdf_partite [SQUADRA] [STAGIONE] (es. /pdf_partite Alfa 2026)")
        return
    if _IN_CORSO["si"]:
        await msg.reply_text("⏳ Sto già preparando un PDF: riprova tra un minuto.")
        return
    _IN_CORSO["si"] = True
    try:
        await msg.reply_text(f"⏳ Preparo il PDF delle partite di {sq['nome']} ({s}-{str(int(s) + 1)[-2:]}): ci vuole qualche secondo…")
        pdfs, n = await asyncio.to_thread(pdf_partite, s, sq["id"])
        if not pdfs:
            await msg.reply_text(f"{sq['nome']} non ha ancora giocato partite nella stagione {s}-{str(int(s) + 1)[-2:]}.")
            return
        await _manda(msg, pdfs, f"partite_{sq['id']}_{s}", f"📄 {sq['nome']}: {n} partite della stagione {s}-{str(int(s) + 1)[-2:]}")
    except Exception as err:
        logger.exception("PDF partite")
        await msg.reply_text(f"❌ PDF non riuscito: {e(str(err))[:200]}")
    finally:
        _IN_CORSO["si"] = False
