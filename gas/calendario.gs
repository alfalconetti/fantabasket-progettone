// Fantabasket — foglio Calendario (loucabot, via gas-router)
// Ricarica tutta la pagina nelle colonne A:E: svuota i valori (clearContent: formattazione e
// celle unite restano) e scrive payload.righe, la griglia del calendario costruita da loucabot
// (intestazioni "Week N …" con il testo in A, partite "Casa | punti | V | punti | Trasferta",
// supplementari nella riga sotto). Le altre colonne e gli altri fogli non si toccano.
// Nome del foglio da CONFIG.CALENDARIO_SHEET_NAME se c'è, altrimenti "Calendario" (maiuscole libere).

// v7.15.0: con payload.foglio (es. "Playoff 26-27") scrive in quel foglio, creandolo se non c'è, con tutte le colonne
// della griglia (i playoff in un foglio a parte, come il vecchio foglio dei playoff; il Calendario resta della regular season).
function trovaFoglioCalendario_(ss, nomeDato) {
  const nome = nomeDato || (typeof CONFIG !== "undefined" && CONFIG.CALENDARIO_SHEET_NAME) || "Calendario";
  const esatto = ss.getSheetByName(nome);
  if (esatto) return esatto;
  const fogli = ss.getSheets();
  for (let i = 0; i < fogli.length; i++) {
    if (fogli[i].getName().trim().toLowerCase() === nome.toLowerCase()) return fogli[i];
  }
  return null;
}

function handleCalendario(payload) {
  const ss = getSpreadsheet();
  let sheet = trovaFoglioCalendario_(ss, payload.foglio);
  if (!sheet && payload.foglio) sheet = ss.insertSheet(payload.foglio);
  if (!sheet) return respond({ error: "Foglio Calendario non trovato" });
  const righe = payload.righe || [];
  if (!righe.length) return respond({ error: "Calendario vuoto" });
  const nc = payload.foglio ? righe[0].length : 5;       // il foglio dei playoff è largo (A–W), il Calendario A:E
  for (let i = 0; i < righe.length; i++) {
    if (!Array.isArray(righe[i]) || righe[i].length !== nc) return respond({ error: "Riga " + (i + 1) + ": servono " + nc + " colonne" });
  }
  const ultima = Math.max(sheet.getLastRow(), righe.length);
  const tutto = sheet.getRange(1, 1, ultima, nc);
  if (payload.stili) { tutto.breakApart(); tutto.clearFormat(); }   // il foglio dei playoff: la formattazione la dà il bot
  tutto.clearContent();
  sheet.getRange(1, 1, righe.length, nc).setValues(righe);
  if (payload.stili) applicaStili_(sheet, payload.stili, payload.larghezze);
  return respond({ ok: true, righe: righe.length, stili: (payload.stili || []).length });
}

// v7.15.1 (Luca, 15/11): la formattazione del foglio dei playoff, per intervalli:
// {range: "B2:W2", sfondo, colore, grassetto, corsivo, dimensione, allinea, formato, unisci, bordo}; larghezze {colonna: pixel}.
function applicaStili_(sheet, stili, larghezze) {
  for (let i = 0; i < stili.length; i++) {
    const s = stili[i];
    const r = sheet.getRange(s.range);
    if (s.unisci) r.merge();
    if (s.sfondo) r.setBackground(s.sfondo);
    if (s.colore) r.setFontColor(s.colore);
    if (s.grassetto) r.setFontWeight("bold");
    if (s.corsivo) r.setFontStyle("italic");
    if (s.dimensione) r.setFontSize(s.dimensione);
    if (s.allinea) r.setHorizontalAlignment(s.allinea);
    if (s.formato) r.setNumberFormat(s.formato);
    if (s.bordo) r.setBorder(true, true, true, true, null, null, s.bordo, SpreadsheetApp.BorderStyle.SOLID);
  }
  Object.keys(larghezze || {}).forEach(function (c) { sheet.setColumnWidth(Number(c), larghezze[c]); });
}
