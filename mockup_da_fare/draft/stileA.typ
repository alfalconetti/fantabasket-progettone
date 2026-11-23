// MOCKUP draft, stile A: tracker chiaro a righe (tipo ESPN), due colonne da 12
#let d = json(bytes(sys.inputs.at("dati")))
#let ink = rgb("#111827")
#let grigio = rgb("#6B7280")
#let riga = rgb("#E5E7EB")
#let rosso = rgb("#DC2626")
#let oro = rgb("#B45309")
#set page(width: 620pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 8pt, fill: ink)
#block(width: 100%, fill: ink, inset: (x: 20pt, top: 16pt, bottom: 14pt))[
  #grid(columns: (1fr, auto), align: (left + bottom, right + bottom),
    stack(spacing: 5pt, text(8pt, weight: "bold", fill: rgb("#FBBF24"), tracking: 2pt)[FANTA DRAFT #d.anno],
      text(22pt, weight: "bold", fill: white)[#d.giro], text(8pt, fill: rgb("#9CA3AF"))[#d.sotto]),
    if d.ora != none { box(fill: rgb("#FBBF24"), radius: 3pt, inset: (x: 10pt, y: 7pt), stack(spacing: 3pt,
      text(6.5pt, weight: "bold", tracking: 1.5pt)[ON THE CLOCK], text(12pt, weight: "bold")[#d.ora.pick · #d.ora.squadra],
      text(7pt)[#d.ora.stato])) })
]
#let r(p) = {
  let c = rgb(p.colore)
  let ora = p.stato == "ora"
  block(width: 100%, height: 40pt, fill: if ora { rgb("#FEF3C7") } else { white }, stroke: (bottom: 0.6pt + riga),
    grid(columns: (4pt, 30pt, 22pt, 1fr, auto), align: horizon, column-gutter: 0pt,
      rect(width: 4pt, height: 40pt, fill: c),
      align(center, text(15pt, weight: "bold", fill: if p.stato == "dopo" { grigio } else { ink })[#p.n]),
      box(width: 18pt, height: 18pt, radius: 50%, fill: c, align(center + horizon, text(6pt, weight: "bold", fill: white)[#p.sigla])),
      pad(left: 6pt, stack(spacing: 2.5pt,
        if p.stato == "fatta" { text(9.5pt, weight: "bold")[#p.gioc] } else if ora { text(9pt, weight: "bold", fill: oro)[On the clock] } else { text(8.5pt, fill: grigio)[—] },
        text(6.8pt, fill: grigio)[#p.squadra · #p.gm#if p.via != "" [ · via #p.via]#if p.sanz != "" [ · #text(fill: rosso, weight: "bold")[#p.sanz]]#if p.prot != "" [ · #text(fill: oro, weight: "bold")[🛡 #p.prot]]])),
      pad(right: 8pt, if p.stato == "fatta" { box(fill: rgb("#ECFDF5"), stroke: 0.6pt + rgb("#10B981"), radius: 3pt, inset: (x: 5pt, y: 3pt),
        text(8pt, weight: "bold", fill: rgb("#047857"))[#p.scala]) } else { text(7.5pt, fill: grigio)[#p.scala] })))
}
#block(inset: (x: 16pt, top: 10pt, bottom: 6pt), grid(columns: (1fr, 1fr), column-gutter: 14pt,
  stack(..d.pick.slice(0, 12).map(r)), stack(..d.pick.slice(12).map(r))))
#block(inset: (x: 20pt, top: 6pt, bottom: 14pt), text(6.5pt, fill: grigio)[#d.note])
