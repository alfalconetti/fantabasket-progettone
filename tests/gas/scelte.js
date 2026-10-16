const fs = require("fs");
eval(fs.readFileSync(process.argv[2], "utf8"));
// v5.6.0: sotto il GM una riga vuota (niente più "Altre pick"), poi "Penalità: N" se la squadra ne ha
global.CONFIG = { SCELTE_SHEET_NAME: "Scelte", SCELTE_DATA_ROW_START: 4, SCELTE_COL_NOME: 2, SCELTE_COL_DIRITTI: 4,
  SCELTE_COL_DRAFT: 6, SCELTE_COL_ANNI_START: 8, SCELTE_ANNI_COUNT: 6, SCELTE_COLS_PER_ANNO: 2 };
global.DIV_COLORS = { A: { dark: "#1", mid: "#2", light: "#3" } };
const celle = {}, colori = {};
const rng = (r, c) => {
  const o = { setValue: (v) => { celle[r + ":" + c] = v; return o; }, setBackground: () => o, setFontWeight: () => o,
    setFontColor: (x) => { colori[r + ":" + c] = x; return o; }, setVerticalAlignment: () => o, setHorizontalAlignment: () => o,
    clearContent: () => o, clearFormat: () => o };
  return o;
};
const sheet = { getRange: rng, getLastRow: () => 3, getLastColumn: () => 20 };
global.getSpreadsheet = () => ({ getSheetByName: () => sheet });
global.respond = (x) => x;
const team = (nome, pen) => ({ team_id: nome, nome, gm: "GM " + nome, div: "A", diritti: [], draft_nums: [], picks_proprie: [],
  picks_altrui: {}, penalita: pen });
const r = handleScelte({ anni: [2027], teams: [team("Alfa", 2), team("Beta", 0)] });
// Alfa: righe 4 (nome), 5 (GM), 6 (vuota), 7 "Penalità: 2"; separatore 8; Beta da 9: 9, 10, 11 vuota, 12 vuota
const ok = r.ok && celle["4:2"] === "Alfa" && celle["5:2"] === "GM Alfa" && celle["6:2"] === "" && celle["7:2"] === "Penalità: 2"
  && colori["7:2"] === "#C62828" && celle["9:2"] === "Beta" && celle["11:2"] === "" && celle["12:2"] === ""
  && !Object.values(celle).includes("Altre pick");
console.log(ok ? "✅" : "❌ FAIL", "GAS scelte: niente «Altre pick», «Penalità: N» sotto il GM solo se ce n'è almeno una", JSON.stringify(celle));
