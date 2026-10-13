const fs = require("fs");
eval(fs.readFileSync(process.argv[2], "utf8"));
const op = [];
const fogli = {};
function nuovo(nome) {
  return { nome, getRange: (a, b, c, d) => (typeof a === "string"
      ? { setNumberFormat: (f) => op.push(["formato", a, f]) }
      : { setValues: (v) => op.push(["valori", a, b, c, d, v[1][1]]), setBackgrounds: (v) => op.push(["sfondi", v[0][0], v[0][1]]),
          setFontColors: () => op.push(["testi"]), setFontWeights: () => op.push(["pesi"]) }),
    clear: () => op.push(["clear", nome]), setFrozenRows: (n) => op.push(["frozenR", n]), setFrozenColumns: (n) => op.push(["frozenC", n]) };
}
global.CONFIG = { CALCOLO_SPREADSHEET_ID: "" };
global.getSpreadsheet = () => ({ getSheetByName: (n) => fogli[n] || null, insertSheet: (n) => (fogli[n] = nuovo(n)) });
global.SpreadsheetApp = { openById: () => { throw new Error("non doveva aprire un altro file"); } };
global.respond = (x) => x;
const righe = [["Calcolo", "", ""], ["Bonus casa", 3, "=B2+1"]];
const r = handleCalcolo({ nome: "Calcolo G1", righe, sfondi: [["#1f3864", "", ""], ["", "", ""]], testi: [["", "", ""], ["", "", ""]],
  pesi: [["bold", "", ""], ["", "", ""]], formati: [{ range: "B2:B2", formato: "0.00" }], congela: { righe: 1, colonne: 2 } });
console.log(r.ok && fogli["Calcolo G1"] && JSON.stringify(op) === JSON.stringify([["clear", "Calcolo G1"], ["valori", 1, 1, 2, 3, 3],
  ["sfondi", "#1f3864", null], ["testi"], ["pesi"], ["formato", "B2:B2", "0.00"], ["frozenR", 1], ["frozenC", 2]]) ? "✅" : "❌ FAIL",
  "GAS: tab creato se manca, svuotato, valori, sfondi (\"\" → null), testi, pesi, formati, righe e colonne bloccate", JSON.stringify(op));
op.length = 0;
handleCalcolo({ nome: "Calcolo G1", righe });
console.log(op[0][0] === "clear" && op.length === 2 ? "✅" : "❌ FAIL", "secondo calcolo: stesso tab, riscritto");
console.log(handleCalcolo({ nome: "Roster", righe }).error ? "✅" : "❌ FAIL", "nome di tab non Calcolo GN: rifiutato (non si tocca il Roster)");
console.log(handleCalcolo({ nome: "Calcolo G2", righe: [["a"], ["b", "c"]] }).error ? "✅" : "❌ FAIL", "righe di lunghezza diversa: rifiutate");
global.CONFIG = { CALCOLO_SPREADSHEET_ID: "xyz" };
let aperto = null; global.SpreadsheetApp = { openById: (id) => { aperto = id; return { getSheetByName: () => null, insertSheet: (n) => nuovo(n) }; } };
handleCalcolo({ nome: "Calcolo G3", righe });
console.log(aperto === "xyz" ? "✅" : "❌ FAIL", "con CALCOLO_SPREADSHEET_ID scrive nel foglio di calcolo");
