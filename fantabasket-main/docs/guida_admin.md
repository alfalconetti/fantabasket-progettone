# Guida admin — bot principale

Da admin puoi fare **tutto quello che fa un GM, al posto suo**: trade, tagli, rookie, DPE, decadimenti, ruoli. In più approvi le richieste dei GM e porti avanti la stagione cambiando fase.

Gli altri bot hanno la loro guida admin: **bot aste** (correzioni e aste per conto di una squadra), **loucabot** (import del calendario, ESPN, punteggi), **IPanchinari** (quintetti, panchine per conto di una squadra, riepiloghi prima della scadenza). Le fasi si cambiano solo qui.

Si parte da **`/admin_menu`**, il pannello coi bottoni. Come il `/menu` dei GM mostra solo le voci che hanno senso nella fase corrente, più **📊 Situazione cap**: cap occupato e tetto di tutte le squadre in un colpo d'occhio.

**Se sei anche GM**, dal `/menu` e dai comandi dei GM (`/dichiarazione_ruoli`, `/cambio_ruolo`, i bottoni dei ruoli da dichiarare, le trade) agisci come GM della tua squadra, con le stesse regole di tutti: solo la tua squadra, stesse fasi e stesse scadenze (dopo la deadline dei ruoli, dal menu sei bloccato anche tu). Le operazioni "da admin" (altre squadre, dopo le scadenze, cambio forzato, Saedro diretta, eccetera) stanno solo nel pannello e nei comandi admin (per i ruoli: pannello → 🎽 Ruoli squadre, anche per la tua squadra, o `/dichiarazione_ruoli SQUADRA`).

Per trovare al volo l'id di una squadra: **`/list`** (nome, id e GM di tutte).

---

## Le fasi della stagione

`/set_fase` (o pannello → Cambia fase) porta la lega alla fase successiva. L'ordine è sempre questo:

```
regular-season-fa → regular-season-deadline → playoff →
offseason-break → offseason-rinnovi → offseason-draft →
offseason-rfa → offseason-fa → offseason-ruoli → (ricomincia)
```

A ogni cambio di fase il bot:

- pubblica sul canale principale un annuncio con cosa si può fare nella nuova fase;
- aggiorna i menu del bot principale e del bot aste (quello delle aste entro 5 minuti);
- apre o chiude da solo il mercato FA del bot aste.

Entrando in **offseason-rinnovi** la stagione avanza di uno, per il bot principale e il bot aste. Solo arrivando dalla stagione prima (regular season, playoff o break): se torni ai rinnovi da draft, RFA, FA o ruoli con "Salta a…", la stagione resta quella.

**La fase si cambia solo da qui.** Il `/set_fase` del bot aste non fa più niente: rimanda a questo.

Per orientarsi:

- **Trade:** aperte in `regular-season-fa` e in tutta l'offseason tranne il break.
- **Free agency:** aperta in `regular-season-fa`, `offseason-fa` e `offseason-ruoli`.
- **Cap in offseason:** 165M per tutti.
- **Cap in regular season:** 150M meno le eventuali penalità della squadra, con salary floor a 115M. La penalità si imposta con `/set_cap_penalizzato team07 5` (0 per toglierla); vale per tutti e due i bot.

---

## Il cambio di stagione

Alcuni passaggi di fase toccano i contratti. Per questi, anche con "Avanza", il bot prima ti mostra cosa succederà e aspetta **✅ Confermo**.

**Entrando in offseason-rinnovi** (stagione nuova). Tutti i contratti scalano di un anno; quelli finiti diventano **x0**: restano in squadra, ma non pesano su cap e slot. Il bot aggiorna la rookie scale:

- rookie al II anno: contratto nuovo con l'importo della tabella (per le pick basse l'importo è lo stesso e non cambia niente);
- rookie al IV anno: se il rinnovo era all'importo di scala sale a quello del IV anno; un rinnovo Doncic è già più alto e resta;
- fine del IV anno: Doncic d'ufficio sulla fantamedia migliore del III e IV anno, se è più alta del contratto. Il contratto diventa un x0 normale, rinnovabile come gli altri;
- rookie a fine II anno: x0, in attesa di rinnovo rookie, RFA o scadenza.

Il dettaglio arriva nel gruppo admin come file (vedi sotto, "Messaggi lunghi"). Elenca ogni rookie che cambia anno di scala, anche quelli che restano uguali, con il motivo ("stesso importo in tabella", "Doncic, la tabella dice 11"). Per i rookie a fine II anno c'è anche la stima del rinnovo rookie: scala del III anno o Doncic, con la fantamedia usata. Se un contratto rookie non torna col suo anno di scala finisce in "⚠️ Da controllare" e il bot non lo tocca.

**Prima del passaggio**, il dev può vedere lo stesso report con `/dev_stagione`, senza che venga scritto niente. Durante la stagione Doncic e rinnovi sono stime con le fantamedie di quel momento. Nello stesso passaggio il bot crea le pick del draft di 6 anni dopo per tutte le squadre (nel 2027 quelle del 2033): fino al draft dell'anno le annate scambiabili sono quindi 7.

Se la trade deadline è ancora quella della stagione prima, nello stesso passaggio ti arriva il promemoria con il comando da usare.

**Durante i rinnovi (e il draft)**, dal pannello:

- **🔁 Rinnovi rookie** → squadra → giocatore: rinnovo rookie per conto del GM (scala III o Doncic, x2);
- **🔒 RFA squadre** → squadra: dichiara, cambia o toglie l'RFA. Da **📋 RFA dichiarati** vedi quelli di tutte le squadre. I GM lo dichiarano e lo cambiano da soli fino all'inizio delle aste RFA (rinnovi e draft). Ogni dichiarazione, cambio, ritiro o trade di un RFA arriva come riga sul **canale log**; sul **canale principale** c'è un solo messaggio con gli RFA dichiarati di tutte le squadre, che il bot modifica a ogni cambio. Un RFA scambiato prima delle aste perde la dichiarazione e chi l'ha ceduto può dichiararne un altro.

Il GM viene avvisato e l'annuncio sul canale riporta il tuo nome.

**Entrando in offseason-rfa.** Il bot aste apre da solo, entro 5 minuti, le aste degli RFA dichiarati. Se un RFA viene scambiato durante l'asta, i diritti passano alla nuova squadra.

**Entrando in offseason-fa.** Gli x0 non rinnovati e non dichiarati RFA scadono e tornano free agent; l'elenco esce sul canale. Gli RFA restano finché la loro asta non è conclusa.

**Entrando in regular-season-fa.** Se una squadra è sotto il salary floor ti arriva nel gruppo il comando già pronto con la penalità (2M per ogni milione sotto), per esempio `/set_cap_penalizzato team07 6`. Non scatta niente in automatico: decidi tu. Lo stesso messaggio segnala chi è sopra il tetto.

Se uno di questi passaggi fallisce, la fase resta cambiata e il messaggio di conferma te lo dice. Il dev lo ripete con `/dev_stagione rifai`: quello che era già stato fatto non si rifà.

**Messaggi lunghi.** Report ed elenchi per admin e dev (cambio di stagione, ruoli mancanti a fine dichiarazione, spalmature, controllo di coerenza, anteprime) arrivano come messaggio se sono corti. Se superano un messaggio di Telegram arriva un riassunto con allegato un file `.md` con il testo completo, creato al momento e non salvato da nessuna parte. Vale anche per gli elenchi admin e dev del bot aste.

---

## Approvare le richieste

Trade, DPE, Saedro, 10-day e decadimenti chiesti dai GM arrivano nel gruppo admin con i bottoni ✅ Approva / ❌ Rifiuta.

- Li può premere solo un admin, e funzionano anche dopo un riavvio del bot.
- **Vale la prima decisione.** Se un altro admin ha già risposto, il tuo bottone dice "già gestita" e non cambia niente: un Rifiuta arrivato dopo non annulla mai un'approvazione.
- Un GM non può mandare due richieste per lo stesso giocatore finché la prima è aperta. Dopo 7 giorni senza risposta può rimandarla.

---

## Trade

Quando tutti i GM coinvolti hanno accettato, la trade arriva nel gruppo. Approvandola il bot:

1. la esegue;
2. le assegna un numero (`TRADE-2026-014`);
3. la annuncia sul canale;
4. avvisa tutte le squadre coinvolte.

Il controllo automatico guarda cap, roster, Stepien Rule e, in regular season, i ruoli minimi. Se un giocatore ha la DPE, la DPE passa con lui alla nuova squadra.

**Ufficializzare una trade già concordata:** pannello → **Trade → Import**, incolli il testo e la trade viene eseguita direttamente, senza voto.

**Tornare indietro:** `/annulla_trade_admin TRADE-2026-014` rimette giocatori, pick e diritti dov'erano, se i roster di oggi lo permettono, e avvisa tutte le squadre.

---

## Tagli, DPE, firme, rookie

**Taglio per conto di una squadra:** pannello → **Taglia giocatore**. Valgono le stesse regole dei GM:

- 3 tagli 1x1 gratuiti a stagione, dal quarto pesa 1M;
- in regular season niente tagli sotto i 10 giocatori o che scoprono un ruolo;
- un contratto finito (x0) non si taglia: non pesa e scade da solo all'inizio della FA.

**DPE diretta:** pannello → **DPE**. Il contratto scende del 25% (arrotondato per eccesso), il GM viene avvisato e parte l'annuncio. Conta il momento dell'approvazione:

- prima della deadline libera uno slot;
- dopo la deadline dà alla squadra un cambio ruolo gratuito "Extra DPE".

**Firma avvenuta fuori dal bot:** `/registra_firma <team_id> <importo> <anni> <nome>`. Esempio:

```
/registra_firma team07 22 2 Jalen Williams
```

Il bot rifiuta gli anni sbagliati (da 20M almeno 2 anni, da 35M obbligatori 3) e ti avvisa se la squadra finisce oltre il tetto o oltre 15 giocatori. In regular season apre anche la dichiarazione del ruolo al GM.

**Rookie:** pannello → **🏀 Attiva diritti** → squadra → giocatore. Il contratto è quello della rookie scale, in qualsiasi fase.

I diritti delle seconde al secondo anno scadono 10 giorni prima della trade deadline, che si imposta ogni stagione con `/trade_deadline 05/02/2027` (senza data ti mostra quella attuale e quando scadono i diritti). La data deve cadere nella stagione in corso:

- nei 3 giorni prima ti arriva un avviso nel gruppo;
- il giorno della scadenza arriva il bottone **Conferma scadenza**, che libera i giocatori e lo annuncia.

**10-day contract** (solo nella fase regular-season-fa). La richiesta del GM arriva nel gruppo con le regole e i giocatori della squadra nel ruolo da coprire, con lo status dell'ultimo snapshot ESPN: si approva solo se nessuno di loro è disponibile (OUT o fuori dalle rotazioni). Il bot controlla da solo il resto: una volta a stagione per squadra, al massimo due squadre per giocatore, free agent, ruolo tra le sue posizioni eleggibili.

- Pannello → **⏱ 10-day**: quelli in corso con la scadenza, **✍️ Firma un 10-day** (scrivi il nome, poi giocatore, squadra e ruolo: firma subito, senza richiesta) e **⏹ Chiudi ora** accanto a ognuno per chiuderlo prima (chiede conferma; annuncio sul canale e avviso al GM, il giocatore torna free agent). Lo stesso da comando: `/firma_10day_admin NOME`.
- Scade da solo: dopo 10 giorni dalla firma, ma solo quando è convalidata l'ultima giornata in cui era in squadra (se i 10 giorni finiscono a giornata in corso, o prima della sua convalida, aspetta la convalida). Annuncio sul canale e avviso al GM.
- Non pesa sul cap, non occupa uno slot, non conta per i minimi dei ruoli; non si taglia, non si scambia, niente DPE. Non registrarlo mai con `/registra_firma`.

---

## Decadimenti e spalmature

Le richieste dei GM arrivano nel gruppo. Per farne uno direttamente: pannello → **🏁 Decadimento** → squadra → giocatore → motivo. Il motivo cambia cosa succede alle spalmature, cioè ai soldi che restano sul cap di chi l'aveva tagliato:

| Motivo | Contratto | Spalmature passate |
|---|---|---|
| Ritiro | chiuso | spariscono, per **tutte** le squadre |
| Altra lega | chiuso | spariscono, per **tutte** le squadre |
| ✂️ Cam Thomas exception | chiuso | restano |
| Altro | chiuso | restano |

**Cam Thomas exception.** Prima di approvare controllate che il giocatore sia stato tagliato in NBA e sia senza squadra da almeno un mese, con il mercato NBA aperto.

Se la stessa squadra lo rifirma entro un anno deve dargli almeno il contratto di prima. Questo lo controllano i bot da soli, sia `/registra_firma` sia il bot aste.

**E se si ritira uno che non ha più contratto?** Esempio: Rossi aveva tagliato Kevin Durant due anni fa e ha ancora 6M di spalmatura su questa stagione. Durant si ritira, ma è free agent, quindi nessuno ha un contratto da far decadere. In quel caso:

```
/ritiro_fa Kevin Durant
```

Le spalmature dalla stagione corrente in poi smettono di pesare su chiunque l'avesse tagliato.

**Come accorgersene.** Il 1° di ogni mese alle 9:45 arriva nel gruppo il **report spalmature**: tutti i free agent che pesano ancora sul cap di qualcuno, con l'ultima partita rilevata su Basketball-Reference. Se uno non gioca da mesi, controllate e usate `/ritiro_fa`. Lo stesso report si chiede quando si vuole con `/report_spalmature`.

---

## Ruoli

### Posizioni eleggibili

- **`/import_posizioni_eleggibili`** carica il CSV `yahoo_id;nome;team;posizioni` preso da Yahoo. Ti mostra un'anteprima (abbinati, posizioni cambiate, nomi ambigui, giocatori sotto contratto senza posizioni) e salva solo quando confermi.
- **`/set_posizioni_eleggibili Jokic C,PF`** corregge un singolo giocatore.
- **`/data_erminio Jokic 03/11/2026`** dice al bot quando Yahoo ha aggiunto l'ultima posizione. La finestra Erminio di 14 giorni parte da lì; senza, parte dalla data dell'import.

### Dichiarazione di inizio stagione

1. **Prima di entrare nella fase**, imposta la scadenza con `/deadline_ruoli 20/10/2026 23:59`. Così l'annuncio esce già con la data.
2. **Durante la fase:**
   - pannello → **🎽 Ruoli squadre** mostra chi ha finito (✅), chi è a metà (🟡) e chi non ha iniziato (❌), e ti fa dichiarare al posto di qualsiasi squadra;
   - ogni giorno alle 17 arriva un riepilogo sul canale log;
   - il giorno prima della deadline i GM in ritardo ricevono un promemoria.
3. **All'uscita dalla fase** arriva nel gruppo l'elenco di chi è rimasto senza ruolo. Da regolamento, il ruolo si estrae a caso tra quelli possibili.

### Controllo dei dati

**`/report_dati`** (o pannello → **🩺 Controllo dati**) manda un file Markdown con tutto quello che può rompere il calcolo o i controlli, da guardare prima di ogni giornata e dopo mercato e trade. Un riepilogo (✅ o quante cose da guardare) e una tabella per controllo:

- **senza id ESPN**: i loro punti non contano (si abbinano su loucabot);
- **ruoli**: senza posizioni eleggibili, senza ruolo in stagione, ruolo non più tra le eleggibili, squadre che non possono rispettare i minimi;
- **squadre**: sopra il cap, sotto il floor in stagione, troppi o troppo pochi giocatori;
- **contratti**: importo non positivo, 10-day scaduti e ancora attivi;
- **anagrafica**: senza data di nascita, mai visti su basketball-reference. A parte, con ℹ️ e senza contare tra le cose da guardare, i rookie al primo anno (draft della stagione) e gli esordienti NBA (0 anni di esperienza su ESPN): è normale finché non debuttano. Gli altri di solito sono fermi da tempo (infortunio lungo, senza squadra) o hanno il nome diverso da quello di bref;
- **registro**: il controllo di coerenza della notte (anche i contratti finiti ancora attivi fuori dalle fasi dei rinnovi).

Non corregge niente.

### Report dei ruoli

**`/report_ruoli`** (o pannello → **🎽 Ruoli squadre** → **📄 Report ruoli (.md)**) manda un file Markdown con la situazione dei ruoli di tutte le squadre in quel momento, in qualsiasi fase. In cima il riepilogo della lega: per ogni squadra quanti PG, SG, SF, PF e C, guardie, ali e centri rispetto ai minimi, giocatori senza ruolo, dichiarazioni in sospeso, cambi ordinari usati e lo stato dei minimi (✅ rispettati · 🟡 non ancora, ma i giocatori senza ruolo li possono coprire · ❌ mancano posti anche con la scelta migliore). Poi una tabella per squadra con ogni giocatore: ruolo, posizioni eleggibili e note (10-day, Saedro in corso, dichiarazione da fare entro, bozza non confermata, Erminio possibile, ruolo non più tra le eleggibili). Non cambia niente.

### Durante la stagione

**Ruoli dopo trade e firme.** Pannello → **⏳ Ruoli in sospeso** mostra le dichiarazioni ancora aperte, e puoi farle tu al posto del GM. Dopo 48 ore il bot estrae il ruolo da solo. Dopo una trade sul canale principale c'è **un solo messaggio** con i ruoli di tutti i giocatori arrivati, che si aggiorna da solo (dichiarati dal GM o da te, assegnati in automatico, estratti); per le firme resta un annuncio per giocatore.

**Cambi ruolo per conto di una squadra.** Pannello → **🔁 Cambi ruolo** → squadra, solo in regular season e playoff:

- **ordinario**: conta nel contatore della squadra;
- **Erminio**;
- **Saedro** diretta;
- **forzato**: non conta e i minimi di ruolo sono solo un avviso; esiste solo qui.

**Richieste Saedro.** Arrivano nel gruppo con l'elenco dei giocatori della squadra in quel ruolo: si approvano se nessuno è disponibile (OUT o fuori rotazione).

**Free agent firmato senza posizioni eleggibili.** Arriva un avviso. Imposta le posizioni con `/set_posizioni_eleggibili` e poi dai il ruolo con un cambio forzato.

**Titolare su Yahoo in un ruolo non comunicato.** Si sistema a mano con un cambio forzato.

---

## Basketball-Reference e date di nascita

Ogni giorno alle 12 (orario in `config/settings.json`, `"orari": {"bref": "12:00"}`), in regular season e playoff, il bot scarica le statistiche da Basketball-Reference, aggiorna il foglio **BrefRaw** e scrive sul canale log quanti giocatori ha aggiornato e chi ha cambiato squadra NBA.

I giocatori nuovi, che non sono ancora nell'anagrafica, arrivano al dev con ✅ Crea tutti / ❌ Ignora. Accanto a ognuno ci sono i nomi simili già presenti, per evitare doppioni.

**Date di nascita:**

- una alla volta: `/set_nascita Victor Wembanyama 04-01-2004`;
- tante insieme: `/set_nascita` seguito da una riga per giocatore.

Se il nome non è esatto il bot propone i candidati coi bottoni, non indovina mai da solo.

**`/nascite_mancanti`** elenca chi è sotto contratto senza data, in un blocco da copiare, completare e rimandare. Lo stesso elenco arriva al dev ogni lunedì.

---

## Penalità

Dal pannello admin **⚠️ Penalità** (o `/penalita`): ➕ Nuova penalità → squadra → scrivi la **motivazione** → anteprima → ✅ Conferma. Il bot la pubblica sul canale principale («Penalità a SQUADRA — la Nª della stagione» con la motivazione), la manda ai GM della squadra, scrive una riga sul canale log e aggiorna il foglio Scelte, dove sotto il GM compare «Penalità: N».

Le penalità si sommano nella stagione e ripartono da zero con la stagione nuova (lo storico resta). Gli effetti del regolamento (posizioni in meno al draft, cap ridotto con `/set_cap_penalizzato`) si applicano a mano: il bot le registra soltanto.

Dal pannello, 📋 sulla squadra mostra l'elenco con 🗑 Revoca: dopo la conferma il messaggio sul canale diventa «revocata», i GM e il log vengono avvisati e il conteggio scende. `/penalita SQUADRA` mostra quelle di una squadra (all'admin anche le revocate, barrate).

---

## Fogli Google

Il bot aggiorna i fogli dopo ogni operazione:

- **Roster:** ruoli, cap con penalità, tagli e cambi ruolo usati, DPE. I contratti finiti (x0) non compaiono, perché non pesano; l'RFA dichiarato c'è, con la sigla A. I giocatori hanno il **nome di Basketball-Reference** (quello delle righe di BrefRaw, a cui si agganciano le formule; per chi non ce l'ha il nome dei bot): chi ha i due nomi diversi lo trovi nel controllo dei dati (`/report_dati`, «Nome sul foglio Roster diverso da quello dei bot»).
- **Scelte:** pick e diritti, con il tag `[STEPIEN]`; sotto il GM «Penalità: N» se la squadra ne ha in questa stagione.
- **BrefRaw:** le statistiche del mattino.

Se sembrano indietro, il dev può forzare un aggiornamento completo con `/sync_sheets`.

---

## Registro delle azioni

Tutto quello che cambia qualcosa, in tutti e quattro i bot, lascia una riga nel **registro delle azioni**: chi l'ha fatto, in che veste (**gm**, **admin**, **dev**, **sistema** per i job automatici), cosa, su quale squadra e giocatore, com'era prima e com'è dopo. Dal pannello admin **📜 Registro** (gli ultimi 7 giorni) o **`/registro`** coi filtri, in qualsiasi ordine: un numero di giorni (`/registro 30`), una squadra (nome, id o GM), un giocatore, una veste (`admin`), un bot (`principale`, `aste`, `loucabot`, `ipanchinari`), `@username` per chi l'ha fatto, altro testo per l'azione (`/registro taglio`). Arriva un file Markdown, al massimo 500 righe, dalla più recente.

La veste la decide il flusso, non chi sei: dal `/menu` normale sei **gm** anche se sei admin; dal pannello e dai comandi admin sei **admin**. Le azioni da admin e da dev vanno anche sul canale log del bot dove le fai, in un formato unico (`🛠 admin Nome · azione · squadra`, sotto `oggetto: prima → dopo`); quelle dei GM e dei job restano nel registro, per non fare rumore. Su loucabot e IPanchinari le azioni admin avevano già la loro riga sul log col nome: quella resta com'è. Un GM con `/registro` vede solo le righe della sua squadra, comprese le azioni degli admin su di essa.

Il registro si tiene per sempre. Le azioni fatte prima della v6.0.0 non ci sono (per quelle restano i movimenti in `/team_diff` e i canali log).

## Varie

**Orari dei job.** In `config/settings.json`, sotto `"orari"` (ora di Roma, "HH:MM"), si cambiano senza un rilascio: per esempio `"orari": {"bref": "11:00", "calcolo": "07:45"}`. L'elenco con i valori di partenza è in `shared/regole.py` (`ORARI`). I job giornalieri li leggono all'avvio: dopo un cambio riavvia il bot (`docker compose restart bot-main`, `loucabot`, …); il blocco delle panchine e il promemoria dei quintetti di IPanchinari valgono subito.

- **`/settings`** (anche dal pannello admin, «⚙️ Impostazioni»): le impostazioni di gioco divise per argomento (cap e roster, contratti, ruoli, tagli/DPE/10-day, partita, fantapunti, aste, sistema, tabelle), col nome in italiano, il valore di adesso e l'unità; *(default)* vuol dire che nel file non c'è e vale il valore del regolamento. Tocchi una voce, scrivi il nuovo valore (con i limiti indicati; la virgola va bene), vedi l'anteprima vecchio → nuovo e confermi. Ogni modifica va sul canale principale e sul canale log (con chi l'ha fatta), e i bot la usano subito, senza riavvio. Scorciatoia: `/settings chiave valore` (es. `/settings salary_floor 115`, `/settings pesi_fantapunti.dreb 1,5`), sempre con conferma. Le tabelle (rookie scale, minimi dei contratti) si vedono ma si cambiano nel file.
- **Pesi dei fantapunti**: si cambiano uno per uno da «🧮 Fantapunti» (di solito dopo la riunione di giugno). Valgono subito per i tabellini nuovi; per ricalcolare quelli della stagione già scaricati il dev lancia il comando dev di loucabot che ricalcola i fantapunti (`dev_ricalcola_fp`). Le giornate convalidate restano come sono.
- **Nomi di squadre e GM**: `/edit_team [SQUADRA]` o «✏️ Nomi squadre e GM» nel pannello admin. Scegli la squadra (o la scrivi: basta una parola del nome o del GM), poi ✏️ Nome squadra o ✏️ Nome GM e scrivi il nuovo (massimo 40 caratteri). Vale subito in tutti i bot; finisce nel registro e sul canale log col tuo nome. I GM cambiano i propri con `/my_team`.
- **`teams.json`** (condiviso con gli altri bot) contiene nomi, GM e colori; i bot lo rileggono a ogni uso, quindi le modifiche valgono subito. I loghi stanno in `config/loghi/{team_id}_logo.png`.
- **`/annulla_admin`** esce da un'operazione admin rimasta bloccata.

**Backup:**

- completo (database, aste, config, secrets cifrati) alle 00 e alle 12 sul canale log;
- ogni sabato alle 00:30 anche nel gruppo admin.

Come si ripristina: `docs/RECOVERY.md` nella cartella principale del repo.

**Date nei comandi.** Ovunque ci sia una data va bene GG/MM/AAAA, GG/MM/AA o AAAA-MM-GG, con `-`, `/` o `.` (20/10/2026, 20-10-26, 2026-10-20). Con l'anno a 2 cifre è sempre giorno, mese, anno.
