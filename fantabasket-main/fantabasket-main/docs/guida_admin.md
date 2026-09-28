# Guida Admin — Fantabasket Main Bot

## Approvazione trade

Quando una trade raggiunge l'approvazione (i GM hanno accettato o il proponente l'ha mandata direttamente), ricevi un messaggio nel gruppo admin con il riepilogo completo e due bottoni:

- **✅ Approva** — esegue la trade, aggiorna roster e pick nel DB, pubblica l'annuncio nel canale principale con trade_ref (es. TRADE-2025-001), tuo nome e ora
- **❌ Rifiuta** — annulla la trade e notifica il proponente

L'annuncio sul canale principale include sempre: testo trade completo, "Approvata da [tuo nome] alle [ora] — ID: TRADE-2025-001".

## Loghi squadre

Carica i loghi in `config/loghi/{team_id}_logo.png`. Il PNG viene incluso automaticamente nel roster generato da `/roster`. Se il file è assente, appare un placeholder colorato.

## Colori squadre

I colori vanno in `teams.json` come campi `colore` e `colore2` (formato `#RRGGBB`). I GM possono modificarli da soli via `/my_team`.

## Aggiornare teams.json

`teams.json` è condiviso tra bot aste (v48) e bot main. Qualsiasi modifica impatta entrambi al prossimo riavvio. I campi usati dal bot main in aggiunta a quelli del bot aste sono:
- `colore` — colore primario per roster PNG
- `colore2` — colore secondario (opzionale)
- `gm_nome` — nome del GM (usato nel roster e negli annunci)
