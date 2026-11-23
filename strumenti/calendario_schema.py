"""Come è stato trovato SCHEMA di shared/calendario_sorteggio.py (v7.28.0): un risolutore di vincoli (CP-SAT di
OR-Tools, solo qui: «pip install ortools», non serve ai bot) cerca 38 giornate con la struttura di Henry e mai più di K
partite di fila nello stesso campo, col minimo di serie lunghe K. Posti 0-11 = conference A (A1-A12), 12-23 = B.
Uso: python3 strumenti/calendario_schema.py [K=2] [secondi=300]; stampa le righe di SCHEMA da incollare.
Con K=2 e 300 secondi: 96 doppie in tutto (il valore nello SCHEMA del 23/11/2026)."""
import sys
from itertools import combinations
from ortools.sat.python import cp_model

K = int(sys.argv[1]) if len(sys.argv) > 1 else 2; SEC = float(sys.argv[2]) if len(sys.argv) > 2 else 300
A, B = range(12), range(12, 24)
T = range(24)
AND, INT, RIT, ULT = range(0, 11), range(11, 23), range(23, 34), range(34, 38)
m = cp_model.CpModel()
g = {}  # g[i,j,r] = i in casa contro j alla giornata r

def var(i, j, r):
    if (i, j, r) not in g:
        g[i, j, r] = m.NewBoolVar(f"g{i}_{j}_{r}")
    return g[i, j, r]

# andata intraconference: ogni coppia una volta in G1-G11
for conf in (A, B):
    for i, j in combinations(conf, 2):
        m.Add(sum(var(i, j, r) + var(j, i, r) for r in AND) == 1)
        for r in AND:  # ritorno: stessa giornata +23, casa invertita
            m.Add(var(j, i, r + 23) == var(i, j, r)); m.Add(var(i, j, r + 23) == var(j, i, r))
# interconference: ogni A contro ogni B una volta
for a in A:
    for b in B:
        m.Add(sum(var(a, b, r) + var(b, a, r) for r in INT) == 1)
# ultime 4: coppie qualsiasi, mai due volte
for i, j in combinations(T, 2):
    m.Add(sum(var(i, j, r) + var(j, i, r) for r in ULT) <= 1)

casa = {}
for r in range(38):
    for t in T:
        mie_casa = [v for (i, j, rr), v in g.items() if rr == r and i == t]
        mie_fuori = [v for (i, j, rr), v in g.items() if rr == r and j == t]
        m.Add(sum(mie_casa) + sum(mie_fuori) == 1)  # una partita a giornata
        casa[t, r] = m.NewBoolVar(f"c{t}_{r}"); m.Add(casa[t, r] == sum(mie_casa))
for r in INT:
    m.Add(sum(casa[a, r] for a in A) == 6)
for t in T:
    m.Add(sum(casa[t, r] for r in INT) == 6)
    m.Add(sum(casa[t, r] for r in ULT) == 2)
    m.Add(sum(casa[t, r] for r in range(34)) == 17)
    for r in range(38 - K):  # mai più di K di fila
        m.Add(sum(casa[t, r + k] for k in range(K + 1)) >= 1)
        m.Add(sum(casa[t, r + k] for k in range(K + 1)) <= K)
# meno serie lunghe possibile: conta le finestre di K uguali
pen = []
if True:  # conta le finestre di K uguali (con K=2 le «doppie»)
    for t in T:
        for r in range(38 - K + 1):
            s = sum(casa[t, r + k] for k in range(K))
            p = m.NewBoolVar(""); q = m.NewBoolVar("")
            m.Add(s == K).OnlyEnforceIf(p); m.Add(s < K).OnlyEnforceIf(p.Not())
            m.Add(s == 0).OnlyEnforceIf(q); m.Add(s > 0).OnlyEnforceIf(q.Not())
            pen += [p, q]
    m.Minimize(sum(pen))
# simmetria: la posizione 0 gioca con 1 alla G1
m.Add(var(0, 1, 0) == 1)
sol = cp_model.CpSolver(); sol.parameters.max_time_in_seconds = SEC; sol.parameters.num_workers = 8
st = sol.Solve(m)
print(sol.StatusName(st), sol.ObjectiveValue() if pen and st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else "")
if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    lab = lambda p: f"A{p + 1}" if p < 12 else f"B{p - 11}"
    for r in range(38):
        day = sorted([(i, j) for (i, j, rr), v in g.items() if rr == r and sol.Value(v)], key=lambda x: (x[0] >= 12, x[0], x[1]))
        print('    "' + " ".join(f"{lab(c)}-{lab(t)}" for c, t in day) + f'",  # G{r + 1}')
