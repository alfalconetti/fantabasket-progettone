// Fantabasket — tab "Calcolo GN" del foglio di controllo del calcolo (loucabot, via gas-router)
// Il tab della giornata si riscrive tutto a ogni calcolo e ricalcolo: si svuota (valori e
// formattazione) e si scrivono payload.righe, payload.sfondi / testi / pesi (stessa forma delle
// righe, "" = niente), payload.formati ([{range: "F12:H40", formato: "0.00"}]) e payload.congela
// ({righe, colonne}). Gli altri tab non si toccano.
// Le formule (le stringhe che iniziano con "=", scritte in inglese con le virgole) non vanno con
// setValues, che le legge come se le scrivesse una persona nella lingua del foglio (in italiano il
// separatore è ";" e si avrebbe #ERROR!): si scrivono con setFormulas, colonna per colonna. Dopo si
// controlla che nessuna dia #ERROR!; se succede, si riscrivono col separatore ";" e si ricontrolla.
// File: CONFIG.CALCOLO_SPREADSHEET_ID se c'è (il foglio di calcolo), altrimenti quello del Roster.

function getSpreadsheetCalcolo_() {
  const id = (typeof CONFIG !== "undefined" && CONFIG.CALCOLO_SPREADSHEET_ID) || "";
  return id ? SpreadsheetApp.openById(id) : getSpreadsheet();
}

function _nulli_(m) {
  return m.map(function (r) { return r.map(function (x) { return x === "" || x === undefined ? null : x; }); });
}

function _formula_(x) { return typeof x === "string" && x.charAt(0) === "="; }

// "," → ";" fuori dalle virgolette (sintassi delle formule dei fogli in italiano)
function _puntoevirgola_(f) {
  let out = "", dentro = false;
  for (let i = 0; i < f.length; i++) {
    const c = f.charAt(i);
    if (c === '"') dentro = !dentro;
    out += (c === "," && !dentro) ? ";" : c;
  }
  return out;
}

// Gruppi di celle con formula contigue in colonna: [{riga, colonna, formule: [[f], [f]…]}]
function _blocchi_(righe) {
  const blocchi = [];
  const nc = righe[0].length;
  for (let j = 0; j < nc; j++) {
    let i = 0;
    while (i < righe.length) {
      if (_formula_(righe[i][j])) {
        const b = { riga: i + 1, colonna: j + 1, formule: [] };
        while (i < righe.length && _formula_(righe[i][j])) { b.formule.push([righe[i][j]]); i++; }
        blocchi.push(b);
      } else {
        i++;
      }
    }
  }
  return blocchi;
}

function _scriviFormule_(sheet, blocchi, conv) {
  blocchi.forEach(function (b) {
    const f = conv ? b.formule.map(function (r) { return [conv(r[0])]; }) : b.formule;
    sheet.getRange(b.riga, b.colonna, f.length, 1).setFormulas(f);
  });
}

function _errori_(range) {
  SpreadsheetApp.flush();
  let n = 0;
  range.getDisplayValues().forEach(function (r) { r.forEach(function (x) { if (x === "#ERROR!") n++; }); });
  return n;
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
  range.setValues(righe.map(function (r) { return r.map(function (x) { return _formula_(x) ? "" : x; }); }));
  const blocchi = _blocchi_(righe);
  _scriviFormule_(sheet, blocchi, null);
  let sintassi = "virgole", errori = _errori_(range);
  if (errori) {
    _scriviFormule_(sheet, blocchi, _puntoevirgola_);
    sintassi = "punto e virgola";
    errori = _errori_(range);
  }
  if (payload.sfondi) range.setBackgrounds(_nulli_(payload.sfondi));
  if (payload.testi) range.setFontColors(_nulli_(payload.testi));
  if (payload.pesi) range.setFontWeights(_nulli_(payload.pesi));
  (payload.formati || []).forEach(function (f) { sheet.getRange(f.range).setNumberFormat(f.formato); });
  if (payload.congela) {
    sheet.setFrozenRows(payload.congela.righe || 0);
    sheet.setFrozenColumns(payload.congela.colonne || 0);
  }
  return respond({ ok: true, righe: righe.length, tab: nome, formule: blocchi.length, sintassi: sintassi, errori: errori });
}
