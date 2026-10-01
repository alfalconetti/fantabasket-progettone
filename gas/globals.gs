// Fantabasket — Configurazione globale GAS
// Contiene CONFIG, colori division, TEAM_ORDER e helper getSpreadsheet()

// ── Spreadsheet ───────────────────────────────────────────────────────────────

function getSpreadsheet() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  return SpreadsheetApp.openById(id);
}

// ── Nomi fogli ────────────────────────────────────────────────────────────────

const CONFIG = {
  ROSTER_SHEET_NAME: "Roster",
  SCELTE_SHEET_NAME: "Scelte",

  // Roster: offset righe per team nel foglio Roster
  CONFERENCE_ROW_BASES: {},  // popolato da TEAM_MAP
  COLS_PER_TEAM: 4,
  OFFSET_PLAYERS_START: 2,
  OFFSET_PLAYERS_END:   16,
  OFFSET_TAGLI:         17,
  OFFSET_CAMBI_RUOLO:   18,
  OFFSET_TAGLIATI_LABEL: 19,
  OFFSET_IMPATTI:       [20, 21],

  // Scelte: prima riga dati (sotto intestazioni fisse)
  SCELTE_DATA_ROW_START: 4,   // riga 1=vuota, 2=header anni, 3=TUTTO OK formule
  SCELTE_COL_NOME:    2,      // colonna B — nome squadra / GM / "Altre pick"
  SCELTE_COL_DIRITTI: 4,      // colonna D — diritti 2nd pick
  SCELTE_COL_DRAFT:   6,      // colonna F — numeri pick draft corrente
  SCELTE_COL_ANNI_START: 8,   // colonna H — primo anno (stagione+1)
  SCELTE_ANNI_COUNT:  6,      // 6 anni scambiabili
  SCELTE_COLS_PER_ANNO: 2,    // colonna anno + colonna separatore (vuota)
};

// ── Colori division ───────────────────────────────────────────────────────────
// Per ogni division: [colore_nome_riga, colore_pick_propria, colore_altre]

const DIV_COLORS = {
  A: { dark: "#f2900e", mid: "#ffc000", light: "#ffe699" },
  B: { dark: "#00b050", mid: "#92d050", light: "#e2efda" },
  C: { dark: "#5b9bd5", mid: "#00b0f0", light: "#ddebf7" },
  D: { dark: "#ffff00", mid: "#ecec5a", light: "#f9f99f" },
  E: { dark: "#ff0000", mid: "#ff4b4b", light: "#f7bdb3" },
  F: { dark: "#8037b7", mid: "#a06bdb", light: "#deb4e4" },
};

// ── Ordine team nel foglio Scelte ─────────────────────────────────────────────
// Ordine fisso: divA → divB → divC → divD → divE → divF

const TEAM_ORDER = [
  { id: "team06", gm: "Flavio",             nome: "A.O. Pelicancer",        div: "A" },
  { id: "team08", gm: "Mathias",            nome: "RSM Money Launderers",   div: "A" },
  { id: "team14", gm: "Lorenzo",            nome: "Montecelio Redskins",    div: "A" },
  { id: "team15", gm: "Gevanni",            nome: "La Pasadena Pupils",     div: "A" },
  { id: "team01", gm: "Luca",              nome: "Baltimora Bats",         div: "B" },
  { id: "team07", gm: "Leo",               nome: "Sex Pistons",            div: "B" },
  { id: "team09", gm: "Andrea",            nome: "Varese Konige",          div: "B" },
  { id: "team21", gm: "Cristian",          nome: "NMMFSIV",                div: "B" },
  { id: "team04", gm: "Matteo",            nome: "Ntilikinerz",            div: "C" },
  { id: "team13", gm: "Diego",             nome: "Lords of Torture",       div: "C" },
  { id: "team19", gm: "Alessandro Delfino",nome: "Champapon Newborns",     div: "C" },
  { id: "team24", gm: "Marco Calamo",      nome: "Tibur Eagles",           div: "C" },
  { id: "team03", gm: "Fabio Brownie",     nome: "Buffalo Brownies",       div: "D" },
  { id: "team10", gm: "Alan",              nome: "Polisportiva Calitri",   div: "D" },
  { id: "team16", gm: "Antonio",           nome: "Ohio Raptors",           div: "D" },
  { id: "team17", gm: "Alex Birra",        nome: "WestSide Hammers",       div: "D" },
  { id: "team02", gm: "Kolera",            nome: "No Trade Knicks",        div: "E" },
  { id: "team11", gm: "Pedro",             nome: "ZZ Killers",             div: "E" },
  { id: "team12", gm: "Gobkor",            nome: "LongNosed Milfhunter",   div: "E" },
  { id: "team22", gm: "È BOOKER-T",        nome: "BOOKER-T",               div: "E" },
  { id: "team05", gm: "Henry",             nome: "DREAMCHASERS",           div: "F" },
  { id: "team18", gm: "Erminio",           nome: "Guston Rockets",         div: "F" },
  { id: "team20", gm: "MarcG",             nome: "Seattle 206ers",         div: "F" },
  { id: "team23", gm: "Enzo",              nome: "Bologna Boricuas",       div: "F" },
];

// ── Roster TEAM_MAP (usato da roster.gs) ─────────────────────────────────────

const TEAM_MAP = {
  "team01": { conference: "East", pos: 0 },
  "team02": { conference: "East", pos: 1 },
  "team03": { conference: "East", pos: 2 },
  "team04": { conference: "East", pos: 3 },
  "team05": { conference: "East", pos: 4 },
  "team06": { conference: "East", pos: 5 },
  "team07": { conference: "East", pos: 6 },
  "team08": { conference: "East", pos: 7 },
  "team09": { conference: "East", pos: 8 },
  "team10": { conference: "East", pos: 9 },
  "team11": { conference: "East", pos: 10 },
  "team12": { conference: "East", pos: 11 },
  "team13": { conference: "West", pos: 0 },
  "team14": { conference: "West", pos: 1 },
  "team15": { conference: "West", pos: 2 },
  "team16": { conference: "West", pos: 3 },
  "team17": { conference: "West", pos: 4 },
  "team18": { conference: "West", pos: 5 },
  "team19": { conference: "West", pos: 6 },
  "team20": { conference: "West", pos: 7 },
  "team21": { conference: "West", pos: 8 },
  "team22": { conference: "West", pos: 9 },
  "team23": { conference: "West", pos: 10 },
  "team24": { conference: "West", pos: 11 },
};
