// Fantabasket — foglio BrefRaw: tabella per_game di Basketball-Reference
// Stesso comportamento del vecchio updateCsvAction: svuota il foglio e riscrive
// tutto da A1 (le formule che puntano a BrefRaw non si rompono: righe e colonne restano).
// Usa getSpreadsheet() da globals.gs; nome del foglio da CONFIG.BREF_SHEET_NAME se c'è.

function handleBrefRaw(payload) {
  const nome = (typeof CONFIG !== "undefined" && CONFIG.BREF_SHEET_NAME) || "BrefRaw";
  const sheet = getSpreadsheet().getSheetByName(nome);
  if (!sheet) {
    return respond({ error: "Sheet not found: " + nome });
  }
  const data = Utilities.parseCsv(payload.csv || "");
  if (!data.length || !data[0].length) {
    return respond({ error: "CSV vuoto" });
  }
  sheet.clear();
  sheet.getRange(1, 1, data.length, data[0].length).setValues(data);
  return respond({ ok: true, righe: data.length - 1 });
}
