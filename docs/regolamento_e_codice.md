# Regolamento e codice

Per ogni regola del regolamento: se il bot la applica, dove sta nel codice e quale prova la
controlla. Riferimento: *FANTA NBA – REGOLAMENTO UFFICIALE*, versione dell'11/10/2026 (18 pagine).
Stato del codice: v6.3.5, bot aste v71, loucabot v40, IPanchinari v29.

| Segno | Significato |
|---|---|
| ✅ | il bot la applica da solo |
| 🤝 | il bot prepara o controlla, decide un admin |
| ✋ | fuori dal bot (Yahoo, Telegram, admin) |
| 🔜 | da fare |
| 📝 | il bot è giusto, il testo del regolamento va corretto (testo proposto qui sotto) |

I numeri (tabelle, soglie, tempi, formule) sono ricopiati a mano dal regolamento in due prove,
`tests/main/regolamento_numeri.py` e `tests/aste/regolamento_numeri_aste.py`. Se cambia il
regolamento, si cambiano prima quelle prove e poi `settings.json` o il codice.

Percorsi: `main/` = `fantabasket-main/`, `aste/` = `fantabasket-aste-beta/`.

---

## Correzioni al regolamento

Decise con Luca il 12/10/2026: il bot fa già così, va aggiornato il testo. Per ognuna il testo
proposto, da sostituire a quello attuale.

**1. Luxury in preseason (capitolo Luxury e salary floor).** Oggi il regolamento fa l'esempio di
una squadra penalizzata con cap 146 che arriva a 160; il bot dà 165 a tutti in offseason, e la
penalità riduce il cap della regular season.

> Durante tutta la preseason è possibile sforare il cap fino a un massimo di 165 milioni, a patto
> che esso torni nei limiti entro l'inizio della regular season. Il limite di 165 milioni vale per
> tutte le franchigie, anche per quelle penalizzate: la decurtazione per le penalità si applica al
> cap della regular season.

**2. Stepien (capitoli Mercato e Stepien rule).** Oggi il Mercato dice "prime scelte, tre anni" e
il paragrafo Stepien "scelte, quattro anni"; il bot usa le proprie prime scelte e quattro anni.

> Nel Mercato: "…a patto che ogni squadra rispetti la Stepien Rule."
>
> Stepien rule: ogni franchigia deve mantenere almeno una delle proprie prime scelte in ogni
> finestra di quattro anni contigui. Contano anche i draft passati in cui la franchigia ha usato
> la propria prima scelta.

**3. RFA in trade (capitolo Asta per i RFA).** Oggi un paragrafo dice che l'RFA non si scambia fino
alla fine della fase RFA e l'ultimo che si scambia solo tra RFA. Regola decisa (nel bot dalla
v3.13.1), al posto della frase "Un giocatore dichiarato RFA non può essere incluso in trade…" e
dell'ultimo paragrafo del capitolo:

> Fino all'inizio delle aste RFA ogni franchigia può dichiarare, cambiare o togliere il proprio
> RFA quante volte vuole. Un giocatore dichiarato RFA può essere scambiato. Se la trade avviene prima dell'inizio delle
> aste RFA, il giocatore perde la dichiarazione: per la squadra che lo riceve è un normale
> contratto x0, mentre la squadra che lo cede può dichiarare un altro RFA. Se la trade avviene ad
> aste RFA aperte, la dichiarazione segue il giocatore e la squadra che lo riceve diventa
> proprietaria dell'RFA; dopo la trade, però, ogni franchigia può avere al massimo un RFA (un RFA
> si scambia quindi con un altro RFA, oppure verso una squadra che non ne ha dichiarati). Finché
> è dichiarato, l'RFA occupa cap ma non slot.

**4. Salary floor nelle trade (capitolo Luxury e salary floor).** Confermato com'è nel bot; il
testo può dirlo meglio:

> Durante la stagione sono bloccate le trade che portano una franchigia sopra il proprio cap o
> sotto il salary floor; una franchigia già sotto il floor può comunque fare trade che non le
> riducono il cap.

**Non sono correzioni:**

- **Offerta massima 141M in asta** (`aste/settings.offerta_massima`): non è una regola a parte, è
  la conseguenza di due regole, cap di 150 e minimo di 10 giocatori (150 − 9 giocatori a 1M).
- **Ordine dell'offseason**: regolamento rinnovi → aste RFA → free agency → fantadraft, bot
  rinnovi → draft → RFA → free agency → dichiarazione ruoli. Il regolamento ammette variazioni
  del calendario.

---

## Roster

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Da 10 a 15 giocatori | ✅ trade, tagli in RS, slot delle aste | `settings.json` `roster_min_regular`/`roster_max`; `main/validators/trade.py`; `main/handlers/tagli._valuta_taglio`; `shared/cap.py` (slot) | `regolamento_numeri`, `revisione_regolamento`, `trade_3_squadre` |
| Almeno 4 G, 4 F, 2 C | ✅ in RS: trade, tagli, firme, cambi ruolo | `shared/ruoli_core.deficit_minimo` | `regolamento_numeri`, `dpe_trade_tagli` |
| Un giocatore disponibile per ruolo con almeno 5 minuti di media | ✋ | admin | — |

## Lega e calendario, playoff, partita

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| 24 franchigie in due conference, calendario, playoff a 12 | ✋ Yahoo e admin | `numero_teams` solo per i controlli | `regolamento_numeri` |
| Fantapunti (punto +0,5, assist +2, rimbalzi +2/+1,25, tripla +1,5, tiri −0,5/+1, liberi −0,75/+1, rubata +2, stoppata +2, perse −2) | ✅ fantamedia di bref (Doncic, rinnovi, report) e fantapunti dei tabellini ESPN (calcolo) | `pesi_fantapunti` in settings.json (`shared/regole.py`): trigger su `bref_stats.fantamedia`, `loucabot/nba.fantapunti`; dopo un cambio `/dev_ricalcola_fp` | `regolamento_numeri`, `regole_config`, `louca_calcolo` |
| Formazioni (quintetto di Yahoo, un giocatore per ruolo) e panchina di 5 sul canale Panchinari, entro la prima partita della giornata | ✅ IPanchinari (quintetto congelato alla scadenza, panchina dal messaggio del GM); fa fede Yahoo, gli admin correggono | `ipanchinari/quintetti.py`, `ipanchinari/panchine.py`, `ipa_formazioni`, `ipa_panchine` | `ipa_panchine` |
| Punteggio del giocatore: media delle sue partite nella giornata; se la sua squadra NBA non gioca, media della stagione (0 se indisponibile) | ✅ | `loucabot/calcolo.punteggio_giocatori` | `louca_calcolo`, `louca_risultati` |
| Regola FADD: titolare che non ha giocato e risulta indisponibile, sostituito dal primo panchinaro del suo ruolo | ✅ | `loucabot/calcolo._fadd_possibile`, `punteggio_squadra` | `louca_calcolo`, `louca_risultati` |
| Titolare messo anche in panchina: in panchina quella posizione vale 0, gli altri non scalano (Luca, 23/10) | ✅ | `loucabot/calcolo.punteggio_squadra` (`doppio`) | `louca_calcolo`, `louca_risultati` |
| Bonus casa 3 (5 nei playoff), scarto minimo 5, supplementari coi panchinari in ordine (pari → trasferta) | ✅ | `loucabot/calcolo.esito`; `bonus_casa`, `scarto_minimo`, `giocatori_panchina` in settings.json | `louca_calcolo`, `regolamento_numeri` |
| Risultati convalidati da un admin, sul canale e sul foglio Calendario | 🤝 calcolo alle 7:45, convalida dell'admin | `loucabot/handlers_risultati.py`, `live.pubblica_definitivo` | `louca_risultati` |

## Draft iniziale

Solo il primo anno: ✋, fuori dal bot. Della sua tabella resta in uso quella dei **compensi minimi
per fantapunti** (0–10,99 → 1 … 45+ → 35), in `settings.json` `tabella_minimo_contratto` e
`main/settings.minimo_contratto_per_media`, per i rinnovi normali (🔜). Prova: `regolamento_numeri`.

## Mercato

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Mercato chiuso dalla trade deadline a inizio stagione | 🤝 l'admin passa alla fase `regular-season-deadline`; trade e FA seguono la fase | `main/settings.FASI_TRADE_APERTE`, `FASI_FA_APERTA` | — |
| Salary cap 150 | ✅ | `cap_regular`; `shared/cap.py` | `regolamento_numeri`, `cap_condiviso` |
| Offerte intere | ✅ | `aste/handlers/offerte.py` (rilancio minimo 1M) | `regolamento_numeri_aste` |
| Offerta massima 141M: conseguenza di cap 150 e minimo 10 giocatori | ✅ | `aste/settings.offerta_massima`; a quella cifra l'asta si chiude subito | `cap_asta_chiusa` |
| Asta FA: serve uno slot e il cap, chiude 18 ore dopo l'ultimo rilancio | ✅ | `aste/handlers/offerte._esegui_offerta`, `aste/scheduler.check_scadenze`; aste chiuse e non firmate impegnano cap e slot | `cap_asta_chiusa`, `apertura_gm`, `autoslot` |
| Il vincitore sceglie 1, 2 o 3 anni; da 20M almeno 2, da 35M 3 | ✅ | `aste/handlers/firma.py`, `firma_comune.anni_minimi`/`_valida_anni` | `regolamento_numeri_aste` |
| Anni e ruolo entro 48 ore, se no 3 anni e ruolo a caso | ✅ | `aste/handlers/firma.firma_automatica` | `regolamento_numeri_aste` (tempi) |
| Trade tra due o più squadre, cap e ruoli in regola dopo la trade | ✅ | `main/validators/trade.valida_trade`; flusso in `main/handlers/trade_*.py` | `trade_3_squadre`, `dpe_trade_tagli` |
| Scelte future e diritti in trade | ✅ | `trade_crea.py` (asset), `trade_esegui._scrivi_trade` | `trade_3_squadre`, `registro_unico` |
| Stepien | ✅ 📝 proprie 1st, 4 anni (correzione 2) | `main/validators/trade.anni_coperti_stepien`, `finestra_scoperta`; tag S su `/assets` e sul foglio | `regolamento_numeri` |
| Protezioni sulle 1st, non sulle 2nd | 🤝 mostrate se scritte nel database (`pick.protezioni`), non si impostano dal bot | `trade_comune._label_item` | — |
| Pick scambiabili dei 6 draft successivi | ✅ le pick dell'anno +6 nascono entrando nei rinnovi | `main/handlers/stagione.crea_pick_anno` | `stagione` |
| Ruolo dei giocatori presi in trade o in FA entro 48 ore, se no a caso | ✅ | `main/handlers/ruoli_rs.py` (trade, diritti), `aste/handlers/firma.py` (firma) | — |
| Ripreso entro 60 giorni: vecchio ruolo | ✅ | `shared/ruoli_core.ruolo_riacquisto` (`giorni_riacquisto_ruolo` in settings.json) | `regolamento_numeri`, `regole_config` |
| Schierato titolare senza comunicare il ruolo: vale quello di Yahoo | ✋ | admin | — |
| Ritiro o altro campionato: libera slot e cap, anche le spalmature | 🤝 su richiesta, approva un admin | `main/handlers/decadimento.applica_decadimento`, `db.cancella_spalmate_ritirato`; `/ritiro_fa` e report mensile per i free agent con spalmature | `revisione_regolamento`, `report_spalmature` |

## 10-day contract

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Uno a stagione per squadra, al massimo due squadre per giocatore, senza peso su cap e roster, 10 giorni (decade all'ufficialità dell'ultima giornata in cui era in squadra), solo prima della chiusura della FA, solo se nel ruolo non c'è nessuno disponibile | 🤝 il bot controlla tutto il resto, la disponibilità del ruolo la decide l'admin approvando (v5.2.0) | `main/handlers/dieci_giorni.py`, `shared/cap.py`, `max_10day_per_giocatore` in `settings.json` | `dieci_giorni` |

## Tagli

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| 3 tagli gratuiti a stagione dei 1x1, poi tagli illimitati | ✅ | `max_tagli_gratuiti` in settings.json, `main/handlers/tagli._e_taglio_gratuito` | `revisione_regolamento`, `regolamento_numeri` |
| Spalmature 50-30-20, 60-50-50-40, 70-70-60-50-50, somma uguale al contratto | ✅ | `tagli.calcola_impatto_taglio` | `regolamento_numeri` |
| Tabella fino a 5M | ✅ voce per voce | `tagli._TABELLA_SPALMATA_BASSA` | `regolamento_numeri` |
| Rifirmato dalla stessa squadra: stipendi sommati | ✅ le spalmature restano e si sommano al contratto nuovo | `shared/cap.py` (`impatto_taglio`) | `pg_rfa_30giorni_dpe` |
| Chi l'ha avuto negli ultimi 30 giorni non lo firma né rilancia in FA (in trade sì) | ✅ | `aste/pg_client.squadre_regola_30_giorni` | `pg_rfa_30giorni_dpe` |
| In RS niente tagli sotto i 10 giocatori o che scoprono i ruoli | ✅ (anche dal pannello admin) | `tagli._valuta_taglio` | `revisione_regolamento`, `dpe_trade_tagli`, `taglio_admin` |
| Cam Thomas exception: decadimento gratuito dopo un mese senza squadra NBA | 🤝 il GM lo chiede, l'admin verifica le condizioni (mese di mercato NBA aperto, 10 giorni dopo l'inizio della stagione) | `decadimento.py` (motivo `cam_thomas`) | `revisione_regolamento` |
| Cam Thomas: rifirmato dalla stessa squadra entro un anno, almeno il contratto di prima | ✅ | `aste/pg_client.minimo_cam_thomas` | `pg_rfa_30giorni_dpe` |

## Disabled Player Exception

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Out for the season: −25% per eccesso (Klay 5 → 3), poi torna intero | ✅ richiesta del GM, approva un admin | `main/handlers/dpe._importo_dpe`; vale per la stagione (`dpe.stagione`) | `regolamento_numeri`, `cap_condiviso`, `dpe_trade_tagli` |
| Prima della deadline libera lo slot | ✅ | `shared/cap.SQL_DPE_LIBERA_SLOT` (`dpe.pre_deadline`) | `cap_condiviso`, `rfa_dichiarati` |
| Dopo la deadline un cambio ruolo in più | ✅ | `main/handlers/cambi_ruolo.dpe_extra` | — |
| La DPE segue il giocatore in trade | ✅ | `trade_esegui._scrivi_trade` | `dpe_trade_tagli` |

## Tanking

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Due giocatori nello stesso ruolo con 5+ punti di media più del migliore di un altro ruolo: cambio ruolo obbligatorio; divieto del cambio inverso | ✋ admin | — | — |
| Media ≥ 27: almeno 60/70/80/90% delle partite da titolare, se no free agent a fine anno | ✋ admin (servono le formazioni di Yahoo) | — | — |
| Cambio ruolo forzato dagli admin, non conta nei due (Vassell) | ✅ | `cambi_ruolo.py`, tipo `forzato_admin` | — |

## Offseason

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Le fasi in ordine | 🤝 l'admin cambia fase dal pannello, con anteprima e conferma | `main/handlers/admin_panel.FASI_ORDINE`, `stagione.dopo_cambio_fase` | `stagione_ui` |
| La durata di tutti i contratti scala di un anno | ✅ entrando nei rinnovi | `stagione.nuova_stagione`; anni residui calcolati in `shared/cap.anni_residui` | `stagione` |
| Riunione di lega | ✋ | — | — |

## Rookie

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Tabella della rookie scale per pick, x2 x1 x2 x1 | ✅ | `settings.json` `rookie_scale`; `stagione.scala`, `importo_scala` | `regolamento_numeri`, `stagione` |
| Rinnovo a fine II anno, quanti se ne vuole | ✅ `/rinnovo_rookie` (GM e admin) | `stagione.candidati_rinnovo_rookie`, `esegui_rinnovo_rookie` | `stagione`, `stagione_ui` |
| Doncic: 12 + 0,6·(X−20) da 20, 15 + 0,4·(X−25) da 25; X per difetto, risultato per eccesso; solo se più della tabella | ✅ fantamedia massima delle due stagioni | `stagione.doncic`, `fantamedia_max` | `regolamento_numeri`, `stagione` |
| Doncic a fine IV anno, x0 | ✅ d'ufficio al cambio di stagione | `stagione.applica_stagione` | `stagione` |
| Rookie scale solo per chi è firmato dopo il draft senza passare dalla FA | ✅ per costruzione: il contratto rookie nasce solo da `/attiva_diritti` o dal draft | `main/handlers/rookie.py` | — |
| La scala parte dall'anno della firma, non della scelta | ✅ | `rookie.anno_firma`; `contratti.stagione_firma` | `stagione` |
| Diritti delle 2nd per due anni, scadono 10 giorni prima della deadline | ✅ avviso, poi conferma di un admin | `main/scheduler.check_scadenza_diritti`; `/trade_deadline` | `registro_unico` |
| Usciti dalla scala: rinnovabili anche da x0, contano tra i due rinnovi | 🔜 con i rinnovi normali | — | — |

## FantaDraft

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Lottery (14 squadre abbinate alla classifica NBA, o le odds della nota [30]), ordine del draft | 🔜 | — | — |
| Pick dell'anno che diventano posizioni, righe `rookie` dal draft | 🔜 | — | — |
| Le 1st vanno firmate, se no free agent | 🔜 oggi è solo scritto nell'annuncio della fase draft | — | — |

## Rinnovi dei giocatori

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Fino a 2 a stagione sui x1 (e sugli ex rookie x0), non cumulabili | 🔜 entro giugno 2027 | `max_rinnovi_standard` in `settings.json` | — |
| +¼ il primo, +½ il secondo, per eccesso, mai sotto la tabella dei minimi | 🔜 | `minimo_contratto_per_media` è già pronta | `regolamento_numeri` (tabella) |
| Durata x2 o x3 (x3 sopra 35) | 🔜 | — | — |

## Asta per i RFA

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Al massimo un x0 dichiarato RFA; si dichiara e si cambia quante volte si vuole fino alle aste RFA | ✅ `/dichiara_rfa` nei rinnovi e nel draft (v3.13.2) | `stagione.dichiara_rfa`, tabella `rfa_dichiarati` | `stagione`, `stagione_ui` |
| Non occupa slot, occupa cap | ✅ | `shared/cap.py` (`sql_rfa`) | `cap_condiviso`, `rfa_dichiarati` |
| In trade: prima delle aste RFA perde la dichiarazione (chi lo cede ne dichiara un altro); con le aste aperte la dichiarazione lo segue e ogni squadra ne ha al massimo uno | ✅ 📝 dalla v3.13.1 (correzione 3), con avviso nel riepilogo e ai GM | `settings.FASI_RFA_PRIMA_DELLE_ASTE`; `trade_esegui._scrivi_trade` (`db.revoca_rfa_trade`, `sposta_rfa_trade`, `ripristina_rfa_trade`); `validators/trade._errori_rfa`, `_cap_post_team`; bot aste: `rfa._allinea_proprietari` | `stagione`, `rfa_dichiarati` |
| Asta RFA, il proprietario non rilancia | ✅ aperte da sole nella fase RFA | `aste/handlers/rfa.job_rfa`; `offerte._check_partecipazione` | `rfa_dichiarati`, `rfa_proprietario` |
| Non si rilancia su se stessi | ✅ | `offerte._check_partecipazione` | — |
| Rilanci solo con slot e cap, contando le altre aste aperte | ✅ | `aste/database.get_cap_virtuale`, `STATI_IMPEGNO` | `cap_asta_chiusa`, `autoslot` |
| Il vincitore sceglie gli anni entro 12 ore, se no il minimo (1, 2 o 3) | ✅ | `firma.py`, `firma_comune.anni_minimi` | `regolamento_numeri_aste` |
| Il proprietario ha 24 ore dalla fine dell'asta per pareggiare, con almeno gli stessi anni | ✅ | `aste/handlers/firma_pareggio.py` (`pareggio_automatico` allo scadere) | `regolamento_numeri_aste` |
| Fasce del pareggio: fino a 20 qualsiasi offerta, 21–34 almeno ⌊⅓⌋, da 35 almeno ⌊½⌋ del vecchio compenso | ✅ | `firma_comune.soglia_pareggio`, `importo_minimo_pareggio` | `regolamento_numeri_aste` |
| Nessuna offerta: il proprietario firma con gli stessi minimi, o lascia andare | ✅ | `firma_pareggio.firma_prop_*`, `lascia_callback` | `rfa_lascio_andare`, `pg_rfa_30giorni_dpe` |
| Pre-impostazioni del proprietario (pareggio o rifiuto automatico) | ✅ in più rispetto al regolamento, non lo contraddicono | `aste/handlers/firma_preimpostazioni.py` | — |

## Cambi ruolo

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Ruoli tra quelli di Yahoo, comunicati prima della RS | ✅ `/dichiarazione_ruoli` nella fase ruoli | `main/handlers/ruoli.py`, posizioni in `posizioni.py` | — |
| In RS e playoff al massimo 2 cambi, non cumulabili né cedibili | ✅ | `max_cambi_ruolo_ordinari` in settings.json | `regolamento_numeri`, `regole_config` |
| Erminio: gratuito nelle due settimane dopo che Yahoo aggiunge il ruolo | ✅ | `cambi_ruolo.ruoli_erminio` (`giorni_erminio` = 14 in settings.json), `/data_erminio` | `regolamento_numeri`, `regole_config` |
| Saedro: una volta a stagione, 10 giorni, valutata dagli admin | ✅ richiesta e approvazione, ritorno automatico | `cambi_ruolo.cb_saedro`, `job_fine_saedro` | `regolamento_numeri`, `regole_config` |
| Sempre nel rispetto dei minimi dei ruoli | ✅ | `cambi_ruolo.verifica` (`deficit_team`), `ruoli_core.deficit_minimo` | `regolamento_numeri` (minimi) |

## Luxury e salary floor

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| In preseason fino a 165 | ✅ 📝 per tutti, penalizzati compresi (correzione 1) | `cap_offseason`; `main/settings.cap_limite_team`; `aste/settings.cap_limite` | `penalita_cap`, `regolamento_numeri` |
| In regola entro l'inizio della RS, se no 0 punti a partita | 🤝 report automatico entrando in RS; i punti sono su Yahoo | `stagione.testo_report_inizio_rs` | `stagione` |
| Floor 115 entro l'inizio della stagione, se no −2M di cap per ogni milione sotto | 🤝 il report calcola la penalità e propone `/set_cap_penalizzato` | `stagione.testo_report_inizio_rs` | `stagione` |
| In stagione bloccate le trade che sforano cap o floor; chi è già sotto il floor può fare trade che non gli riducono il cap | ✅ 📝 (correzione 4) | `main/validators/trade.py` | `regolamento_numeri` |

## Penalità

| Regola | Stato | Dove | Prova |
|---|---|---|---|
| Penalità per panchina, schierati sbagliati, Start Active Player, ruoli su Yahoo | 🤝 le decide l'admin, il bot le registra (motivazione, canale, GM, foglio Scelte «Penalità: N»), si sommano nella stagione e si azzerano con la nuova | `main/handlers/penalita.py`, tabella `penalita` | `penalita` |
| Ogni 2 rilanci non validi una penalità | non serve: il bot non accetta rilanci senza slot o cap | `aste/handlers/offerte.py` | `cap_asta_chiusa` |
| Scelte al draft che scendono ogni 3 penalità | 🔜 con il draft | — | — |
| Cap ridotto di 1M ogni 3 (o 4) penalità | 🤝 l'admin imposta la penalità di cap | `/set_cap_penalizzato` (`admin_panel.py`), `cap_penalizzato` in `teams.json`, vale in RS | `penalita_cap` |

---

## Regole senza una prova di flusso

Funzionano (le ha provate la prova generale sulla copia dei dati veri) ma non hanno una prova
automatica che le ripercorra: dichiarazione dei ruoli di inizio stagione, ruoli post-trade e
post-firma con estrazione a 48 ore, cambi ruolo (ordinario, Erminio, Saedro, forzato, DPE extra),
regola dei 60 giorni. `regolamento_numeri` controlla solo le costanti e i minimi dei ruoli. È il
primo posto dove aggiungere prove.
