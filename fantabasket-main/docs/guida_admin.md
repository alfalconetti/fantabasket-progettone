# Guida admin — bot principale

Da admin puoi fare **tutto quello che fa un GM, al posto suo**: trade, tagli, rookie, DPE, decadimenti, ruoli. In più approvi le richieste dei GM e porti avanti la stagione cambiando fase.

Si parte da **`/admin_menu`**, il pannello coi bottoni. Come il `/menu` dei GM mostra solo le voci che hanno senso nella fase corrente, più **📊 Situazione cap**: cap occupato e tetto di tutte le squadre in un colpo d'occhio.

**Se sei anche GM**, dal `/menu` e da `/cambio_ruolo` agisci come GM della tua squadra, con le stesse regole di tutti. Le operazioni "da admin" (cambio forzato, Saedro diretta, eccetera) stanno solo nel pannello.

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
- aggiorna i menu di entrambi i bot (quello delle aste entro 5 minuti);
- apre o chiude da solo il mercato FA del bot aste.

Entrando in **offseason-rinnovi** la stagione avanza di uno, per tutti e due i bot.

**La fase si cambia solo da qui.** Il `/set_fase` del bot aste non fa più niente: rimanda a questo.

Per orientarsi:

- **Trade:** aperte in `regular-season-fa` e in tutta l'offseason tranne il break.
- **Free agency:** aperta in `regular-season-fa`, `offseason-fa` e `offseason-ruoli`.
- **Cap in offseason:** 165M per tutti.
- **Cap in regular season:** 150M meno le eventuali penalità della squadra, con salary floor a 115M. La penalità si imposta con `/set_cap_penalizzato team07 5` (0 per toglierla); vale per tutti e due i bot.

---

## Approvare le richieste

Trade, DPE, Saedro e decadimenti chiesti dai GM arrivano nel gruppo admin con i bottoni ✅ Approva / ❌ Rifiuta.

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
- in regular season niente tagli sotto i 10 giocatori o che scoprono un ruolo.

**DPE diretta:** pannello → **DPE**. Il contratto scende del 25% (arrotondato per eccesso), il GM viene avvisato e parte l'annuncio. Conta il momento dell'approvazione:

- prima della deadline libera uno slot;
- dopo la deadline dà alla squadra un cambio ruolo gratuito "Extra DPE".

**Firma avvenuta fuori dal bot:** `/registra_firma <team_id> <importo> <anni> <nome>`. Esempio:

```
/registra_firma team07 22 2 Jalen Williams
```

Il bot rifiuta gli anni sbagliati (da 20M almeno 2 anni, da 35M obbligatori 3) e ti avvisa se la squadra finisce oltre il tetto o oltre 15 giocatori. In regular season apre anche la dichiarazione del ruolo al GM.

**Rookie:** pannello → **🏀 Attiva diritti** → squadra → giocatore. Il contratto è quello della rookie scale, in qualsiasi fase.

I diritti delle seconde al secondo anno scadono 10 giorni prima della `trade_deadline` scritta in `globals.json`:

- nei 3 giorni prima ti arriva un avviso nel gruppo;
- il giorno della scadenza arriva il bottone **Conferma scadenza**, che libera i giocatori e lo annuncia.

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
- **`/data_erminio Jokic 2026-11-03`** dice al bot quando Yahoo ha aggiunto l'ultima posizione. La finestra Erminio di 14 giorni parte da lì; senza, parte dalla data dell'import.

### Dichiarazione di inizio stagione

1. **Prima di entrare nella fase**, imposta la scadenza con `/deadline_ruoli 2026-10-20 23:59`. Così l'annuncio esce già con la data.
2. **Durante la fase:**
   - pannello → **🎽 Ruoli squadre** mostra chi ha finito (✅), chi è a metà (🟡) e chi non ha iniziato (❌), e ti fa dichiarare al posto di qualsiasi squadra;
   - ogni giorno alle 17 arriva un riepilogo sul canale log;
   - il giorno prima della deadline i GM in ritardo ricevono un promemoria.
3. **All'uscita dalla fase** arriva nel gruppo l'elenco di chi è rimasto senza ruolo. Da regolamento, il ruolo si estrae a caso tra quelli possibili.

### Durante la stagione

**Ruoli dopo trade e firme.** Pannello → **⏳ Ruoli in sospeso** mostra le dichiarazioni ancora aperte, e puoi farle tu al posto del GM. Dopo 48 ore il bot estrae il ruolo da solo.

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

Ogni mattina alle 10, in regular season e playoff, il bot scarica le statistiche da Basketball-Reference, aggiorna il foglio **BrefRaw** e scrive sul canale log quanti giocatori ha aggiornato e chi ha cambiato squadra NBA.

I giocatori nuovi, che non sono ancora nell'anagrafica, arrivano al dev con ✅ Crea tutti / ❌ Ignora. Accanto a ognuno ci sono i nomi simili già presenti, per evitare doppioni.

**Date di nascita:**

- una alla volta: `/set_nascita Victor Wembanyama 04-01-2004`;
- tante insieme: `/set_nascita` seguito da una riga per giocatore.

Se il nome non è esatto il bot propone i candidati coi bottoni, non indovina mai da solo.

**`/nascite_mancanti`** elenca chi è sotto contratto senza data, in un blocco da copiare, completare e rimandare. Lo stesso elenco arriva al dev ogni lunedì.

---

## Fogli Google

Il bot aggiorna i fogli dopo ogni operazione:

- **Roster:** ruoli, cap con penalità, tagli e cambi ruolo usati, DPE.
- **Scelte:** pick e diritti, con il tag `[STEPIEN]`.
- **BrefRaw:** le statistiche del mattino.

Se sembrano indietro, il dev può forzare un aggiornamento completo con `/sync_sheets`.

---

## Varie

- **`/settings`** mostra le impostazioni di gioco; `/settings chiave valore` ne cambia una. Esempio: `/settings salary_floor 115`.
- **`teams.json`** (condiviso col bot aste) contiene nomi, GM e colori. Le modifiche valgono dal riavvio. I loghi stanno in `config/loghi/{team_id}_logo.png`.
- **`/annulla_admin`** esce da un'operazione admin rimasta bloccata.

**Backup:**

- completo (database, aste, config, secrets cifrati) alle 00 e alle 12 sul canale log;
- ogni sabato alle 00:30 anche nel gruppo admin.

Come si ripristina: `docs/RECOVERY.md` nella cartella principale del repo.
