import json
import os

SETTINGS_PATH = os.environ.get("SETTINGS_PATH", "/config/settings.json")
GLOBALS_PATH  = os.environ.get("GLOBALS_PATH",  "/config/globals.json")


def get() -> dict:
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_globals() -> dict:
    with open(GLOBALS_PATH, encoding="utf-8") as f:
        return json.load(f)

def save_globals(data: dict):
    with open(GLOBALS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── cap ────────────────────────────────────────────────────────────────────────

def cap_massimo() -> int:
    """Cap regular season (150M). Alias per compatibilità."""
    return get()["cap_regular"]

def luxury_cap() -> int:
    """Cap dinamico: offseason=165M, regular=150M."""
    f = fase()
    if f.startswith("offseason"):
        return get()["cap_offseason"]
    return get()["cap_regular"]

def cap_limite() -> int:
    """Alias di luxury_cap() — nome più chiaro."""
    return luxury_cap()

def salary_floor() -> int:
    return get()["salary_floor"]

# ── roster ─────────────────────────────────────────────────────────────────────

def max_roster() -> int:
    return get()["roster_max"]

def min_roster() -> int:
    return get()["roster_min_regular"]

def min_guardie() -> int:
    return get()["roster_min_guardie"]

def min_ali() -> int:
    return get()["roster_min_ali"]

def min_centri() -> int:
    return get()["roster_min_centri"]

def slot_massimo() -> int:
    """Alias di max_roster()."""
    return max_roster()

# ── contratti ──────────────────────────────────────────────────────────────────

def max_rinnovi_standard() -> int:
    return get()["max_rinnovi_standard"]

def stepien_anni() -> int:
    return get()["stepien_anni"]

def soglia_anni_2() -> int:
    return get()["soglia_anni_2"]

def soglia_anni_3() -> int:
    return get()["soglia_anni_3"]

def ore_comunicazione_ruolo() -> int:
    return get()["ore_comunicazione_ruolo"]

def doncic_soglia_1() -> int:
    return get()["doncic_soglia_1"]

def doncic_soglia_2() -> int:
    return get()["doncic_soglia_2"]

# ── globals ────────────────────────────────────────────────────────────────────

def fase() -> str:
    return load_globals()["fase"]

def stagione_corrente() -> str:
    return load_globals()["stagione_corrente"]

def admin_ids() -> list:
    return load_globals().get("admin_ids", [])

def dev_id() -> int | None:
    return load_globals().get("dev_id")

def admin_group_id() -> int | None:
    return load_globals().get("admin_group_id")

def log_channel_id() -> int | None:
    return load_globals().get("log_channel_id")

# ── business logic ─────────────────────────────────────────────────────────────

def anni_minimi_contratto(importo: int) -> int:
    """Anni minimi obbligatori per importo (20M→2, 35M→3)."""
    if importo >= soglia_anni_3():
        return 3
    if importo >= soglia_anni_2():
        return 2
    return 1

def minimo_contratto_per_media(fantamedia: float) -> int:
    """Compenso minimo per rinnovi/firme in base alla fantamedia."""
    for fascia in get()["tabella_minimo_contratto"]:
        if fascia["da"] <= fantamedia <= fascia["a"]:
            return fascia["minimo"]
    return 1


# ── decorators ─────────────────────────────────────────────────────────────────

def solo_privato(func):
    """Decorator: ignora silenziosamente il comando se non siamo in chat privata."""
    import functools
    from telegram import Update
    from telegram.ext import ContextTypes

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_chat and update.effective_chat.type != "private":
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


FASI_TRADE_APERTE = {
    "regular-season-fa",
    "offseason-rinnovi",
    "offseason-draft",
    "offseason-rfa",
    "offseason-fa",
}

FASI_FA_APERTA = {
    "regular-season-fa",
    "offseason-fa",
}

FASI_MERCATO_APERTO = {
    "regular-season-fa",
    "offseason-fa",
}


def trade_aperte() -> bool:
    return fase() in FASI_TRADE_APERTE

def fa_aperta() -> bool:
    return fase() in FASI_FA_APERTA


def richiede_fase(*fasi_ok: str, msg: str | None = None):
    """
    Decorator: blocca il comando se la fase corrente non è tra quelle consentite.
    """
    import functools
    from telegram import Update
    from telegram.ext import ContextTypes

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            f = fase()
            if f not in fasi_ok:
                testo = msg or f"❌ Comando non disponibile nella fase corrente (<b>{f}</b>)."
                if update.effective_message:
                    await update.effective_message.reply_text(testo, parse_mode="HTML")
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
