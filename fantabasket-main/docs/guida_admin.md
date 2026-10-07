# Guida Admin — Fantabasket Main Bot

`/admin_menu` apre il pannello. Gli admin possono fare **qualsiasi operazione al posto di un GM**: firme, tagli, DPE, trade, ruoli.

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

- Le trade proposte dai GM arrivano nel gruppo admin con ✅ Approva / ❌ Rifiuta; l'approvazione esegue, assegna `TRADE-AAAA-NNN` e annuncia sul canale.
- Pannello → **Trade → Import**: importa dal testo e ufficializza direttamente.
- `/annulla_trade_admin TRADE-AAAA-NNN`: rollback di una trade eseguita (giocatori, pick e diritti), dopo aver verificato che il roster sia compatibile.
- La validazione controlla cap, roster, Stepien Rule (finestre di 4 anni, solo 1st proprie possedute) e in regular season i ruoli minimi.

---

## DPE, tagli, firme, decadimento

- Pannello → **DPE**: attivazione diretta (contratto − 25% arrotondato per eccesso), con notifica al GM e annuncio.
- Pannello → **Taglia giocatore**: taglio per conto di una squadra.
- `/registra_firma`: firma avvenuta fuori dal bot. In regular season apre anche la dichiarazione del ruolo per il GM.
- Le richieste di decadimento dei GM arrivano nel gruppo admin da approvare.

---

## Diritti 2nd round

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

- Pannello → **⏳ Ruoli in sospeso**: dichiarazioni post-trade/firma ancora aperte, dichiarabili al posto del GM. Dopo 48h il bot estrae il ruolo da solo.
- Pannello → **🔁 Cambi ruolo** → squadra: cambio **ordinario** per conto del GM (conta nel contatore), **Erminio**, **Saedro** diretta, **forzato** (non conta; i vincoli dei ruoli sono solo un avviso).
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
