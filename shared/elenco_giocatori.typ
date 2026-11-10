// /giocatori (v7.5.0): fino a 25 giocatori in un'immagine, con la foto ESPN. Dati da shared/elenco_giocatori.py.
#let dati = json(bytes(sys.inputs.dati))
// i colori di partita.typ di loucabot: il viola di Yahoo
#let viola = rgb("#5F01D1")
#let viola_scuro = rgb("#39007D")
#let viola_medio = rgb("#7B3FE4")
#let lilla = rgb("#EFE7FD")
#let lilla2 = rgb("#F7F3FE")
#let bordo = rgb("#D6C8F5")
#let grigio = rgb("#6B6480")
#let rosso = rgb("#C0392B")
#let verde = rgb("#1B8A4B")
#let inchiostro = rgb("#1D1630")
#set page(width: 600pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: inchiostro)

#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 16pt, y: 11pt))[
  #grid(columns: (1fr, auto), align: (left + horizon, right + bottom),
    [#text(16pt, weight: "bold", fill: white)[Giocatori #text(11pt, weight: "regular")[· #dati.stagione]] \
     #text(8.5pt, fill: white.transparentize(25%))[#dati.filtri]],
    text(8.5pt, fill: white.transparentize(25%))[#dati.da–#dati.a di #dati.tot #if dati.pagine > 1 [\ immagine #dati.pagina/#dati.pagine]])
]

#let foto(r) = box(width: 30pt, height: 30pt, radius: 50%, clip: true, fill: lilla, stroke: 1pt + bordo,
  if r.foto != none { align(center + bottom, image(r.foto, width: 42pt)) }
  else { align(center + horizon, text(11pt, weight: "bold", fill: grigio)[#r.iniziali]) })

#let stato(r) = {
  let (bg, fg) = if r.stato == "firmati" { (rgb(r.colore), white) } else if r.stato == "diritti" { (white, rgb(r.colore)) } else { (rgb("#E3F4EA"), verde) }
  box(fill: bg, stroke: if r.stato == "diritti" { 0.8pt + rgb(r.colore) } else { none }, radius: 3pt, inset: (x: 5pt, y: 2.5pt),
    text(7.5pt, weight: "bold", fill: fg)[#r.squadra])
}

#block(inset: (x: 10pt, top: 6pt, bottom: 6pt))[
#table(
  columns: (18pt, 36pt, 1fr, 34pt, 84pt, 150pt),
  inset: (x: 3pt, y: 3pt),
  align: (right + horizon, center + horizon, left + horizon, center + horizon, right + horizon, left + horizon),
  fill: (x, y) => if calc.rem(y, 2) == 1 { lilla2 } else { white },
  stroke: (x, y) => (bottom: 0.5pt + bordo),
  ..dati.righe.map(r => (
    text(fill: grigio, 8pt)[#r.n],
    foto(r),
    [#text(10pt, weight: "bold")[#r.nome]#if r.inf != none [ #text(7.5pt, weight: "bold", fill: rosso)[🩹 #r.inf]] \
     #text(7.5pt, fill: grigio)[#r.pos#if r.dettagli != "" [ · #r.dettagli]]],
    text(9pt, weight: "bold", fill: viola_medio)[#r.nba],
    [#text(12pt, weight: "bold", fill: viola)[#r.media] \ #text(7pt, fill: grigio)[#r.sotto_media]],
    [#stato(r) \ #v(1.5pt) #text(7.5pt, fill: grigio)[#r.contratto]],
  )).flatten()
)
#v(3pt)
#text(6.5pt, fill: grigio)[#dati.fonte]
]
