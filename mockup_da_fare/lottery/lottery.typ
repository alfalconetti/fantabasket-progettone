// MOCKUP odds della lottery a fine regular season (Luca, 18/11)
#let d = json(bytes(sys.inputs.at("dati")))
#let scuro = rgb("#14213D")
#let medio = rgb("#23395B")
#let oro = rgb("#E0A21B")
#let grigio = rgb("#5E6B82")
#let bordo = rgb("#DCE3EE")
#let testo = rgb("#111C33")
#set page(width: 640pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 8pt, fill: testo)

#block(width: 100%, fill: gradient.linear(scuro, medio, angle: 0deg), inset: (x: 16pt, y: 14pt))[
  #grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
    stack(spacing: 5pt,
      text(17pt, weight: "bold", fill: white)[Draft #d.anno · le odds della lottery],
      text(8.5pt, fill: white.transparentize(20%))[#d.sotto]),
    box(fill: oro, radius: 4pt, inset: (x: 8pt, y: 5pt), text(8pt, weight: "bold", fill: scuro)[#d.quando]))
]

#let cella(p) = {
  if p == 0 { [] } else {
    let a = calc.min(p / 60, 1)
    box(width: 100%, height: 15pt, fill: oro.transparentize(100% - a * 85%), radius: 2pt,
      align(center + horizon, text(if p >= 10 { 7.5pt } else { 6.8pt }, weight: if p >= 30 { "bold" } else { "regular" },
        fill: if p < 1 { grigio } else { testo })[#if p < 0.1 { "<0,1" } else { str(calc.round(p, digits: 1)).replace(".", ",") }]))
  }
}

#block(width: 100%, inset: (x: 16pt, top: 12pt, bottom: 4pt))[
  #text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[LOTTERY · LE 12 FUORI DAI PLAYOFF, DALL'ULTIMA · % DI OGNI PICK]
  #v(6pt)
  #table(columns: (20pt, 1fr, 34pt) + (27pt,) * 12, stroke: (x, y) => (bottom: 0.4pt + bordo), inset: (x: 2pt, y: 3pt), align: center + horizon,
    table.header(text(6.5pt, fill: grigio)[seed], align(left, text(6.5pt, fill: grigio)[squadra · chi ha la pick]), text(6.5pt, fill: grigio)[W-L],
      ..range(1, 13).map(i => text(6.5pt, weight: "bold", fill: grigio)[#i])),
    ..d.lottery.map(r => (
      text(9pt, weight: "bold")[#r.seed],
      align(left, stack(spacing: 2.5pt,
        [#box(width: 7pt, height: 7pt, radius: 50%, fill: rgb(r.colore)) #h(2pt) #text(8.5pt, weight: "bold")[#r.squadra]],
        if r.di != "" { text(6.5pt, fill: grigio)[pick in mano a #text(weight: "bold", fill: rgb(r.di_colore))[#r.di]] })),
      text(7.5pt, fill: grigio)[#r.wl],
      ..r.odds.map(cella))).flatten())
]

#block(width: 100%, inset: (x: 16pt, top: 12pt, bottom: 4pt))[
  #text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[GIÀ DECISE · DALLA 13ª ALLA 24ª, IN ORDINE INVERSO DELLA CLASSIFICA]
  #v(6pt)
  #grid(columns: (1fr,) * 4, column-gutter: 5pt, row-gutter: 5pt,
    ..d.fisse.map(r => box(width: 100%, radius: 4pt, stroke: 0.6pt + bordo, inset: (x: 6pt, y: 5pt),
      grid(columns: (auto, 1fr), column-gutter: 6pt, align: horizon,
        text(11pt, weight: "bold", fill: medio)[#r.pick],
        stack(spacing: 2.5pt,
          [#box(width: 6pt, height: 6pt, radius: 50%, fill: rgb(r.colore)) #h(1.5pt) #text(7.5pt, weight: "bold")[#r.squadra] #text(6.5pt, fill: grigio)[#r.wl]],
          if r.di != "" { text(6.3pt, fill: grigio)[in mano a #text(weight: "bold", fill: rgb(r.di_colore))[#r.di]] } else { text(6.3pt, fill: grigio)[#r.nota] })))))
]

#block(inset: (x: 16pt, top: 10pt, bottom: 12pt), text(6.8pt, fill: grigio)[#d.note])
