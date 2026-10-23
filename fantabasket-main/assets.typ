// assets.typ — visualizzatore asset completo
// Input: stessi del roster.typ + picks + diritti

#let team_nome     = sys.inputs.at("team_nome")
#let team_gm       = sys.inputs.at("team_gm")
#let colore_hex    = sys.inputs.at("colore_header")
#let colore_riga1  = sys.inputs.at("colore_riga1")
#let colore_riga2  = sys.inputs.at("colore_riga2")
#let colore_sez    = sys.inputs.at("colore_sezione")
#let colore_pick_h = sys.inputs.at("colore_pick")
#let colore_dir_h  = sys.inputs.at("colore_diritti")
#let _ton_hdr     = rgb(sys.inputs.at("text_on_header", default: "#ffffff"))        // testo sull'intestazione
#let _ton_hdr_m   = rgb(sys.inputs.at("text_on_header_muted", default: "#cccccc"))
#let _ton_dark    = rgb(sys.inputs.at("text_on_dark", default: "#ffffff"))          // testo sulla riga dei titoli
#let _ton_dark_m  = rgb(sys.inputs.at("text_on_dark_muted", default: "#cccccc"))
#let _ton_r1       = rgb(sys.inputs.at("text_on_riga1"))
#let _ton_r2       = rgb(sys.inputs.at("text_on_riga2"))
#let _ton_sez      = rgb(sys.inputs.at("text_on_sezione"))
#let _ton_sez_m    = rgb(sys.inputs.at("text_on_sezione_muted"))
#let _ton_ftr      = rgb(sys.inputs.at("text_on_footer"))
#let _ton_ftr_m    = rgb(sys.inputs.at("text_on_footer_muted"))
#let _ton_pick     = rgb(sys.inputs.at("text_on_pick"))
#let _ton_pick_m   = rgb(sys.inputs.at("text_on_pick_muted"))
#let _ton_dir      = rgb(sys.inputs.at("text_on_dir"))
#let salary_cap    = sys.inputs.at("salary_cap")
#let salary_detail = sys.inputs.at("salary_detail")
#let eta_media     = sys.inputs.at("eta_media")
#let logo_path     = sys.inputs.at("logo_path")
#let giocatori_raw = sys.inputs.at("giocatori")
#let fine_10day    = sys.inputs.at("fine_10day", default: "")
// picks: "2027|1st|Propria|S;2027|2nd|Propria|;2028||;2029|1st|Propria|;..."  (S = bloccata Stepien)
// anno vuoto = anno senza pick → mostra cella vuota
#let picks_raw     = sys.inputs.at("picks")
#let diritti_raw   = sys.inputs.at("diritti")

// ── parse giocatori ───────────────────────────────────────────────────────────
#let giocatori = if giocatori_raw == "" { () } else {
  giocatori_raw.split(";").map(r => {
    let p = r.split("|")
    (nome: p.at(0, default: ""), importo: p.at(1, default: "0"),
     anni: p.at(2, default: "1"), flag: p.at(3, default: "N"),
     importo_orig: p.at(4, default: ""), badge: p.at(5, default: ""),
     ruolo: p.at(6, default: ""), eleg: p.at(7, default: ""), extra: p.at(9, default: ""))
  })
}

// ── parse picks ───────────────────────────────────────────────────────────────
// Struttura interna: dict anno → list of (round, by)
#let picks_parsed = if picks_raw == "" { (:) } else {
  let acc = (:)
  for r in picks_raw.split(";") {
    let p = r.split("|")
    let anno = p.at(0, default: "")
    let rnd  = p.at(1, default: "")
    let by   = p.at(2, default: "")
    let stp  = p.at(3, default: "") == "S"
    if anno != "" {
      if anno not in acc { acc.insert(anno, ()) }
      if rnd != "" {
        acc.at(anno).push((round: rnd, by: by, stepien: stp))
      }
    }
  }
  acc
}
#let anni_pick = picks_parsed.keys().sorted()

// ── colori ────────────────────────────────────────────────────────────────────
// Padding a 15 righe
#let roster_max = 15
#let extra_g   = giocatori.filter(g => g.extra != "")
#let base_g    = giocatori.filter(g => g.extra == "")
#let base_g    = if base_g.len() >= roster_max { base_g } else {
  base_g + range(roster_max - base_g.len()).map(_ =>
    (nome: "", importo: "", anni: "", flag: "VUOTO", importo_orig: "", badge: "", ruolo: "", eleg: "", extra: "")
  )
}
// fuori dai 15 (DPE che libera lo slot, 10-day): sotto, dopo una riga più spessa
#let n_base    = base_g.len()
#let giocatori = base_g + extra_g

#let c_primary  = color.rgb(colore_hex)
#let c_dark     = c_primary.darken(20%)
#let c_row_odd  = if colore_riga1 != "" { color.rgb(colore_riga1) } else { c_primary.lighten(75%) }
#let c_row_even = if colore_riga2 != "" { color.rgb(colore_riga2) } else { white }
#let c_subhdr   = c_primary.lighten(50%)
#let c_sezione  = if colore_sez != "" { color.rgb(colore_sez) } else { c_primary.lighten(85%) }
#let c_pick_bg  = if colore_pick_h != "" { color.rgb(colore_pick_h) } else { c_primary.lighten(90%) }
#let c_dir_bg   = if colore_dir_h != "" { color.rgb(colore_dir_h) } else { c_primary.lighten(95%) }
#let c_r0  = color.rgb("#1565C0")
#let c_r1  = color.rgb("#2E7D32")
#let c_r2  = color.rgb("#F57F17")
#let c_r3  = color.rgb("#6A1B9A")
#let c_rfa = color.rgb("#E65100")
#let c_10d = color.rgb("#00838F") // 10-day  — verde petrolio
#let c_dpe = color.rgb("#C62828") // DPE — rosso scuro

#set page(width: 420pt, height: auto, margin: 0pt, fill: white)
#set text(font: "Liberation Sans", size: 9pt)
#set block(spacing: 0pt)                 // niente strisce bianche tra un blocco e l'altro

#let pieni = base_g.filter(g => g.flag != "VUOTO").len()
#let stemma(d) = box(width: d, height: d, radius: 50%, clip: true, fill: c_dark,
  stroke: 1.5pt + _ton_hdr.transparentize(55%),
  if logo_path != "" { image(logo_path, width: d, height: d, fit: "contain") }
  else { align(center + horizon, text(d * 0.42, weight: "bold", fill: _ton_dark)[#team_nome.slice(0, 1)]) })
#let sezione(t, colore) = text(7pt, weight: "bold", fill: colore, tracking: 0.8pt)[#t]

// ── header ────────────────────────────────────────────────────────────────────
#block(width: 100%, fill: gradient.linear(c_primary, c_primary.darken(12%), angle: 0deg), inset: (x: 12pt, y: 10pt))[
  #grid(columns: (auto, 1fr, auto), column-gutter: 10pt, align: horizon,
    stemma(46pt),
    stack(spacing: 4pt,
      text(15pt, weight: "bold", fill: _ton_hdr)[#team_nome],
      text(8pt, fill: _ton_hdr_m)[#team_gm · età media #eta_media]),
    align(right, stack(spacing: 3pt,
      text(6.5pt, weight: "bold", fill: _ton_hdr_m, tracking: 0.6pt)[SALARY CAP],
      text(14pt, weight: "bold", fill: _ton_hdr)[#salary_cap M],
      ..if salary_detail != "" and salary_detail != salary_cap {
        let parts = salary_detail.split("+")
        (text(6.5pt, fill: _ton_hdr_m)[contratti #parts.at(0, default: "")M · tagli #parts.at(1, default: "0")M],)
      } else { () })),
  )
]

// ── roster ────────────────────────────────────────────────────────────────────
#let titolo(t, al: center) = align(al, text(6.5pt, weight: "bold", fill: _ton_dark, tracking: 0.5pt)[#t])
#table(
  columns:  (32pt, 1fr, 56pt, 30pt),
  rows:     (16pt,) + base_g.map(g => if g.flag == "VUOTO" { 12pt } else { 18pt })
            + if extra_g.len() > 0 { (13pt,) + extra_g.map(_ => 18pt) } else { () },
  inset:    (x: 6pt, y: 0pt),
  align:    horizon + left,
  stroke:   (x, y) => if y > 0 { (bottom: 0.4pt + c_dark.transparentize(88%)) } else { none },
  fill: (col, row) => {
    if row == 0 { return c_dark }
    if extra_g.len() > 0 and row == n_base + 1 { return c_sezione }
    let i = if extra_g.len() > 0 and row > n_base + 1 { row - 2 } else { row - 1 }
    let g = giocatori.at(i, default: none)
    if g == none { return white }
    if calc.odd(i) { c_row_odd } else { c_row_even }
  },
  titolo[RUOLO], titolo(al: left)[GIOCATORI · #pieni/#roster_max], titolo[\$], titolo[ANNI],
  ..if extra_g.len() > 0 { (table.hline(y: n_base + 1, stroke: 1.5pt + c_dark),) } else { () },
  ..giocatori.enumerate().map(((i, g)) => {
    // fuori dai 15 (DPE che libera lo slot, 10-day): sotto la riga spessa, con un'etichetta
    let etichetta = if extra_g.len() > 0 and i == n_base {
      (table.cell(colspan: 4, inset: (x: 6pt, y: 0pt))[#text(6pt, weight: "bold", fill: _ton_sez, tracking: 0.6pt)[FUORI DAI 15]],)
    } else { () }
    let is_vuoto = g.flag == "VUOTO"
    let (fc, bold) = if g.flag == "R0"    { (c_r0,  true) }
                else if g.flag == "R1"    { (c_r1,  true) }
                else if g.flag == "R2"    { (c_r2,  true) }
                else if g.flag == "R3"    { (c_r3,  true) }
                else if g.flag == "A"     { (c_rfa, true) }
                else if g.flag == "D"     { (c_10d, true) }
                else                       { (none, false) }
    let ha_dpe = g.importo_orig != ""
    let tc = if calc.odd(i) { _ton_r1 } else { _ton_r2 }
    let fc_nome = if ha_dpe { c_dpe } else if fc == none { tc } else { fc }   // nomi normali: testo leggibile sulla riga
    let cella_importo = if is_vuoto { [] } else if ha_dpe {
      align(center, [#text(6pt, fill: c_dpe.transparentize(30%))[#strike[#g.importo_orig]] #text(8.5pt, fill: c_dpe, weight: "bold")[#g.importo]])
    } else {
      align(center, text(8.5pt, fill: tc, weight: "bold")[#g.importo])
    }
    etichetta + if is_vuoto {
      ([], text(6.5pt, fill: tc.transparentize(65%), style: "italic")[posto libero], [], [])
    } else {
      (
        align(center, box(fill: c_dark, radius: 3pt, inset: (x: 3pt, y: 2pt), width: 21pt,
          align(center, text(7pt, fill: _ton_dark, weight: "bold")[#if g.ruolo != "" [#g.ruolo] else [–]]))),
        {
          if fc != none or ha_dpe { box(width: 2.5pt, height: 10pt, radius: 1pt, fill: if ha_dpe { c_dpe } else { fc }, baseline: 25%); h(4pt) }
          let t = text(8.5pt, fill: fc_nome, weight: if bold or ha_dpe {"bold"} else {"regular"})[#g.nome]
          if g.badge == "badge" { box(fill: white.transparentize(25%), radius: 2pt, inset: (x: 2pt, y: 1pt), t) } else { t }
        },
        cella_importo,
        align(center, text(8.5pt, fill: tc)[#g.anni]),
      )
    }
  }).flatten(),
)

// ── leggenda ──────────────────────────────────────────────────────────────────
#let has_rookie = giocatori.any(g => g.flag != "VUOTO" and g.flag.starts-with("R"))
#let has_rfa    = giocatori.any(g => g.flag == "A")
#let has_dpe    = giocatori.any(g => g.flag != "VUOTO" and g.importo_orig != "")
#let has_10d    = giocatori.any(g => g.flag == "D")
#let voce(c, t) = box(inset: (right: 8pt), [#box(width: 7pt, height: 7pt, radius: 2pt, fill: c, baseline: 10%) #text(7pt, fill: _ton_sez, weight: "bold")[#t]])
#if has_rookie or has_rfa or has_dpe or has_10d {
  block(width: 100%, fill: c_sezione, inset: (x: 10pt, y: 5pt))[
    #if giocatori.any(g => g.flag == "R0") { voce(c_r0)[Anno I] }
    #if giocatori.any(g => g.flag == "R1") { voce(c_r1)[Anno II] }
    #if giocatori.any(g => g.flag == "R2") { voce(c_r2)[Anno III] }
    #if giocatori.any(g => g.flag == "R3") { voce(c_r3)[Anno IV] }
    #if has_rfa { voce(c_rfa)[RFA] }
    #if has_dpe { voce(c_dpe)[DPE] }
    #if has_10d { voce(c_10d)[10-day#if fine_10day != "" [ #fine_10day]] }
  ]
}

// ── pick ──────────────────────────────────────────────────────────────────────
// propria: gettone pieno; presa da un'altra squadra: gettone col bordo e la squadra d'origine
#let gettone(p) = {
  let propria = p.by == "Propria" or p.by == ""
  let dentro = [#text(8.5pt, weight: "bold")[#p.round]#if not propria [#h(3pt)#text(7pt)[da #p.by]]]
  box(inset: (bottom: 4pt), {
    if propria { box(fill: c_dark, radius: 8pt, inset: (x: 7pt, y: 3pt), text(fill: _ton_dark, dentro)) }
    else { box(stroke: 1pt + _ton_pick.transparentize(40%), radius: 8pt, inset: (x: 7pt, y: 3pt), text(fill: _ton_pick, dentro)) }
    if p.stepien { h(3pt); box(fill: c_dpe, radius: 2pt, inset: (x: 3pt, y: 2pt), text(5.5pt, weight: "bold", fill: white)[STEPIEN]) }
  })
}
#if anni_pick.len() > 0 {
  block(width: 100%, fill: c_pick_bg, inset: (x: 10pt, top: 9pt, bottom: 6pt))[
    #block(below: 7pt, sezione([PICK], _ton_pick))
    #grid(columns: (1fr,) * calc.min(anni_pick.len(), 3), column-gutter: 6pt, row-gutter: 6pt,
      ..anni_pick.map(anno => {
        let anno_picks = picks_parsed.at(anno, default: ())
        block(width: 100%, radius: 5pt, clip: true, fill: _ton_pick.transparentize(93%))[
          #block(width: 100%, fill: c_primary, inset: (y: 3pt))[#align(center, text(9pt, weight: "bold", fill: _ton_hdr)[#anno])]
          #block(inset: (x: 6pt, top: 6pt, bottom: 2pt))[
            #set par(leading: 2pt)
            #if anno_picks.len() == 0 [#text(7.5pt, fill: _ton_pick_m, style: "italic")[nessuna pick]] else {
              for p in anno_picks { gettone(p); linebreak() }
            }
          ]
        ]
      })
    )
  ]
}

// ── diritti ───────────────────────────────────────────────────────────────────
#if diritti_raw != "" {
  block(width: 100%, fill: c_dir_bg, inset: (x: 10pt, y: 8pt))[
    #block(below: 6pt, sezione([DIRITTI ROOKIE], _ton_dir))
    #for d in diritti_raw.split(", ") {
      box(inset: (right: 5pt, bottom: 3pt), box(stroke: 0.8pt + _ton_dir.transparentize(55%), radius: 8pt, inset: (x: 7pt, y: 3pt), text(8pt, fill: _ton_dir)[#d]))
    }
  ]
}
#block(width: 100%, height: 4pt, fill: c_dark)
