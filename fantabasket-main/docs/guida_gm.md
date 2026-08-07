# Guida GM — Fantabasket Main Bot

## Menu principale

Usa `/menu` o `/start` per aprire il menu interattivo. Da lì accedi a Trade, Tagli, Rookie e Roster con bottoni inline — nessun comando da ricordare.

Tutti i flussi si chiudono automaticamente dopo **5 minuti di inattività**. Usa `/annulla` in qualsiasi momento per uscire da un'operazione in corso.

---

## Roster

`/roster` — genera una foto del tuo roster attuale.

`/roster <team_id>` — roster di qualsiasi squadra.

`/roster <DD-MM-YY>` — tuo roster a una data specifica (utile per verificare lo stato dopo una trade).

`/roster <team_id> <DD-MM-YY>` — combinazione dei due.

---

## Trade

### Modalità Builder

Dal menu → Trade → **Build**. Scegli quante squadre (2-4), poi per ogni squadra seleziona cosa cede: giocatori, pick o diritti rookie. Premi ← Indietro per correggere, ✅ Conferma squadra quando hai finito.

Al termine vedi il riepilogo con la validazione (cap, roster size, Stepien Rule). Puoi:
- **Proponi ai GM** — le altre squadre ricevono la proposta in privato e votano
- **Manda ad admin** — vai direttamente all'approvazione senza voto GM

### Modalità Import

Dal menu → Trade → **Import**. Invia il testo nel formato standard:

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

Per trade a 3+ squadre aggiungi anche le sezioni "riceve":
```
Nome GM riceve:
...
```

Se ci sono errori (giocatore non trovato, pick non nel DB, GM non riconosciuto) la bozza **non viene salvata** — correggi e reinvia.

### Bozze

Le bozze sono numerate per team (es. **Bozza #3**). Il numero definitivo (TRADE-2025-001) viene assegnato solo all'approvazione admin.

`/bozze_trade` — lista tutte le tue bozze attive.

### Trade dipendenti

Da una bozza esistente puoi creare una seconda trade che dipende dalla prima — se la prima viene rifiutata, la seconda viene annullata automaticamente.

---

## Tagli

Dal menu → **Tagli** → scegli il giocatore. Il bot mostra l'anteprima della spalmata cap calcolata automaticamente prima di chiedere la conferma.

`/taglia <giocatore>` — alternativa testuale.

**Nota:** se stai rifirmando un giocatore che hai tagliato in precedenza, il bot somma automaticamente la spalmata residua al nuovo contratto.

---

## Rookie

Dal menu → **Rookie** → scegli il giocatore con diritti 2nd pick disponibili. Inserisci l'importo (il contratto è sempre x1 per questa modalità).

`/attiva_diritti` — alternativa testuale.

---

## Il tuo team

`/my_team` — visualizza nome squadra, nome GM e colori. Premi i bottoni per modificarli.

I **colori** vanno inseriti nel formato `#RRGGBB` (es. `#1A237E`). Il colore primario viene usato nell'header del roster PNG. Il colore secondario (opzionale) colora le righe alternate.
