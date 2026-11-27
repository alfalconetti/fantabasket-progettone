# Funzioni per fase — censimento

Controllo generale chiesto da Luca (14/11 e 15/11; fatto il 27/11, v7.38.0): per ogni azione dei bot, in quali fasi
si può fare, dove è controllato (comando, bottone, menu), cosa fa il bot da solo ai cambi di fase. Da aggiornare
quando si aggiunge un'azione legata a una fase. Le viste (roster, assets, pick, classifica, player, carriera…) non
sono legate alle fasi e non sono qui, tranne dove cambiano comportamento.

Fasi, in ordine: **RS** `regular-season-fa` · **DL** `regular-season-deadline` · **PO** `playoff` · **BR**
`offseason-break` · **RI** `offseason-rinnovi` · **DR** `offseason-draft` · **RF** `offseason-rfa` · **FA**
`offseason-fa` · **RU** `offseason-ruoli`. La stagione avanza entrando in RI (da RS, DL, PO o BR).

## Azioni dei GM (bot principale e bot aste)

| Azione | RS | DL | PO | BR | RI | DR | RF | FA | RU | Costante | Controllo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Trade: crea, importa, modifica | ✅ | | | | ✅ | ✅ | ✅ | ✅ | ✅ | `FASI_TRADE_APERTE` | comando (`richiede_fase`), menu, `/` |
| Trade: voto ed esecuzione | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | `FASI_TRADE_APERTE` | v7.38.0: a trade chiuse i voti si fermano e nessuna trade si esegue; ⚠️ solo un admin può **forzarla** (approvazione nel gruppo o «Ufficializza ora», con l'avviso); al cambio di fase l'elenco delle trade rimaste a metà agli admin |
| Taglio | ✅ | | | | ✅ | ✅ | ✅ | ✅ | ✅ | `FASI_TRADE_APERTE` | comando, bottone di conferma, menu |
| Attivazione diritti 2nd | ✅ | | | | ✅ | ✅ | ✅ | ✅ | ✅ | `FASI_TRADE_APERTE` | comando, bottone, menu |
| DPE | ✅ | ✅ | | | ✅ | ✅ | ✅ | ✅ | ✅ | `FASI_DPE` | comando, approvazione admin, menu |
| Decadimento | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | v7.38.0: in ogni fase, anche nel menu |
| Dichiarazione ruoli | | | | | | | | | ✅ | `FASE_RUOLI` | comando, bottoni |
| Cambio ruolo | ✅ | ✅ | ✅ | | | | | | | `FASI_RUOLI_RS` | comando, bottoni |
| 10-day | ✅ | | | | | | | | | `FASI_10DAY` | comando, bottoni; chiusi entrando in BR |
| Rinnovi normali, rinnovi rookie | | | | | ✅ | | | | | `FASE_RINNOVI` | comando, bottoni (anche la conferma) |
| Dichiarazione RFA | | | | | ✅ | ✅ | | | | `FASI_RFA_PRIMA_DELLE_ASTE` | comando, bottoni |
| Scelta al draft (`/scelgo`) | | | | | | ✅ | | | | — | comando |
| Asta FA: aprirne una | ✅ | | | | | | | ✅ | ✅ | `FASI_MERCATO_APERTO` → `mercato_aperto` | bot aste, all'apertura |
| Asta FA: rilanci su un'asta aperta | ✅ | ✅ | | | | | | ✅ | ✅ | — | un'asta aperta alla chiusura del mercato finisce normalmente (Luca, 27/11) |
| Aste RFA | | | | | | | ✅ | | | `FASE_RFA` | il bot aste le apre da solo |
| Quintetti e panchine | giornate in calendario (RS e PO) | | | | | | | | | — | IPanchinari: solo le giornate aperte; nei PO solo chi è in gioco |

## Azioni degli admin

| Azione | Fasi | Controllo |
|---|---|---|
| Cambio di fase | — | `blocco_passaggio`: niente salto dei rinnovi, niente ritorno da offseason a PO/BR, PO solo con l'ultima giornata convalidata e il calendario dei PO, RS solo con le 38 giornate datate; anteprima con `/dev_stagione` |
| Rinnovi rookie e RFA per conto | RI, DR | `FASI_ADMIN_RINNOVI` |
| Draft (`/draft_avvia`, `/draft_scegli`, `/draft_correggi`…), `/lottery_quando`, `/lottery_stato` | DR | `richiede_fase` |
| Sorteggio del calendario (`/calendario_quando`) | FA, RU | `FASI_SORTEGGIO` |
| Date del calendario (`/importa_date`), calendario da CSV (`/importa_calendario`) | sempre | v7.38.0: le giornate con dei risultati non si cambiano più (date e partite), le altre sì |
| Calendario dei playoff (`/importa_playoff`), seed (`/set_seed`) | prima del blocco del tabellone | `playoff.stato` |
| Archivio del foglio di controllo (`/archivia_calcolo`) | dopo la finale | `archivio_calcolo.problemi` |
| Firme, tagli, 10-day, DPE per conto, penalità, cap penalizzato, ritiro FA, riassegna | sempre (gli admin correggono) | — |
| Calcolo, ricalcolo, convalida, congelamento, correzioni dei tabellini | sempre (servono le giornate) | — |

## Cosa fa il bot da solo, per fase

| Quando | Cosa |
|---|---|
| Entrando in RI dalla stagione prima | stagione +1 (`inizi_stagione`), rookie scale, pick dell'anno +6 |
| Entrando in BR | penalità → sanzioni, 10-day chiusi, promemoria dell'archivio del foglio di controllo |
| Entrando in DR | controllo cap e slot con tutte le 1st, promemoria della lottery |
| Entrando in FA | x0 scaduti; con RU: promemoria del sorteggio del calendario |
| Entrando in RS | report del cap, squadre fuori dai minimi dei ruoli |
| Uscendo da RU | giocatori senza ruolo agli admin |
| Passaggio ai PO | regular season congelata (niente più ricontrolli), seed, bozza del tabellone |
| Cap | 150 in RS, DL, PO; 165 in offseason |
| Ogni notte | sync ESPN; in offseason solo i roster (niente giornate); tanking solo nelle giornate di RS |
| Bref | ogni giorno alle 12 e la sera in cui inizia una giornata con squadre a media (RS, DL, PO: `FASI_RUOLI_RS`) |
| Scenari (`/scenari` e canale) | RS, DL; sul canale dalle ultime 5 giornate |
| Prospetto rinnovi (menu) | da RS a RI; il comando sempre, con le stime solo fino a RI |

## Decisioni (Luca, 27/11)

1. **Trade dopo la deadline**: nessuna si esegue; solo gli admin la possono forzare dal loro pannello, con un avviso in più.
2. **Decadimento**: in ogni fase, anche nel menu.
3. **Aste FA aperte alla chiusura del mercato**: finiscono normalmente.
