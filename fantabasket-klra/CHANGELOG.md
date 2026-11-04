# klra — CHANGELOG

## v1 (2026-11-05, progettone v7.0.0)

- **Nasce klra** (Luca, 04/11/2026): loucabot coi sistemi di punteggio alternativi. Database `klra` suo, utente `klra` con sola lettura su un elenco di tabelle della lega (`setup_db.sql`, rilanciato da deploy.sh), motore che usa il codice di calcolo di loucabot coi parametri del sistema (pesi, bonus del giocatore e di squadra, partita, classifica), cache per firma dei parametri, l'Ufficiale verificato contro i risultati convalidati della lega
- **Comandi** (mockup approvati da Luca il 04/11): `/sistemi` con schede ed editor a bottoni, `/usa`, `/classifica`, `/giornata`, `/partita`, `/risultati`, `/confronta` (immagine nuova: classifica col sistema accanto all'ufficiale, partite che cambiano esito), `/klra_verifica` (dev). Un sistema si copia da qualsiasi altro; lo modifica solo chi l'ha creato
- **`/top`** col sistema (Luca, 04/11), accanto la fantamedia della lega
- **Tutto segnato NON UFFICIALE** (Luca, 04/11): striscia rossa e filigrana su ogni immagine, didascalie e testi, avviso in /start e /sistemi
- **Fantamedie**, sistema predefinito (Luca, 04/11): chi gioca prende la sua media prima della giornata (chi non ha ancora giocato quest'anno quella dell'anno prima, se c'è, se no 0); voce «Chi gioca prende» nell'editor
