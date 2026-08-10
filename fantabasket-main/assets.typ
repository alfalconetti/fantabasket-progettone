// assets.typ — visualizzatore asset completo
// Input: stessi del roster.typ + picks + diritti

#let team_nome     = sys.inputs.at("team_nome",    default: "Baltimora Bats")
#let team_gm       = sys.inputs.at("team_gm",      default: "Luca")
#let colore_hex    = sys.inputs.at("colore",        default: "#1A237E")
#let colore_riga1  = sys.inputs.at("colore_riga1",  default: "")
#let colore_riga2  = sys.inputs.at("colore_riga2",  default: "")
#let colore_sez    = sys.inputs.at("colore_sezione",default: "")
#let colore_pick_h = sys.inputs.at("colore_pick",   default: "")
#let colore_dir_h  = sys.inputs.at("colore_diritti",default: "")
#let _ton_r1       = rgb(sys.inputs.at("text_on_riga1",        default: "#1a1a1a"))
#let _ton_r2       = rgb(sys.inputs.at("text_on_riga2",        default: "#1a1a1a"))
#let _ton_sez      = rgb(sys.inputs.at("text_on_sezione",      default: "#1a1a1a"))
#let _ton_sez_m    = rgb(sys.inputs.at("text_on_sezione_muted",default: "#555555"))
#let _ton_ftr      = rgb(sys.inputs.at("text_on_footer",        default: "#f0f0f0"))
#let _ton_ftr_m    = rgb(sys.inputs.at("text_on_footer_muted",  default: "#bbbbbb"))
#let _ton_pick     = rgb(sys.inputs.at("text_on_pick",         default: "#1a1a1a"))
#let _ton_pick_m   = rgb(sys.inputs.at("text_on_pick_muted",   default: "#555555"))
#let _ton_dir      = rgb(sys.inputs.at("text_on_dir",          default: "#1a1a1a"))
#let salary_cap    = sys.inputs.at("salary_cap",    default: "142")
#let salary_detail = sys.inputs.at("salary_detail", default: "")
#let eta_media     = sys.inputs.at("eta_media",     default: "26.8")
#let logo_path     = sys.inputs.at("logo_path",     default: "")
#let giocatori_raw = sys.inputs.at("giocatori",     default: "")
// picks: "2027|1st|Propria;2027|2nd|Propria;2028||;2029|1st|Propria;..."
// anno vuoto = anno senza pick → mostra cella vuota
#let picks_raw     = sys.inputs.at("picks",         default: "")
#let diritti_raw   = sys.inputs.at("diritti",       default: "")

// ── parse giocatori ───────────────────────────────────────────────────────────
#let giocatori = if giocatori_raw == "" { () } else {
  giocatori_raw.split(";").map(r => {
    let p = r.split("|")
    (nome: p.at(0, default: ""), importo: p.at(1, default: "0"),
     anni: p.at(2, default: "1"), flag: p.at(3, default: "N"))
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
    if anno != "" {
      if anno not in acc { acc.insert(anno, ()) }
      if rnd != "" {
        acc.at(anno).push((round: rnd, by: by))
      }
    }
  }
  acc
}
#let anni_pick = picks_parsed.keys().sorted()

// ── colori ────────────────────────────────────────────────────────────────────
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

#set page(width: 420pt, height: auto, margin: 0pt, fill: white)
#set text(font: "Liberation Sans", size: 9pt)

// ── header ────────────────────────────────────────────────────────────────────
#block(width: 100%, fill: c_primary)[
  #pad(x: 8pt, y: 6pt)[
    #grid(columns: (40pt, 1fr), gutter: 8pt, align: horizon,
      if logo_path != "" {
        image(logo_path, width: 40pt, height: 40pt, fit: "contain")
      } else {
        block(width: 40pt, height: 40pt, fill: c_dark, radius: 4pt)[
          #align(center + horizon)[#text(6pt, fill: c_subhdr, weight: "bold")[LOGO]]
        ]
      },
      stack(spacing: 3pt,
        text(13pt, weight: "bold", fill: white)[#team_nome],
        text(8pt, fill: c_subhdr)[#team_gm],
      )
    )
  ]
]

// ── roster ────────────────────────────────────────────────────────────────────
#table(
  columns:  (1fr, 26pt, 20pt),
  rows:     17pt,
  inset:    (x: 6pt, y: 0pt),
  align:    horizon + left,
  stroke:   none,
  fill: (col, row) => {
    if row == 0 { return c_dark }
    let i = row - 1
    let g = giocatori.at(i, default: none)
    if g == none { return white }
    if calc.odd(i) { c_row_odd } else { c_row_even }
  },
  [#text(7.5pt, weight: "bold", fill: white)[GIOCATORE]],
  [#align(center)[#text(7.5pt, weight: "bold", fill: white)[\$]]],
  [#align(center)[#text(7.5pt, weight: "bold", fill: white)[Y]]],
  ..giocatori.enumerate().map(((i, g)) => {
    let (fc, bold) = if g.flag == "R0"    { (c_r0,  true) }
                else if g.flag == "R1"    { (c_r1,  true) }
                else if g.flag == "R2"    { (c_r2,  true) }
                else if g.flag == "R3"    { (c_r3,  true) }
                else if g.flag == "A"     { (c_rfa, true) }
                else                       { (black, false) }
    let tc = if calc.odd(i) { _ton_r1 } else { _ton_r2 }
    (
      [#text(8pt, fill: fc, weight: if bold {"bold"} else {"regular"})[#g.nome]],
      [#align(center)[#text(8pt, fill: tc, weight: "bold")[#g.importo]]],
      [#align(center)[#text(8pt, fill: tc)[#g.anni]]],
    )
  }).flatten(),
)

// ── leggenda rookie ───────────────────────────────────────────────────────────
#let has_rookie = giocatori.any(g => g.flag.starts-with("R"))
#let has_rfa    = giocatori.any(g => g.flag == "A")
#if has_rookie or has_rfa {
  block(width: 100%, fill: c_sezione)[
    #pad(x: 6pt, y: 3pt)[
      #if giocatori.any(g => g.flag == "R0") [#text(7pt, fill: c_r0,  weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno I ]  ]
      #if giocatori.any(g => g.flag == "R1") [#text(7pt, fill: c_r1,  weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno II ]  ]
      #if giocatori.any(g => g.flag == "R2") [#text(7pt, fill: c_r2,  weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno III ]  ]
      #if giocatori.any(g => g.flag == "R3") [#text(7pt, fill: c_r3,  weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno IV ]  ]
      #if has_rfa                             [#text(7pt, fill: c_rfa, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[RFA]]
    ]
  ]
}

// ── pick ──────────────────────────────────────────────────────────────────────
#if anni_pick.len() > 0 {
  block(width: 100%, fill: c_pick_bg)[
    #pad(x: 6pt, y: 6pt)[
      #text(7.5pt, weight: "bold", fill: _ton_pick)[PICK]
      #v(5pt)
      #grid(
        columns: (1fr, 1fr, 1fr),
        gutter:  6pt,
        ..anni_pick.map(anno => {
          let anno_picks = picks_parsed.at(anno, default: ())
          block(width: 100%)[
            #block(fill: c_primary, radius: 2pt, inset: (x: 4pt, y: 2pt), width: 100%)[
              #align(center)[#text(8.5pt, weight: "bold", fill: white)[#anno]]
            ]
            #v(2pt)
            #if anno_picks.len() == 0 {
              block(below: 0pt)[
                #text(6.5pt, fill: _ton_pick_m)[—]
              ]
            } else {
              for p in anno_picks {
                let is_propria = p.by == "Propria" or p.by == ""
                block(below: 3pt)[
                  #text(9pt,
                    fill: _ton_pick,
                    weight: if is_propria { "bold" } else { "regular" }
                  )[
                    #if is_propria [★] else [○] #p.round
                    #if not is_propria [
                      #linebreak()
                      #h(8pt)#text(8pt, fill: _ton_pick_m)[#p.by]
                    ]
                  ]
                ]
              }
            }
          ]
        })
      )
    ]
  ]
}

// ── diritti ───────────────────────────────────────────────────────────────────
#if diritti_raw != "" {
  block(width: 100%, fill: c_dir_bg)[
    #pad(x: 6pt, y: 5pt)[
      #text(8pt, weight: "bold", fill: _ton_dir)[DIRITTI ROOKIE]
      #v(3pt)
      #text(8pt)[#diritti_raw]
    ]
  ]
}

// ── footer ────────────────────────────────────────────────────────────────────
#block(width: 100%, fill: if colore_sez != "" { c_sezione } else { c_dark })[
  #pad(x: 6pt, y: 5pt)[
    #grid(columns: (1fr, auto),
      [#text(8pt, weight: "bold", fill: _ton_ftr)[SALARY CAP]],
      [#text(8pt, weight: "bold", fill: _ton_ftr)[#salary_cap M]],
    )
    #if salary_detail != "" and salary_detail != salary_cap [
      #v(1pt)
      #let parts = salary_detail.split("+")
      #grid(columns: (1fr, auto),
        [#text(6.5pt, fill: _ton_ftr_m)[  contratti]],
        [#text(6.5pt, fill: _ton_ftr_m)[#parts.at(0, default: "")M]],
      )
      #grid(columns: (1fr, auto),
        [#text(6.5pt, fill: _ton_ftr_m)[  impatto tagli]],
        [#text(6.5pt, fill: _ton_ftr_m)[#parts.at(1, default: "0")M]],
      )
    ]
    #v(3pt)
    #grid(columns: (1fr, auto),
      [#text(7.5pt, fill: _ton_ftr_m)[ETA MEDIA]],
      [#text(7.5pt, fill: _ton_ftr)[#eta_media]],
    )
  ]
]
