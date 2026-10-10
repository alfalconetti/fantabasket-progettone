// Fantabasket — handler aggiornamento foglio Roster
// Usa CONFIG, TEAM_MAP e getSpreadsheet() da globals.gs

function handleRoster(payload) {
  const sheet = getSpreadsheet().getSheetByName(CONFIG.ROSTER_SHEET_NAME);
  if (!sheet) {
    return respond({ error: "Sheet not found: " + CONFIG.ROSTER_SHEET_NAME });
  }

  let updated = 0;
  let skipped = 0;
  for (const team of payload.teams) {
    if (updateTeamRoster(sheet, team)) {
      updated++;
    } else {
      skipped++;
    }
  }

  return respond({ ok: true, updated: updated, skipped: skipped });
}

function updateTeamRoster(sheet, team) {
  const mapping = TEAM_MAP[team.team_id];
  if (!mapping) return false;

  const rowBase = CONFIG.CONFERENCE_ROW_BASES[mapping.conference];
  const colBase = mapping.pos * CONFIG.COLS_PER_TEAM + 1;

  // Pulisci righe giocatori
  const playerRowStart = rowBase + CONFIG.OFFSET_PLAYERS_START;
  const numPlayerRows = CONFIG.OFFSET_PLAYERS_END - CONFIG.OFFSET_PLAYERS_START + 1;
  sheet.getRange(playerRowStart, colBase, numPlayerRows, CONFIG.COLS_PER_TEAM).clearContent();

  // Scrivi giocatori
  team.giocatori.forEach((g, i) => {
    if (i >= numPlayerRows) return;
    const row = playerRowStart + i;
    sheet.getRange(row, colBase).setValue(g.ruolo || "");
    sheet.getRange(row, colBase + 1).setValue(g.nome);
    sheet.getRange(row, colBase + 2).setValue(g.importo);
    sheet.getRange(row, colBase + 3).setValue(g.anni);
  });

  // Salary cap label con eventuale penalità
  const capPen = team.cap_penalizzato || 0;
  const capLabel = capPen !== 0 ? `SALARY CAP [-${Math.abs(capPen)}]` : "SALARY CAP";  // penalità sempre col meno
  // La riga SALARY CAP è OFFSET_PLAYERS_END + 1 = rowBase + CONFIG.OFFSET_PLAYERS_END + 1
  // Non la tocchiamo se è formula — scriviamo solo il label nella prima cella del blocco
  const capRow = rowBase + CONFIG.OFFSET_PLAYERS_END + 1;
  sheet.getRange(capRow, colBase).setValue(capLabel);  // rowBase+18

  // Tagli gratuiti usati
  sheet.getRange(rowBase + CONFIG.OFFSET_TAGLI, colBase, 1, CONFIG.COLS_PER_TEAM)
    .setValue(`TAGLI GRATUITI USATI: ${team.tagli_gratuiti_usati || 0}/3`);

  // Cambi ruolo usati
  sheet.getRange(rowBase + CONFIG.OFFSET_CAMBI_RUOLO, colBase, 1, CONFIG.COLS_PER_TEAM)
    .setValue(`CAMBI RUOLO USATI: ${team.cambi_ruolo_usati || 0}/2`);

  // Pulisci area tagliati/impatti
  sheet.getRange(rowBase + CONFIG.OFFSET_TAGLIATI_LABEL, colBase, 1, CONFIG.COLS_PER_TEAM).clearContent();
  CONFIG.OFFSET_IMPATTI.forEach(offset => {
    sheet.getRange(rowBase + offset, colBase, 1, CONFIG.COLS_PER_TEAM).clearContent();
  });

  // Scrivi impatti tagli se presenti
  if (team.impatti_tagli && team.impatti_tagli.length > 0) {
    sheet.getRange(rowBase + CONFIG.OFFSET_TAGLIATI_LABEL, colBase, 1, CONFIG.COLS_PER_TEAM)
      .setValue("TAGLIATI:");
    team.impatti_tagli.forEach((imp, i) => {
      if (i < CONFIG.OFFSET_IMPATTI.length) {
        sheet.getRange(rowBase + CONFIG.OFFSET_IMPATTI[i], colBase, 1, CONFIG.COLS_PER_TEAM)
          .setValue(`${imp.nome} ${imp.stringa}`);
      }
    });
  }

  // DPE attive — sotto i tagliati, prima riga libera
  const dpeList = team.dpe || [];
  if (dpeList.length > 0) {
    // Trova prima riga libera dopo i tagliati
    let dpeStartRow = rowBase + CONFIG.OFFSET_TAGLIATI_LABEL + 1;
    if (team.impatti_tagli && team.impatti_tagli.length > 0) {
      dpeStartRow += team.impatti_tagli.length;
    }
    dpeList.forEach((d, i) => {
      const row = dpeStartRow + i;
      const cell = sheet.getRange(row, colBase, 1, CONFIG.COLS_PER_TEAM);
      cell.setFontColor("#C62828");

      // Testo con importo originale barrato via RichTextValue
      const prefix   = `DIS. ${d.nome} `;
      const barrato  = `${d.importo_orig}x${d.anni}`;
      const suffisso = `  ${d.importo_dpe}x${d.anni}`;
      const rtv = SpreadsheetApp.newRichTextValue()
        .setText(prefix + barrato + suffisso)
        .setTextStyle(
          prefix.length,
          prefix.length + barrato.length,
          SpreadsheetApp.newTextStyle().setStrikethrough(true).setForegroundColor("#C62828").build()
        )
        .setTextStyle(
          0,
          prefix.length,
          SpreadsheetApp.newTextStyle().setForegroundColor("#C62828").build()
        )
        .setTextStyle(
          prefix.length + barrato.length,
          prefix.length + barrato.length + suffisso.length,
          SpreadsheetApp.newTextStyle().setForegroundColor("#C62828").build()
        )
        .build();
      sheet.getRange(row, colBase).setRichTextValue(rtv);
    });
  }

  // ── Rookie scale — colonne AX-BA (50-53) ─────────────────────────────────
  const rookieCols = [50, 51, 52, 53];  // AX, AY, AZ, BA
  const rookieData = team.rookie_scale || [];
  const anniColonne = team.anni_colonne || [null, null, null, null];

  rookieData.forEach((colData, ci) => {
    const col = rookieCols[ci];
    const anno = anniColonne[ci];

    // Riga 1: anno di draft
    sheet.getRange(1, col).setValue(anno || "");

    // Righe 2-25: pick (24 slot, None = vuoto)
    const picks = colData.picks || [];
    for (let pi = 0; pi < 24; pi++) {
      sheet.getRange(2 + pi, col).setValue(picks[pi] || "");
    }

    // Riga 26: vuota
    sheet.getRange(26, col).setValue("");

    // Righe 27+: diritti 2nd attivati
    const diritti = colData.diritti || [];
    diritti.forEach((nome, di) => {
      sheet.getRange(27 + di, col).setValue(nome);
    });
  });

  return true;
}

function testRoster() {
  const payload = {
    teams: [
      {
        team_id: "team06",
        tagli_gratuiti_usati: 1,
        cambi_ruolo_usati: 0,
        giocatori: [
          { ruolo: "PG", nome: "LeBron James", importo: 30, anni: 2 },
          { ruolo: "SG", nome: "Stephen Curry", importo: 25, anni: 1 },
        ],
        impatti_tagli: []
      }
    ]
  };
  handleRoster(payload);
  Logger.log("Test roster completato");
}
