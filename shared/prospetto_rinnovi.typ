// Prospetto dei rinnovi (v7.33.0, mockup approvato da Luca il 26/11). Dati da shared/prospetto_rinnovi.py (dati).
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#3B0A8C")
#let viola2 = rgb("#6A11CB")
#let grigio = rgb("#6B7280")
#let bordo = rgb("#E5E7EB")
#let oro = rgb("#E0A21B")
#let verde = rgb("#047857")
#let rosso = rgb("#B91C1C")
#set page(width: 600pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 8pt, fill: rgb("#111827"))

#if d.striscia != "" {
  block(width: 100%, fill: if d.modo == "senza" { rgb("#4B5563") } else { rgb("#C2410C") }, inset: (x: 14pt, y: 5pt),
    align(center, text(8pt, weight: "bold", fill: white)[#d.striscia]))
}
#block(width: 100%, fill: gradient.linear(viola, viola2, angle: 0deg), inset: (x: 18pt, y: 16pt))[
  #text(16pt, weight: "bold", fill: white)[#d.nome] \
  #v(4pt)
  #text(8.5pt, fill: white.transparentize(20%))[Prospetto rinnovi · #d.periodo]
  #v(10pt)
  #grid(columns: (1fr,) * d.riquadri.len(), column-gutter: 6pt,
    ..d.riquadri.map(r => box(width: 100%, fill: white.transparentize(88%), radius: 5pt, inset: (x: 8pt, y: 6pt), stack(spacing: 3pt,
      text(6.5pt, weight: "bold", fill: white.transparentize(25%), tracking: 0.6pt)[#upper(r.t)],
      text(13pt, weight: "bold", fill: white)[#r.v],
      text(6.5pt, fill: white.transparentize(30%))[#r.s]))))
]

#let intest(t) = text(6.5pt, weight: "bold", fill: grigio, tracking: 0.6pt)[#upper(t)]
#let opz(o) = if o == none { box(width: 100%, fill: rgb("#F3F4F6"), radius: 4pt, inset: (x: 6pt, y: 9pt),
  align(center, text(7pt, fill: grigio, style: "italic")[da stimare])) } else { box(width: 100%, fill: if o.tab { oro.transparentize(85%) } else { viola.transparentize(93%) }, radius: 4pt,
  inset: (x: 6pt, y: 5pt), align(center, stack(spacing: 2.5pt,
    text(12pt, weight: "bold", fill: viola)[#o.imp#text(8pt)[M]],
    text(6.3pt, fill: grigio)[#o.conto],
    text(6.3pt, weight: "bold", fill: if o.x3 { rosso } else { verde })[#if o.x3 [solo x3] else [x2 o x3]]
      + if o.tab { text(6.3pt, weight: "bold", fill: oro)[ · minimo] }))) }

#let riga(g) = block(width: 100%, inset: (x: 18pt, y: 8pt), stroke: (bottom: 0.5pt + bordo),
  grid(columns: (1fr, 72pt, 84pt, 84pt), column-gutter: 8pt, align: (left + horizon, center + horizon, center, center),
    stack(spacing: 3.5pt,
      text(10pt, weight: "bold")[#g.nome],
      text(7pt, fill: grigio)[#g.motivo],
      if g.doncic != none { box(fill: rgb("#FEF3C7"), radius: 3pt, inset: (x: 5pt, y: 3pt),
        text(6.8pt, fill: rgb("#92400E"))[*Prima la fine della rookie scale:* #g.doncic]) }),
    stack(spacing: 3pt,
      text(11pt, weight: "bold")[#g.base],
      if g.min != none { text(6.5pt, fill: grigio)[fm #if g.fm != none [#g.fm] else [—] → min #g.min] }),
    opz(g.q), opz(g.m)))

#block(width: 100%, inset: (x: 18pt, top: 10pt, bottom: 5pt), stroke: (bottom: 1pt + bordo),
  grid(columns: (1fr, 72pt, 84pt, 84pt), column-gutter: 8pt, align: (left, center, center, center),
    intest("Rinnovabili"), intest("Base · minimo"), intest("Da ¼"), intest("Da ½")))
#for g in d.giocatori { riga(g) }
#if d.giocatori.len() == 0 {
  block(width: 100%, inset: (x: 18pt, y: 14pt), text(9pt, fill: grigio)[Nessun giocatore rinnovabile alla prossima offseason.])
}

#if d.rookie.len() > 0 {
  block(width: 100%, fill: rgb("#F9FAFB"), inset: (x: 18pt, y: 8pt), stroke: (bottom: 0.5pt + bordo), stack(spacing: 5pt,
    text(8.5pt, weight: "bold")[Rinnovi rookie a fine II anno #text(7pt, weight: "regular", fill: grigio)[ · illimitati, non contano nei 2]],
    ..d.rookie.map(r => grid(columns: (1fr, auto), text(8pt)[*#r.nome* #text(fill: grigio)[#r.come]], text(9pt, weight: "bold", fill: viola)[#r.nuovo]))))
}
#block(width: 100%, inset: (x: 18pt, y: 10pt), text(6.8pt, fill: grigio, style: "italic")[#d.note])
