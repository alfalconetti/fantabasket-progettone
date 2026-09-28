# Guida GM — Fantabasket Main Bot

## Menu principale

Usa `/menu` per aprire il menu interattivo. Da lì accedi a Trade, Tagli, Rookie, Roster e Assets con bottoni inline — nessun comando da ricordare.

Tutti i flussi si chiudono automaticamente dopo **5 minuti di inattività**. Usa `/annulla` o `/annulla_trade` in qualsiasi momento per uscire da un'operazione in corso.

---

## Roster e Assets

`/roster` — genera una foto del tuo roster attuale.

`/roster <team_id>` — roster di qualsiasi squadra.

`/roster <DD-MM-YY>` — tuo roster a una data specifica (utile per verificare lo stato dopo una trade).

`/assets` — roster completo + pick per anno + diritti rookie.

---

## Trade

### Modalità Builder

Dal menu → Trade → **Build** (oppure `/build_trade`). Scegli quante squadre (2-4), poi per ogni squadra seleziona cosa cede: giocatori, pick o diritti rookie.

Al termine vedi il riepilogo con la validazione (cap, roster size, Stepien Rule). Puoi:
- **📝 Aggiungi nota** — allega un messaggio opzionale visibile alle altre squadre (max 300 caratteri). Usa `/salta` per saltare.
- **✅ Proponi ai GM** — le altre squadre ricevono la proposta in privato e votano
- **📨 Manda ad admin** — vai direttamente all'approvazione senza voto GM
- **💾 Salva bozza** — salva senza inviare, riprendi con `/bozze_trade`
- **✏️ Modifica** — torna all'editor
- **🗑️ Elimina bozza** — cancella

### Modalità Import

Dal menu → Trade → **Import** (oppure `/import_trade`). Invia il testo nel formato standard:

```
TRADE

Nome GM cede:
Giocatore 25x2
1st round pick 2027 by GM
2nd round pick 2028 by GM
Diritti di Nome Rookie

Altro GM cede:
Giocatore 10x1
```

Se ci sono errori (giocatore non trovato, pick non nel DB, GM non riconosciuto) la bozza **non viene salvata** — correggi e reinvia.

### Bozze

`/bozze_trade` — lista tutte le tue bozze attive.

Le bozze hanno label `{AAA}-B{N}` (prime 3 lettere nome team + numero bozza, es. `CHE-B3`). Il riferimento definitivo (TRADE-2026-001) viene assegnato solo all'approvazione admin.

### Votazione

Quando ricevi una proposta di trade avrai i bottoni ✅ Accetta e ❌ Rifiuta. Se rifiuti puoi scegliere di aggiungere una nota di spiegazione — verrà mostrata al proponente.

---

## Tagli

Dal menu → **Tagli** → scegli il giocatore. Il bot mostra l'anteprima della spalmata cap prima di chiedere la conferma.

---

## Rookie

Dal menu → **Rookie** → scegli il giocatore con diritti 2nd pick disponibili. Inserisci l'importo.

---

## Decadimento contratto

`/decadimento` — segnala un contratto decaduto (ritiro del giocatore, firma in altra lega, ecc.). Richiede approvazione admin.

---

## Palette colori

`/palette` — personalizza i colori del roster/assets PNG. Inserisci i colori in formato `#RRGGBB`. Anteprima live prima di salvare.

