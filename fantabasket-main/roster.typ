// roster.typ

#let team_nome     = sys.inputs.at("team_nome")
#let team_gm       = sys.inputs.at("team_gm")
#let colore_hex    = sys.inputs.at("colore_header")
#let colore_riga1  = sys.inputs.at("colore_riga1")
#let colore_riga2  = sys.inputs.at("colore_riga2")
#let colore_sez    = sys.inputs.at("colore_sezione")
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
#let salary_cap    = sys.inputs.at("salary_cap")
#let eta_media     = sys.inputs.at("eta_media")
#let tagli_usati   = sys.inputs.at("tagli_usati")
#let cambi_usati   = sys.inputs.at("cambi_usati")
#let logo_path     = sys.inputs.at("logo_path")
#let giocatori_raw = sys.inputs.at("giocatori")
#let fine_10day    = sys.inputs.at("fine_10day", default: "")
#let salary_detail = sys.inputs.at("salary_detail")
#let fm_label      = sys.inputs.at("fm_label", default: "FP")
#let fm_nota       = sys.inputs.at("fm_nota", default: "")   // "* FP 26-27": chi ha i fantapunti dell'altra stagione

// flag: N=normale, A=RFA, R0-R3=rookie anno scale 1-4
#let giocatori = if giocatori_raw == "" { () } else {
  giocatori_raw.split(";").map(r => {
    let p = r.split("|")
    (nome: p.at(0, default: ""), importo: p.at(1, default: "0"),
     anni: p.at(2, default: "1"), flag: p.at(3, default: "N"),
     importo_orig: p.at(4, default: ""), badge: p.at(5, default: ""),
     ruolo: p.at(6, default: ""), eleg: p.at(7, default: ""), fm: p.at(8, default: ""), extra: p.at(9, default: ""))
  })
}

// Padding a 15 righe — aggiunge slot vuoti se il roster è incompleto
#let roster_max = 15
#let extra_g   = giocatori.filter(g => g.extra != "")
#let base_g    = giocatori.filter(g => g.extra == "")
#let base_g    = if base_g.len() >= roster_max { base_g } else {
  base_g + range(roster_max - base_g.len()).map(_ =>
    (nome: "", importo: "", anni: "", flag: "VUOTO", importo_orig: "", badge: "", ruolo: "", eleg: "", fm: "", extra: "")
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

// Colori rookie scale (evitare rosso = DPE futuro)
#let c_r0 = color.rgb("#1565C0")  // Anno I  — blu scuro
#let c_r1 = color.rgb("#2E7D32")  // Anno II — verde scuro
#let c_r2 = color.rgb("#F57F17")  // Anno III— ambra scura
#let c_r3 = color.rgb("#6A1B9A")  // Anno IV — viola (option year)
#let c_rfa = color.rgb("#E65100") // RFA     — arancio
#let c_10d = color.rgb("#00838F") // 10-day  — verde petrolio
#let c_dpe = color.rgb("#C62828") // DPE     — rosso scuro

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
          #align(center + horizon)[#text(6pt, fill: _ton_dark_m, weight: "bold")[LOGO]]
        ]
      },
      stack(spacing: 3pt,
        text(13pt, weight: "bold", fill: _ton_hdr)[#team_nome],
        text(8pt, fill: _ton_hdr_m)[#team_gm],
      )
    )
  ]
]

// ── tabella ───────────────────────────────────────────────────────────────────
#table(
  columns:  (30pt, 1fr, 34pt, 26pt, 20pt),
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
  [#align(center)[#text(6.5pt, weight: "bold", fill: _ton_dark)[RUOLO]]],
  [#text(8pt, weight: "bold", fill: _ton_dark)[GIOCATORE]],
  [#align(center)[#text(6.5pt, weight: "bold", fill: _ton_dark)[#fm_label]]],
  [#align(center)[#text(8pt, weight: "bold", fill: _ton_dark)[\$]]],
  [#align(center)[#text(8pt, weight: "bold", fill: _ton_dark)[Y]]],
  // giocatori
  ..if extra_g.len() > 0 { (table.hline(y: n_base + 1, stroke: 2pt + c_dark),) } else { () },
  ..giocatori.enumerate().map(((i, g)) => {
    let is_vuoto = g.flag == "VUOTO"
    let (fc, bold) = if g.flag == "R0"     { (c_r0,  true) }
                    else if g.flag == "R1"  { (c_r1,  true) }
                    else if g.flag == "R2"  { (c_r2,  true) }
                    else if g.flag == "R3"  { (c_r3,  true) }
                    else if g.flag == "A"   { (c_rfa, true) }
                    else if g.flag == "D"   { (c_10d, true) }
                    else                     { (none, false) }
    let ha_dpe = g.importo_orig != ""
    let tc = if calc.odd(i) { _ton_r1 } else { _ton_r2 }
    let fc_nome = if ha_dpe { c_dpe } else if fc == none { tc } else { fc }   // nomi normali: testo leggibile sulla riga
    let cella_importo = if is_vuoto {
      [#align(center)[]]
    } else if ha_dpe {
      [#align(center)[
        #text(7pt, fill: c_dpe, weight: "bold", overhang: false)[#strike[#g.importo_orig]#sym.space#g.importo]
      ]]
    } else {
      [#align(center)[#text(8.5pt, fill: tc, weight: "bold")[#g.importo]]]
    }
    (
      if is_vuoto { [] } else { [#align(center)[#text(8pt, fill: tc, weight: "bold")[#g.ruolo]]] },
      if is_vuoto { [] } else {
        [#{
          let t = text(8.5pt, fill: fc_nome, weight: if bold or ha_dpe {"bold"} else {"regular"})[#g.nome]
          if g.badge == "badge" { box(fill: white.transparentize(25%), radius: 2pt, inset: (x: 2pt, y: 1pt), t) } else { t }
          if g.eleg != "" { h(4pt); text(7pt, fill: tc, style: "italic")[(#g.eleg)] }
        }]
      },
      if is_vuoto { [] } else { [#align(center)[#text(8pt, fill: tc)[#g.fm]]] },
      cella_importo,
      if is_vuoto { [] } else { [#align(center)[#text(8.5pt, fill: tc)[#g.anni]]] },
    )
  }).flatten(),
)

// ── leggenda ─────────────────────────────────────────────────────────────────
#let has_rookie = giocatori.any(g => g.flag != "VUOTO" and g.flag.starts-with("R"))
#let has_rfa    = giocatori.any(g => g.flag == "A")
#let has_dpe    = giocatori.any(g => g.flag != "VUOTO" and g.importo_orig != "")
#let has_10d    = giocatori.any(g => g.flag == "D")

#if has_rookie or has_rfa or has_dpe or has_10d or fm_nota != "" {
  block(width: 100%, fill: c_sezione)[
    #pad(x: 6pt, y: 4pt)[
      #if giocatori.any(g => g.flag == "R0") [#text(7pt, fill: c_r0, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno I]  ]
      #if giocatori.any(g => g.flag == "R1") [#text(7pt, fill: c_r1, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno II]  ]
      #if giocatori.any(g => g.flag == "R2") [#text(7pt, fill: c_r2, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno III]  ]
      #if giocatori.any(g => g.flag == "R3") [#text(7pt, fill: c_r3, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[Anno IV]  ]
      #if has_rfa                             [#text(7pt, fill: c_rfa, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[RFA]  ]
      #if has_dpe                             [#text(7pt, fill: c_dpe, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[DPE]  ]
      #if has_10d [#text(7pt, fill: c_10d, weight: "bold")[■ ]#text(7pt, fill: _ton_sez, weight: "bold")[10-day#if fine_10day != "" [ #fine_10day]]  ]
      #if fm_nota != "" [#h(8pt)#text(7pt, fill: _ton_sez, weight: "bold")[#fm_nota]]
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
      [#text(8pt, fill: _ton_ftr_m)[ETÀ MEDIA]],
      [#text(8pt, fill: _ton_ftr)[#eta_media]],
    )
    #v(3pt)
    #grid(columns: (1fr, auto),
      [#text(7.5pt, fill: _ton_ftr_m)[TAGLI SENZA IMPATTO USATI]],
      [#text(7.5pt, fill: _ton_ftr)[#tagli_usati]],
    )
    #v(2pt)
    #grid(columns: (1fr, auto),
      [#text(7.5pt, fill: _ton_ftr_m)[CAMBI RUOLO USATI]],
      [#text(7.5pt, fill: _ton_ftr)[#cambi_usati]],
    )
  ]
]
