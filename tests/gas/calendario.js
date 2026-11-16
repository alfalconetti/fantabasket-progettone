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
// v7.15.0: i playoff in un foglio a parte, creato se non c'è; il Calendario non si tocca
const creati = [];
const fogliP = {};
global.getSpreadsheet = () => ({ getSheetByName: (n) => fogliP[n] || null, getSheets: () => [sheet],
  insertSheet: (n) => { creati.push(n); const g = []; const fmt = []; return (fogliP[n] = { getName: () => n, getLastRow: () => g.length,
    getRange: (r, c, nr, nc) => (typeof r === "string"
      ? { merge: () => fmt.push(["unisci", r]), setBackground: (x) => fmt.push(["sfondo", r, x]), setFontColor: (x) => fmt.push(["colore", r, x]),
          setFontWeight: () => fmt.push(["grassetto", r]), setFontStyle: () => fmt.push(["corsivo", r]), setFontSize: (x) => fmt.push(["dim", r, x]),
          setHorizontalAlignment: (x) => fmt.push(["allinea", r, x]), setNumberFormat: (x) => fmt.push(["formato", r, x]),
          setBorder: () => fmt.push(["bordo", r]) }
      : { clearContent: () => {}, breakApart: () => fmt.push(["separa"]), clearFormat: () => fmt.push(["pulisci"]),
          setValues: (v) => v.forEach((row, i) => (g[r - 1 + i] = row)) }),
    setColumnWidth: (c, w) => fmt.push(["larghezza", c, w]), _g: g, _fmt: fmt }); } });
global.SpreadsheetApp = { BorderStyle: { SOLID: "solid" } };
op.length = 0;
const rp = handleCalendario({ righe: [["", "", "PRIMO TURNO", "", "", "", "SERIE"], ["DATA", "", "Alfa", 500, 480, "Beta", "1-0"]], foglio: "Playoff 26-27" });
console.log(rp.ok && creati[0] === "Playoff 26-27" && fogliP["Playoff 26-27"]._g[1][3] === 500 && op.length === 0 ? "✅" : "❌ FAIL",
  "foglio dei playoff: creato se non c'è, largo quanto la griglia, il Calendario non si tocca");
console.log(handleCalendario({ righe: [["a", "b"], ["a"]], foglio: "Playoff 26-27" }).error ? "✅" : "❌ FAIL", "foglio dei playoff: righe di lunghezza diversa rifiutate");
handleCalendario({ righe: [["X", "", "", "", ""]], foglio: "Playoff 26-27" });
const fP = fogliP["Playoff 26-27"];
fP._fmt.length = 0;
const rs = handleCalendario({ righe: [["", "TITOLO", ""]], foglio: "Playoff 26-27",
  stili: [{ range: "B1:C1", unisci: true, sfondo: "#2A1A00", colore: "#FFD23F", grassetto: true, dimensione: 18, allinea: "center" },
          { range: "C1", formato: "0.00", bordo: "#F0D48A", corsivo: true }], larghezze: { 3: 170 } });
const f = JSON.stringify(fP._fmt);
console.log(rs.ok && rs.stili === 2 && fP._fmt[0][0] === "separa" && fP._fmt[1][0] === "pulisci" && f.includes('["unisci","B1:C1"]')
  && f.includes('["sfondo","B1:C1","#2A1A00"]') && f.includes('["dim","B1:C1",18]') && f.includes('["formato","C1","0.00"]')
  && f.includes('["bordo","C1"]') && f.includes('["larghezza",3,170]') ? "✅" : "❌ FAIL",
  "foglio dei playoff: formattazione tolta e rimessa dal bot (unioni, colori, grassetto, dimensioni, formati, bordi, larghezze)", f);
console.log(creati.length === 1 ? "✅" : "❌ FAIL", "foglio Playoff già creato: si riusa");
