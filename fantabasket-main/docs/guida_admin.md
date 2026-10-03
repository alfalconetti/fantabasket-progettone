# Guida Admin — Fantabasket Main Bot

## Pannello admin

`/admin_menu` — apre il pannello con tutte le operazioni disponibili.

---

## Approvazione trade

Quando una trade raggiunge l'approvazione (GM hanno accettato, o il proponente l'ha mandata direttamente), ricevi un messaggio nel gruppo admin con riepilogo e bottoni:

- **✅ Approva** — esegue la trade, aggiorna DB, pubblica annuncio nel canale con `TRADE-2026-001`, tuo nome e ora
- **❌ Rifiuta** — annulla e notifica il proponente

### Import e ufficializzazione diretta

Dal pannello admin → **Trade → Import**: importa una trade dal testo nel formato standard. Dopo la validazione puoi ufficializzarla direttamente senza voto GM.

L'annuncio sul canale usa sempre il formato standard con importi e anni contratto.

### Annullamento trade

`/annulla_trade_admin TRADE-2026-XXX` — annulla una trade già eseguita. Il bot verifica la compatibilità del roster prima del rollback.

---

## DPE admin

Dal pannello → **DPE**: attiva direttamente la DPE per un giocatore senza aspettare la richiesta del GM. Selezione team → giocatore → conferma. Operazione immediata con notifica al GM e annuncio canale.

---

## Taglio admin

Dal pannello → **Taglia giocatore**: taglia un giocatore per conto di un team.

---

## Registra firma

`/registra_firma` — registra una firma avvenuta fuori dal bot (ricerca fuzzy giocatore, check contratto attivo, sync GAS automatico).

---

## Cambio fase

Dal pannello → **Cambia fase** oppure `/set_fase`. Il passaggio a `offseason-rinnovi` incrementa automaticamente la stagione corrente.

Fasi disponibili:
```
regular-season-fa → regular-season-deadline → playoff →
offseason-break → offseason-rinnovi → offseason-draft →
offseason-rfa → offseason-fa
```

---

## Loghi squadre

Carica i loghi in `config/loghi/{team_id}_logo.png`. Vengono inclusi automaticamente in `/roster` e `/assets`.

---

## teams.json

Condiviso tra bot main e bot aste. Modifiche impattano entrambi al prossimo riavvio. Campi rilevanti per bot main:
- `gm_nome` — nome del GM (usato negli annunci e nel fuzzy match di `/roster`, `/assets`, `/team_diff`)
- `colore_header` — colore primario per roster/assets PNG
- `colore_riga1`, `colore_riga2`, `colore_sezione`, `colore_pick`, `colore_diritti` — palette personalizzata (i GM la impostano via `/palette`)

---

## Comandi utili

`/annulla_admin` — esce da qualsiasi operazione admin bloccata.

`/sync_sheets` (solo dev) — sincronizzazione manuale completa di tutti i roster e del foglio Scelte su Google Sheets.

---

## Google Sheets — struttura auto-aggiornata

Il bot aggiorna automaticamente i fogli dopo ogni operazione (trade, taglio, DPE, firma, rookie, rollback).

**Foglio Roster**: 15 righe giocatori + SALARY CAP (con `[-N]` se penalità) + età media (formula) + tagli gratuiti usati + cambi ruolo usati (0/2, da implementare) + tagliati con impatto cap + righe DPE in rosso (`DIS. Nome 9x1   7x1`).

**Foglio Scelte**: pick proprie (1st riga 1, 2nd riga 2) + pick altrui per anno + diritti 2nd pick + numeri draft corrente. `[STEPIEN]` indica pick non cedibile senza violare la Stepien Rule. Colori per division. Minimo 4 righe per team.

**Secrets richiesti** (in `secrets/`): `gas_token`, `gas_roster_url`, `gas_scelte_url` (stesso URL del roster).
