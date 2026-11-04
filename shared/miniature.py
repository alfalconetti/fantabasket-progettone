"""
Miniature delle immagini per i PDF (v6.20.0 nel bot principale, in shared dalla v6.22.0 per i PDF di loucabot):
foto e loghi interi in un PDF vettoriale lo gonfiano oltre i 50 MB che Telegram accetta dai bot.
"""
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

_MINI_DIR = os.path.join(tempfile.gettempdir(), "fb_miniature")


def miniatura(path: str, lato: int, jpeg: bool = False) -> str:
    """Una copia piccola dell'immagine (lato lungo `lato` pixel), per il PDF dei roster (v6.20.0, Luca 04/11: in vettoriale
    con le foto intere passava i 50 MB di Telegram). In cache in /tmp, rifatta se l'originale cambia. JPEG su bianco per
    le foto (molto più leggero), PNG per i loghi (la trasparenza serve). Se qualcosa va storto, l'originale."""
    if not path or not os.path.exists(path):
        return path
    try:
        from PIL import Image
        os.makedirs(_MINI_DIR, exist_ok=True)
        st = os.stat(path)
        dest = os.path.join(_MINI_DIR, f"{abs(hash((path, st.st_mtime, lato)))}.{'jpg' if jpeg else 'png'}")
        if not os.path.exists(dest):
            im = Image.open(path)
            im.thumbnail((lato, lato))
            if jpeg:
                fondo = Image.new("RGB", im.size, "white")
                fondo.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[3])
                fondo.save(dest, "JPEG", quality=82)
            else:
                im.save(dest, "PNG", optimize=True)
        return dest
    except Exception as e:
        logger.warning("Miniatura di %s: %s", path, e)
        return path
