const fs = require("fs");
eval(fs.readFileSync(process.argv[2], "utf8"));
// v5.2.0: il 10-day va sotto le DIS., in verde petrolio; le righe sotto gli impatti si puliscono (testo e colore)
global.CONFIG = { ROSTER_SHEET_NAME: "Roster", CONFERENCE_ROW_BASES: [3, 30], OFFSET_PLAYERS_START: 3, OFFSET_PLAYERS_END: 17,
  OFFSET_TAGLI: 20, OFFSET_CAMBI_RUOLO: 21, OFFSET_TAGLIATI_LABEL: 22, OFFSET_IMPATTI: [23, 24], COLS_PER_TEAM: 4 };
global.TEAM_MAP = { team01: { conference: 0, pos: 0 } };
const celle = {}, colori = {}, op = [];
const rng = (r, c, nr = 1, nc = 1) => ({
  setValue: (v) => { celle[r + ":" + c] = v; },
  clearContent: () => { for (let i = 0; i < nr; i++) for (let j = 0; j < nc; j++) delete celle[(r + i) + ":" + (c + j)]; op.push(["clear", r, nr]); },
  setFontColor: (x) => { for (let i = 0; i < nr; i++) colori[r + i] = x; },
  setRichTextValue: (v) => { celle[r + ":" + c] = v.testo; },
});
const sheet = { getRange: rng };
global.getSpreadsheet = () => ({ getSheetByName: () => sheet });
global.respond = (x) => x;
global.SpreadsheetApp = { newRichTextValue: () => { const o = { setText: (t) => { o.testo = t; return o; }, setTextStyle: () => o, build: () => o }; return o; },
  newTextStyle: () => { const s = { setStrikethrough: () => s, setForegroundColor: () => s, build: () => s }; return s; } };
celle["29:1"] = "DIS. vecchia"; colori[29] = "#C62828";
const team = { team_id: "team01", giocatori: [{ ruolo: "PG", nome: "A", importo: 10, anni: 2 }], impatti_tagli: [{ nome: "T", stringa: "1x1" }],
  dpe: [{ nome: "Rotto", importo_orig: 20, importo_dpe: 15, anni: 2 }], dieci_giorni: [{ nome: "Dieci", ruolo: "C", fine: "fino al 26/10" }],
  rookie_scale: [], anni_colonne: [] };
const r = handleRoster({ teams: [team] });
// riga base 3: label 25, impatto 26, DIS. 27, 10-DAY 28; pulite 26..29 (2 impatti + 2)
const ok = r.ok && celle["26:1"] === "T 1x1" && celle["27:1"].startsWith("DIS. Rotto") && celle["28:1"] === "10-DAY C Dieci fino al 26/10"
  && colori[28] === "#00838F" && colori[27] === "#C62828" && celle["29:1"] === undefined && colori[29] === null;
console.log(ok ? "✅" : "❌ FAIL", "GAS roster: 10-DAY sotto le DIS. in verde petrolio, righe sotto pulite (testo e colore)", JSON.stringify(celle), JSON.stringify(colori));

// v5.4.0: tutti gli impatti, uno dopo l'altro; se l'area non basta, l'ultima riga lo dice
for (const k of Object.keys(celle)) delete celle[k];
const t2 = { ...team, impatti_tagli: [{ nome: "T1", stringa: "1x1" }, { nome: "T2", stringa: "2x2" }, { nome: "T3", stringa: "3x1" }],
  dpe: [], dieci_giorni: [] };
handleRoster({ teams: [t2] });
const ok2 = celle["25:1"] === "TAGLIATI:" && celle["26:1"] === "T1 1x1" && celle["27:1"] === "T2 2x2" && celle["28:1"] === "T3 3x1";
console.log(ok2 ? "✅" : "❌ FAIL", "GAS roster: tre impatti, tutti scritti", JSON.stringify(celle));
for (const k of Object.keys(celle)) delete celle[k];
const t3 = { ...team, impatti_tagli: [{ nome: "T1", stringa: "1x1" }, { nome: "T2", stringa: "2x2" }, { nome: "T3", stringa: "3x1" }],
  dpe: [{ nome: "Rotto", importo_orig: 20, importo_dpe: 15, anni: 2 }], dieci_giorni: [{ nome: "Dieci", ruolo: "C", fine: "" }] };
handleRoster({ teams: [t3] });
const ok3 = celle["28:1"] === "T3 3x1" && celle["29:1"] === "… altre 2 righe: aumentare RIGHE_EXTRA_SOTTO" && celle["30:1"] === undefined;
console.log(ok3 ? "✅" : "❌ FAIL", "GAS roster: area piena, l'ultima riga dice quante mancano (e non sconfina nella conference sotto)", JSON.stringify(celle));
