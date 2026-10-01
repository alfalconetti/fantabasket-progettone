// Fantabasket — handler aggiornamento foglio Scelte (pick e diritti)
// Ricostruisce completamente la sezione dati ad ogni sync, lasciando
// intatte le righe 1-3 (vuota, header anni, formule TUTTO OK).

function handleScelte(payload) {
  const ss    = getSpreadsheet();
  const sheet = ss.getSheetByName(CONFIG.SCELTE_SHEET_NAME);
  if (!sheet) {
    return respond({ error: "Sheet not found: " + CONFIG.SCELTE_SHEET_NAME });
  }

  const anni       = payload.anni;        // es. [2027,2028,2029,2030,2031,2032]
  const teams_data = payload.teams;       // array ordinato per TEAM_ORDER

  // ── 1. Pulisci tutta l'area dati (dalla riga 4 in poi) ──────────────────
  const lastRow = sheet.getLastRow();
  if (lastRow >= CONFIG.SCELTE_DATA_ROW_START) {
    sheet.getRange(
      CONFIG.SCELTE_DATA_ROW_START, 1,
      lastRow - CONFIG.SCELTE_DATA_ROW_START + 1,
      sheet.getLastColumn()
    ).clearContent().clearFormat();
  }

  // ── 2. Scrivi i dati team per team ──────────────────────────────────────
  let currentRow = CONFIG.SCELTE_DATA_ROW_START;

  for (const team of teams_data) {
    const colors = DIV_COLORS[team.div];
    currentRow = writeTeamBlock(sheet, team, anni, colors, currentRow);
    // Riga separatore vuota tra team
    currentRow++;
  }

  return respond({ ok: true, last_row: currentRow });
}


function writeTeamBlock(sheet, team, anni, colors, startRow) {
  const colNome    = CONFIG.SCELTE_COL_NOME;
  const colDiritti = CONFIG.SCELTE_COL_DIRITTI;
  const colDraft   = CONFIG.SCELTE_COL_DRAFT;
  const colAnniS   = CONFIG.SCELTE_COL_ANNI_START;
  const colsAnno   = CONFIG.SCELTE_COLS_PER_ANNO;

  // ── Riga 1: nome squadra + 1st pick proprie + diritti ───────────────────
  const r1 = startRow;
  _setCell(sheet, r1, colNome, team.nome, colors.dark, true, "white");

  // Diritti 2nd pick — elencati uno per riga nella colonna D
  const diritti = team.diritti || [];
  if (diritti.length > 0) {
    _setCell(sheet, r1, colDiritti, diritti[0], colors.light, false);
  }

  // Pick 1st proprie per anno (riga 1)
  anni.forEach((anno, i) => {
    const col = colAnniS + i * colsAnno;
    const pick1st = _find1st(team.picks_proprie, anno);
    if (pick1st) {
      _setCell(sheet, r1, col, pick1st, colors.mid, true);
    } else {
      _setCell(sheet, r1, col, "", colors.mid, false);
    }
  });

  // ── Riga 2: nome GM + 2nd pick proprie ──────────────────────────────────
  const r2 = startRow + 1;
  _setCell(sheet, r2, colNome, team.gm, colors.dark, false);

  // Diritti riga 2+
  if (diritti.length > 1) {
    _setCell(sheet, r2, colDiritti, diritti[1], colors.light, false);
  }

  // Pick 2nd proprie per anno (riga 2)
  anni.forEach((anno, i) => {
    const col = colAnniS + i * colsAnno;
    const pick2nd = _find2nd(team.picks_proprie, anno);
    if (pick2nd) {
      _setCell(sheet, r2, col, pick2nd, colors.mid, false);
    } else {
      _setCell(sheet, r2, col, "", colors.mid, false);
    }
  });

  // ── Righe 3+: Altre pick ─────────────────────────────────────────────────
  // Raccoglie: diritti rimanenti, numeri draft, pick altrui per anno
  let altreRows = [];

  // Diritti riga 3+
  for (let d = 2; d < diritti.length; d++) {
    altreRows.push({ tipo: "diritto", valore: diritti[d] });
  }

  // Numeri draft corrente
  const draft_nums = team.draft_nums || [];
  draft_nums.forEach(n => altreRows.push({ tipo: "draft", valore: n }));

  // Pick altrui per anno — costruiamo matrice anni
  // altrePickPerAnno[i] = array di stringhe per l'anno anni[i]
  const altrePickPerAnno = anni.map((anno, i) => {
    return (team.picks_altrui[anno] || []);
  });

  // Numero di righe necessarie per "Altre pick"
  const maxAltreRighe = Math.max(
    altreRows.length,
    ...altrePickPerAnno.map(a => a.length),
    1  // almeno la riga "Altre pick"
  );

  for (let ri = 0; ri < maxAltreRighe; ri++) {
    const r = startRow + 2 + ri;

    // Prima colonna: "Altre pick" solo sulla prima riga
    if (ri === 0) {
      _setCell(sheet, r, colNome, "Altre pick", colors.light, false);
    } else {
      _setCell(sheet, r, colNome, "", colors.light, false);
    }

    // Colonna diritti (D): diritti rimanenti dalla riga 3
    if (ri + 2 < diritti.length) {
      _setCell(sheet, r, colDiritti, diritti[ri + 2], colors.light, false);
    }

    // Colonna draft (F): numeri draft corrente
    if (ri < draft_nums.length) {
      _setCell(sheet, r, colDraft, "#" + draft_nums[ri], colors.light, false);
    }

    // Colonne anni: pick altrui
    anni.forEach((anno, i) => {
      const col   = colAnniS + i * colsAnno;
      const picks = altrePickPerAnno[i];
      if (ri < picks.length) {
        _setCell(sheet, r, col, picks[ri], colors.light, false);
      } else {
        _setCell(sheet, r, col, "", colors.light, false);
      }
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

function _setCell(sheet, row, col, value, bgColor, bold, fontColor) {
  const cell = sheet.getRange(row, col);
  cell.setValue(value);
  cell.setBackground(bgColor);
  cell.setFontWeight(bold ? "bold" : "normal");
  cell.setFontColor(fontColor || "#000000");
  cell.setVerticalAlignment("middle");
}
