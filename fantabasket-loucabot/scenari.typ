// Scenari di fine regular season (v7.37.0, mockup approvato da Luca il 26/11): una conference o la lottery
#let d = json(bytes(sys.inputs.at("dati")))
#let grigio = rgb("#6B7280")
#let bordo = rgb("#E5E7EB")
#let verde = rgb("#047857")
#let rosso = rgb("#B91C1C")
#let oro = rgb("#B45309")
#let viola = rgb("#3B0A8C")
#let blu = rgb("#0F3D5E")
#let lottery = d.tipo == "lottery"
#let (c1, c2) = if lottery { (blu, rgb("#1F6FA8")) } else { (viola, rgb("#6A11CB")) }
#set page(width: 640pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 8pt, fill: rgb("#111827"))

#block(width: 100%, fill: gradient.linear(c1, c2, angle: 0deg), inset: (x: 18pt, y: 14pt))[
  #grid(columns: (1fr, auto), align: (left + horizon, right + horizon), column-gutter: 10pt,
    stack(spacing: 5pt, text(16pt, weight: "bold", fill: white)[#if lottery [Corsa alla lottery] else [Corsa ai playoff · Conference #d.conf]],
      text(8pt, fill: white.transparentize(20%))[#d.sotto]),
    box(fill: white.transparentize(85%), radius: 5pt, inset: (x: 9pt, y: 6pt),
      stack(spacing: 2pt, text(6.5pt, weight: "bold", fill: white.transparentize(25%), tracking: 0.6pt)[#if d.mancano == 1 [MANCA] else [MANCANO]],
        text(15pt, weight: "bold", fill: white)[#d.mancano #if d.mancano == 1 [giornata] else [giornate]])))
]
#let intest(t) = text(6.3pt, weight: "bold", fill: grigio, tracking: 0.5pt)[#upper(t)]
#let serve(r, sx) = if r.serve != "" { pad(left: sx, text(7pt, fill: grigio)[→ #r.serve]) }

#if not lottery {
  let stato(s) = {
    let (c, t) = if s == "bye" { (viola, "BYE ASSICURATO") } else if s == "dentro" { (verde, "DENTRO") }
      else if s == "fuori" { (rosso, "ELIMINATA") } else { (oro, "IN CORSA") }
    box(fill: c.transparentize(88%), radius: 3pt, inset: (x: 5pt, y: 2.5pt), text(6.5pt, weight: "bold", fill: c)[#t])
  }
  let barra(p, c) = box(width: 42pt, height: 6pt, fill: bordo, radius: 3pt,
    place(left, box(width: p / 100 * 42pt, height: 6pt, fill: c, radius: 3pt)))
  let colonne = (16pt, 1fr, 38pt, 46pt, 70pt, 70pt, 66pt)
  block(width: 100%, inset: (x: 18pt, top: 10pt, bottom: 5pt), stroke: (bottom: 1pt + bordo),
    grid(columns: colonne, column-gutter: 6pt, align: (center, left, center, center, left, left, center),
      intest("#"), intest("Squadra"), intest("W-L"), intest("Seed poss."), intest("Playoff"), intest("Bye (1-2)"), intest("Stato")))
  for (i, r) in d.righe.enumerate() {
    let linea = if i == 6 { (top: 1.6pt + rosso.transparentize(40%)) } else { (:) }
    block(width: 100%, inset: (x: 18pt, y: 5pt), stroke: (bottom: 0.5pt + bordo, ..linea),
      fill: if i < 2 { viola.transparentize(96%) } else if i < 6 { verde.transparentize(97%) } else { white },
      stack(spacing: 3pt,
        grid(columns: colonne, column-gutter: 6pt,
          align: (center + horizon, left + horizon, center + horizon, center + horizon, left + horizon, left + horizon, center + horizon),
          text(9pt, weight: "bold", fill: grigio)[#(i + 1)],
          text(9.5pt, weight: "bold")[#r.nome],
          text(9pt)[#r.wl],
          text(9pt, weight: "bold")[#r.seed],
          [#barra(r.po, verde) #h(3pt) #text(7.5pt, weight: "bold")[#r.po%]],
          [#barra(r.bye, viola) #h(3pt) #text(7.5pt, weight: "bold")[#r.bye%]],
          stato(r.stato)),
        serve(r, 22pt)))
  }
  block(width: 100%, inset: (x: 18pt, y: 4pt), text(6.5pt, fill: rosso)[La linea rossa: sopra le prime 6, ai playoff. Le prime 2 saltano il primo turno.])
} else {
  let cella(p) = box(width: 100%, height: 15pt, radius: 2pt,
    fill: if p == 0 { white } else { blu.transparentize(100% - calc.min(p, 100) * 0.9%) },
    align(center + horizon, text(6.8pt, weight: "bold", fill: if p >= 45 { white } else if p == 0 { bordo } else { blu })[#if p == 0 [·] else [#p]]))
  let colonne = (1fr, 34pt, 40pt, ..((18pt,) * 6), 46pt, 46pt)
  block(width: 100%, inset: (x: 18pt, top: 10pt, bottom: 5pt), stroke: (bottom: 1pt + bordo),
    grid(columns: colonne, column-gutter: 4pt, align: center,
      align(left, intest("Squadra")), intest("W-L"), intest("Fuori PO"),
      ..range(1, 7).map(k => intest(str(k) + "ª")), intest("1ª scelta"), intest("Top 4")))
  for r in d.righe {
    block(width: 100%, inset: (x: 18pt, y: 4pt), stroke: (bottom: 0.5pt + bordo), stack(spacing: 3pt,
      grid(columns: colonne, column-gutter: 4pt, align: (left + horizon, ..((center + horizon,) * 10)),
        text(9.5pt, weight: "bold")[#r.nome #text(7pt, weight: "regular", fill: grigio)[#r.conf]],
        text(9pt)[#r.wl], text(8pt, weight: "bold", fill: if r.fuori == 100 { grigio } else { oro })[#r.fuori%],
        ..r.posti.map(cella),
        text(9pt, weight: "bold", fill: blu)[#r.prima%], text(8.5pt, weight: "bold")[#r.top4%]),
      serve(r, 4pt)))
  }
  block(width: 100%, inset: (x: 18pt, y: 5pt), text(6.5pt, fill: grigio)[Posto in lottery: 1ª = il record peggiore della lega tra chi non va ai playoff (le odds più alte). Nelle caselle la probabilità di finire in quel posto (i primi 6 su 12); «1ª scelta» e «Top 4»: le probabilità di prendere la scelta 1 o una delle prime 4 all'estrazione, con le odds della lottery.])
}

#if d.chiave.len() > 0 {
  block(width: 100%, fill: rgb("#F9FAFB"), inset: (x: 18pt, y: 10pt), stroke: (top: 0.5pt + bordo))[
    #text(8.5pt, weight: "bold")[#if lottery [Partite chiave per la lottery · G#d.prossima] else [Partite chiave della G#d.prossima]]
    #h(6pt) #text(7pt, fill: grigio)[#if lottery [quanto sposta le probabilità della 1ª scelta] else [quanto sposta le probabilità di playoff]]
    #v(6pt)
    #for k in d.chiave {
      block(inset: (y: 3pt), grid(columns: (1fr, auto), align: (left, right), column-gutter: 8pt,
        text(8pt)[*#k.partita* #text(fill: grigio)[· #k.dice]],
        text(7.5pt, weight: "bold", fill: oro)[#k.testo_peso]))
    }
  ]
}
#block(width: 100%, inset: (x: 18pt, y: 10pt), text(6.8pt, fill: grigio, style: "italic")[#d.note])
