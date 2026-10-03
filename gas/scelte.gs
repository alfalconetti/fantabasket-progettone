// Fantabasket — handler aggiornamento foglio Scelte (pick e diritti)
// Ricostruisce completamente la sezione dati ad ogni sync, lasciando
// intatte le righe 1-3 (vuota, header anni, formule TUTTO OK).

function handleScelte(payload) {
  const ss    = getSpreadsheet();
  const sheet = ss.getSheetByName(CONFIG.SCELTE_SHEET_NAME);
  if (!sheet) {
    return respond({ error: "Sheet not found: " + CONFIG.SCELTE_SHEET_NAME });
  }

  const anni       = payload.anni;
  const teams_data = payload.teams;

  // ── 1. Pulisci tutta l'area dati (dalla riga 4 in poi) ──────────────────
  const lastRow = sheet.getLastRow();
  if (lastRow >= CONFIG.SCELTE_DATA_ROW_START) {
    sheet.getRange(
      CONFIG.SCELTE_DATA_ROW_START, 1,
      lastRow - CONFIG.SCELTE_DATA_ROW_START + 1,
      sheet.getLastColumn()
    ).clearContent().clearFormat().setHorizontalAlignment("left").setFontColor("#000000");
  }

  // ── 2. Scrivi i dati team per team ──────────────────────────────────────
  let currentRow = CONFIG.SCELTE_DATA_ROW_START;

  for (const team of teams_data) {
    const colors = DIV_COLORS[team.div];
    currentRow = writeTeamBlock(sheet, team, anni, colors, currentRow);
    currentRow++; // riga separatore vuota
  }

  return respond({ ok: true, last_row: currentRow });
}


function writeTeamBlock(sheet, team, anni, colors, startRow) {
  const colNome    = CONFIG.SCELTE_COL_NOME;
  const colDiritti = CONFIG.SCELTE_COL_DIRITTI;
  const colDraft   = CONFIG.SCELTE_COL_DRAFT;
  const colAnniS   = CONFIG.SCELTE_COL_ANNI_START;
  const colsAnno   = CONFIG.SCELTE_COLS_PER_ANNO;

  const diritti   = team.diritti || [];
  const draft_nums = team.draft_nums || [];
  const altrePickPerAnno = anni.map(anno => (team.picks_altrui[anno] || []));

  // Minimo 4 righe (nome + gm + "Altre pick" + 1 riga dati minima)
  const minAltreRighe = 2;
  const maxAltreRighe = Math.max(
    minAltreRighe,
    Math.max(0, diritti.length - 2),
    draft_nums.length,
    ...altrePickPerAnno.map(a => a.length)
  );

  // ── Riga 1: nome squadra ─────────────────────────────────────────────────
  const r1 = startRow;
  _setCell(sheet, r1, colNome, team.nome, colors.dark, true, "#000000", "center");

  // Diritti riga 1
  if (diritti.length > 0) {
    _setCell(sheet, r1, colDiritti, diritti[0], colors.light, true, "#000000", "center");
  } else {
    _setCell(sheet, r1, colDiritti, "", colors.light, false, "#000000", "center");
  }

  // Pick 1st proprie per anno (riga 1)
  anni.forEach((anno, i) => {
    const col = colAnniS + i * colsAnno;
    const pick1st = _find1st(team.picks_proprie, anno);
    _setCell(sheet, r1, col, pick1st || "", colors.mid, !!pick1st, "#000000", "center");
  });

  // ── Riga 2: nome GM ──────────────────────────────────────────────────────
  const r2 = startRow + 1;
  _setCell(sheet, r2, colNome, team.gm, colors.dark, false, "#000000", "center");

  // Diritti riga 2
  if (diritti.length > 1) {
    _setCell(sheet, r2, colDiritti, diritti[1], colors.light, true, "#000000", "center");
  } else {
    _setCell(sheet, r2, colDiritti, "", colors.light, false, "#000000", "center");
  }

  // Pick 2nd proprie per anno (riga 2)
  anni.forEach((anno, i) => {
    const col = colAnniS + i * colsAnno;
    const pick2nd = _find2nd(team.picks_proprie, anno);
    _setCell(sheet, r2, col, pick2nd || "", colors.mid, !!pick2nd, "#000000", "center");
  });

  // ── Righe 3+: Altre pick ─────────────────────────────────────────────────
  for (let ri = 0; ri < maxAltreRighe; ri++) {
    const r = startRow + 2 + ri;

    // Colonna nome
    _setCell(sheet, r, colNome, ri === 0 ? "Altre pick" : "", colors.light, ri === 0, "#000000", "center");

    // Colonna diritti (dalla 3a in poi)
    const dIdx = ri + 2;
    if (dIdx < diritti.length) {
      _setCell(sheet, r, colDiritti, diritti[dIdx], colors.light, true, "#000000", "center");
    } else {
      _setCell(sheet, r, colDiritti, "", colors.light, false, "#000000", "center");
    }

    // Colonna draft
    if (ri < draft_nums.length) {
      _setCell(sheet, r, colDraft, draft_nums[ri], colors.light, false, "#000000", "center");
    } else {
      _setCell(sheet, r, colDraft, "", colors.light, false, "#000000", "center");
    }

    // Colonne anni: pick altrui
    anni.forEach((anno, i) => {
      const col   = colAnniS + i * colsAnno;
      const picks = altrePickPerAnno[i];
      _setCell(sheet, r, col, ri < picks.length ? picks[ri] : "", colors.light, false, "#000000", "center");
    });
  }

  return startRow + 2 + maxAltreRighe;
}


// ── Helper pick ───────────────────────────────────────────────────────────────

function _find1st(picks_proprie, anno) {
  const p = picks_proprie.find(p => p.anno == anno && p.round == 1);
  return p ? p.label : null;
}

function _find2nd(picks_proprie, anno) {
  const p = picks_proprie.find(p => p.anno == anno && p.round == 2);
  return p ? p.label : null;
}


// ── Helper celle ─────────────────────────────────────────────────────────────

function _setCell(sheet, row, col, value, bgColor, bold, fontColor, hAlign) {
  const cell = sheet.getRange(row, col);
  cell.setValue(value);
  cell.setBackground(bgColor);
  cell.setFontWeight(bold ? "bold" : "normal");
  cell.setFontColor(fontColor || "#000000");
  cell.setVerticalAlignment("middle");
  cell.setHorizontalAlignment(hAlign || "left");
}
