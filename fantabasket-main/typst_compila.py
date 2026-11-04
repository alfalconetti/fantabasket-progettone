"""
Typst con la libreria Python (`typst` su PyPI, la stessa di loucabot) invece del programma `typst` (v6.24.0, Luca 04/11).

I comandi si costruiscono ancora come per il programma («typst compile --input k=v … --ppi N template uscita»): `esegui`
li legge e chiama la libreria. Così una sola versione di Typst per i due bot (0.15), niente processo per ogni immagine,
errori come eccezioni Python. I font: quelli in /usr/share/fonts (Liberation Sans e Noto Color Emoji del Dockerfile),
indicati esplicitamente come faceva TYPST_FONT_PATHS per il programma.
"""
import os

FONT = ["/usr/share/fonts"]


def leggi(cmd: list[str]) -> tuple[str, str, dict, float | None, str]:
    """(template, uscita, input, ppi, root) da un comando «typst compile …»."""
    inputs, ppi, root, pos = {}, None, "/", []
    i = 2 if cmd[:2] == ["typst", "compile"] else 0
    while i < len(cmd):
        a = cmd[i]
        if a == "--input":
            k, _, v = cmd[i + 1].partition("=")
            inputs[k] = v
            i += 2
        elif a == "--ppi":
            ppi = float(cmd[i + 1])
            i += 2
        elif a == "--root":
            root = cmd[i + 1]
            i += 2
        elif a == "--font-path":
            i += 2
        else:
            pos.append(a)
            i += 1
    if len(pos) != 2:
        raise ValueError(f"comando typst non valido: {pos}")
    return pos[0], pos[1], inputs, ppi, root


def esegui(cmd: list[str]) -> None:
    """Compila come il programma: scrive il PNG o il PDF nel file d'uscita. Errori → RuntimeError("Errore Typst: …")."""
    import typst
    template, uscita, inputs, ppi, root = leggi(cmd)
    formato = "pdf" if uscita.endswith(".pdf") else "png"
    kw = {"root": root, "format": formato, "sys_inputs": inputs, "font_paths": [f for f in FONT if os.path.isdir(f)]}
    if formato == "png" and ppi:
        kw["ppi"] = ppi
    try:
        dati = typst.compile(template, **kw)
    except Exception as err:
        raise RuntimeError(f"Errore Typst: {str(err)[:300]}") from err
    if isinstance(dati, list):                 # più pagine in PNG: la prima (i nostri template sono a pagina unica)
        dati = dati[0]
    with open(uscita, "wb") as f:
        f.write(dati)
