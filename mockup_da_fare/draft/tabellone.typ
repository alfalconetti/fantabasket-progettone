// MOCKUP tabellone del draft (Luca, 18/11; rivisto il 23/11: due colonne da 12, niente tempo, protezioni, firma/diritti)
#let d = json(bytes(sys.inputs.at("dati")))
#let notte = rgb("#0A1128")
#let blu = rgb("#13294B")
#let oro = rgb("#F2B705")
#let grigio = rgb("#8A93A8")
#set page(width: if d.col == 2 { 520pt } else { 640pt }, height: auto, margin: 0pt, fill: notte)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 8pt, fill: white)

// ── testata ──
#block(width: 100%, inset: (x: 22pt, top: 20pt, bottom: 14pt),
  fill: gradient.linear(blu, notte, angle: 90deg))[
  #grid(columns: (1fr, auto), align: (left + bottom, right + bottom),
    stack(spacing: 6pt,
      text(9pt, weight: "bold", fill: oro, tracking: 2pt)[FANTA DRAFT #d.anno],
      text(if d.col == 2 { 24pt } else { 28pt }, weight: "bold", tracking: 1pt)[#upper(d.giro)],
      text(8.5pt, fill: grigio)[#d.sotto]),
    if d.ora != none {
      box(stroke: 1.5pt + oro, radius: 4pt, inset: (x: 12pt, y: 8pt), stack(spacing: 4pt,
        text(7pt, weight: "bold", fill: oro, tracking: 1.5pt)[ON THE CLOCK],
        text(14pt, weight: "bold")[#d.ora.pick · #d.ora.squadra],
        text(7.5pt, fill: grigio)[#d.ora.stato]))
    })
  #v(10pt)
  #line(length: 100%, stroke: 2pt + oro)
]

#let logo(p, dd) = box(width: dd, height: dd, radius: 50%, fill: rgb(p.colore), stroke: 1.5pt + white.transparentize(70%),
  align(center + horizon, text(dd * 0.34, weight: "bold")[#p.sigla]))

#let card(p) = {
  let c = rgb(p.colore)
  let ora = p.stato == "ora"
  let dopo = p.stato == "dopo"
  box(width: 100%, height: 74pt, radius: 4pt, clip: true,
    fill: if ora { gradient.linear(oro.transparentize(55%), blu, angle: 0deg) } else if dopo { white.transparentize(95%) } else { gradient.linear(c.transparentize(45%), blu, angle: 0deg) },
    stroke: if ora { 1.5pt + oro } else { 0.6pt + white.transparentize(85%) },
    {
      // il numero grande in trasparenza
      place(right + top, dx: -6pt, dy: -4pt, text(38pt, weight: "bold", fill: white.transparentize(if dopo { 92% } else { 86% }))[#p.n])
      place(left + top, rect(width: 4pt, height: 74pt, fill: if dopo { c.transparentize(60%) } else { c }))
      pad(left: 12pt, right: 8pt, top: 8pt, grid(columns: (auto, 1fr), column-gutter: 8pt, align: top,
        logo(p, 26pt),
        stack(spacing: 3.5pt,
          text(7pt, weight: "bold", fill: if ora { oro } else { white.transparentize(30%) }, tracking: 1pt)[PICK #p.n],
          text(8pt, weight: "bold", fill: white.transparentize(if dopo { 35% } else { 0% }))[#upper(p.squadra)],
          text(6.3pt, fill: grigio)[GM #p.gm#if p.via != "" [ · via #p.via]],
          if p.prot != "" { text(6.3pt, weight: "bold", fill: oro)[🛡 #p.prot: resta a #p.squadra] },
          if p.sanz != "" { text(6.3pt, weight: "bold", fill: rgb("#FF7A6B"))[#p.sanz] }
          )))
      // in basso: il giocatore
      place(left + bottom, dx: 12pt, dy: -7pt, box(width: 100% - 20pt,
        if p.stato == "fatta" {
          grid(columns: (1fr, auto), align: (left + bottom, right + bottom),
            text(10pt, weight: "bold")[#upper(p.gioc)],
            box(fill: white.transparentize(88%), radius: 3pt, inset: (x: 5pt, y: 3pt), text(8.5pt, weight: "bold")[#p.scala]))
        } else if ora {
          text(9pt, weight: "bold", fill: oro, tracking: 1pt)[ON THE CLOCK]
        } else { text(8pt, fill: grigio)[#p.scala] }))
    })
}

#block(width: 100%, inset: (x: 22pt, top: 8pt, bottom: 6pt))[
  // in verticale (Luca, 18/11): le pick scendono per colonne, 1–12 e 13–24 (o tre da 8)
  #let per = calc.ceil(d.pick.len() / d.col)
  #grid(columns: (1fr,) * d.col, column-gutter: 8pt,
    ..range(d.col).map(k => stack(spacing: 7pt, ..d.pick.slice(k * per, calc.min((k + 1) * per, d.pick.len())).map(card))))
]
#block(inset: (x: 22pt, top: 6pt, bottom: 16pt), text(6.8pt, fill: grigio)[#d.note])
