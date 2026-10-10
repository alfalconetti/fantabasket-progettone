# Guida Admin — Fantabasket Main Bot

`/admin_menu` apre il pannello. Gli admin possono fare **qualsiasi operazione al posto di un GM**: trade, tagli, attivazione diritti, decadimento, DPE, ruoli, cambi ruolo. Come il /menu dei GM, il pannello mostra solo le voci utili nella fase corrente, più **📊 Situazione cap** (cap occupato e tetto attuale di tutte le squadre).

**Admin che è anche GM:** dal `/menu` e da `/cambio_ruolo` agisci come GM della tua squadra, con le stesse regole degli altri (niente cambio forzato, Saedro su richiesta). Le operazioni "da admin" si fanno solo dal pannello.

Anche il menu dei comandi di Telegram (il tasto `/`) segue la fase: comandi come `/cambio_ruolo` o `/dichiarazione_ruoli` compaiono solo quando servono (dopo un cambio di fase può servire riaprire la chat).

---

## Fasi

`/set_fase` (o pannello → Cambia fase) avanza alla fase successiva:

```
regular-season-fa → regular-season-deadline → playoff →
offseason-break → offseason-rinnovi → offseason-draft →
offseason-rfa → offseason-fa → offseason-ruoli → (ricomincia)
```

- Il passaggio a `offseason-rinnovi` incrementa la stagione.
- A ogni cambio il bot pubblica sul **canale principale** un annuncio con cosa si può fare nella nuova fase (trade/FA/DPE calcolati dalle regole del bot + indicazioni specifiche, in `FASI_INDICAZIONI` di `admin_panel.py`).
- Mercato aperto (trade e FA): `regular-season-fa`, `offseason-fa`, `offseason-ruoli`; trade anche in `offseason-rinnovi`, `offseason-draft`, `offseason-rfa`.
- Cap: in offseason fino a 165M per tutti; in regular season 150M meno le eventuali penalità della squadra. Salary floor 115M controllato sulle trade in stagione.

---

## Trade

- **Bottoni di approvazione** (trade, DPE, Saedro, decadimento): funzionano anche dopo un riavvio, li può premere solo un admin, e la prima decisione vale. Se la richiesta è già stata gestita (da un altro admin o da un altro messaggio) il bottone risponde "già gestita" e non cambia niente: un Rifiuta non annulla mai un'approvazione. Un GM non può mandare una seconda richiesta per lo stesso giocatore finché la prima è aperta (dopo 7 giorni senza risposta può rimandarla).
- Le trade proposte dai GM arrivano nel gruppo admin con ✅ Approva / ❌ Rifiuta; l'approvazione esegue, assegna `TRADE-AAAA-NNN` e annuncia sul canale.
- Pannello → **Trade → Import**: importa dal testo e ufficializza direttamente.
- `/annulla_trade_admin TRADE-AAAA-NNN`: rollback di una trade eseguita (giocatori, pick e diritti), dopo aver verificato che il roster sia compatibile.
- La validazione controlla cap, roster, Stepien Rule (finestre di 4 anni, solo 1st proprie possedute) e in regular season i ruoli minimi.

---

## DPE, tagli, firme, decadimento

- Pannello → **DPE**: attivazione diretta (contratto − 25% arrotondato per eccesso), con notifica al GM e annuncio. Pre o post deadline, importo e squadra si valutano al momento dell'approvazione (anche per le richieste dei GM); la DPE post-deadline dà alla squadra un cambio ruolo gratuito "Extra DPE" verso il ruolo dell'infortunato.
- Pannello → **Taglia giocatore**: taglio per conto di una squadra.
- `/registra_firma`: firma avvenuta fuori dal bot. In regular season apre anche la dichiarazione del ruolo per il GM.
- Le richieste di decadimento dei GM arrivano nel gruppo admin da approvare.
- Pannello → **🏁 Decadimento** → squadra → giocatore → motivo: decadimento diretto, con avviso al GM e annuncio sul canale.

---

## Diritti 2nd round

Pannello → **🏀 Attiva diritti** → squadra (tra parentesi quanti diritti ha) → giocatore: attivazione per conto del GM con il contratto della rookie scale, in qualsiasi fase. Il GM riceve un messaggio; in regular season gli si apre anche la dichiarazione del ruolo.

I diritti al secondo anno scadono 10 giorni prima della `trade_deadline` (in `globals.json`). Nei 3 giorni precedenti arriva un avviso nel gruppo admin; dal giorno della scadenza arriva il bottone **Conferma scadenza**, che segna i diritti scaduti e annuncia nel gruppo e sul canale chi torna free agent.

---

## Ruoli

### Posizioni eleggibili

- `/import_posizioni_eleggibili` — import da CSV `yahoo_id;nome;team;posizioni` esportato dalle pagine giocatori Yahoo. Mostra un'anteprima (abbinati, posizioni cambiate, ambigui, conflitti, sotto contratto senza posizioni) e salva solo con conferma.
- `/set_posizioni_eleggibili <nome> <PG,SG>` — correzione puntuale.
- `/data_erminio <nome> <AAAA-MM-GG>` — data in cui Yahoo ha aggiunto l'ultima posizione: la finestra Erminio di 14 giorni parte da lì (altrimenti dalla data dell'import).

### Dichiarazione a inizio stagione

- Prima di entrare nella fase: `/deadline_ruoli AAAA-MM-GG [HH:MM]`, così l'annuncio esce con la data.
- Pannello → **🎽 Ruoli squadre**: stato di tutte le squadre (✅ completa, 🟡 parziale, ❌ nessuna) e dichiarazione per conto di qualsiasi squadra, anche fuori fase.
- Durante la fase: report ogni giorno alle 17 sul canale log; promemoria privato ai GM incompleti il giorno prima della deadline; all'uscita dalla fase, elenco dei giocatori senza ruolo nel gruppo admin (regolamento: ruolo casuale tra quelli disponibili).

### Regular season

- Free agency: il ruolo lo sceglie il vincitore nel bot aste insieme agli anni (o viene estratto dopo 48h insieme ai 3 anni di penale). Se il giocatore non ha posizioni eleggibili, la firma avviene senza ruolo e arriva un avviso nel gruppo admin: impostale con `/set_posizioni_eleggibili` e assegna il ruolo con un cambio forzato.
- Pannello → **⏳ Ruoli in sospeso**: dichiarazioni post-trade/firma ancora aperte, dichiarabili al posto del GM. Dopo 48h il bot estrae il ruolo da solo.
- Pannello → **🔁 Cambi ruolo** → squadra (solo in regular season e playoff): cambio **ordinario** per conto del GM (conta nel contatore), **Erminio**, **Saedro** diretta, **forzato** (non conta; i vincoli dei ruoli sono solo un avviso). Il forzato esiste solo qui, non nel /menu.
- Le richieste di **Saedro** dei GM arrivano nel gruppo con l'elenco dei giocatori della squadra in quel ruolo: da approvare se nessuno è disponibile (OUT o fuori rotazione).
- Il caso "schierato titolare su Yahoo senza aver comunicato il ruolo" va corretto a mano con un cambio forzato.

---

## Google Sheets

Il bot aggiorna i fogli dopo ogni operazione; dopo dichiarazioni e cambi ruolo aggiorna i roster di **tutte** le squadre. `/sync_sheets` forza una sincronizzazione completa.

- **Roster**: ruolo di ogni giocatore (ordinati per ruolo quando la squadra li ha dichiarati tutti), cap con penalità, tagli gratuiti usati, cambi ruolo usati, tagli con impatto, righe DPE.
- **Scelte**: pick proprie e altrui, diritti 2nd, tag `[STEPIEN]` sulle 1st non cedibili.

---

## Configurazione

- `teams.json` (condiviso con il bot aste): `gm_nome`, `gm_ids`, colori; modifiche attive al riavvio.
- Loghi in `config/loghi/{team_id}_logo.png`.
- `/annulla_admin` esce da un'operazione admin bloccata.

---

## Backup e ripristino

Backup unico e completo (database, aste, config, secrets cifrati) alle 00 e alle 12 sul canale log e la domenica nel gruppo admin. Procedura di ripristino e di emergenza: `docs/RECOVERY.md` nella cartella principale del repo.
