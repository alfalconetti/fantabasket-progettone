// /player in immagine (v7.7.0, Luca 13/11): sul viola di Yahoo come /partita e /giocatori. Dati da
// shared/giocatore.py (dati_scheda). Testata con foto ESPN (se no le iniziali), nascita, squadra NBA con lo status
// abbreviato, prossima partita; i riquadri (la fantamedia accesa, giallo-arancio); il fantabasket (contratto, ruolo,
// posizioni eleggibili, la nota sui contratti di prima del bot); le 9 categorie a partita; le ultime partite.
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#5F01D1")
#let viola_scuro = rgb("#39007D")
#let viola_medio = rgb("#7B3FE4")
#let lilla = rgb("#EFE7FD")
#let lilla2 = rgb("#F7F3FE")
#let bordo = rgb("#E4DAF7")
#let grigio = rgb("#6B6480")
#let testo = rgb("#1D1630")
#let oro = rgb("#E0A21B")
#set page(width: 520pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: testo)

#let etichetta(t) = text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[#upper(t)]

// ── testata ──
#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 16pt, top: 14pt, bottom: 12pt))[
  #grid(columns: (auto, 1fr), column-gutter: 14pt, align: horizon,
    box(width: 74pt, height: 74pt, radius: 50%, clip: true, fill: lilla, stroke: 2.5pt + white.transparentize(40%),
      // stesse proporzioni di /carriera: foto 520×380 alta 1,2 volte il tondo, centrata, un filo più su
      if d.foto != "" { place(top + left, dx: -24pt, dy: -3.5pt, image(d.foto, height: 89pt, width: 122pt)) }
      else { align(center + horizon, text(24pt, weight: "bold", fill: viola_scuro)[#d.iniziali]) }),
    stack(spacing: 5pt,
      text(18pt, weight: "bold", fill: white)[#d.nome],
      if d.nascita != "" { text(8.5pt, fill: white.transparentize(20%))[#d.nascita] },
      if d.espn {
        [#box(fill: white, radius: 3pt, inset: (x: 5pt, y: 2.5pt), text(8.5pt, weight: "bold", fill: viola_scuro)[#d.nba])
         #if d.status != "" {
           let c = if d.status_k == "out" { rgb("#FF8A7A") } else { rgb("#FFC46B") }
           [#h(4pt) #box(fill: c.transparentize(80%), stroke: 0.6pt + c, radius: 3pt, inset: (x: 4pt, y: 2pt), text(7pt, weight: "bold", fill: c)[#d.status])
            #h(3pt) #text(7.5pt, fill: white.transparentize(15%))[#d.status_det]]
         }]
      } else { text(8pt, style: "italic", fill: white.transparentize(20%))[NBA: non abbinato a ESPN (niente statistiche)] },
      if d.prossima != "" { text(8pt, fill: white.transparentize(15%))[📅 Prossima: #d.prossima] }))
  #v(12pt)
  // il primo riquadro (la fantamedia) acceso: giallo-arancio su viola
  #let riquadro(r, acceso) = box(fill: if acceso { gradient.linear(rgb("#FFD23F"), rgb("#FF9F1C"), angle: 0deg) } else { white.transparentize(88%) },
    radius: 6pt, inset: (x: 9pt, y: 6pt), width: 100%,
    stack(spacing: 3pt, text(6.5pt, weight: "bold", fill: if acceso { viola_scuro.transparentize(20%) } else { white.transparentize(30%) }, tracking: 0.6pt)[#upper(r.t)],
      text(15pt, weight: "bold", fill: if acceso { viola_scuro } else { white })[#r.v],
      text(6.5pt, fill: if acceso { viola_scuro.transparentize(25%) } else { white.transparentize(30%) })[#r.s]))
  #grid(columns: (1fr,) * calc.max(d.riquadri.len(), 4), column-gutter: 6pt,
    ..d.riquadri.enumerate().map(((i, r)) => riquadro(r, i == 0)))
]

// ── fantabasket ──
#let f = d.fanta
#let cf = rgb(f.colore)
#block(width: 100%, inset: (x: 16pt, top: 12pt, bottom: 4pt))[
  #etichetta("Fantabasket")
  #v(5pt)
  #block(width: 100%, radius: 6pt, stroke: 0.8pt + if f.tipo == "diritti" { cf } else { bordo }, clip: true,
    fill: if f.tipo == "fa" { rgb("#EEF8F2") } else { white })[
    #block(inset: (x: 10pt, y: 7pt), width: 100%, stroke: (left: 5pt + cf))[
      #grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
        stack(spacing: 4pt,
          text(11pt, weight: "bold", fill: cf)[#f.squadra],
          text(8pt)[#f.contratto]),
        stack(spacing: 4pt,
          if f.tipo == "firmato" {
            align(right)[#text(7pt, fill: grigio)[ruolo] #if f.ruolo != "" {
              box(fill: viola, radius: 3pt, inset: (x: 5pt, y: 2pt), text(8pt, weight: "bold", fill: white)[#f.ruolo])
            } else { text(7.5pt, style: "italic", fill: grigio)[#f.ruolo_txt] }]
          },
          align(right)[#text(7pt, fill: grigio)[eleggibile] #if d.pos.len() == 0 { text(7.5pt, style: "italic", fill: grigio)[non registrate] } else {
            for p in ("PG", "SG", "SF", "PF", "C") {
              let si = p in d.pos
              box(fill: if si { lilla } else { white }, stroke: 0.5pt + if si { viola_medio } else { bordo }, radius: 2pt, inset: (x: 3pt, y: 1.5pt),
                text(7pt, weight: "bold", fill: if si { viola } else { rgb("#C9C2D9") })[#p])
              h(1.5pt)
            }
          }]))
      #if f.nota != "" { v(5pt); text(6.8pt, style: "italic", fill: grigio)[#f.nota] }
    ]
  ]
]

// ── le 9 categorie ──
#if d.medie.len() > 0 {
  block(width: 100%, inset: (x: 16pt, top: 10pt, bottom: 4pt))[
    #etichetta("Stagione " + d.stagione + " · le 9 categorie, a partita")
    #v(5pt)
    #grid(columns: (1fr,) * d.medie.len(), column-gutter: 3.5pt,
      ..d.medie.map(m => box(fill: lilla2, radius: 4pt, inset: (y: 5pt), width: 100%, align(center, stack(spacing: 3pt,
        text(12pt, weight: "bold")[#m.v], text(6.5pt, fill: grigio)[#m.t])))))
    #v(5pt)
    #text(7.5pt, fill: grigio)[#d.sotto_medie]
  ]
} else if d.nota_stagione != "" {
  block(width: 100%, inset: (x: 16pt, top: 10pt, bottom: 4pt))[
    #etichetta("Stagione " + d.stagione) #v(5pt) #text(8pt, style: "italic", fill: grigio)[#d.nota_stagione]]
}

// ── ultime partite ──
#if d.ultime.len() > 0 {
  block(width: 100%, inset: (x: 16pt, top: 10pt, bottom: 6pt))[
    #etichetta("Ultime partite")
    #v(4pt)
    #let fps = d.ultime.filter(u => u.fp != none).map(u => u.fp)
    #let mx = if fps.len() > 0 { calc.max(..fps, 1) } else { 1 }
    #table(columns: (36pt, 46pt, 1fr, 120pt), stroke: (x, y) => (bottom: 0.5pt + bordo), inset: (x: 4pt, y: 5pt),
      align: horizon,
      ..d.ultime.map(u => (
        text(8pt, fill: grigio)[#u.data], text(8pt, weight: "bold")[#u.avv],
        if u.fp == none { text(8pt, style: "italic", fill: grigio)[#u.riga] } else { text(7.5pt)[#u.riga] },
        if u.fp == none { [] } else {
          box(grid(columns: (auto, auto), column-gutter: 4pt, align: horizon,
            box(width: calc.max(80pt * u.fp / mx, 1pt), height: 7pt, radius: 2pt, fill: if u.fp == mx { oro } else { viola_medio }),
            text(8.5pt, weight: "bold")[#u.fpt]))
        })).flatten())
  ]
}
#block(inset: (x: 16pt, top: 4pt, bottom: 12pt), text(6.5pt, fill: grigio)[Dati NBA: tabellini, roster e infortunati di ESPN · stagione passata: Basketball-Reference])
