# Guida GM — loucabot

loucabot è il bot del campionato: il calendario della lega, le scadenze per la formazione, le squadre NBA a media e, man mano, i punteggi. Roster, trade e tagli restano nel bot principale, le aste nel bot delle aste.

Funziona in privato e nei gruppi. In privato ti riconosce come GM della tua squadra.

---

## La tua giornata: `/calendario`

Scrivi `/calendario` e vedi la giornata in corso, o la prossima se non ne è in corso nessuna:

- **le date** della giornata (giorni NBA, cioè della costa est americana);
- **⏰ entro quando mettere formazione e panchina**: l'ora della prima partita NBA della giornata, in ora italiana. È la scadenza del regolamento: la panchina va inserita prima dell'inizio della prima partita;
- **📉 le squadre NBA a media**: quelle che nella giornata non giocano. I loro giocatori prendono la media (ma chi è infortunato o squalificato prende 0);
- **🏀 il tuo avversario**, e se giochi in casa (+3 punti) o in trasferta;
- **le prossime tre giornate**: 🏠 in casa, ✈️ in trasferta.

`/calendario 12` mostra la giornata 12.

## Tutte le partite: `/giornata`

`/giornata` elenca le 12 partite della giornata in corso (o la prossima), `/giornata 12` quelle della 12. Va bene anche nei gruppi. Per le giornate già convalidate dagli admin ci sono anche i risultati (chi vince in grassetto, i supplementari se ci sono stati); una giornata calcolata ma non ancora convalidata lo dice. Anche `/calendario` mostra il risultato della tua partita quando c'è.

## La classifica: `/classifica` e `/classifica_full`

`/classifica` manda l'immagine della classifica: vittorie, sconfitte, punti fatti e subiti (col bonus casa), media punti e striscia (3W = tre vittorie di fila, 1L = una sconfitta). Contano solo le giornate convalidate dagli admin. A parità di vittorie contano gli scontri diretti tra le squadre a pari (solo vittorie e sconfitte, mai lo scarto; con tre o più squadre la classifica avulsa tra loro), poi la media punti, poi la differenza.

`/classifica_full` manda la classifica completa (un file, perché è larga): in più media delle ultime 10 giornate, quante volte hai fatto il punteggio più alto della giornata, massimo e minimo, età media, record subiti (quante volte l'avversario ha fatto il punteggio più alto, o più basso, della giornata), coefficiente di variazione dei punti, fantapunti medi e percentuale di partite giocate di roster e quintetto di adesso, età del quintetto, scarto medio nelle vittorie e nelle sconfitte (senza supplementari) e supplementari giocati (vinti-persi).

## Un giocatore: `/player`

`/player Wembanyama` (basta un pezzo del nome; se ce n'è più d'uno ti fa scegliere): la squadra NBA di adesso e lo status degli infortunati, la squadra del fantabasket con ruolo e contratto (o svincolato), poi la stagione: partite, media dei fantapunti (la stessa che usa il calcolo), minuti, punti, rimbalzi, assist, recuperi, stoppate, perse e percentuali al tiro, e le ultime 5 partite coi fantapunti.

---

## Da dove vengono questi dati

Il calendario della lega lo importano gli admin. Le partite NBA il bot le scarica da ESPN e le ricontrolla ogni mattina: se l'NBA sposta una partita, la scadenza o le squadre a media di una giornata possono cambiare, e il bot si aggiorna da solo (gli admin ricevono un avviso).

Se le squadre a media scritte nel calendario pubblicato e quelle del bot non coincidono, vale il bot: le calcola dalle partite NBA vere.

## I punteggi

Il bot scarica ogni mattina i tabellini delle partite della notte e calcola i fantapunti di ogni giocatore con la formula del regolamento (punto +0,5, assist +2, rimbalzo offensivo +2, difensivo +1,25, tripla +1,5, tiro dal campo tentato −0,5 e segnato +1, libero tentato −0,75 e segnato +1, recupero +2, stoppata +2, palla persa −2). Il risultato di ogni giornata lo calcola il bot la mattina dopo l'ultima notte, dai quintetti e dalle panchine di IPanchinari: chi ha giocato più partite prende la media (uno 0 con 0 minuti non conta), arrotondata all'ottavo (dopo la virgola solo ,00 ,13 ,25 ,38 ,50 ,63 ,75 ,88), chi è in una squadra NBA che non gioca prende la sua media della stagione (0 se è infortunato tutta la giornata), con la FADD e i supplementari del regolamento. Gli admin lo controllano sul foglio di calcolo e lo convalidano: solo allora finisce sul foglio Calendario.

**Punteggi live.** Durante la giornata, sul canale principale c'è un messaggio con tutte le partite che si aggiorna ogni 10 minuti dalla prima partita di ogni notte fino alle 8 di mattina (e un'ultima volta verso le 10): punteggi, chi vince al momento (solo quando dei 10 in campo ne restano al massimo 4 da giocare), quanti dei tuoi 5 in campo stanno giocando (🏀) e quanti hanno ancora una partita nella giornata (⏳). Sono **provvisori**: fanno fede i risultati convalidati dagli admin.

---

`/start` ti ricorda i comandi, `/guida` ti manda questa guida.

Se qualcosa non torna, scrivi a un admin.
