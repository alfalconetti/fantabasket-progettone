// Fantabasket — foglio Calendario (loucabot, via gas-router)
// Ricarica tutta la pagina nelle colonne A:E: svuota i valori (clearContent: formattazione e
// celle unite restano) e scrive payload.righe, la griglia del calendario costruita da loucabot
// (intestazioni "Week N …" con il testo in A, partite "Casa | punti | V | punti | Trasferta",
// supplementari nella riga sotto). Le altre colonne e gli altri fogli non si toccano.
// Nome del foglio da CONFIG.CALENDARIO_SHEET_NAME se c'è, altrimenti "Calendario" (maiuscole libere).

function trovaFoglioCalendario_(ss) {
  const nome = (typeof CONFIG !== "undefined" && CONFIG.CALENDARIO_SHEET_NAME) || "Calendario";
  const esatto = ss.getSheetByName(nome);
  if (esatto) return esatto;
  const fogli = ss.getSheets();
  for (let i = 0; i < fogli.length; i++) {
    if (fogli[i].getName().trim().toLowerCase() === nome.toLowerCase()) return fogli[i];
  }
  return null;
}

function handleCalendario(payload) {
  const sheet = trovaFoglioCalendario_(getSpreadsheet());
  if (!sheet) return respond({ error: "Foglio Calendario non trovato" });
  const righe = payload.righe || [];
  if (!righe.length) return respond({ error: "Calendario vuoto" });
  for (let i = 0; i < righe.length; i++) {
    if (!Array.isArray(righe[i]) || righe[i].length !== 5) return respond({ error: "Riga " + (i + 1) + ": servono 5 colonne" });
  }
  const ultima = Math.max(sheet.getLastRow(), righe.length);
  sheet.getRange(1, 1, ultima, 5).clearContent();
  sheet.getRange(1, 1, righe.length, 5).setValues(righe);
  return respond({ ok: true, righe: righe.length });
}
