// MOCKUP draft, stile B: «manifesto» elegante su carta, serif, due colonne da 12
#let d = json(bytes(sys.inputs.at("dati")))
#let carta = rgb("#F5EFE3")
#let ink = rgb("#1F1A14")
#let grigio = rgb("#7A6F60")
#let bordeaux = rgb("#7F1D1D")
#let oro = rgb("#A16207")
#set page(width: 600pt, height: auto, margin: 0pt, fill: carta)
#set block(spacing: 0pt)
#set text(font: "Liberation Serif", size: 8.5pt, fill: ink)
#block(width: 100%, inset: (x: 26pt, top: 22pt, bottom: 10pt))[
  #align(center, stack(spacing: 6pt,
    text(8pt, tracking: 4pt, fill: grigio)[FANTABASKET · DRAFT #d.anno],
    text(30pt, weight: "bold", style: "italic")[#d.giro],
    text(8pt, fill: grigio, style: "italic")[#d.sotto#if d.ora != none [ · in attesa: #text(fill: bordeaux, weight: "bold")[#d.ora.pick, #d.ora.squadra] (#d.ora.stato)]]))
  #v(10pt) #line(length: 100%, stroke: 1.2pt + ink) #v(2pt) #line(length: 100%, stroke: 0.4pt + ink)
]
#let r(p) = {
  let c = rgb(p.colore)
  let ora = p.stato == "ora"
  block(width: 100%, inset: (y: 5.5pt), stroke: (bottom: 0.4pt + grigio.transparentize(60%)),
    grid(columns: (26pt, 1fr, auto), align: (right + horizon, left + horizon, right + horizon), column-gutter: 8pt,
      text(17pt, weight: "bold", fill: if p.stato == "dopo" { grigio.transparentize(40%) } else { bordeaux })[#p.n],
      stack(spacing: 3pt,
        if p.stato == "fatta" { text(11pt, weight: "bold")[#p.gioc] } else if ora { text(10pt, style: "italic", fill: bordeaux)[sta scegliendo…] } else { text(9pt, fill: grigio)[ ] },
        text(7.2pt, fill: grigio)[#box(width: 6pt, height: 6pt, radius: 50%, fill: c) #smallcaps(p.squadra) · #p.gm#if p.via != "" [, via #p.via]#if p.sanz != "" [ · #text(fill: bordeaux)[#p.sanz]]#if p.prot != "" [ · #text(fill: oro)[#p.prot]]]),
      if p.stato == "fatta" { text(9pt, weight: "bold", style: "italic", fill: oro)[#p.scala] } else { text(7.5pt, fill: grigio, style: "italic")[#p.scala] }))
}
#block(inset: (x: 26pt, top: 4pt, bottom: 8pt), grid(columns: (1fr, 1fr), column-gutter: 22pt,
  stack(..d.pick.slice(0, 12).map(r)), stack(..d.pick.slice(12).map(r))))
#block(inset: (x: 26pt, top: 4pt, bottom: 18pt), align(center, text(6.8pt, fill: grigio, style: "italic")[#d.note]))
