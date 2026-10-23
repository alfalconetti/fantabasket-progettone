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
#set block(spacing: 0pt)                 // niente strisce bianche tra un blocco e l'altro

#let pieni = base_g.filter(g => g.flag != "VUOTO").len()

// stemma tondo con anello, iniziale se manca il logo
#let stemma(d) = box(width: d, height: d, radius: 50%, clip: true, fill: c_dark,
  stroke: 1.5pt + _ton_hdr.transparentize(55%),
  if logo_path != "" { image(logo_path, width: d, height: d, fit: "contain") }
  else { align(center + horizon, text(d * 0.42, weight: "bold", fill: _ton_dark)[#team_nome.slice(0, 1)]) })

// ── header ────────────────────────────────────────────────────────────────────
#block(width: 100%, fill: gradient.linear(c_primary, c_primary.darken(12%), angle: 0deg), inset: (x: 10pt, y: 10pt))[
  #grid(columns: (auto, 1fr, auto), column-gutter: 9pt, align: horizon,
    stemma(42pt),
    stack(spacing: 4pt,
      text(14pt, weight: "bold", fill: _ton_hdr)[#team_nome],
      text(8pt, fill: _ton_hdr_m)[#team_gm]),
    align(right, stack(spacing: 3pt,
      text(6.5pt, weight: "bold", fill: _ton_hdr_m, tracking: 0.6pt)[SALARY CAP],
      text(13pt, weight: "bold", fill: _ton_hdr)[#salary_cap M],
      ..if salary_detail != "" and salary_detail != salary_cap {
        let parts = salary_detail.split("+")
        (text(6.5pt, fill: _ton_hdr_m)[contratti #parts.at(0, default: "")M · tagli #parts.at(1, default: "0")M],)
      } else { () })),
  )
]

// ── tabella ───────────────────────────────────────────────────────────────────
#let titolo(t, al: center) = align(al, text(6.5pt, weight: "bold", fill: _ton_dark, tracking: 0.5pt)[#t])
#table(
  columns:  (30pt, 1fr, 30pt, 30pt, 26pt),
  rows:     (16pt,) + base_g.map(g => if g.flag == "VUOTO" { 13pt } else { 20pt })
            + if extra_g.len() > 0 { (13pt,) + extra_g.map(_ => 20pt) } else { () },
  inset:    (x: 5pt, y: 0pt),
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
  // intestazione
  titolo[RUOLO], titolo(al: left)[GIOCATORI · #pieni/#roster_max], titolo[#fm_label], titolo[\$], titolo[ANNI],
  // giocatori
  ..if extra_g.len() > 0 { (table.hline(y: n_base + 1, stroke: 1.5pt + c_dark),) } else { () },
  ..giocatori.enumerate().map(((i, g)) => {
    // fuori dai 15 (DPE che libera lo slot, 10-day): sotto la riga spessa, con un'etichetta
    let etichetta = if extra_g.len() > 0 and i == n_base {
      (table.cell(colspan: 5, inset: (x: 6pt, y: 0pt))[#text(6pt, weight: "bold", fill: _ton_sez, tracking: 0.6pt)[FUORI DAI 15]],)
    } else { () }
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
    let cella_importo = if is_vuoto { [] } else if ha_dpe {
      align(center, stack(spacing: 1.5pt,
        text(6pt, fill: c_dpe.transparentize(30%))[#strike[#g.importo_orig]],
        text(8.5pt, fill: c_dpe, weight: "bold")[#g.importo]))
    } else {
      align(center, text(9pt, fill: tc, weight: "bold")[#g.importo])
    }
    etichetta + if is_vuoto {
      ([], text(6.5pt, fill: tc.transparentize(65%), style: "italic")[posto libero], [], [], [])
    } else {
      (
        align(center, box(fill: c_dark, radius: 3pt, inset: (x: 3pt, y: 2pt), width: 21pt,
          align(center, text(7pt, fill: _ton_dark, weight: "bold")[#if g.ruolo != "" [#g.ruolo] else [–]]))),
        {
          // colore del tipo di contratto: una barretta davanti al nome (oltre al colore del nome)
          if fc != none or ha_dpe { box(width: 2.5pt, height: 11pt, radius: 1pt, fill: if ha_dpe { c_dpe } else { fc }, baseline: 25%); h(4pt) }
          let t = text(9pt, fill: fc_nome, weight: if bold or ha_dpe {"bold"} else {"regular"})[#g.nome]
          if g.badge == "badge" { box(fill: white.transparentize(25%), radius: 2pt, inset: (x: 2pt, y: 1pt), t) } else { t }
          if g.eleg != "" { h(4pt); text(6.5pt, fill: tc.transparentize(30%))[#g.eleg] }
        },
        align(center, text(8pt, fill: tc)[#g.fm]),
        cella_importo,
        align(center, text(8.5pt, fill: tc)[#g.anni]),
      )
    }
  }).flatten(),
)

// ── leggenda ─────────────────────────────────────────────────────────────────
#let has_rookie = giocatori.any(g => g.flag != "VUOTO" and g.flag.starts-with("R"))
#let has_rfa    = giocatori.any(g => g.flag == "A")
#let has_dpe    = giocatori.any(g => g.flag != "VUOTO" and g.importo_orig != "")
#let has_10d    = giocatori.any(g => g.flag == "D")
#let voce(c, t) = box(inset: (right: 7pt), [#box(width: 7pt, height: 7pt, radius: 2pt, fill: c, baseline: 10%) #text(7pt, fill: _ton_sez, weight: "bold")[#t]])

#if has_rookie or has_rfa or has_dpe or has_10d or fm_nota != "" {
  block(width: 100%, fill: c_sezione, inset: (x: 8pt, y: 5pt))[
    #if giocatori.any(g => g.flag == "R0") { voce(c_r0)[Anno I] }
    #if giocatori.any(g => g.flag == "R1") { voce(c_r1)[Anno II] }
    #if giocatori.any(g => g.flag == "R2") { voce(c_r2)[Anno III] }
    #if giocatori.any(g => g.flag == "R3") { voce(c_r3)[Anno IV] }
    #if has_rfa { voce(c_rfa)[RFA] }
    #if has_dpe { voce(c_dpe)[DPE] }
    #if has_10d { voce(c_10d)[10-day#if fine_10day != "" [ #fine_10day]] }
    #if fm_nota != "" [#text(7pt, fill: _ton_sez_m, weight: "bold")[#fm_nota]]
  ]
}

// ── footer: riquadri ──────────────────────────────────────────────────────────
#let c_footer = if colore_sez != "" { c_sezione } else { c_dark }
#let riquadro(etichetta, valore) = box(width: 100%, height: 31pt, radius: 4pt, fill: _ton_ftr.transparentize(90%), inset: (x: 6pt, y: 5pt),
  stack(spacing: 5pt,
    text(5.8pt, weight: "bold", fill: _ton_ftr_m, tracking: 0.4pt)[#etichetta],
    text(11pt, weight: "bold", fill: _ton_ftr)[#valore]))
#block(width: 100%, fill: c_footer, inset: 8pt)[
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 6pt,
    riquadro([ETÀ MEDIA], eta_media),
    riquadro([TAGLI SENZA IMPATTO], tagli_usati),
    riquadro([CAMBI RUOLO], cambi_usati),
  )
]
