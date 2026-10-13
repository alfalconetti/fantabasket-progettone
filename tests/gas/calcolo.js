const fs = require("fs");
eval(fs.readFileSync(process.argv[2], "utf8"));
const op = [];
let errorePerVirgole = false;                     // finto foglio in italiano: le virgole danno #ERROR!
const scritte = {};
function nuovo(nome) {
  return { nome,
    getRange: (a, b, c, d) => (typeof a === "string"
      ? { setNumberFormat: (f) => op.push(["formato", a, f]) }
      : { setValues: (v) => op.push(["valori", a, b, c, d, v[1][1], v[1][2]]),
          setFormulas: (f) => { op.push(["formule", a, b, f.length]); f.forEach((r, i) => scritte[(a + i) + ":" + b] = r[0]); },
          getDisplayValues: () => [Object.values(scritte).map((x) => (errorePerVirgole && x.replace(/"[^"]*"/g, "").includes(",") ? "#ERROR!" : "ok"))],
          setBackgrounds: (v) => op.push(["sfondi", v[0][0], v[0][1]]),
          setFontColors: () => op.push(["testi"]), setFontWeights: () => op.push(["pesi"]) }),
    clear: () => op.push(["clear", nome]), setFrozenRows: (n) => op.push(["frozenR", n]), setFrozenColumns: (n) => op.push(["frozenC", n]) };
}
const fogli = {};
global.CONFIG = { CALCOLO_SPREADSHEET_ID: "" };
global.getSpreadsheet = () => ({ getSheetByName: (n) => fogli[n] || null, insertSheet: (n) => (fogli[n] = nuovo(n)) });
global.SpreadsheetApp = { openById: () => { throw new Error("non doveva aprire un altro file"); }, flush: () => {} };
global.respond = (x) => x;
const righe = [["Calcolo", "", ""], ["Bonus casa", 3, '=IF(B2>1,"sì, va","no")'], ["", 4, "=SUM(B2,B3)"]];
let r = handleCalcolo({ nome: "Calcolo G1", righe, sfondi: [["#1f3864", "", ""], ["", "", ""], ["", "", ""]],
  testi: [["", "", ""], ["", "", ""], ["", "", ""]], pesi: [["bold", "", ""], ["", "", ""], ["", "", ""]],
  formati: [{ range: "B2:B2", formato: "0.00" }], congela: { righe: 1, colonne: 2 } });
console.log(r.ok && r.errori === 0 && r.sintassi === "virgole" && fogli["Calcolo G1"]
  && JSON.stringify(op) === JSON.stringify([["clear", "Calcolo G1"], ["valori", 1, 1, 3, 3, 3, ""], ["formule", 2, 3, 2],
  ["sfondi", "#1f3864", null], ["testi"], ["pesi"], ["formato", "B2:B2", "0.00"], ["frozenR", 1], ["frozenC", 2]]) ? "✅" : "❌ FAIL",
  "GAS: valori senza le formule, poi le formule con setFormulas (colonna per colonna), sfondi, testi, pesi, formati, righe bloccate", JSON.stringify(op));
op.length = 0; for (const k in scritte) delete scritte[k]; errorePerVirgole = true;
r = handleCalcolo({ nome: "Calcolo G1", righe });
console.log(r.ok && r.sintassi === "punto e virgola" && r.errori === 0 && scritte["2:3"] === '=IF(B2>1;"sì, va";"no")' && scritte["3:3"] === "=SUM(B2;B3)"
  ? "✅" : "❌ FAIL", "foglio in italiano: #ERROR! con le virgole → riscritte col ;, virgole tra virgolette intatte", JSON.stringify(scritte), JSON.stringify(r));
console.log(handleCalcolo({ nome: "Roster", righe }).error ? "✅" : "❌ FAIL", "nome di tab non Calcolo GN: rifiutato (non si tocca il Roster)");
console.log(handleCalcolo({ nome: "Calcolo G2", righe: [["a"], ["b", "c"]] }).error ? "✅" : "❌ FAIL", "righe di lunghezza diversa: rifiutate");
global.CONFIG = { CALCOLO_SPREADSHEET_ID: "xyz" }; errorePerVirgole = false;
let aperto = null; global.SpreadsheetApp = { openById: (id) => { aperto = id; return { getSheetByName: () => null, insertSheet: (n) => nuovo(n) }; }, flush: () => {} };
handleCalcolo({ nome: "Calcolo G3", righe });
console.log(aperto === "xyz" ? "✅" : "❌ FAIL", "con CALCOLO_SPREADSHEET_ID scrive nel foglio di calcolo");
