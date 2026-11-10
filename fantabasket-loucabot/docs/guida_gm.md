# Guida GM — loucabot

loucabot è il bot del campionato: il calendario della lega, le scadenze per la formazione, le squadre NBA che prendono la media e, man mano, i punteggi. Roster, trade e tagli restano nel bot principale, le aste nel bot delle aste.

Funziona in privato e nei gruppi. In privato ti riconosce come GM della tua squadra.

---

## La tua giornata: `/calendario`

Scrivi `/calendario` e vedi la giornata in corso, o la prossima se non ne è in corso nessuna:

- **le date** della giornata (giorni NBA, cioè della costa est americana);
- **⏰ entro quando mettere formazione e panchina**: l'ora della prima partita NBA della giornata, in ora italiana. È la scadenza del regolamento: la panchina va inserita prima dell'inizio della prima partita;
- **📈 le squadre NBA che prendono la media**: quelle che nella giornata non giocano. I loro giocatori prendono la media (ma chi è infortunato o squalificato prende 0);
- **🏀 il tuo avversario**, e se giochi in casa (+3 punti) o in trasferta;
- **le prossime tre giornate**: 🏠 in casa, ✈️ in trasferta.

`/calendario 12` mostra la giornata 12. Puoi anche guardare quella di un'altra squadra scrivendone l'id, il nome (anche solo l'inizio) o il nome del GM: `/calendario Buffalo`, `/calendario 12 Buffalo`.

## Tutta la stagione: `/calendario_full`

`/calendario_full` manda in un solo messaggio tutto il calendario della tua squadra: per ogni giornata la data, 🏠 casa o ✈️ trasferta e l'avversario, e per le giornate già convalidate il risultato (✅ V o ❌ S, i tuoi punti prima, «supp.» se si è andati ai supplementari), con il record in cima. `/calendario_full SQUADRA` per un'altra squadra.

## Tutte le partite: `/giornata`

`/notte` mostra i tuoi schierati in una notte NBA: per ogni titolare e panchinaro la partita (vs / @ e avversario), l'orario se deve ancora giocare, i fantapunti se ha giocato (🏀 se è in campo adesso, DNP se non è entrato), 🩹 se è nel rapporto infortuni, e il totale dei titolari. Senza niente la tua squadra e la notte in corso (fino a mezzogiorno di New York, cioè le 18 da noi, quella appena passata); `/notte Alfa`, `/notte 21/10`, `/notte Marco 21/10/26` per un'altra squadra (nome, id o GM) o un'altra notte. I fantapunti sono provvisori fino alla convalida.

`/partita` manda l'immagine di una sfida: in alto il tabellone (punteggi, sotto ogni logo il **record** della squadra di adesso, W-L, con «prima di questa partita: W-L» se dopo quella giornata se ne sono convalidate altre, supplementari, se è in corso, calcolata o convalidata, e a che ora sono stati scaricati gli ultimi tabellini), sotto le due squadre con quintetto e panchina, una colonna per ogni notte della giornata (i fantapunti, DNP se la sua squadra ha giocato ma lui no, «vs XXX» o «@XXX» se deve ancora giocare, vuota se non gioca) e la colonna **Punti effettivi**, quello che il giocatore porta davvero (sotto la panchina, tra due righe viola, la **Tribuna**: gli altri giocatori a roster col loro punteggio della giornata, «25,00 (20,00 · 30,00)» se hanno giocato più partite, «vs XXX» se devono ancora giocare, DNP, «—» se la loro squadra non gioca, NA se non hanno una squadra NBA; i ceduti dopo la scadenza restano nella squadra vecchia fino a fine giornata): la media delle sue partite nella giornata, MEDIA se la sua squadra NBA non gioca, ↓ FADD se è uscito, ↑ se è entrato per la FADD, S1, S2… se ha giocato i supplementari. Sotto, le spiegazioni (FADD, medie, supplementari). Senza niente la tua partita della giornata in corso (la stessa fino alla convalida; la successiva dalle 16 del suo primo giorno); `/partita Alfa G3`, oppure `/partita Alfa - Beta` per le sfide tra due squadre nella stagione (se sono più d'una scegli coi bottoni).

**`/giornata`** (o `/giornata N`) ti manda il tabellone della giornata come immagine, uguale al live: a giornata in corso i punteggi provvisori, a giornata calcolata o convalidata i risultati, con l'etichetta CALCOLATA o CONVALIDATA. **`/risultati`** elenca in testo le 12 partite della giornata in corso; finita una giornata resta quella, coi risultati, fino alle 16 del primo giorno della successiva (come `/partita`), e solo dopo la convalida; `/giornata 12` quelle della 12. Va bene anche nei gruppi. Per le giornate già convalidate dagli admin ci sono anche i risultati (chi vince in grassetto, i supplementari se ci sono stati). Una giornata iniziata e non ancora convalidata mostra i punteggi, con scritto in testa cosa sono: **live** (provvisori, durante la giornata) oppure, dopo il calcolo delle 7:45, **calcolati, in attesa della convalida** di un admin. Anche `/calendario` mostra il risultato della tua partita quando c'è.

## La classifica: `/classifica` e `/classifica_full`

`/classifica` manda l'immagine della classifica: vittorie, sconfitte, punti fatti e subiti (col bonus casa), media punti e striscia (3W = tre vittorie di fila, 1L = una sconfitta). Contano solo le giornate convalidate dagli admin. A parità di vittorie contano gli scontri diretti tra le squadre a pari (solo vittorie e sconfitte, mai lo scarto; con tre o più squadre la classifica avulsa tra loro), poi la media punti, poi la differenza.

Nelle immagini il valore migliore di ogni colonna è in **verde** e il peggiore in **rosso** (tranne vittorie e sconfitte; per punti subiti, età e simili il migliore è il più basso). A pari merito sono colorati tutti.

`/classifica_conference` è la stessa classifica divisa per conference: l'ordine è quello della generale (gli ex aequo si risolvono sulla generale, non tra le sole squadre della conference), con la posizione nella conference e, a destra, quella generale. In fondo a ogni conference, sotto la colonna Media, la media punti della conference.

`/classifica_full` manda la classifica completa (un file, perché è larga): in più media delle ultime 10 giornate, quante volte hai fatto il punteggio più alto della giornata, massimo e minimo, età media, record subiti (quante volte l'avversario ha fatto contro di te il suo punteggio più alto, o più basso, della stagione), coefficiente di variazione dei punti, fantapunti medi e percentuale di partite giocate del roster di adesso e del quintetto migliore possibile (per ogni ruolo il giocatore con più fantapunti di media), età del quintetto, scarto medio nelle vittorie e nelle sconfitte (senza supplementari) e supplementari giocati (vinti-persi).

## Gli infortunati di una squadra: `/status`

`/status` (la tua squadra) o `/status SQUADRA`: i giocatori sotto contratto che sono nella lista degli infortunati di ESPN, dall'ultimo snapshot che il bot ha già (niente richieste a ESPN): stato (prima gli Out), squadra NBA, da quando e il dettaglio di ESPN. Chi non c'è è disponibile; chi non è abbinato a ESPN è elencato a parte.

## Un giocatore: `/player`

`/player Wembanyama` (basta un pezzo del nome, anche col cognome prima del nome; se ce n'è più d'uno ti fa scegliere), con la foto ESPN del giocatore quando il bot l'ha già (le scarica piano piano di notte): la squadra NBA di adesso e lo status degli infortunati, le posizioni eleggibili, la squadra del fantabasket col ruolo (o la dichiarazione ancora aperta) e lo stato del contratto (importo, anni rimasti e fino a quale stagione, rookie, 10-day, DPE, contratto finito x0 e se è dichiarato RFA; il bot è nato nel 2026, quindi i contratti firmati prima risultano firmati nel 2026-27, e una nota in corsivo lo ricorda), oppure free agent o i diritti rookie di chi (per una seconda scelta anche quando scadono: 10 giorni prima della trade deadline della stagione dopo il draft), con la data di nascita e l'età in cima; poi la stagione: partite giocate su quelle della sua squadra NBA (da quando c'è, se è arrivato a stagione in corso; con le due squadre, se è stato scambiato), media dei fantapunti (la stessa che usa il calcolo), minuti, punti, rimbalzi, assist, recuperi, stoppate, perse e percentuali al tiro, la **media delle ultime 5 partite giocate** (fantapunti e minuti, da 6 partite in su), la media della stagione prima (da Basketball-Reference, con le partite giocate), e le ultime 5 partite coi fantapunti. Sotto la squadra NBA c'è anche la **prossima partita** (avversario, in casa o fuori, giorno e ora italiana e in quale giornata del fantabasket cade). Anche le partite **saltate** (non era nel tabellino: infortunato, fuori rotazione) compaiono, e quelle di fila stanno in una riga sola («dal 02/11 al 11/11: 10 partite saltate»); «non è entrato» (a referto senza giocare) resta a parte.

## Il rendimento: `/rendimento` e `/rendimento_carriera`

`/rendimento NOME` manda un grafico della **stagione partita per partita**: un punto per partita coi fantapunti, del colore della squadra del fantabasket in cui era il giocatore quel giorno (grigio se libero), una × per le partite in cui non ha giocato (o ha fatto 0 in 0 minuti, che non fa media). Play-in e playoff in fondo, su sfondo dorato, col rombo. Due linee: la **media delle ultime 5** (piena) e la **media dall'inizio della stagione** (tratteggiata). Sotto, una fascia per ogni periodo in una squadra, con la media in quel periodo. In alto la media della stagione come in `/player` (regular season e play-in), quella dei playoff e la migliore partita.

`/rendimento_carriera NOME` manda una barra per **ogni stagione**: la fantamedia dalle medie di Basketball-Reference (regular season), con partite, minuti e squadre NBA (in ordine, se ha cambiato squadra); la stagione in corso dai tabellini, come `/player`; i tondi delle squadre del fantabasket in cui è stato in quella stagione, uno sopra l'altro, coi nomi colorati sotto la barra (dal 2026-27). In alto la fantamedia della carriera, pesata sulle partite. Funziona anche per i giocatori che non sono mai stati nella lega: se il nome non è nel bot lo cerca tra tutti quelli di Basketball-Reference, **dal 1979-80**.

**`/confronto A vs B`** mette **due giocatori** uno sopra l'altro nello stesso grafico della stagione: A in blu, B in arancione, le partite sulle date (così quelle dello stesso giorno sono una sopra l'altra), per ognuno la media delle ultime 5 (piena) e quella dall'inizio (tratteggiata); sotto una tabella con fantamedia (come `/player`), partite, ultime 5, playoff, minuti e migliore partita, il migliore dei due in grassetto. **`/confronto_carriera A vs B`** confronta le **carriere**: barre affiancate stagione per stagione, allineate per **stagione di carriera** (1ª, 2ª…: così si confrontano anche giocatori di epoche diverse), sotto le stagioni vere; tabella con fantamedia in carriera, stagioni, partite e stagione migliore. Funziona anche coi giocatori storici. I nomi: `A vs B`, `A contro B`, `A, B` o `A - B`; se un nome è ambiguo il bot elenca i possibili e chiede il nome completo.

Ci sono anche nel bot principale, in privato.

---

## Da dove vengono questi dati

- **ESPN** (le pagine pubbliche delle partite NBA): calendario e risultati NBA, i **tabellini** da cui il bot calcola i fantapunti (anche quelli live), la lista degli **infortunati**, la squadra NBA di ogni giocatore e le foto. I tabellini si ricontrollano alle 11:05 e alle 20 del giorno dopo: fino ad allora possono cambiare.
- **Basketball-Reference**: le statistiche della stagione di ogni giocatore (medie a partita), aggiornate ogni giorno alle 12. Da lì la **fantamedia** del roster, della lista dei free agent e del foglio Roster.
- **Yahoo**: la lega dove si schierano i quintetti (per il regolamento fa fede Yahoo) e le **posizioni eleggibili** dei giocatori, che decidono i ruoli.
- Tutto il resto (contratti, trade, aste, panchine, risultati, classifica) è della lega e sta nel database dei bot.

Il calendario della lega lo importano gli admin. Le partite NBA il bot le scarica da ESPN e le ricontrolla ogni mattina: se l'NBA sposta una partita, la scadenza o le squadre che prendono la media in una giornata possono cambiare, e il bot si aggiorna da solo (gli admin ricevono un avviso).

Se le squadre che prendono la media scritte nel calendario pubblicato e quelle del bot non coincidono, vale il bot: le calcola dalle partite NBA vere.

## I punteggi

Il bot scarica ogni mattina i tabellini delle partite della notte e calcola i fantapunti di ogni giocatore con la formula del regolamento (punto +0,5, assist +2, rimbalzo offensivo +2, difensivo +1,25, tripla +1,5, tiro dal campo tentato −0,5 e segnato +1, libero tentato −0,75 e segnato +1, recupero +2, stoppata +2, palla persa −2). Il risultato di ogni giornata lo calcola il bot la mattina dopo l'ultima notte, dai quintetti e dalle panchine di IPanchinari: chi ha giocato più partite prende la media (uno 0 con 0 minuti non conta), arrotondata all'ottavo (dopo la virgola solo ,00 ,13 ,25 ,38 ,50 ,63 ,75 ,88), chi è in una squadra NBA che non gioca prende la sua media della stagione (0 se è infortunato tutta la giornata), con la FADD e i supplementari del regolamento. Gli admin lo controllano sul foglio di calcolo e lo convalidano: solo allora finisce sul foglio Calendario.

**Punteggi live.** Durante la giornata, sul canale principale c'è un'**immagine** con tutte le partite (il tabellone) che si sostituisce ogni 5 minuti (dalle 2 di notte ogni 10) dalla prima partita di ogni notte fino alle 8 di mattina (e un'ultima volta verso le 10). Una scheda per partita, con loghi e punteggi; in grassetto chi è avanti, ma solo quando dei 10 titolari ne restano al massimo 4 da giocare (prima c'è scritto «HANNO GIOCATO IN MENO DI 6»); in alto nella scheda «SI VA AI SUPPL.» col punteggio dei supplementari, se servono. In alto, sotto il titolo, la banda **NBA · NOTTE DEL …** con tutte le partite NBA vere della notte (fino alle 18 italiane quella appena giocata, poi, se la giornata continua, quella che arriva, con gli orari: lo stesso cambio di `/notte`): loghi, punteggi, quarto e minuti; quelle in corso hanno il bordo rosso, quelle finite «FINALE» (con OT se c'è stato il supplementare), quelle da iniziare l'ora italiana. Se nella giornata qualche squadra NBA non gioca, sotto la banda c'è la **fascia arancione «PRENDONO LA MEDIA IN QUESTA GIORNATA»** con quelle squadre, la stessa di `/partita` (anche in `/giornata` e nella prima pagina di `/pdf_giornata`). Sotto ogni squadra delle etichette col numero di titolari: 🏀 sono in campo adesso, ⏳ devono giocare, 🔁 devono rigiocare (hanno già giocato ma hanno un'altra partita nella giornata, coi punti fatti finora, in ballo), ✅ hanno finito tutti, 📈 prendono media (la loro squadra NBA non gioca nella giornata). La legenda è in fondo all'immagine. **`/top`** ti dà i migliori 20 giocatori NBA per fantamedia della stagione (fantapunti ESPN, regular season e play-in), con partite, squadra NBA, squadra del fanta o «libero» e posizioni eleggibili; entra solo chi ha giocato almeno il 40% delle partite della sua squadra. `/top 50` i primi 50, `/top 50 80` dal 50° all'80°, con `firmati` solo quelli sotto contratto; se è troppo lunga per un messaggio arriva come file. **`/top_storica ANNO`** fa lo stesso per una **stagione passata**, dalle medie di Basketball-Reference (regular season, dal 1979-80): l'anno è quello in cui comincia la stagione, come nella lega (`/top_storica 2014` = 2014-15; va bene anche `2014-15`), poi `N` o `DA A` come per `/top`; entra chi ha giocato almeno il 40% delle partite di chi ne ha giocate di più; per chi ha cambiato squadra le squadre in ordine. **`/pdf_giornata`** (o `/pdf_giornata N`) ti manda la giornata in PDF: i risultati in prima pagina, poi le 12 partite come `/partita`. **`/pdf_partite`** (o `/pdf_partite SQUADRA 2026`) tutte le partite di una squadra nella stagione, una per pagina. **`/live`** (o `/live N`) ti manda l'immagine del live, la stessa del canale, coi dati dell'ultimo aggiornamento. **`/live_results`** (o `/live_results N`) ti manda lo stesso live in testo, completo, anche in più messaggi se è lungo. Sono **provvisori**: alla convalida degli admin l'immagine sparisce ed esce il messaggio dei **risultati definitivi**. In fondo, «📊 In questa giornata»: 🔝 miglior e 🔻 peggior punteggio di squadra; ⭐ il giocatore che ha contato di più (chi ha giocato più partite nella giornata conta per la media: è quel valore); 💥 la miglior singola partita, se un altro l'ha fatta e la media con l'altra partita l'ha abbassata; 👀 il migliore tra tutti i giocatori a roster, anche non schierati. Chi prende la media non entra; sempre con la squadra accanto.

**Top 20 della notte.** Ogni mattina alle 9, nel gruppo della lega, la classifica dei 20 migliori fantapunti della notte appena passata tra i giocatori **schierati** nella giornata (quintetto e panchina, anche i panchinari che non sono entrati nel calcolo): fantapunti, partita (vs/@), squadra e, se era in panchina, «(panchina)». Sotto, se ci sono, le **prestazioni notevoli di giocatori firmati non schierati**: chi sarebbe stato nei 20 tra tutti i giocatori sotto contratto, con la squadra che l'ha lasciato fuori. I fantapunti a quell'ora non sono ancora ricontrollati (11:05 e 20): possono cambiare di poco.

---

`/start` ti ricorda i comandi, `/guida` ti manda questa guida.

Se qualcosa non torna, scrivi a un admin.
