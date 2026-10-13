const fs = require("fs");
eval(fs.readFileSync(process.argv[2], "utf8"));
const griglia = Array.from({ length: 12 }, (_, i) => ["vecchio" + i, i, "V", i, "x"]);
griglia.forEach(r => r.push("F colonna non toccata"));
const op = [];
const sheet = {
  getName: () => "calendario", getLastRow: () => griglia.length,
  getRange: (r, c, nr, nc) => ({
    clearContent: () => { op.push(["clear", r, c, nr, nc]); for (let i = 0; i < nr; i++) for (let j = 0; j < nc; j++) if (griglia[r - 1 + i]) griglia[r - 1 + i][c - 1 + j] = ""; },
    setValues: (v) => { op.push(["set", r, c, v.length, v[0].length]); v.forEach((row, i) => { griglia[r - 1 + i] = griglia[r - 1 + i] || ["", "", "", "", "", ""]; row.forEach((x, j) => griglia[r - 1 + i][c - 1 + j] = x); }); },
  }),
};
global.getSpreadsheet = () => ({ getSheetByName: () => null, getSheets: () => [sheet] });
global.respond = (x) => x;
const righe = [["Week 1 20/10 - 22/10 (media OKC)", "", "", "", ""], ["Alfa", 110.5, "V", 98.25, "Beta"], ["", "", "", "", ""]];
const r = handleCalendario({ righe });
const ok = r.ok && r.righe === 3 && JSON.stringify(op) === JSON.stringify([["clear", 1, 1, 12, 5], ["set", 1, 1, 3, 5]])
  && griglia[1][1] === 110.5 && griglia[5][0] === "" && griglia[5][5] === "F colonna non toccata" && griglia[0][0].startsWith("Week 1");
console.log(ok ? "✅" : "❌ FAIL", "GAS: svuota i valori di A:E fino all'ultima riga, scrive la griglia, colonna F intatta", JSON.stringify(op));
console.log(handleCalendario({ righe: [["a", "b"]] }).error ? "✅" : "❌ FAIL", "riga senza 5 colonne rifiutata");
console.log(handleCalendario({ righe: [] }).error ? "✅" : "❌ FAIL", "griglia vuota rifiutata (non si svuota il foglio)");
