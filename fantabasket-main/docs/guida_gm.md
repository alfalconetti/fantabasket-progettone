# Guida GM — Fantabasket Main Bot

## Menu principale

Usa `/menu` per aprire il menu interattivo. Da lì accedi a Trade, Tagli, Rookie, DPE, Roster e Assets con bottoni inline — nessun comando da ricordare.

Tutti i flussi si chiudono automaticamente dopo **5 minuti di inattività**. Usa `/annulla` o `/annulla_trade` in qualsiasi momento per uscire da un'operazione in corso.

---

## Roster e Assets

`/roster` — genera il PNG del tuo roster attuale.

`/roster <squadra>` — roster di qualsiasi squadra. Puoi usare il nome del GM, il nome della squadra (anche parziale o con typo), o il team_id (`team08`).

`/roster <DD-MM-YY>` — tuo roster a una data specifica.

`/assets` — roster completo + pick per anno (★ proprie, ○ altrui) + diritti rookie. Accetta gli stessi argomenti di `/roster`.

`/team_diff` — variazioni roster nell'ultima settimana. Opzionalmente: `/team_diff <squadra>`, `/team_diff <DD-MM-YY>`, `/team_diff <DD-MM-YY> <DD-MM-YY>`.

---

## Trade

### Modalità Builder

Dal menu → Trade → **Build** (oppure `/build_trade`). Scegli quante squadre (2-4), poi per ogni squadra seleziona cosa cede: giocatori, pick o diritti rookie.

Al termine vedi il riepilogo con la validazione (cap, roster size, Stepien Rule). Puoi:
- **📝 Aggiungi nota** — allega un messaggio opzionale visibile alle altre squadre. Usa `/salta` per saltare.
- **✅ Proponi ai GM** — le altre squadre ricevono la proposta in privato e votano
- **📨 Manda ad admin** — vai direttamente all'approvazione senza voto GM
- **💾 Salva bozza** — salva senza inviare, riprendi con `/bozze_trade`
- **✏️ Modifica** — torna all'editor
- **🗑️ Elimina bozza** — cancella

### Modalità Import

Dal menu → Trade → **Import** (oppure `/import_trade`). Invia il testo nel formato standard della lega:

```
TRADE

Nome GM cede:
Giocatore 25x2
1st round pick 2027 by AltroGM
2nd round pick 2028 by AltroGM
Diritti di Nome Rookie

Altro GM cede:
Giocatore 10x1
```

Se ci sono errori (giocatore non trovato, pick non nel DB, GM non riconosciuto) la bozza **non viene salvata** — correggi e reinvia.

### Bozze

`/bozze_trade` — lista le tue bozze attive con bottoni diretti. Clicca su una bozza per modificarla, o su una trade in votazione per vedere il riepilogo e votare.

`/edit_trade <N>` — apre direttamente l'editor della bozza numero N (il numero che vedi nella label, es. `/edit_trade 3`).

Le bozze hanno label `BUF03-3` (prime 3 lettere nome team + numero team + numero bozza). Il riferimento definitivo (`TRADE-2026-001`) viene assegnato solo all'approvazione admin.

### Votazione

Quando ricevi una proposta avrai i bottoni ✅ Accetta e ❌ Rifiuta. Se rifiuti puoi aggiungere una nota di spiegazione — verrà mostrata al proponente.

---

## Tagli

Dal menu → **Tagli** → scegli il giocatore. Il bot mostra l'anteprima della spalmata cap prima di chiedere la conferma.

Hai a disposizione **3 tagli gratuiti** a stagione (contratti 1Mx1). Se li esaurisci il taglio è bloccato.

---

## DPE — Disabled Player Exception

`/dpe` — attiva la DPE per un giocatore infortunato. Disponibile da `offseason-rinnovi` fino a `regular-season-deadline`.

Effetti:
- Riduce l'importo del contratto del 25% (arrotondato per eccesso) per la stagione corrente
- **Pre-deadline**: libera uno slot roster
- **Post-deadline**: nessuno slot liberato (cambio ruolo aggiuntivo — da implementare)

La richiesta va approvata da un admin. Il contratto torna all'importo originale dalla stagione successiva.

---

## Rookie

Dal menu → **Rookie** → scegli il giocatore con diritti 2nd pick disponibili. Inserisci l'importo del contratto.

---

## Decadimento contratto

`/decadimento` — segnala un contratto decaduto (ritiro del giocatore, firma in altra lega, ecc.). Richiede approvazione admin.

---

## Palette colori

`/palette` — personalizza i colori del roster/assets PNG. Inserisci i colori in formato `#RRGGBB`. Anteprima live prima di salvare. I colori si applicano a entrambi `/roster` e `/assets`.
