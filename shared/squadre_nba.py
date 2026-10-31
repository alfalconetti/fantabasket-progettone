"""
Le 30 squadre NBA: nome, colore principale e logo (v6.13.0, Luca 31/10).

- `NBA`: sigla → (nome, colore), per la barra della carriera e per il segnaposto del logo (tondo col
  colore e la sigla) quando il logo non c'è.
- `sigla(s)`: sigle di ESPN e di Basketball-Reference → le nostre (GS → GSW, PHO → PHX, BRK → BKN…).
- `logo(s)`: il file del logo, se c'è. I loghi li scarica loucabot da ESPN (`nba.scarica_loghi`) in
  config/foto/nba/<SIGLA>.png (la sola cartella di config/ dove loucabot scrive; fuori da git); un logo
  messo a mano in config/loghi/nba/ vale prima di quello di ESPN.
- `squadra(s)`: {"nome", "sigla", "colore", "logo", "nba": True} per i template Typst.
"""
import os

NBA = {
    "ATL": ("Atlanta Hawks", "#C8102E"), "BOS": ("Boston Celtics", "#007A33"), "BKN": ("Brooklyn Nets", "#000000"),
    "CHA": ("Charlotte Hornets", "#1D1160"), "CHI": ("Chicago Bulls", "#CE1141"), "CLE": ("Cleveland Cavaliers", "#860038"),
    "DAL": ("Dallas Mavericks", "#00538C"), "DEN": ("Denver Nuggets", "#0E2240"), "DET": ("Detroit Pistons", "#C8102E"),
    "GSW": ("Golden State Warriors", "#1D428A"), "HOU": ("Houston Rockets", "#CE1141"), "IND": ("Indiana Pacers", "#002D62"),
    "LAC": ("LA Clippers", "#C8102E"), "LAL": ("Los Angeles Lakers", "#552583"), "MEM": ("Memphis Grizzlies", "#5D76A9"),
    "MIA": ("Miami Heat", "#98002E"), "MIL": ("Milwaukee Bucks", "#00471B"), "MIN": ("Minnesota Timberwolves", "#0C2340"),
    "NOP": ("New Orleans Pelicans", "#0C2340"), "NYK": ("New York Knicks", "#006BB6"), "OKC": ("Oklahoma City Thunder", "#007AC1"),
    "ORL": ("Orlando Magic", "#0077C0"), "PHI": ("Philadelphia 76ers", "#006BB6"), "PHX": ("Phoenix Suns", "#1D1160"),
    "POR": ("Portland Trail Blazers", "#E03A3E"), "SAC": ("Sacramento Kings", "#5A2D81"), "SAS": ("San Antonio Spurs", "#8A8D8F"),
    "TOR": ("Toronto Raptors", "#CE1141"), "UTA": ("Utah Jazz", "#002B5C"), "WAS": ("Washington Wizards", "#002B5C"),
}
# sigle di ESPN e di Basketball-Reference → le nostre
SIGLE = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS", "PHO": "PHX", "BRK": "BKN",
         "CHO": "CHA", "NOH": "NOP"}
GRIGIO = "#4B5563"


def sigla(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s).strip().upper()
    return SIGLE.get(s, s)


def cartelle() -> list[str]:
    """Dove cercare i loghi, in ordine: quelli messi a mano, poi quelli scaricati da ESPN."""
    config = os.environ.get("CONFIG_DIR") or os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json"))
    loghi = os.environ.get("LOGHI_DIR") or os.path.join(config, "loghi")
    foto = os.environ.get("FOTO_DIR") or os.path.join(config, "foto")
    return [os.path.join(loghi, "nba"), os.path.join(foto, "nba")]


def cartella_espn() -> str:
    return cartelle()[1]


def logo(s: str | None) -> str:
    s = sigla(s)
    if not s:
        return ""
    for d in cartelle():
        for est in ("png", "jpg", "webp"):
            p = os.path.join(d, f"{s}.{est}")
            if os.path.exists(p):
                return os.path.abspath(p)
    return ""


def squadra(s: str | None) -> dict | None:
    s = sigla(s)
    if not s:
        return None
    nome, colore = NBA.get(s, (s, GRIGIO))
    return {"nome": nome, "sigla": s, "colore": colore, "logo": logo(s), "nba": True}
