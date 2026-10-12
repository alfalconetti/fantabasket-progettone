// Fantabasket — foglio Calendario (loucabot, via gas-router)
// Il foglio ha una formattazione sua che non va toccata: si scrivono SOLO le celle che cambiano.
// payload.blocchi = [{numero: N, righe: [[A, B, C, D, E], ...]}]: la prima riga è l'intestazione
// "Week N ..." (celle unite A:E: si scrive solo A), poi le righe della giornata come nel CSV
// (squadre e punteggi regolamentari in B e D, subito sotto i supplementari). null = non toccare.
// La giornata si trova cercando "Week N" (o "Giornata N") nella colonna A.
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
  const ultima = sheet.getLastRow();
  if (ultima < 1) return respond({ error: "Foglio Calendario vuoto" });
  const colA = sheet.getRange(1, 1, ultima, 1).getDisplayValues().map(function (r) { return String(r[0]).trim(); });
  const blocchi = payload.blocchi || [];
  let celle = 0;
  const nonTrovate = [];
  blocchi.forEach(function (b) {
    const re = new RegExp("^(week|giornata)\\s+" + Number(b.numero) + "\\b", "i");
    let r0 = -1;
    for (let i = 0; i < colA.length; i++) { if (re.test(colA[i])) { r0 = i; break; } }
    if (r0 < 0) { nonTrovate.push(b.numero); return; }
    const righe = b.righe || [];
    if (!righe.length) return;
    const attuali = sheet.getRange(r0 + 1, 1, righe.length, 5).getValues();
    righe.forEach(function (riga, i) {
      (riga || []).forEach(function (v, j) {
        if (v === null || v === undefined) return;
        if (i === 0 && j > 0) return;                  // intestazione: solo A (celle unite A:E)
        if (String(attuali[i][j]) === String(v)) return;
        sheet.getRange(r0 + 1 + i, j + 1).setValue(v);
        celle++;
      });
    });
  });
  return respond({ ok: true, celle: celle, non_trovate: nonTrovate });
}
