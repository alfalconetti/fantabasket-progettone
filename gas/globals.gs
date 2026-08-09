// Fantabasket — configurazione globale condivisa tra tutti gli handler
// ATTENZIONE: questo file è nel gitignore — contiene dati specifici della lega

const CONFIG = {
  SPREADSHEET_ID: "1w93dDLaSPjSjp0WPapD2DQLVrxuAjfxntzKMd03Tevo", // aggiornare con ID definitivo
  ROSTER_SHEET_NAME: "Roster",
  SCELTE_SHEET_NAME: "Scelte",
  CONFERENCE_ROW_BASES: [3, 30],
  OFFSET_PLAYERS_START: 3,
  OFFSET_PLAYERS_END: 17,
  OFFSET_TAGLI: 20,
  OFFSET_CAMBI_RUOLO: 21,
  OFFSET_TAGLIATI_LABEL: 22,
  OFFSET_IMPATTI: [23, 24],
  COLS_PER_TEAM: 4,
};

const TEAM_MAP = {
  // Conference 0 — compilare con i team_id corretti
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

function getSpreadsheet() {
  return SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
}

function respond(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
