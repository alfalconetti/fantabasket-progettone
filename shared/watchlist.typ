// Il report delle 9:30 della watchlist (v7.8.0, mockup approvato da Luca il 14/11): bot principale,
// handlers/watchlist.dati_report. Viola Yahoo come /partita e /giocatori.
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#5F01D1")
#let viola_scuro = rgb("#39007D")
#let viola_medio = rgb("#7B3FE4")
#let lilla = rgb("#EFE7FD")
#let lilla2 = rgb("#F7F3FE")
#let bordo = rgb("#E4DAF7")
#let grigio = rgb("#6B6480")
#let testo = rgb("#1D1630")
#let verde = rgb("#1B8A4B")
#let rosso = rgb("#C0392B")
#let oro = rgb("#E0A21B")
#set page(width: 560pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: testo)

#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 16pt, y: 12pt))[
  #grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
    stack(spacing: 4pt, text(16pt, weight: "bold", fill: white)[👁 La tua watchlist],
      text(8.5pt, fill: white.transparentize(20%))[#d.sotto]),
    box(fill: gradient.linear(rgb("#FFD23F"), rgb("#FF9F1C"), angle: 0deg), radius: 6pt, inset: (x: 10pt, y: 6pt),
      stack(spacing: 2pt, text(6.5pt, weight: "bold", fill: viola_scuro.transparentize(20%), tracking: 0.6pt)[MIGLIORE DELLA NOTTE],
        text(12pt, weight: "bold", fill: viola_scuro)[#d.migliore])))
]

#let foto(r) = box(width: 30pt, height: 30pt, radius: 50%, clip: true, fill: lilla,
  if r.foto != "" { align(center + bottom, image(r.foto, width: 42pt)) }
  else { align(center + horizon, text(10pt, weight: "bold", fill: grigio)[#r.iniziali]) })
#let stato(r) = {
  let c = rgb(r.colore)
  if r.tipo == "fa" { box(fill: rgb("#E3F4EA"), radius: 3pt, inset: (x: 4pt, y: 2pt), text(7pt, weight: "bold", fill: verde)[FA]) }
  else if r.tipo == "diritti" { box(stroke: 0.7pt + c, radius: 3pt, inset: (x: 4pt, y: 2pt), text(7pt, weight: "bold", fill: c)[diritti · #r.squadra]) }
  else { box(fill: c, radius: 3pt, inset: (x: 4pt, y: 2pt), text(7pt, weight: "bold", fill: white)[#r.squadra]) }
}

#block(inset: (x: 12pt, top: 8pt, bottom: 4pt))[
  #text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[HANNO GIOCATO]
  #v(4pt)
  #table(columns: (36pt, 1fr, 60pt, 70pt), inset: (x: 4pt, y: 4pt), align: horizon,
    stroke: (x, y) => (bottom: 0.5pt + bordo),
    fill: (x, y) => if calc.rem(y, 2) == 1 { lilla2 } else { white },
    ..d.giocato.map(r => (
      foto(r),
      [#text(10pt, weight: "bold")[#r.nome] #h(3pt) #stato(r) #if r.inf != "" [ #box(stroke: 0.6pt + rgb("#E67E22"), radius: 2pt, inset: (x: 3pt, y: 1pt), text(6.5pt, weight: "bold", fill: rgb("#E67E22"))[#r.inf])] \
       #text(7.5pt, fill: grigio)[#r.partita · #r.riga]],
      align(right, stack(spacing: 2pt, text(13pt, weight: "bold", fill: if r.top { oro.darken(20%) } else { viola })[#r.fp],
        text(6.5pt, fill: grigio)[media #r.media])),
      if r.delta == "" { [] } else {
        align(center, box(fill: (if r.delta_v >= 0 { verde } else { rosso }).transparentize(88%), radius: 4pt, inset: (x: 6pt, y: 4pt),
          text(9pt, weight: "bold", fill: if r.delta_v >= 0 { verde } else { rosso })[#if r.delta_v >= 0 [▲] else [▼] #r.delta]))
      },
    )).flatten())
]
#if d.non_giocato.len() > 0 {
  block(inset: (x: 16pt, top: 6pt, bottom: 4pt))[
    #text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[NON HANNO GIOCATO]
    #v(4pt)
    #text(8pt)[#d.non_giocato.join("  ·  ")]
  ]
}
#block(inset: (x: 16pt, top: 8pt, bottom: 12pt), text(6.5pt, fill: grigio)[Fantapunti della notte dai tabellini ESPN · ▲▼ rispetto alla fantamedia della stagione · oro: sopra la soglia della grande prestazione · /watchlist per tutta la lista, /unwatch per togliere, /watch_soglia per la soglia])
