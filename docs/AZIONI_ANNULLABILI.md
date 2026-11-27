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
| Taglio | ✅ pannello → ✂️ Taglia giocatore → ↩️ Annulla un taglio (v7.20.2) | — (si annulla e si rifà) | contratto, spalmature (`impatto_taglio`), tagli gratuiti usati, foglio, canale | — (non se dopo ci sono altri movimenti del giocatore) |
| Firma registrata a mano (`/registra_firma`) | ✅ pannello → ✍️ Firme registrate (v7.20.2) | ✅ `/correggi_firma ID IMPORTO ANNI` (v7.20.2) | contratto, cap, slot, foglio, dichiarazione di ruolo | — (non se dopo ci sono altri movimenti o è dichiarato RFA) |
| Firma da asta FA (bot aste) | ✅ `/annulla_firma_asta ID [ore]` (v7.38.0): via contratto e movimento, l'asta si riapre con l'offerta in testa di prima | — (si annulla e si rifà) | contratto, cap, slot, ruolo, foglio, asta | le RFA no (cap liberato al proprietario, pareggio): a mano |
| Offerta in asta | ✅ `/annulla_offerta` (l'ultima) | — | asta, scadenza | — |
| Asta | ✅ `/annulla_asta`, `/riapri_asta` | ✅ `/estendi_asta` | — | — |
| Decadimento | ✅ ↩️ Annulla azioni → 🏁 (v7.38.0) | ✅ causa: pannello admin → 🏁 Decadimento → ✏️ (v7.19.0) | contratto, slot, spalmature (ritiro/altra lega anche degli altri, salvate in `spalmature_tolte`), RFA revocato, Cam Thomas | i decadimenti di prima della v7.38.0 che avevano tolto spalmature non si annullano (non erano salvate); da ritiro/altra lega a un'altra causa le spalmature non si rimettono (si annulla e si rifà) |
| Free agent ritirato (`/ritiro_fa`) | ✅ ↩️ Annulla azioni → 👋 (v7.38.0) | — | spalmature di chi l'aveva tagliato | — (dalla v7.38.0) |
| DPE approvata | ✅ ↩️ Annulla azioni → 🏥, o 🏥 DPE → ↩️ (v7.38.0) | — (si annulla e si rifà) | cap, slot, cambio ruolo extra | — (non se il cambio extra di una DPE post-deadline è già usato: prima quello) |
| Attivazione diritti 2nd | ✅ ↩️ Annulla azioni → 🏀, o 🏀 Attiva diritti → ↩️ (v7.38.0) | — | contratto rookie, slot, diritti, ruolo da dichiarare | — (non se dopo ci sono movimenti, una DPE o l'RFA) |
| Rinnovo rookie III-IV | ✅ ↩️ Annulla azioni → 🔁 rinnovo rookie (v7.38.0) | — (si annulla e si rifà) | contratto, scala | — (solo nella stagione) |
| Rinnovo normale (¼, ½) | ✅ entro 24 ore (v7.32.0, 📝 Rinnovi) | — | contratto | — |
| Dichiarazione RFA | ✅ si cambia fino alle aste RFA (`/dichiara_rfa`) | ✅ | aste RFA | — |
| 10-day | ✅ chiuso prima dagli admin (pannello ⏱ 10-day) | — | slot, ruolo coperto | — |
| Cap / slot anticipato | ✅ tolto (bot aste) | — | cap, slot | — |
| Cap penalizzato | 🟡 si reimposta il valore (`/set_cap_penalizzato`) | ✅ | cap | — |
| Penalità | ✅ revocata (⚠️ Penalità) | — (si revoca e si rifà) | sanzioni a fine RS | — |

## Ruoli

| Azione | Annullabile | Modificabile | Cosa si porta dietro | Cosa manca |
|---|---|---|---|---|
| Dichiarazione dei ruoli | 🟡 si rifà fino alla deadline (anche per conto, 🎽 Ruoli squadre) | ✅ | ruoli, minimi | dopo la deadline: correzione admin con registro |
| Cambio ruolo | ✅ ↩️ Annulla azioni → 🔁, o 🔁 Cambi ruolo → ↩️ (v7.38.0) | — (si annulla e si rifà) | ruolo, cambi usati | — (solo l'ultimo del giocatore; una Saedro già finita no) |
| Ruolo assegnato / estratto (sistema) | ✅ si corregge con un cambio **forzato** dagli admin (🔁 Cambi ruolo, non conta nei cambi; verificato il 27/11) | ✅ | ruoli | — (in offseason i ruoli si dichiarano da capo) |
| Posizioni eleggibili | ✅ `/set_posizioni_eleggibili` | ✅ | ruoli possibili | — |

## Giornate, tabellini, formazioni (loucabot, IPanchinari)

| Azione | Annullabile | Modificabile | Cosa si porta dietro | Cosa manca |
|---|---|---|---|---|
| Correzione di un tabellino | ✅ `/correggi_tabellino … annulla` (v7.17.0) | ✅ | fantapunti, calcolo | — |
| Notte / giornata congelata | ✅ `/scongela_notte`, `/scongela` | — | riscarichi da ESPN | — |
| Status valido per il calcolo | ✅ tolto | ✅ | calcolo | — |
| Calcolo della giornata | ✅ `/ricalcola` | — | risultati, foglio, classifica | — |
| Giornata convalidata | ✅ `/ricalcola N` e di nuovo la convalida (verificato il 27/11) | ✅ | classifica, playoff, Cup, foglio | — |
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

1. ~~Annulla taglio e annulla/correggi firma registrata~~ fatti nella v7.20.2: i movimenti sbagliati si cancellano (non si aggiungono movimenti contrari), così carriera, roster alla data e `/team_diff` non mostrano cose mai avvenute; nel registro delle azioni resta tutto.
2. ~~Annulla decadimento~~ fatto nella v7.38.0, con il ritiro dei free agent.
3. ~~Annulla DPE, attivazione diritti, cambio ruolo~~ fatti nella v7.38.0, con il rinnovo rookie; tutto in /admin_menu → ↩️ Annulla azioni.
4. ~~Verificare i ❔~~ fatto il 27/11; ~~firma da asta~~ fatta nella v7.38.0 (si riapre l'asta, Luca 27/11); il ruolo assegnato dal sistema si corregge già col cambio forzato. Resta solo il **seed dei playoff dopo il blocco** (a tabellone partito: probabilmente non serve mai).

Ogni comando nuovo: solo admin, conferma con gli effetti scritti, una transazione sola, riga nel registro con
prima → dopo, messaggio sul canale se l'azione originale era stata annunciata, sync del foglio.
