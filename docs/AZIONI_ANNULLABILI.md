# Azioni annullabili e modificabili — censimento

Direzione decisa da Luca il 20/11/2026: ogni azione che scrive qualcosa deve potersi **annullare o correggere dal
bot**, senza SQL a mano, lasciando sempre la riga nel registro (prima → dopo). Questo file è il punto di partenza
(v7.19.0): per ogni azione dice cosa si può fare oggi e cosa manca. Da aggiornare quando si aggiunge
un'azione o un comando di correzione. «Annullabile» = si torna a prima; «modificabile» = se ne cambia un dettaglio.

Legenda: ✅ c'è · 🟡 in parte · ❌ manca · ❔ da verificare nel codice prima di toccarlo.

## Mercato e contratti (bot principale, bot aste)

| Azione | Annullabile | Modificabile | Cosa si porta dietro | Cosa manca |
|---|---|---|---|---|
| Trade approvata | ✅ `/annulla_trade_admin` (`_scrivi_trade(inverti=True)`) | — (si annulla e si rifà) | asset, cap, foglio, registro, canale | — |
| Bozza di trade | ✅ `/annulla_trade` | ✅ `/edit_trade` | — | — |
| Taglio | ❌ | ❌ | contratto, spalmature (`impatto_taglio`), tagli gratuiti usati, foglio, canale | **annulla taglio** (rimette contratto, toglie spalmature, ridà il taglio gratuito) — priorità alta |
| Firma registrata a mano (`/registra_firma`) | ❌ | ❌ | contratto, cap, slot, foglio | **annulla firma** e **correggi importo/anni** — priorità alta |
| Firma da asta (bot aste) | ❔ | ❔ | contratto, cap, slot, foglio | da verificare con `riapri_asta` dopo la firma |
| Offerta in asta | ✅ `/annulla_offerta` (l'ultima) | — | asta, scadenza | — |
| Asta | ✅ `/annulla_asta`, `/riapri_asta` | ✅ `/estendi_asta` | — | — |
| Decadimento | ❌ | ✅ causa: pannello admin → 🏁 Decadimento → ✏️ (v7.19.0) | contratto, slot, spalmature (ritiro/altra lega anche degli altri), Cam Thomas | **annulla decadimento** (rimette il contratto); da ritiro/altra lega a un'altra causa: le spalmature tolte agli altri non si rimettono |
| Free agent ritirato (`/ritiro_fa`) | ❌ | — | spalmature di chi l'aveva tagliato | annulla (rimettere le spalmature tolte) |
| DPE approvata | ❌ | ❌ | cap, slot | annulla DPE |
| Attivazione diritti 2nd | ❌ | ❌ | contratto rookie, slot | annulla attivazione |
| Rinnovo rookie | ❔ | ❔ | contratto, scala | da verificare |
| Dichiarazione RFA | ✅ si cambia fino alle aste RFA (`/dichiara_rfa`) | ✅ | aste RFA | — |
| 10-day | ✅ chiuso prima dagli admin (pannello ⏱ 10-day) | — | slot, ruolo coperto | — |
| Cap / slot anticipato | ✅ tolto (bot aste) | — | cap, slot | — |
| Cap penalizzato | 🟡 si reimposta il valore (`/set_cap_penalizzato`) | ✅ | cap | — |
| Penalità | ✅ revocata (⚠️ Penalità) | ❔ | sanzioni a fine RS | — |

## Ruoli

| Azione | Annullabile | Modificabile | Cosa si porta dietro | Cosa manca |
|---|---|---|---|---|
| Dichiarazione dei ruoli | 🟡 si rifà fino alla deadline (anche per conto, 🎽 Ruoli squadre) | ✅ | ruoli, minimi | dopo la deadline: correzione admin con registro |
| Cambio ruolo | ❌ | ❌ | cambi usati (2) | annulla cambio (ridà il cambio) |
| Ruolo assegnato / estratto (sistema) | ❌ | ❔ | ruoli | correzione admin |
| Posizioni eleggibili | ✅ `/set_posizioni_eleggibili` | ✅ | ruoli possibili | — |

## Giornate, tabellini, formazioni (loucabot, IPanchinari)

| Azione | Annullabile | Modificabile | Cosa si porta dietro | Cosa manca |
|---|---|---|---|---|
| Correzione di un tabellino | ✅ `/correggi_tabellino … annulla` (v7.17.0) | ✅ | fantapunti, calcolo | — |
| Notte / giornata congelata | ✅ `/scongela_notte`, `/scongela` | — | riscarichi da ESPN | — |
| Status valido per il calcolo | ✅ tolto | ✅ | calcolo | — |
| Calcolo della giornata | ✅ `/ricalcola` | — | risultati, foglio, classifica | — |
| Giornata convalidata | ❔ | ❔ | classifica, playoff, Cup | da verificare (riaprire una convalida) |
| Quintetto / panchina | ✅ per conto (`/quintetto_admin`, `/panchina_admin`) | ✅ | calcolo, controlli | — |
| Controllo di una formazione | ✅ tolto | — | foglio di controllo | — |
| Seed dei playoff | 🟡 `/set_seed` solo prima del blocco | 🟡 | tabellone | dopo il blocco: correzione admin |
| Calendario importato | 🟡 si reimporta | — | giornate | — |

## Lega e impostazioni

| Azione | Annullabile | Modificabile | Note |
|---|---|---|---|
| Cambio di fase | ❌ | — | i passaggi di stagione non si disfano: prima `/dev_stagione` per l'anteprima |
| Riassegnazione squadra | 🟡 si rifà | — | — |
| Nomi squadre e GM, palette | ✅ | ✅ | — |
| Impostazioni, deadline, trade deadline | ✅ | ✅ | — |
| Date di nascita, data Erminio | ✅ | ✅ | — |

## Ordine proposto per i comandi mancanti

1. Annulla taglio e annulla/correggi firma registrata (gli errori più facili da fare e più pesanti sul cap).
2. Annulla decadimento.
3. Annulla DPE, attivazione diritti, cambio ruolo.
4. Verificare i ❔ (firma da asta, rinnovo rookie, convalida, penalità) e completare la tabella.

Ogni comando nuovo: solo admin, conferma con gli effetti scritti, una transazione sola, riga nel registro con
prima → dopo, messaggio sul canale se l'azione originale era stata annunciata, sync del foglio.
