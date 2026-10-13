// Fantabasket — tab "Calcolo GN" del foglio di controllo del calcolo (loucabot, via gas-router)
// Il tab della giornata si riscrive tutto a ogni calcolo e ricalcolo: si svuota (valori e
// formattazione) e si scrivono payload.righe (valori e formule: una stringa che inizia con "=" è
// una formula, in inglese con le virgole), payload.sfondi / testi / pesi (stessa forma delle righe,
// "" = niente), payload.formati ([{range: "F12:H40", formato: "0.00"}]) e payload.congela
// ({righe, colonne}). Gli altri tab non si toccano.
// File: CONFIG.CALCOLO_SPREADSHEET_ID se c'è (il foglio di calcolo), altrimenti quello del Roster.

function getSpreadsheetCalcolo_() {
  const id = (typeof CONFIG !== "undefined" && CONFIG.CALCOLO_SPREADSHEET_ID) || "";
  return id ? SpreadsheetApp.openById(id) : getSpreadsheet();
}

function _nulli_(m) {
  return m.map(function (r) { return r.map(function (x) { return x === "" || x === undefined ? null : x; }); });
}

function handleCalcolo(payload) {
  const nome = payload.nome || "";
  const righe = payload.righe || [];
  if (!/^Calcolo G\d+$/.test(nome)) return respond({ error: "Nome del tab non valido: " + nome });
  if (!righe.length) return respond({ error: "Griglia vuota" });
  const nc = righe[0].length;
  for (let i = 0; i < righe.length; i++) {
    if (!Array.isArray(righe[i]) || righe[i].length !== nc) return respond({ error: "Riga " + (i + 1) + ": servono " + nc + " colonne" });
  }
  const ss = getSpreadsheetCalcolo_();
  const sheet = ss.getSheetByName(nome) || ss.insertSheet(nome);
  sheet.clear();
  const range = sheet.getRange(1, 1, righe.length, nc);
  range.setValues(righe);
  if (payload.sfondi) range.setBackgrounds(_nulli_(payload.sfondi));
  if (payload.testi) range.setFontColors(_nulli_(payload.testi));
  if (payload.pesi) range.setFontWeights(_nulli_(payload.pesi));
  (payload.formati || []).forEach(function (f) { sheet.getRange(f.range).setNumberFormat(f.formato); });
  if (payload.congela) {
    sheet.setFrozenRows(payload.congela.righe || 0);
    sheet.setFrozenColumns(payload.congela.colonne || 0);
  }
  return respond({ ok: true, righe: righe.length, tab: nome });
}
