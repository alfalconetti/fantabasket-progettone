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
          .setValue(`${imp.nome} ${imp.importo}x${imp.anni}`);
      }
    });
  }

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
