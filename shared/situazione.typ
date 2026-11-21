// /rendimento_situazione (v7.20.0, mockup approvato da Luca il 21/11): tabella a doppia entrata squadra × dove era.
// Dati da shared/situazione.py (dati).
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#3B0A8C")
#let viola2 = rgb("#6A11CB")
#let grigio = rgb("#6B7280")
#let bordo = rgb("#E5E7EB")
#let oro = rgb("#E0A21B")
#set page(width: 560pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 8pt, fill: rgb("#111827"))
// klra (v7.20.1): filigrana «NON UFFICIALE» e striscia rossa in cima, solo se nei dati (come live.typ)
#let _filigrana = d.at("filigrana", default: "")
#set page(foreground: if _filigrana != "" {
  layout(sz => {
    let n = calc.max(1, calc.floor(sz.height / 450pt))
    for i in range(n) { place(center + horizon, dy: sz.height * ((i + 0.5) / n - 0.5),
      rotate(-22deg, text(50pt, weight: "bold", fill: rgb("#C0392B").transparentize(84%))[#_filigrana])) }
  })
})
#if d.at("striscia", default: "") != "" {
  block(width: 100%, fill: rgb("#C0392B"), inset: (x: 14pt, y: 6pt), align(center, text(9pt, weight: "bold", fill: white)[#d.striscia]))
}

#block(width: 100%, fill: gradient.linear(viola, viola2, angle: 0deg), inset: (x: 18pt, y: 16pt))[
  #text(16pt, weight: "bold", fill: white)[#d.nome] \
  #v(4pt)
  #text(8.5pt, fill: white.transparentize(20%))[Media per situazione · #d.periodo]
  #v(10pt)
  #grid(columns: (1fr,) * d.riquadri.len(), column-gutter: 6pt,
    ..d.riquadri.map(r => box(width: 100%, fill: white.transparentize(88%), radius: 5pt, inset: (x: 8pt, y: 6pt), stack(spacing: 3pt,
      text(6.5pt, weight: "bold", fill: white.transparentize(25%), tracking: 0.6pt)[#upper(r.t)],
      text(13pt, weight: "bold", fill: white)[#r.v],
      text(6.5pt, fill: white.transparentize(30%))[#r.s]))))
]

#let cella(c, migliore: false, totale: false) = {
  if c == none { align(center + horizon, text(9pt, fill: bordo)[—]) }
  else {
    box(width: 100%, inset: (y: 3pt), align(center, stack(spacing: 2.5pt,
      text(if totale { 11pt } else { 10.5pt }, weight: "bold", fill: if migliore { rgb("#9A6A00") } else { rgb("#111827") })[#c.media],
      text(6.5pt, fill: grigio)[#c.g #if c.g == 1 [partita] else [partite]])))
  }
}

#block(width: 100%, inset: (x: 18pt, top: 14pt, bottom: 6pt))[
  #table(columns: (1.5fr, 1fr, 1fr, 1fr, 1fr), stroke: (x, y) => (bottom: 0.5pt + bordo, left: if x == 4 { 0.8pt + bordo } else { none }),
    inset: (x: 4pt, y: 5pt), align: (left + horizon, center, center, center, center),
    fill: (x, y) => if y == d.righe.len() + 1 { rgb("#F5F3FF") } else if x == 4 { rgb("#FAFAFA") } else { white },
    table.header(
      text(6.5pt, weight: "bold", fill: grigio, tracking: 0.6pt)[SQUADRA],
      ..d.colonne.map(c => text(6.5pt, weight: "bold", fill: grigio, tracking: 0.6pt)[#upper(c)]),
      text(6.5pt, weight: "bold", fill: grigio, tracking: 0.6pt)[TOTALE]),
    ..d.righe.map(r => (
      stack(spacing: 2.5pt,
        [#box(width: 7pt, height: 7pt, radius: 50%, fill: rgb(r.colore)) #h(2pt) #text(8.5pt, weight: "bold")[#r.nome]],
        text(6.3pt, fill: grigio)[#r.quando]),
      ..r.celle.map(c => cella(c, migliore: c != none and c.at("migliore", default: false))),
      cella(r.totale, totale: true))).flatten(),
    text(8.5pt, weight: "bold")[Totale],
    ..d.totali.map(c => cella(c, totale: true)),
    cella(d.totale, totale: true))
]
#block(inset: (x: 18pt, top: 6pt, bottom: 14pt), text(6.8pt, fill: grigio)[#d.nota])
