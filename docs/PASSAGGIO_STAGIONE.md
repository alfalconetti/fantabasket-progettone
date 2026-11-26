# Passaggio di stagione

Dalla fine della regular season alla regular season dopo, bot per bot, nell'ordine in cui si fa. I blocchi del bot
principale impediscono di saltare i passi che contano: qui c'è il perché e cosa fare quando un passo si ferma.

Bot: **principale** (fasi, contratti, rinnovi, draft), **loucabot** (calendario, calcolo, playoff, sorteggio),
**IPanchinari** (quintetti e panchine), **aste** (RFA e free agency). Le fasi si cambiano sempre dal bot principale
(`/set_fase` o pannello admin → Fase), mai a mano in `globals.json`.

## 1. Fine della regular season → playoff

1. **loucabot**: l'ultima giornata di regular season convalidata. All'avviso «Regular season finita» nel gruppo admin:
   `/importa_playoff` col CSV delle date dei playoff (se non è già fatto).
2. **principale**: `/set_fase` → 🏆 Playoff. Si può solo con l'ultima giornata convalidata e il calendario dei playoff
   importato; se manca qualcosa il bot lo dice.
3. **loucabot** da solo: bozza del tabellone nel gruppo admin, `/set_seed` per le correzioni, conferma col bottone,
   blocco alle 15 del giorno dopo l'ultima notte (classifica finale per la lottery, P1 in calendario).
4. Ogni giornata P si calcola e si convalida come in regular season; alla convalida le serie si aggiornano e la
   giornata dopo entra in calendario. IPanchinari chiede formazioni e panchine solo a chi gioca.

## 2. Dopo la finale → break

1. **loucabot**: la convalida della finale scrive la campione (annuncio sul canale).
2. **principale**: `/set_fase` → 😴 Break. Le penalità della stagione diventano sanzioni per il draft, i 10-day ancora
   aperti si chiudono.
3. **loucabot**: `/archivia_calcolo` (admin). I tab «Calcolo GN/PN» del foglio di controllo vanno in un file nuovo
   («Calcolo AAAA-AA · archivio») e si tolgono: la stagione nuova riparte da «Calcolo G1». Finché la stagione vecchia
   non è archiviata, loucabot non scrive i tab di quella nuova (lo dice nella proposta del calcolo). I calcoli restano
   comunque nel bot (`/storico_calcolo`).
4. Il foglio **Calendario** non si tocca: si riscrive da solo col calendario nuovo. Il foglio **«Playoff AA-AA»** è
   uno per stagione e resta.

## 3. Break → rinnovi: la stagione nuova

1. **principale**: `/set_fase` → 📝 Rinnovi. Si può solo con la finale dei playoff convalidata (la campione). Prima
   l'anteprima di cosa succede ai contratti, poi la conferma:
   - la stagione avanza di uno (`stagione_corrente`), per tutti i bot; il momento si registra (`inizi_stagione`) e
     serve alle viste a una data (`/roster DATA`, `/assets DATA`, `/pick DATA`, `/team_diff`, `/trova_trade`);
   - rookie scale: II e IV anno, Doncic d'ufficio a fine IV anno, rookie a fine II anno da rinnovare;
   - pick del draft di sei anni dopo;
   - promemoria della trade deadline: `/trade_deadline GG/MM/AAAA` per la stagione nuova, e `/deadline_nba` per quella NBA.
2. Da qui **loucabot e IPanchinari** sono già nella stagione nuova, che non ha ancora calendario: niente calcoli,
   niente promemoria; la sincronizzazione delle 8:30 scarica solo i roster ESPN (i movimenti NBA dell'estate).
3. Nella fase: rinnovi normali (`/rinnovo`, uno da ¼ e uno da ½), rinnovi rookie (`/rinnovo_rookie`), RFA
   (`/dichiara_rfa`). Il prospetto `/prospetto_rinnovi` mostra i numeri veri.

## 4. Draft e RFA

1. **principale**: `/set_fase` → 🎯 Draft. Il bot ricorda di fissare la lottery: `/lottery_quando GG/MM HH:MM`. Dopo
   l'estrazione l'ordine del draft è scritto; il draft si avvia con `/draft_avvia`.
2. **principale**: `/set_fase` → ⚖️ RFA: le aste RFA sul bot aste.

## 5. Free agency e ruoli: il calendario nuovo

1. **principale**: `/set_fase` → 💸 Free agency. Gli x0 non RFA scadono (anteprima e conferma). Se il calendario
   della stagione non è completo, promemoria nel gruppo admin.
2. **loucabot**: `/calendario_quando GG/MM HH:MM` (solo in free agency e nei ruoli): sorteggio del calendario con drand
   all'ora del round. Poi `/importa_date` col CSV delle date delle 38 giornate.
3. **loucabot**, quando ESPN pubblica il calendario NBA: `/nba_sync`, poi `/espn_mancanti` per abbinare rookie e
   giocatori nuovi (senza id ESPN i loro punti non contano).
4. **IPanchinari**: `/quintetti_import` coi quintetti di tutte le squadre.
5. **principale**: `/set_fase` → 🎽 Ruoli (di nuovo il promemoria del calendario, se manca).

## 6. Regular season

1. **principale**: `/set_fase` → 🏀 Regular season. Si può solo con le 38 giornate e le date della stagione; se no il
   bot dice cosa manca (sorteggio da fissare, sorteggio da fare, date da importare). All'ingresso il report di floor e
   tetto nel gruppo admin.
2. Controlli della prima settimana: `/calendario_check` su loucabot, i promemoria di IPanchinari ai GM, il primo
   calcolo (il tab «Calcolo G1» sul foglio di controllo).

## Cosa NON si può fare (blocchi del bot principale)

- Saltare i rinnovi venendo dalla stagione prima (la stagione non avanzerebbe).
- Tornare a playoff o break dall'offseason nuova (la stagione avanzerebbe due volte).
- Passare ai rinnovi senza la campione, ai playoff senza la regular season finita e il calendario dei playoff, alla
  regular season senza il calendario.
- Questi controlli valgono anche toccando un «✅ Confermo» rimasto da un tentativo di prima.

Le prove che fanno tutto il giro sono `tests/main/transizioni.py` (fasi e contratti), `tests/main/event_sourcing.py`
(il registro), `tests/louca/louca_prova_playoff.py` (playoff col calcolo vero) e `tests/louca/louca_archivio_calcolo.py`.
