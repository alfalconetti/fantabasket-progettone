"""
Messaggi amministrativi potenzialmente lunghi (report, elenchi, diagnostica), per tutti e
due i bot (v3.11.1).

Se il testo sta in un messaggio Telegram si manda così com'è. Se no, si manda un riassunto
breve con allegato il testo completo come file Markdown, generato al volo in memoria (non
resta niente su disco). Prima questi testi venivano spezzati in più messaggi, oppure, oltre
i 4096 caratteri, Telegram li rifiutava proprio.

Uso (il testo è lo stesso HTML che si manderebbe come messaggio):
    from shared.messaggi import manda_lungo
    await manda_lungo(bot, chat_id, testo_html, "stagione-2027")
"""
import html
import io
import re
from datetime import datetime

# sotto i 4096 di Telegram, con un margine per gli a capo e le entità HTML
LIMITE_MESSAGGIO = 3800
LIMITE_DIDASCALIA = 1000


def html_a_markdown(testo: str) -> str:
    """Dal sottoinsieme HTML di Telegram (b, i, u, s, code, pre, a) a Markdown. La prima
    riga diventa il titolo, le righe che iniziano in grassetto diventano sezioni, i "•"
    diventano elenchi puntati."""
    t = testo.replace("\r\n", "\n")
    t = re.sub(r"<pre[^>]*>(.*?)</pre>", lambda m: "\n```\n" + m.group(1).strip("\n") + "\n```\n", t, flags=re.S)
    t = re.sub(r'<a href="([^"]+)">(.*?)</a>', r"[\2](\1)", t, flags=re.S)
    t = re.sub(r"</?b>", "**", t)
    t = re.sub(r"</?(i|em)>", "_", t)
    t = re.sub(r"</?code>", "`", t)
    t = re.sub(r"<[^>]+>", "", t)                 # u, s, tg-spoiler… → testo semplice
    t = html.unescape(t)
    righe = t.split("\n")
    out = []
    for n, riga in enumerate(righe):
        s = riga.rstrip()
        if n == 0 and s.strip():
            out += ["# " + s.replace("**", "").strip(), ""]
            continue
        m = re.match(r"^\*\*(.+?)\*\*(.*)$", s.strip())
        if m and not s.startswith(" "):
            out += ["", "## " + (m.group(1) + m.group(2)).strip(), ""]
            continue
        s = re.sub(r"^\s*[•·] ", "- ", s)
        out.append(s)
    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md


def _riassunto(testo: str) -> str:
    """Prima riga del testo (il titolo), chiusa bene come HTML."""
    prima = testo.strip().split("\n", 1)[0]
    if prima.count("<b>") != prima.count("</b>") or prima.count("<i>") != prima.count("</i>"):
        prima = html.escape(re.sub(r"<[^>]+>", "", prima))
    return prima


async def manda_lungo(bot, chat_id, testo: str, nome_file: str, riassunto: str | None = None,
                      parse_mode: str = "HTML", **kwargs) -> None:
    """Manda `testo` (HTML) a `chat_id`: un messaggio se ci sta, altrimenti `riassunto` (o la
    prima riga del testo) con il testo completo in un file `<nome_file>-<data>.md`.
    `kwargs` vanno al messaggio (per esempio reply_markup), non al file."""
    if len(testo) <= LIMITE_MESSAGGIO:
        await bot.send_message(chat_id=chat_id, text=testo, parse_mode=parse_mode, **kwargs)
        return
    nome = f"{nome_file}-{datetime.now().strftime('%Y-%m-%d')}.md"
    contenuto = io.BytesIO(html_a_markdown(testo).encode("utf-8"))
    contenuto.name = nome
    didascalia = (riassunto or _riassunto(testo)) + "\n<i>Testo completo nel file allegato.</i>"
    if len(didascalia) > LIMITE_DIDASCALIA:
        didascalia = _riassunto(testo) + "\n<i>Testo completo nel file allegato.</i>"
    await bot.send_document(chat_id=chat_id, document=contenuto, filename=nome,
                            caption=didascalia, parse_mode="HTML")
