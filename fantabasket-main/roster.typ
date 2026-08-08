// roster.typ

#let team_nome     = sys.inputs.at("team_nome",    default: "Baltimora Bats")
#let team_gm       = sys.inputs.at("team_gm",      default: "Luca")
#let colore_hex    = sys.inputs.at("colore",        default: "#2E7D32")
#let colore2_hex   = sys.inputs.at("colore2",       default: "")
#let colore_riga1  = sys.inputs.at("colore_riga1",  default: "")
#let colore_riga2  = sys.inputs.at("colore_riga2",  default: "")
#let colore_sez    = sys.inputs.at("colore_sezione",default: "")
#let _ton_r1       = rgb(sys.inputs.at("text_on_riga1",        default: "#1a1a1a"))
#let _ton_r2       = rgb(sys.inputs.at("text_on_riga2",        default: "#1a1a1a"))
#let _ton_sez      = rgb(sys.inputs.at("text_on_sezione",      default: "#1a1a1a"))
#let _ton_sez_m    = rgb(sys.inputs.at("text_on_sezione_muted",default: "#555555"))
#let salary_cap    = sys.inputs.at("salary_cap",    default: "142")
#let eta_media     = sys.inputs.at("eta_media",     default: "26.86")
#let tagli_usati   = sys.inputs.at("tagli_usati",   default: "0/3")
#let cambi_usati   = sys.inputs.at("cambi_usati",   default: "0/2")
#let logo_path     = sys.inputs.at("logo_path",     default: "")
#let giocatori_raw = sys.inputs.at("giocatori",     default: "")
#let salary_detail = sys.inputs.at("salary_detail", default: "")

// flag: N=normale, A=RFA, R0-R3=rookie anno scale 1-4
#let giocatori = if giocatori_raw == "" { () } else {
  giocatori_raw.split(";").map(r => {
    let p = r.split("|")
    (nome: p.at(0, default: ""), importo: p.at(1, default: "0"),
     anni: p.at(2, default: "1"), flag: p.at(3, default: "N"))
  })
}

#let c_primary  = color.rgb(colore_hex)
#let c_dark     = c_primary.darken(20%)
#let c_row_odd  = if colore_riga1 != "" { color.rgb(colore_riga1) } else { c_primary.lighten(75%) }
#let c_row_even = if colore_riga2 != "" { color.rgb(colore_riga2) } else if colore2_hex != "" { color.rgb(colore2_hex).lighten(75%) } else { white }
#let c_subhdr   = c_primary.lighten(50%)
#let c_sezione  = if colore_sez != "" { color.rgb(colore_sez) } else { c_primary.lighten(85%) }

// Colori rookie scale (evitare rosso = DPE futuro)
#let c_r0 = color.rgb("#1565C0")  // Anno I  — blu scuro
#let c_r1 = color.rgb("#2E7D32")  // Anno II — verde scuro
#let c_r2 = color.rgb("#F57F17")  // Anno III— ambra scura
#let c_r3 = color.rgb("#6A1B9A")  // Anno IV — viola (option year)
#let c_rfa = color.rgb("#E65100") // RFA     — arancio

#set page(width: 300pt, height: auto, margin: 0pt, fill: white)
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

// ── tabella ───────────────────────────────────────────────────────────────────
#table(
  columns:  (1fr, 26pt, 20pt),
  rows:     18pt,
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
  // intestazione
  [#text(8pt, weight: "bold", fill: white)[GIOCATORE]],
  [#align(center)[#text(8pt, weight: "bold", fill: white)[\$]]],
  [#align(center)[#text(8pt, weight: "bold", fill: white)[Y]]],
  // giocatori
  ..giocatori.enumerate().map(((i, g)) => {
    let (fc, bold) = if g.flag == "R0"     { (c_r0,  true) }
                    else if g.flag == "R1"  { (c_r1,  true) }
                    else if g.flag == "R2"  { (c_r2,  true) }
                    else if g.flag == "R3"  { (c_r3,  true) }
                    else if g.flag == "A"   { (c_rfa, true) }
                    else                     { (black, false) }
    let tc = if calc.odd(i) { _ton_r1 } else { _ton_r2 }
    (
      [#text(8.5pt, fill: fc, weight: if bold {"bold"} else {"regular"})[#g.nome]],
      [#align(center)[#text(8.5pt, fill: tc, weight: "bold")[#g.importo]]],
      [#align(center)[#text(8.5pt, fill: tc)[#g.anni]]],
    )
  }).flatten(),
)

// ── leggenda ─────────────────────────────────────────────────────────────────
#let has_rookie = giocatori.any(g => g.flag.starts-with("R"))
#let has_rfa    = giocatori.any(g => g.flag == "A")

#if has_rookie or has_rfa {
  block(width: 100%, fill: c_sezione)[
    #pad(x: 6pt, y: 4pt)[
      #if giocatori.any(g => g.flag == "R0") [#text(7pt, fill: c_r0, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno I]  ]
      #if giocatori.any(g => g.flag == "R1") [#text(7pt, fill: c_r1, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno II]  ]
      #if giocatori.any(g => g.flag == "R2") [#text(7pt, fill: c_r2, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno III]  ]
      #if giocatori.any(g => g.flag == "R3") [#text(7pt, fill: c_r3, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno IV]  ]
      #if has_rfa                             [#text(7pt, fill: c_rfa, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[RFA]]
    ]
  ]
}

// ── footer ────────────────────────────────────────────────────────────────────
#block(width: 100%, fill: c_sezione)[
  #pad(x: 6pt, y: 5pt)[
    #grid(columns: (1fr, auto),
      [#text(8pt, weight: "bold", fill: _ton_sez)[SALARY CAP]],
      [#text(8pt, weight: "bold", fill: _ton_sez)[#salary_cap M]],
    )
    #if salary_detail != "" and salary_detail != salary_cap [
      #v(1pt)
      #let parts = salary_detail.split("+")
      #grid(columns: (1fr, auto),
        [#text(6.5pt, fill: _ton_sez_m)[  contratti]],
        [#text(6.5pt, fill: _ton_sez_m)[#parts.at(0, default: "")M]],
      )
      #grid(columns: (1fr, auto),
        [#text(6.5pt, fill: _ton_sez_m)[  impatto tagli]],
        [#text(6.5pt, fill: _ton_sez_m)[#parts.at(1, default: "0")M]],
      )
    ]
    #v(3pt)
    #grid(columns: (1fr, auto),
      [#text(8pt, fill: _ton_sez_m)[ETÀ MEDIA]],
      [#text(8pt, fill: _ton_sez)[#eta_media]],
    )
    #v(3pt)
    #grid(columns: (1fr, auto),
      [#text(7.5pt, fill: _ton_sez_m)[TAGLI SENZA IMPATTO USATI]],
      [#text(7.5pt, fill: _ton_sez)[#tagli_usati]],
    )
    #v(2pt)
    #grid(columns: (1fr, auto),
      [#text(7.5pt, fill: _ton_sez_m)[CAMBI RUOLO USATI]],
      [#text(7.5pt, fill: _ton_sez)[#cambi_usati]],
    )
  ]
]
