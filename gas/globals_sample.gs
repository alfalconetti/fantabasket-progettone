// Fantabasket — configurazione globale condivisa tra tutti gli handler
// ATTENZIONE: questo file è nel gitignore — la versione con SPREADSHEET_ID
// reale va tenuta solo in locale. Questo è il sample senza dati sensibili.

const CONFIG = {
  SPREADSHEET_ID: "YOUR_SPREADSHEET_ID_HERE",
  ROSTER_SHEET_NAME: "Roster",
  SCELTE_SHEET_NAME: "Scelte",
  CONFERENCE_ROW_BASES: [3, 30],
  OFFSET_PLAYERS_START: 3,
  OFFSET_PLAYERS_END:   17,
  OFFSET_TAGLI:         20,
  OFFSET_CAMBI_RUOLO:   21,
  OFFSET_TAGLIATI_LABEL: 22,
  OFFSET_IMPATTI:       [23, 24],
  COLS_PER_TEAM: 4,

  // Scelte
  SCELTE_DATA_ROW_START: 4,
  SCELTE_COL_NOME:       2,
  SCELTE_COL_DIRITTI:    4,
  SCELTE_COL_DRAFT:      6,
  SCELTE_COL_ANNI_START: 8,
  SCELTE_ANNI_COUNT:     6,
  SCELTE_COLS_PER_ANNO:  2,
};

const TEAM_MAP = {
  // Conference 0
  "team06": { conference: 0, pos: 0 },
  "team08": { conference: 0, pos: 1 },
  "team14": { conference: 0, pos: 2 },
  "team15": { conference: 0, pos: 3 },
  "team07": { conference: 0, pos: 4 },
  "team21": { conference: 0, pos: 5 },
  "team09": { conference: 0, pos: 6 },
  "team01": { conference: 0, pos: 7 },
  "team24": { conference: 0, pos: 8 },
  "team13": { conference: 0, pos: 9 },
  "team19": { conference: 0, pos: 10 },
  "team04": { conference: 0, pos: 11 },
  // Conference 1
  "team17": { conference: 1, pos: 0 },
  "team16": { conference: 1, pos: 1 },
  "team03": { conference: 1, pos: 2 },
  "team10": { conference: 1, pos: 3 },
  "team12": { conference: 1, pos: 4 },
  "team22": { conference: 1, pos: 5 },
  "team11": { conference: 1, pos: 6 },
  "team02": { conference: 1, pos: 7 },
  "team20": { conference: 1, pos: 8 },
  "team18": { conference: 1, pos: 9 },
  "team23": { conference: 1, pos: 10 },
  "team05": { conference: 1, pos: 11 },
};

const DIV_COLORS = {
  A: { dark: "#f2900e", mid: "#ffc000", light: "#ffe699" },
  B: { dark: "#00b050", mid: "#92d050", light: "#e2efda" },
  C: { dark: "#5b9bd5", mid: "#00b0f0", light: "#ddebf7" },
  D: { dark: "#ffff00", mid: "#ecec5a", light: "#f9f99f" },
  E: { dark: "#ff0000", mid: "#ff4b4b", light: "#f7bdb3" },
  F: { dark: "#8037b7", mid: "#a06bdb", light: "#deb4e4" },
};

function getSpreadsheet() {
  return SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
}

function respond(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
