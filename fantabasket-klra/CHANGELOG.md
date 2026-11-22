# klra — CHANGELOG

## v1 (2026-11-05, progettone v7.0.0)

- **Nasce klra** (Luca, 04/11/2026): loucabot coi sistemi di punteggio alternativi. Database `klra` suo, utente `klra` con sola lettura su un elenco di tabelle della lega (`setup_db.sql`, rilanciato da deploy.sh), motore che usa il codice di calcolo di loucabot coi parametri del sistema (pesi, bonus del giocatore e di squadra, partita, classifica), cache per firma dei parametri, l'Ufficiale verificato contro i risultati convalidati della lega
- **Comandi** (mockup approvati da Luca il 04/11): `/sistemi` con schede ed editor a bottoni, `/usa`, `/classifica`, `/giornata`, `/partita`, `/risultati`, `/confronta` (immagine nuova: classifica col sistema accanto all'ufficiale, partite che cambiano esito), `/klra_verifica` (dev). Un sistema si copia da qualsiasi altro; lo modifica solo chi l'ha creato
- **`/top`** col sistema (Luca, 04/11), accanto la fantamedia della lega
- **Tutto segnato NON UFFICIALE** (Luca, 04/11): striscia rossa e filigrana su ogni immagine, didascalie e testi, avviso in /start e /sistemi
- **Fantamedie**, sistema predefinito (Luca, 04/11): chi gioca prende la sua media prima della giornata (chi non ha ancora giocato quest'anno quella dell'anno prima, se c'è, se no 0); voce «Chi gioca prende» nell'editor

## v2 (2026-11-06, progettone v7.1.0)

- **Come loucabot** (Luca, 04/11): `/calendario`, `/calendario_full`, `/classifica_full`, `/classifica_conference` (il codice di loucabot coi risultati del sistema), `/pdf_giornata` e `/pdf_partite` col sistema; tutto NON UFFICIALE
- **`/klra_verifica`** controlla il motore contro il ricalcolo di oggi di loucabot e mostra a parte cosa è cambiato dopo la convalida; **`/confronta`** e il 🔄 di `/risultati` partono dall'Ufficiale ricalcolato (le correzioni di ESPN non si mescolano con le regole)
- La FADD di chi era fuori da inizio stagione torna giusta anche nelle giornate vecchie (loucabot v86): cache rifatta (`VERSIONE_MOTORE` 2)
- **Fantapanchine**, sistema predefinito (Luca, 05/11): contano solo i panchinari, sommati; vince chi fa di più. Voce nuova nell'editor «Nel totale contano: titolari / panchina / tutti»
- **Classifica cumulativa** (Luca, 06/11): opzione dell'editor, i punti fatti in tutte le giornate senza bonus casa né supplementari; Fantapanchine la usa
- **Conference alternative** (`/conference`, Luca 06/11): le crea chiunque scegliendo le squadre della prima conference, ognuna prende a caso il posto di una squadra della sua conference nel calendario vero (accoppiamento salvato); attive per utente, valgono in tutti i comandi insieme al sistema; le modifica solo chi le ha create
- **`/player`** col sistema (Luca, 06/11): la scheda di loucabot con in fondo fantamedia e ultime 5 partite del sistema; **🔀 Squadre a caso** nella creazione delle conference

## v3 (2026-11-09, progettone v7.2.0)

- **`/partita`: record W-L sotto i loghi coi risultati del sistema** (Luca, 09/11), con la stessa regola di loucabot («prima di questa partita: W-L» se dopo ne sono state convalidate altre); i pareggi del sistema come terzo numero (es. 5-2-1)

## v4 (2026-11-11, progettone v7.6.0)

- Chi prende la media: coi pesi ufficiali la fantamedia di Basketball-Reference come loucabot v100; con un sistema attivo restano le medie dei tabellini coi pesi del sistema (`motore._medie_assenti`)

## v5 (2026-11-13, progettone v7.7.0)

- `/player` di loucabot è un'immagine: col sistema attivo la stagione col sistema arriva sotto in testo (`motore._extra_player` al posto di `player.extra`); i bottoni «Quale?» mandano sempre l'immagine

## v6 (2026-11-14, progettone v7.9.4)

- `motore._ordina` accetta la vincitrice della Quasi NBA Cup che la classifica di loucabot passa dalla v7.9.4: vale solo per l'Ufficiale, non per i sistemi

## v7 (2026-11-21, progettone v7.19.0)

- Se Telegram non risponde all'avvio klra aspetta invece di andare in crash

## v8 (2026-11-21, progettone v7.20.1)

- **Copia quasi speculare di loucabot** (Luca, 21/11): `/rendimento`, `/rendimento_carriera`, `/confronto`, `/confronto_carriera`, `/rendimento_situazione`, `/rendimento_team`, `/classifica_home_away`, `/quasi_cup`, `/top_storica`, `/playoff`, coi bottoni «Quale?»; tutto NON UFFICIALE (testi, didascalie, striscia e filigrana). Niente `/giocatori`, `/status` né live
- Fantapunti delle partite coi pesi e i bonus del sistema; medie storiche di Basketball-Reference (carriera, `/top_storica`) solo coi pesi, con una nota se il sistema ha bonus per partita o un tetto, che dalle medie non si calcolano
- **Quasi Cup col sistema**: qualificazione dalla classifica del sistema, semifinali e finale coi punteggi del sistema nella giornata del turno (un pari va alla squadra in casa); il live della Cup non si vede
- **`/playoff` col sistema**: il tabellone dai seed della classifica di regular season del sistema, senza serie (le serie vere non si rifanno: le eliminate non schierano più)
- `setup_db.sql`: in più `lega_giornate_playoff` (date dei turni per `/playoff`)

## v9 (2026-11-21, progettone v7.20.2)

- `/rendimento` e `/confronto` col periodo come loucabot v132 (anche dal bottone «Quale?»)

## v10 (2026-11-21, progettone v7.20.5)

- «Uso:» di `/partita` con una squadra vera a caso

## v11 (2026-11-22, progettone v7.24.0)

- `/rendimento`: la distribuzione dei fantapunti e il decile della lega, coi fantapunti del sistema (da `shared/rendimento.py`)

## v12 (2026-11-22, progettone v7.24.1)

- `/rendimento`: nel decile della lega «dati dal» è il primo giorno coi tabellini nel tratto confrontato

## v13 (2026-11-22, progettone v7.25.0)

- I «Quale?» a pagine e di chi ha cercato, il nome tra apici, la scelta dei due nomi nei confronti (`cf:`, col sistema attivo); i comandi di loucabot ricevono il `bot_data` vero
