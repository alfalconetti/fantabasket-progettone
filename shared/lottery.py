"""
La lottery del draft (v7.27.1, Luca 23/11), verificabile da chiunque.

- **Matrice e algoritmo di Henry** (il suo `Lottery.py`, «Odds Matrix» del file «Proposta odds Lottery» di Luca, 18/11):
  righe = seed (1 = l'ultima in classifica), colonne = pick 1–12. La matrice è doppiamente stocastica; la scomposizione
  di Birkhoff–von Neumann (deterministica: stessa matrice, stesse permutazioni nello stesso ordine) la scrive come
  somma pesata di permutazioni, e un solo numero uniforme in [0, 1) ne sceglie una: ogni estrazione è un ordine
  valido e, su tante estrazioni, le frequenze sono quelle della matrice. Le funzioni `validate_odds_matrix`,
  `find_perfect_matching`, `birkhoff_decomposition` sono copiate dal suo file (solo i tipi semplificati).
- **Il numero uniforme da drand** (Luca, 15/11): il seme è la `randomness` di un round futuro del beacon pubblico
  drand (League of Entropy, rete quicknet), dichiarato prima; u = primi 8 byte di SHA-256(randomness ‖ "lottery") / 2^64.
  Niente `random` di Python: lo stesso seme dà la stessa estrazione con qualsiasi versione.
- **Penalità** (regolamento, Luca 15/11): `scendi` sposta ogni pick penalizzata delle sue posizioni, le altre salgono
  a riempire; due pick sulla stessa posizione: prima quella pescata meglio.

Senza dipendenze (solo la libreria standard): lo usa anche lo script `strumenti/lottery_verifica.py`.
"""
import hashlib
import json
import urllib.request
from datetime import datetime, timezone


class LotteryError(Exception):
    pass


# dal Lottery.py di Henry (Odds.xlsx, foglio «Odds Matrix», B5:M16). Righe: seed 1..12; colonne: pick 1..12.
ODDS = [
    [0.14, 0.3551853664681282, 0.24380836766850866, 0.1607036925727639, 0.10030257329059931, 0, 0, 0, 0, 0, 0, 0],
    [0.14, 0.5607684347662873, 0.1280081352422556, 0.08391664006491963, 0.053205529008597985, 0.0341012609179395, 0, 0, 0, 0, 0, 0],
    [0.14, 0.05603976578419088, 0.5366790459475915, 0.1178049556311759, 0.07423784690883185, 0.048111124738829024, 0.027127260989380814, 0, 0, 0, 0, 0],
    [0.12, 0.01803016679653696, 0.058021279495446124, 0.5356304981166196, 0.11246842813168241, 0.07223633838935592, 0.0412330056059481, 0.02217073804160677, 0.011117110769874462, 0.00505082535399096, 0.0030317342312659603, 0.0010098750676727738],
    [0.1, 0.005992159478347605, 0.02094515007988616, 0.06276910419466933, 0.5526581185797038, 0.12003540084943723, 0.06818281424589019, 0.03617136051760376, 0.018137466638080437, 0.009064413953770348, 0.004030275529830518, 0.002013735932780601],
    [0.08, 0.0019970583536947388, 0.0069805697073939054, 0.02291194001725045, 0.06506680464141398, 0.5940776205880944, 0.11228265651685958, 0.060275696889583064, 0.030224144897447392, 0.015104874689279837, 0.007051823483507223, 0.004026810215475505],
    [0.07, 0.0009955825474607433, 0.0029828443960331747, 0.008939084703474669, 0.0249518440268299, 0.07678280756556512, 0.6057365728551547, 0.10817608523747259, 0.054242917848719784, 0.027108541190027445, 0.013057596993604061, 0.007026122635657808],
    [0.06, 0.00019872259883806258, 0.0009923144859946744, 0.003965066924973964, 0.009960992794541036, 0.030851404813342212, 0.08279979316175125, 0.6177830209031209, 0.10426117385753118, 0.051103723747481455, 0.0250610870196944, 0.013022699692730764],
    [0.05, 0.00019790507597188458, 0.0009882322135833653, 0.0019743775383594666, 0.003968005747278816, 0.013875574112458329, 0.035765420504013684, 0.08860274456183947, 0.6249903034190579, 0.10278488886480071, 0.050914296479229314, 0.025938251483406893],
    [0.04, 0.00019826986433148255, 0.00019801075435074754, 0.0009890084040221154, 0.001987659885215076, 0.00595763582245875, 0.015925042259702447, 0.03989485909837686, 0.09302114283001378, 0.6428398556812305, 0.1060169271858198, 0.052971588214478456],
    [0.035, 0.0001981632424327636, 0.00019790427179139865, 0.0001976953106767771, 0.000993295499131513, 0.0029772160176551555, 0.006963459293509158, 0.017943032330681726, 0.04298664671580028, 0.09892211812559887, 0.6797428532818742, 0.11387761591084812],
    [0.025, 0.0001984050237793372, 0.00019814573716478992, 0.00019793652109420846, 0.0001989014861744232, 0.000993616184864218, 0.003983974567790018, 0.008982462419714945, 0.02101909302347478, 0.048020758393819814, 0.1110934057951745, 0.7801133008469491],
]


def validate_odds_matrix(matrix: list, tol: float = 1e-7) -> None:
    """Validate that matrix is square and approximately doubly-stochastic."""
    n = len(matrix)
    if n == 0:
        raise LotteryError("Odds matrix is empty.")
    if any(len(row) != n for row in matrix):
        raise LotteryError("Odds matrix must be square: same number of seeds and picks.")
    for i, row in enumerate(matrix, start=1):
        if any(value < -tol for value in row):
            raise LotteryError(f"Odds matrix contains a negative value on row {i}.")
        total = sum(row)
        if abs(total - 1.0) > tol:
            raise LotteryError(f"Seed row {i} sums to {total:.12f}, not 1.0.")
    for col in range(n):
        total = sum(matrix[row][col] for row in range(n))
        if abs(total - 1.0) > tol:
            raise LotteryError(f"Pick column {col + 1} sums to {total:.12f}, not 1.0.")


def find_perfect_matching(support_matrix: list, eps: float) -> list:
    """Find one perfect matching in the positive support graph.

    Returns a list perm where perm[row] = matched column.
    """
    n = len(support_matrix)
    col_to_row = [-1] * n

    def dfs(row: int, seen_cols: list) -> bool:
        for col, value in enumerate(support_matrix[row]):
            if value <= eps or seen_cols[col]:
                continue
            seen_cols[col] = True
            if col_to_row[col] == -1 or dfs(col_to_row[col], seen_cols):
                col_to_row[col] = row
                return True
        return False

    for row in range(n):
        seen = [False] * n
        if not dfs(row, seen):
            raise LotteryError("Could not find a perfect matching in the residual odds matrix.")

    perm = [-1] * n
    for col, row in enumerate(col_to_row):
        if row == -1:
            raise LotteryError("Internal matching error: unmatched column.")
        perm[row] = col
    return perm


def birkhoff_decomposition(matrix: list, eps: float = 1e-12) -> list:
    """Decompose a doubly-stochastic matrix into weighted permutation matrices."""
    validate_odds_matrix(matrix)
    n = len(matrix)
    residual = [[max(0.0, float(value)) for value in row] for row in matrix]
    decomposition: list = []

    # A safe cap for this tiny 12x12 case. A normal decomposition is much shorter.
    max_steps = n * n * 4
    for _ in range(max_steps):
        remaining = sum(sum(row) for row in residual)
        if remaining <= eps * n:
            break

        perm = find_perfect_matching(residual, eps)
        weight = min(residual[row][perm[row]] for row in range(n))
        if weight <= eps:
            break

        decomposition.append((weight, tuple(perm)))
        for row in range(n):
            col = perm[row]
            residual[row][col] -= weight
            if abs(residual[row][col]) <= eps:
                residual[row][col] = 0.0
            elif residual[row][col] < 0:
                residual[row][col] = 0.0
    else:
        raise LotteryError("Birkhoff decomposition did not converge.")

    total_weight = sum(weight for weight, _ in decomposition)
    if not decomposition or abs(total_weight - 1.0) > 1e-7:
        raise LotteryError(f"Invalid decomposition total weight: {total_weight:.12f}")

    # Normalize tiny floating-point drift.
    return [(weight / total_weight, perm) for weight, perm in decomposition]


# ── la scelta con un seme pubblico ────────────────────────────────────────────

_DECOMPOSIZIONE = None


def decomposizione() -> list:
    global _DECOMPOSIZIONE
    if _DECOMPOSIZIONE is None:
        _DECOMPOSIZIONE = birkhoff_decomposition(ODDS)
    return _DECOMPOSIZIONE


def uniforme(randomness_hex: str, etichetta: str = "lottery") -> float:
    """Il numero in [0, 1) dal seme: primi 8 byte di SHA-256(seme ‖ etichetta), diviso 2^64."""
    h = hashlib.sha256(bytes.fromhex(randomness_hex) + etichetta.encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def scegli(u: float) -> tuple:
    """La permutazione (seed → pick) col numero u, come `choose_weighted_permutation` di Henry."""
    cum = 0.0
    dec = decomposizione()
    for peso, perm in dec:
        cum += peso
        if u <= cum:
            return perm
    return dec[-1][1]


def estrai(squadre_per_seed: list, randomness_hex: str) -> list:
    """Le squadre (seed 1 = l'ultima in classifica) → l'ordine delle pick 1..12."""
    if len(squadre_per_seed) != len(ODDS):
        raise LotteryError(f"servono {len(ODDS)} squadre, ne ho {len(squadre_per_seed)}")
    perm = scegli(uniforme(randomness_hex))
    ordine = [None] * len(ODDS)
    for seed, pick in enumerate(perm):
        ordine[pick] = squadre_per_seed[seed]
    return ordine


def impronta() -> str:
    """SHA-256 di questo file: si pubblica prima dell'estrazione, così si sa che il codice non cambia."""
    return hashlib.sha256(open(__file__, "rb").read()).hexdigest()


# ── penalità: le discese ──────────────────────────────────────────────────────

def scendi(ordine: list, discese: dict) -> list:
    """`ordine` (chi ha la 1ª, la 2ª, …), `discese` {voce: posizioni}: l'ordine finale. Ogni pick penalizzata finisce
    esattamente d posizioni più giù (non oltre l'ultima), le altre salgono a riempire; due sulla stessa posizione:
    prima quella che partiva più in alto."""
    pos = {x: i for i, x in enumerate(ordine)}
    pen = [x for x in ordine if discese.get(x)]
    base = [x for x in ordine if not discese.get(x)]
    # dalla destinazione più alta in su; a pari destinazione prima la peggiore, così la migliore le passa davanti
    for x in sorted(pen, key=lambda x: (pos[x] + discese[x], -pos[x])):
        base.insert(min(pos[x] + discese[x], len(base)), x)
    return base


# ── drand (rete quicknet) ─────────────────────────────────────────────────────

CATENA = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"      # quicknet
RELAY = ("https://api.drand.sh", "https://api2.drand.sh", "https://api3.drand.sh", "https://drand.cloudflare.com")


def _get(url: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def info() -> dict:
    """genesis_time e period letti dalla rete (non scritti nel codice)."""
    for base in RELAY:
        try:
            return _get(f"{base}/{CATENA}/info")
        except Exception:
            continue
    raise LotteryError("drand: nessun relay risponde")


def round_al(quando: datetime, inf: dict | None = None) -> int:
    """Il primo round uscito a quell'ora o dopo."""
    inf = inf or info()
    t = quando.timestamp()
    g, p = int(inf["genesis_time"]), int(inf["period"])
    return max(1, int(-(-(t - g) // p)) + 1)


def randomness(rnd: int, servono: int = 2) -> str:
    """La randomness del round, uguale su almeno `servono` relay; se il round non c'è ancora, LotteryError (si riprova
    dopo: vale il round dichiarato, mai un altro)."""
    visti = {}
    for base in RELAY:
        try:
            r = _get(f"{base}/{CATENA}/public/{rnd}")
        except Exception:
            continue
        if int(r.get("round", -1)) == rnd and r.get("randomness"):
            visti.setdefault(r["randomness"], []).append(base)
    for val, chi in visti.items():
        if len(chi) >= servono:
            return val
    raise LotteryError(f"drand: round {rnd} non ancora confermato da {servono} relay ({len(visti)} valori visti)")


def ora_round(rnd: int, inf: dict) -> datetime:
    return datetime.fromtimestamp(int(inf["genesis_time"]) + (rnd - 1) * int(inf["period"]), tz=timezone.utc)
