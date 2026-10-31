# Guida admin — loucabot

Da admin in loucabot gestisci il calendario della stagione e controlli i punteggi. I comandi admin funzionano in privato e nel gruppo admin, e compaiono nel menu `/` solo lì.

Gli admin sono quelli di `admin_ids` in `globals.json`, gli stessi degli altri bot.

---

## Canali

- **Gruppo admin** (`admin_group_id`): qui arrivano solo i cambi che contano per la lega, cioè una scadenza che si sposta o le squadre a media di una giornata che cambiano. loucabot deve essere nel gruppo.
- **Canale principale** (`main_channel_id`, lo stesso del bot principale): il messaggio dei punteggi live di ogni giornata. **loucabot deve essere amministratore del canale** (con il permesso di pubblicare e modificare i messaggi).
- **Gruppo della lega** (`gruppo_lega_id` in `globals.json`, da aggiungere a mano): la **top 20 della notte** alle 9. loucabot deve essere nel gruppo; senza la chiave non pubblica niente.
- **Canale log** (`log_channel_id_louca` in `globals.json`; senza, quello del bot principale): la parte tecnica. Ci vanno avvio ed errori, ogni import del calendario, ogni `/nba_sync`, `/tabellini`, `/espn_giocatori`, ogni abbinamento a mano e la sincronizzazione delle 8:30, anche quando non cambia niente (così si vede che gira).

---

## Il calendario

**A inizio stagione:**

1. Manda il CSV del calendario come file, con didascalia `/importa_calendario`. Va bene anche rispondere con `/importa_calendario` al messaggio che contiene il file. Un nuovo import sostituisce il calendario di regular season della stagione, senza doppioni.
2. `/nba_sync`: scarica da ESPN tutte le partite NBA della stagione (qualche minuto).
3. `/calendario_check`: scadenza di ogni giornata e squadre a media, con il confronto tra quelle scritte nel CSV e quelle calcolate dalle partite NBA.

**Il CSV** è quello degli admin: per ogni giornata una riga `Week N gg/mm - gg/mm (media XXX,YYY)` e sotto le partite `Casa,,V,,Trasferta`. Le squadre si riconoscono solo per nome esatto (senza maiuscole e accenti) o per id, come in `teams.json`. Se un nome non c'è, il bot propone il più simile ma non importa niente. Controlli: giornate da 1 in ordine e senza sovrapposizioni, ogni squadra una volta per giornata.

**Squadre a media.** Vale il calcolo dalle partite NBA, che è quello che vedono i GM. Se `/calendario_check` mostra differenze, correggi le note nel CSV e reimportalo, così anche il calendario pubblicato torna giusto.

**Il foglio Google Calendario** (stesso file del Roster) lo ricarica il bot, tutto, nelle colonne A:E: all'import, quando cambiano le squadre a media, con `/calendario_foglio` e dopo ogni giornata convalidata. Scrive il calendario come nel CSV, con le squadre a media calcolate nelle intestazioni e i punteggi in B e D (regolamentari nella riga delle squadre, supplementari subito sotto). La formattazione, le celle unite e le altre colonne non si toccano; i valori di A:E invece sì: quello che si scrive lì a mano sparisce al primo aggiornamento.

**Ogni mattina alle 8:30** il bot riscarica le partite dei giorni vicini (da 3 giorni fa a 2 settimane avanti) e ricalcola. Se in una giornata non ancora finita cambiano la prima partita o le squadre a media, arriva un avviso al gruppo admin.

---

## Il calcolo della giornata

**Alla scadenza**, appena IPanchinari congela quintetti e panchine, nel tab **«Calcolo GN»** del foglio di controllo esce l'elenco degli schierati, per trasparenza verso i GM: per ogni partita, per ogni squadra, i 5 del quintetto e la panchina in ordine, col ruolo e la squadra NBA (panchina non mandata, posti vuoti e doppioni sono segnati). Niente punteggi né formule. Se un admin corregge una formazione o una panchina, il tab si riscrive entro 5 minuti (riga sul canale log). Il calcolo della mattina riscrive lo stesso tab per intero.

**Nei giorni in mezzo alla giornata**, alle 10 (`orari.foglio_parziale`), il tab si riscrive col calcolo fino alla notte appena finita, con le formule come il definitivo e **PROVVISORIO** nel titolo (sfondo arancio chiaro): chi deve ancora giocare per ora conta 0 e la FADD si decide a giornata finita, come nel live. Se un admin corregge una formazione dopo la prima notte, il tab si riscrive subito col calcolo provvisorio. L'ultimo giorno vale il calcolo delle 7:45.

**Alle 7:45** del giorno dopo l'ultima notte della giornata il bot calcola da solo, coi tabellini definitivi: riscarica le partite e i tabellini **dell'ultima notte** (le notti prima sono già congelate, vedi sotto), anche quelli già presi nel live (così entra subito una correzione di ESPN arrivata dopo il live; se ce n'è qualcuna lo scrive nel canale log), prende i quintetti congelati alla scadenza e le panchine da IPanchinari e applica le regole qui sotto. Poi:
- scrive il tab **«Calcolo GN»** del foglio di controllo del calcolo: una riga per giocatore coi fantapunti di ogni notte, la media della stagione, lo status di ogni notte, il punteggio, chi è in campo (FADD), l'ordine dei supplementari, e in cima il riquadro dei risultati. Punteggi, totali, supplementari e vincitore sono **formule** che rifanno i conti del bot: se tutto quadra sul foglio, quadra anche nel bot. I dati scritti dal bot sono in blu, le formule in nero, le righe della FADD in arancione;
- manda al gruppo admin la proposta: risultati, FADD, avvisi (panchina mancante → senza supplementari, quintetto incompleto, giocatori senza id ESPN, panchinari ceduti prima della scadenza → tolti dalla panchina e gli altri scalano, titolari non più in squadra alla scadenza → da correggere da Yahoo), con **✅ Convalida** e **🔄 Ricalcola**.

**Ricalcolo di una giornata già convalidata**: la proposta nuova dice in fondo cosa cambia rispetto ai risultati convalidati, partita per partita (punti, supplementari, ⚠️ vincitore), oppure «stessi risultati»; lo ripete il messaggio di conferma quando la convalidi. Sul canale, se cambia chi vince, esce anche un avviso.

Se a quell'ora la giornata non si può ancora calcolare (una partita non finita, un tabellino che manca, quintetti non congelati) lo dice sul canale log: quando è pronta, `/ricalcola N`.

**Controlli e correzioni.** Si correggono sempre dal bot, mai a mano sul foglio (il bot riscrive il tab a ogni ricalcolo):
- status di un giocatore: `/set_valid_status GIOCATORE N` (qui);
- quintetto della giornata: `/quintetto_admin SQUADRA GN` (IPanchinari);
- panchina della giornata: `/panchina_admin SQUADRA GN` (IPanchinari);
- fantapunti sbagliati: finché la notte è aperta il ricalcolo li riscarica da ESPN; se no `/correggi_tabellino`.

Poi **🔄 Ricalcola** (o `/ricalcola N`): il bot riscarica i tabellini delle notti non ancora congelate, ricalcola, riscrive il tab e manda una proposta nuova; quella vecchia perde i bottoni.

**✅ Convalida**: solo allora i risultati si salvano e il foglio **Calendario** si aggiorna (punti col bonus casa nella riga della partita, i soli punti dei supplementari nella riga sotto). Sul canale principale esce il messaggio dei **risultati definitivi** e quello live si cancella (da lì il live di quella giornata non si aggiorna più). Se dopo un ricalcolo (per esempio dopo il primo controllo delle 11:05 o il controllo finale delle 20) convalidi di nuovo, si **modifica** lo stesso messaggio dei definitivi; un messaggio in più, in risposta, solo se cambia chi vince una partita. Il bottone di una proposta superata non convalida niente.

**Storico del calcolo**: **`/storico_calcolo N`** mostra tutte le versioni calcolate della giornata (la prima, ogni ricalcolo), quando, quale è stata convalidata e, per ognuna, cosa cambia rispetto alla precedente (punti, supplementari, vincitore). Lo storico c'è dalla v6.9.0: delle giornate di prima resta solo l'ultima versione.

### I controlli dei tabellini, notte per notte

ESPN a volte corregge un tabellino ore dopo la partita. La regola (Luca, 30/10, come Yahoo): **ogni notte NBA si ricontrolla fino alle 20 del giorno dopo, poi è congelata** e non si riscarica più da sola.

| Quando (Roma) | Cosa fa il bot | Cosa arriva |
|---|---|---|
| durante la notte, fino alle 8 | live: riscarica ogni 10 minuti | il tabellone sul canale principale |
| 7:45, dopo l'ultima notte della giornata | riscarica l'ultima notte e calcola | la proposta al gruppo admin (✅ Convalida, 🔄 Ricalcola) |
| 11:05 | **primo controllo** della notte appena finita, anche a giornata già convalidata | cambi degli schierati col dettaglio sul canale log; se la giornata è calcolata, anche al gruppo admin con 🔄 Ricalcola |
| 20:00 del giorno dopo | **controllo finale** della notte: riscarica un'ultima volta, poi la notte è **congelata** | se ESPN ha cambiato degli schierati, al gruppo admin col dettaglio delle statistiche (es. «Norman Powell: 16,00 → 18,00 (rimbalzi difensivi 4 → 5)»): **✅ Uguale su Yahoo** tiene i valori nuovi, **❌ Non corrisponde** rimette quelli di prima; più 🔄 Ricalcola se la giornata è calcolata |
| 20:00, stesso giro | rilegge le **notti prima della stessa giornata**, già congelate, **senza salvare niente** | se ESPN ora le dà diverse per qualche schierato, al gruppo admin: **✅ Su Yahoo è così: aggiorna** salva i valori nuovi (poi 🔄 Ricalcola), **❌ Lascia com'è** non cambia niente. La stessa differenza non si ripete le sere dopo; se ESPN la cambia ancora arriva un avviso nuovo e i bottoni del vecchio non valgono più. Se le dà uguali, una riga sul log |

Dopo ogni ✅ o ❌ che cambia dei valori: 🔄 **Ricalcola** e poi **✅ Convalida** (se era già convalidata, la proposta dice cosa cambia). Un bottone premuto sparisce e il messaggio dice chi l'ha premuto.

**A mano** (vale più della regola):

| Comando | Cosa fa |
|---|---|
| `/controllo_notte GG/MM` | rifà il controllo finale di una notte, **anche se è congelata**: riscarica, salva e chiede ✅/❌ come alle 20. Per i casi eccezionali (ESPN non rispondeva alle 20, una correzione arrivata dopo) |
| `/congela_notte GG/MM` · `/scongela_notte GG/MM` | chiude o riapre una notte. Una notte riaperta si riscarica alle 7:45 e con `/ricalcola`, ma non ha un nuovo controllo delle 20: resta aperta finché non la richiudi |
| `/congela N` · `/scongela N` | lo stesso per tutte le notti della giornata N |
| `/congelamento` · `/congelamento_notti` | lo stato delle giornate e delle notti |

**Ai playoff** (quando ci saranno) stessa regola notte per notte, ma il controllo finale è alle 20 oppure un'ora prima della prima partita della giornata successiva, se viene prima; dalla generazione del tabellone si congelano tutte le giornate di regular season.

**Correggere un punteggio**: **`/correggi_tabellino GIOCATORE GN VALORE`** (con la data `GG/MM` in fondo se in quella giornata ha giocato più partite: se manca, il bot propone i comandi già scritti) cambia i fantapunti di quella partita senza riscaricare; poi `/ricalcola N` e la convalida. Su una giornata aperta il bot avvisa che un ricontrollo può rimettere il valore di ESPN (`/congela N` per tenerlo). `/congela`, `/scongela` e ogni correzione vanno nel registro, nel canale log e **sul canale principale**.

**Dopo la convalida**, se scopri un errore: correggi e `/ricalcola N`; alla nuova convalida il Calendario si riscrive.

Il foglio di controllo è un file Google a parte (`CALCOLO_SPREADSHEET_ID` in `gas/globals.gs`; senza, il tab va nel file del Roster).

---

**Titolare anche in panchina** (quintetto corretto copiando Yahoo, per esempio): nel calcolo conta da titolare, e in panchina **quella posizione vale 0** (gli altri non scalano: ai supplementari, a quel giro, la squadra prende 0; non entra per la FADD). Un panchinaro **ceduto** prima della scadenza invece esce dalla panchina e gli altri scalano. Tutti e due arrivano negli avvisi.

**Il foglio di calcolo** ha tutte le celle con lo sfondo bianco esplicito: si legge anche col tema scuro dell'app di Google Fogli.

## I punteggi live

Alla palla a due della prima partita della giornata il bot pubblica sul canale principale un'**immagine** (il tabellone, `live.typ`, v53; Luca, 23/10) con una scheda per partita: loghi, punteggi, chi è avanti in grassetto, etichette 🏀 in campo · ⏳ devono giocare · 🔁 devono rigiocare coi punti già fatti · ✅ finito · 📈 prendono media (legenda in fondo, al plurale; Luca, 25/10), «HANNO GIOCATO IN MENO DI 6» quando l'esito non si dà, «SI VA AI SUPPL.» coi punti dei supplementari. Il testo di prima, con lo stesso contenuto, lo manda **`/live_results`** a chi lo chiede. Il testo: punteggio di casa e trasferta (bonus casa compreso) e, quando dei 10 in campo ne restano al massimo 4 da giocare, l'esito "al momento" (chi vince, coi supplementari se servono); con più di 4 ancora da giocare nessun esito. Accanto, quanti dei 10 titolari stanno giocando adesso (🏀) e, sotto ogni partita, una riga per squadra: «devono giocare N · devono rigiocare N (finora X)», cioè i titolari che non hanno ancora una partita finita, quelli che ne hanno finita una e ne hanno un'altra, e i fantapunti già fatti da questi ultimi. Tra una partita e l'altra c'è una riga vuota. È il calcolo vero (medie, media della stagione, FADD, supplementari) sui tabellini live di ESPN. Sotto c'è scritto che sono **risultati provvisori, da valutare e convalidare da un admin**, e l'ora dell'ultimo aggiornamento.

- Le emoji dell'immagine vengono dal font Noto Color Emoji, installato nel container di loucabot (Dockerfile). Se manca, nel tabellone escono quadratini e il bot lo scrive una volta nel canale log: si ricostruisce loucabot.
- L'anteprima agli admin (`/live` prima della giornata, `/dev_prova_live`) e la proposta delle 7:45 restano in testo.
- Si aggiorna (sostituendo la foto dello stesso messaggio; se il messaggio di prima era di testo o è stato cancellato, ne esce uno nuovo; se Telegram non risponde in tempo il messaggio resta e si riprova al giro dopo) **ogni 10 minuti** dalla prima partita di ogni notte della giornata **fino alle 8 di mattina**, poi **una volta alle 11:05**: il primo controllo della notte appena finita. Riscarica tutte le partite di quella notte (ESPN a volte riassegna le statistiche) e aggiorna il messaggio; se è cambiato il tabellino di un giocatore schierato, sul canale log arriva una riga con le statistiche cambiate, e se la giornata è già calcolata anche al gruppo admin col bottone 🔄 Ricalcola. Il controllo finale della notte è alle 20.
- Formazioni: quelle congelate da IPanchinari alla scadenza (nei primi minuti, finché IPanchinari non chiude la giornata, i quintetti di quel momento).
- Se ESPN risponde storto il bot riprova subito un paio di volte; se ancora non va salta il giro e riprova dopo 10 minuti, con una riga sul canale log **a ogni giro saltato**. Se manca solo il tabellino di una partita, il tabellone si aggiorna lo stesso con le altre (riga sul log) e quella si riprova al giro dopo.
- **`/live`**: aggiorna subito, senza aspettare i 10 minuti (se nessuna giornata è in corso, ti manda l'anteprima della prossima). Anche `/dev_prova_calcolo` manda l'anteprima del messaggio live.
- Fa fede sempre il calcolo delle 7:45 convalidato: il live è solo una stima. **Alla convalida** il messaggio live si cancella (e non si aggiorna più) ed esce quello dei risultati definitivi; vedi sopra.
- Gli orari (fine delle notti alle 8, primo controllo alle 11:05, controllo finale alle 20) si cambiano in `config/settings.json` sotto `"orari"` (`fine_live_notte`, `primo_controllo`, `controllo_notte`), poi riavvio di loucabot.

---

## I punteggi

**Tabellini.** A partita finita il bot scarica da ESPN il tabellino e salva statistiche e fantapunti di ogni giocatore NBA. Lo fa alle 8:30; `/tabellini` lo fa subito, per le partite finite che ancora non ce l'hanno.

**Infortunati.** ESPN dà solo lo stato di adesso, quindi il bot ne salva uno snapshot (dai ruoli dell'offseason fino ai playoff; nelle altre fasi no) ogni 4 ore, anche di notte (0:30, 4:30, 8:30, 12:30, 16:30, 20:30), più uno 30-40 minuti prima di ogni partita NBA (il report subito prima delle partite) e, la prima sera di ogni giornata, uno ogni mezz'ora dalle 19 alla prima partita (`orari.injury_fitti`): IPanchinari avvisa i GM di ogni cambio di stato dei loro giocatori. Per il calcolo conta, di ogni giorno, **l'ultimo snapshot prima della partita della squadra del giocatore** (v68, Luca 31/10: così un Out dell'ultimo minuto, arrivato dopo la prima partita della notte, conta per la FADD); nei giorni in cui la sua squadra non gioca, quello subito prima della prima partita NBA. Il più recente è lo stato che IPanchinari mostra accanto ai giocatori. Si tengono tutti gli snapshot dell'ultima settimana; per i giorni più vecchi restano quelli che contano (quello del giorno e l'ultimo prima di ogni partita). Anche `/tabellini` ne salva uno. Servono per due regole:
- chi è in una squadra a media prende 0 invece della media se nello snapshot del giorno di ogni giorno della giornata risulta indisponibile (stato diverso da Probable);
- la FADD (il panchinaro che entra al posto del titolare che non ha giocato): il titolare deve avere il tag in tutti i giorni in cui la sua squadra ha giocato, o in tutta la giornata se la sua squadra non ha giocato. La panchina scala e resta di 4: al quinto supplementare quella squadra aggiunge 0. Se manca lo snapshot di uno di quei giorni il bot non sostituisce e lo segnala: decide un admin.

**Giocatori e id ESPN.** Il calcolo collega i giocatori dell'anagrafica a ESPN con l'id ESPN, non col nome. L'abbinamento è automatico quando il nome è uguale (senza accenti, punteggiatura, Jr./III) e corrisponde a un solo giocatore.
- `/espn_giocatori` scarica i roster delle 30 squadre e abbina. Si rifà ogni tanto, per esempio dopo il mercato NBA.
- `/espn_mancanti` elenca i giocatori a roster nella lega senza id ESPN, con i nomi ESPN più simili.
- `/espn_abbina ID_GIOCATORE ID_ESPN` abbina a mano. L'id del giocatore è quello di `/espn_mancanti`; l'id ESPN è il numero nell'indirizzo della pagina del giocatore su espn.com (`…/player/_/id/4432174/cam-thomas`). Attenzione ai suggerimenti: sono solo nomi simili, non per forza giusti.

**`/set_valid_status GIOCATORE N`**: quando gli snapshot non tornano (un report arrivato tardi, un giocatore segnato Out che poi ha giocato, uno sparito dalla lista per sbaglio) decidi tu lo status che vale per il calcolo della giornata N. Il bot mostra tutti gli snapshot del giocatore in quella giornata, giorno per giorno, con ★ quello che conta, e un bottone per ogni stato catturato (Out, Questionable, sano…): quello che scegli vale per tutta la giornata, sia per la media a 0 sia per la FADD, al posto degli snapshot. "↩️ Torna agli snapshot" annulla. Ogni scelta finisce sul canale log. Gli snapshot dei giorni più vecchi di una settimana si riducono a uno per giorno: le correzioni conviene farle prima.

**`/fantapunti [N]`** mostra i fantapunti della giornata di tutti i giocatori a roster, divisi per squadra (📈 = ha preso la media). Serve per controllare il calcolo. Se è lungo arriva come file.

**Come si calcola** (regolamento, capitolo Partita):
- chi ha giocato una o più partite della giornata → media delle partite giocate (uno 0 con 0 minuti non conta, uno 0 con dei minuti sì), arrotondata all'ottavo: dopo la virgola solo ,00 ,13 ,25 ,38 ,50 ,63 ,75 ,88 (sul foglio `ROUND(media*8)/8`; lo stesso per la media della stagione);
- chi non ha giocato, se la sua squadra NBA non aveva partite (o solo partite rinviate) → la sua media della stagione, 0 se indisponibile;
- chi non ha giocato mentre la sua squadra sì → 0;
- squadra: somma dei 5 titolari, con la FADD; vince chi ha almeno 5 punti di scarto, bonus casa compreso (3, nei playoff 5); altrimenti supplementari con i panchinari in ordine; pari fino al decimo uomo → vince la trasferta. Sul Calendario: punti col bonus casa, e sotto i soli punti dei supplementari.

Restano agli admin le 72 ore di attesa per le partite rinviate e le penalità.

---

## Controllo del tanking

**Il mattino dopo la prima notte** di ogni giornata, alle 11 (`orari.controllo_tanking`), arriva **solo al gruppo admin** un report con gli **indizi** di formazioni che sembrano fatte per perdere. Sono indizi, non verdetti: minutaggi, rientri e riposi sono scelte legittime, decidete voi. Per ogni squadra, dalla formazione congelata e dalla panchina:

- **titolare scarso**: in rosa c'è un escluso che può giocare quel posto (posizioni eleggibili di Yahoo), è sano, ha partite nella giornata e ha una media **almeno +8 o +30%** più alta del titolare;
- **titolare indisponibile** mentre in rosa c'è un sano che può giocare quel posto e ha partite.

Se l'escluso adesso ha un altro ruolo, il report lo dice («ora è PG: servirebbe un cambio ruolo»): può giocare quel posto per le posizioni eleggibili, ma non si vuole costringere un GM a un cambio ruolo subito, quindi l'indizio pesa meno.

Lo stato è quello dell'injury report **alla scadenza** (l'ultimo prima della prima partita della giornata), cioè quello che il GM sapeva quando ha schierato. È diverso apposta dalla FADD, che guarda l'ultimo report prima della partita del giocatore: un Out dell'ultimo minuto non è un indizio di tanking. Per lo stesso motivo gli status decisi con `/set_valid_status` qui non contano.
- **posto del quintetto vuoto** e **panchina non mandata**.

Un titolare la cui squadra NBA non gioca nella giornata prende la sua media: non è un indizio (salvo se indisponibile). Le medie sono quelle della stagione prima della giornata. Le squadre sono in ordine dal fondo della classifica; quelle nell'ultimo terzo hanno ⬇️, perché lì il tanking conviene. Se non c'è niente, una riga «nessun indizio».

**`/tanking [N]`** ti manda lo stesso report quando vuoi (senza N, l'ultima giornata iniziata).

La seconda parte (dopo la convalida, quanti punti avrebbe fatto la formazione migliore e lo storico per squadra) è da fare.

## Foto dei giocatori

Il bot scarica da ESPN le foto **piano piano, solo di notte negli Stati Uniti** (dalle 8 alle 12 italiane circa), una al minuto, per non farsi limitare: prima i giocatori a roster, poi tutti gli attivi in NBA, poi tutti gli altri del database con un id ESPN. La prima volta servono alcune notti; poi aggiorna chi cambia squadra e le foto più vecchie di 14 giorni (90 per chi non gioca). `/dev_foto` (dev) dice a che punto è. Stanno in `config/foto` sul server (non in git e **non nel backup**: se si perdono, il bot le riscarica da solo). `/player` mostra la foto quando c'è.

## Comandi

| Comando | Cosa fa |
|---|---|
| `/importa_calendario` | importa il CSV (didascalia del file, o in risposta al file) |
| `/calendario_check` | scadenze e squadre a media, confronto col CSV |
| `/nba_sync` | riscarica le partite NBA della stagione |
| `/calendario_foglio` | ricarica il foglio Google Calendario (A:E) |
| `/tabellini` | tabellini mancanti e snapshot degli infortunati |
| `/espn_giocatori` | roster NBA da ESPN e abbinamento automatico |
| `/espn_mancanti` | giocatori a roster senza id ESPN |
| `/espn_abbina ID_GIOCATORE ID_ESPN` | abbinamento a mano |
| `/ricalcola N` | riscarica i tabellini della giornata N (se non è congelata), ricalcola, riscrive il tab «Calcolo GN» e ripropone la convalida |
| `/tanking [N]` | controllo del tanking della giornata: indizi nelle formazioni (solo a te) |
| `/storico_calcolo N` | tutte le versioni calcolate della giornata N, quale è convalidata e cosa cambia da una all'altra |
| `/congelamento` · `/congela N` · `/scongela N` | stato delle giornate (ricontrollate o congelate), e cambiarlo a mano |
| `/congelamento_notti` · `/congela_notte GG/MM` · `/scongela_notte GG/MM` | lo stesso, notte per notte |
| `/controllo_notte GG/MM` | rifà il controllo finale di una notte (riscarica anche se congelata) |
| `/correggi_tabellino GIOCATORE GN VALORE [GG/MM]` | corregge i fantapunti di una partita, senza riscaricare (poi `/ricalcola N`) |
| `/live` | aggiorna subito il messaggio live della giornata in corso (o l'anteprima, se non è iniziata); mai una giornata già convalidata |
| `/fantapunti [N]` | fantapunti della giornata, per squadra |
| `/set_valid_status GIOCATORE N` | lo status di un giocatore che vale per il calcolo della giornata N, scelto tra quelli degli snapshot |
| `/calendario [N]`, `/giornata [N]`, `/live_results [N]` | come i GM |
| `/guida_admin` | questa guida |

## Registro delle azioni

Le azioni che cambiano qualcosa (calendario importato, partite e tabellini riscaricati, abbinamenti ESPN, status validi, giornate calcolate, ricalcolate e convalidate) lasciano una riga nel registro unico di tutti i bot: chi, in che veste (gm, admin, dev, sistema), cosa, prima → dopo. Sul canale log restano le righe di sempre, col nome di chi. Il registro si consulta dal bot principale (comando registro, o pannello admin → 📜 Registro); i GM vedono le righe della loro squadra.
