// /playoff: il tabellone dei playoff. Mockup approvato da Luca il 14/11 (a piramide, sul giallo), collegato ai dati
// nella v7.10.0 (playoff.dati_tabellone); v7.12.0 (Luca, 15/11): più leggibile su Telegram (pagina più stretta, scritte
// più grandi, primo turno a due colonne con la 1ª e la 2ª che aspettano nella loro semifinale, gare senza «in casa»)
// e la finale con le due squadre, le gare e la campione. Dati di esempio in docs/playoff_esempio.json; per vederlo:
//   typst compile --input dati="$(cat docs/playoff_esempio.json)" playoff.typ playoff.png
// La prima conference di divisions.json sopra che scende verso la finale, la finale al centro, l'altra sotto che sale.
#let d = json(bytes(sys.inputs.at("dati")))
#let scuro = rgb("#2A1A00")
#let marrone = rgb("#6B4A00")
#let giallo1 = rgb("#FFD23F")
#let giallo2 = rgb("#FF9F1C")
#let crema = rgb("#FFF8E1")
#let crema2 = rgb("#FFFDF5")
#let bordo = rgb("#F0D48A")
#let grigio = rgb("#8A7A5A")
#let verde = rgb("#1B8A4B")
#let rosso = rgb("#C62828")
#set page(width: 560pt, height: auto, margin: 0pt, fill: crema2)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 11pt, fill: scuro)

#let stemma(t, dd: 18pt) = box(width: dd, height: dd, radius: 50%, clip: true, fill: rgb(t.colore), stroke: 1pt + white,
  if t.logo != "" { image(t.logo, width: dd, height: dd, fit: "cover") } else { align(center + horizon, text(dd * .36, weight: "bold", fill: white)[#t.sigla]) })

// una serie: due righe, vittorie a destra, pallini delle partite
#let riga(t, vinte, avanti, fuori) = box(width: 100%, inset: (x: 5pt, y: 3pt), radius: 3pt,
  fill: if avanti { giallo1.lighten(55%) } else { none },
  grid(columns: (13pt, auto, 1fr, auto), column-gutter: 5pt, align: horizon,
    text(10pt, weight: "bold", fill: grigio)[#t.seed],
    stemma(t, dd: 22pt),
    text(12pt, weight: if avanti { "bold" } else { "regular" }, fill: if fuori { grigio } else { scuro })[#t.nome],
    text(17pt, weight: "bold", fill: if avanti { scuro } else { grigio })[#vinte]))
#let serie(s, titolo: "") = block(width: 100%, radius: 6pt, fill: white, stroke: (if s.at("live", default: false) { 1.3pt + rosso } else { 0.8pt + bordo }), inset: 4pt)[
  #if titolo != "" [#align(center, text(9pt, weight: "bold", fill: marrone, tracking: .5pt)[#upper(titolo)]) #v(3pt)]
  #riga(s.a, s.va, s.va > s.vb, s.at("fine", default: false) and s.va < s.vb)
  #riga(s.b, s.vb, s.vb > s.va, s.at("fine", default: false) and s.vb < s.va)
  #let gg = s.at("gare", default: ())
  #if gg.len() > 0 {
    v(4pt)
    block(width: 100%, inset: (x: 6pt, y: 4pt), radius: 3pt, fill: crema, {
      set text(10pt)
      grid(columns: (auto, auto, 1fr, auto, auto, auto), column-gutter: 5pt, row-gutter: 4pt, align: (left, left, left, right, center, left),
        ..gg.map(g => (
          text(fill: grigio, weight: "bold")[G#g.n],
          text(9pt, fill: grigio)[#g.p],
          [],
          text(weight: if g.v == "a" { "bold" } else { "regular" }, fill: if g.v == "" { rosso } else { scuro })[#g.pa],
          text(fill: grigio)[–],
          text(weight: if g.v == "b" { "bold" } else { "regular" }, fill: if g.v == "" { rosso } else { scuro })[#g.pb],
        )).flatten())
    })
  }
  #v(3pt)
  #align(center, text(9pt, fill: grigio)[#s.nota])
]
#let attesa(x) = block(width: 100%, radius: 6pt, fill: white, stroke: 0.8pt + bordo, inset: 5pt)[
  #if x.at("titolo", default: "") != "" [#align(center, text(9pt, weight: "bold", fill: marrone, tracking: .5pt)[#upper(x.titolo)]) #v(3pt)]
  #if type(x.a) == dictionary { riga(x.a, "", false, false) } else { box(width: 100%, inset: (x: 5pt, y: 6pt), text(11pt, fill: grigio)[#x.a]) }
  #box(width: 100%, inset: (x: 5pt, y: 6pt), radius: 3pt, stroke: (paint: bordo, thickness: .8pt, dash: "dashed"), text(11pt, fill: grigio)[#x.b])
  #v(3pt) #align(center, text(9pt, fill: grigio)[#x.nota])]
#let freccia(t) = align(center, text(16pt, fill: giallo2)[#t])
// a piramide (Luca, 14/11): una riga per turno; la conference di sopra scende verso la finale, quella di sotto sale
#let conf(c, sopra) = {
  let blocco(x) = if x.tipo == "serie" { serie(x, titolo: x.at("titolo", default: "")) } else { attesa(x) }
  let f = if sopra { "▼" } else { "▲" }
  let titolo(t) = align(center, text(10pt, weight: "bold", fill: grigio, tracking: .6pt)[#upper(t)])
  // primo turno: sotto la semifinale 1 la 1ª (che aspetta) e il 4–5, sotto la 2 la 2ª e il 3–6
  let r1 = grid(columns: (1fr, 1fr), column-gutter: 10pt, align: top,
    serie(c.r1.at(0), titolo: "4 – 5"), serie(c.r1.at(1), titolo: "3 – 6"))
  let r2 = grid(columns: (1fr, 1fr), column-gutter: 10pt, align: top, blocco(c.r2.at(0)), blocco(c.r2.at(1)))
  let r3 = pad(x: 120pt, blocco(c.r3))
  let frecce(n) = grid(columns: range(n).map(_ => 1fr), ..range(n).map(_ => freccia(f)))
  let righe = ((titolo("Primo turno"), r1), (titolo("Semifinali"), r2), (titolo("Finale di conference"), r3))
  block(width: 100%)[
    #if not sopra { freccia(f); v(4pt) }
    #align(center, text(14pt, weight: "bold", fill: marrone, tracking: 1pt)[#upper(c.nome)])
    #v(6pt)
    #if sopra [
      #righe.at(0).at(0) #v(4pt) #righe.at(0).at(1) #v(3pt) #frecce(2) #v(3pt)
      #righe.at(1).at(0) #v(4pt) #righe.at(1).at(1) #v(3pt) #frecce(1) #v(3pt)
      #righe.at(2).at(0) #v(4pt) #righe.at(2).at(1)
    ] else [
      #righe.at(2).at(1) #v(4pt) #righe.at(2).at(0) #v(3pt) #frecce(1) #v(3pt)
      #righe.at(1).at(1) #v(4pt) #righe.at(1).at(0) #v(3pt) #frecce(2) #v(3pt)
      #righe.at(0).at(1) #v(4pt) #righe.at(0).at(0)
    ]
    #if sopra { v(4pt); freccia(f) }
  ]
}

// ── testata ──
#block(width: 100%, fill: gradient.linear(giallo1, giallo2, angle: 0deg), inset: (x: 20pt, y: 14pt))[
  #grid(columns: (auto, 1fr, auto), column-gutter: 12pt, align: horizon,
    text(30pt)[🏆],
    stack(spacing: 8pt, text(24pt, weight: "bold", fill: scuro)[Playoff #d.anno],
      text(12pt, fill: scuro.lighten(20%))[#d.fase]),
    box(fill: scuro, radius: 6pt, inset: (x: 10pt, y: 6pt), stack(spacing: 4pt,
      text(8pt, weight: "bold", fill: giallo1, tracking: .6pt)[ADESSO],
      text(14pt, weight: "bold", fill: white)[#d.adesso])))
]

#let lato(t, vinte, avanti, fuori) = box(width: 100%, radius: 6pt, fill: if avanti { white.transparentize(88%) } else { none },
  stroke: (paint: if avanti { giallo1 } else { white.transparentize(70%) }, thickness: .9pt), inset: (x: 8pt, y: 7pt),
  grid(columns: (auto, 1fr, auto), column-gutter: 8pt, align: horizon,
    stemma(t, dd: 26pt),
    stack(spacing: 3pt, text(13pt, weight: "bold", fill: if fuori { white.transparentize(45%) } else { white })[#t.nome],
      text(9pt, fill: white.transparentize(40%))[#t.at("conf", default: "")]),
    text(22pt, weight: "bold", fill: if avanti { giallo1 } else { white.transparentize(45%) })[#vinte]))
#let finale = {
  let f = d.at("finale", default: none)
  let c = d.at("campione", default: none)
  block(width: 100%, radius: 10pt, fill: gradient.linear(giallo1, giallo2, angle: 0deg), inset: 3pt,
  block(width: 100%, radius: 8pt, fill: scuro, inset: (x: 14pt, y: 10pt))[
    #grid(columns: (auto, 1fr, auto), column-gutter: 14pt, align: horizon,
      text(30pt)[🏆],
      align(center)[
        #if c != none [
          #stack(spacing: 7pt, text(9pt, weight: "bold", fill: giallo1, tracking: 1.5pt)[CAMPIONE #d.anno],
            stemma(c, dd: 46pt), text(20pt, weight: "bold", fill: white)[#c.nome])
          #v(10pt)
        ] else [
          #text(18pt, weight: "bold", fill: giallo1, tracking: 1.5pt)[FINALE] \ #v(2pt) #text(9pt, fill: white.transparentize(25%))[#d.finale_nota]
          #v(8pt)
        ]
        #if f == none {
          grid(columns: (1fr, auto, 1fr), column-gutter: 8pt, align: horizon,
            box(width: 100%, radius: 5pt, stroke: (paint: white.transparentize(50%), thickness: .8pt, dash: "dashed"), inset: 7pt, text(11pt, fill: white.transparentize(30%))[campione #d.at("conf_sopra", default: "")]),
            text(9pt, weight: "bold", fill: giallo1)[vs],
            box(width: 100%, radius: 5pt, stroke: (paint: white.transparentize(50%), thickness: .8pt, dash: "dashed"), inset: 7pt, text(11pt, fill: white.transparentize(30%))[campione #d.at("conf_sotto", default: "")]))
        } else {
          grid(columns: (1fr, auto, 1fr), column-gutter: 8pt, align: horizon,
            lato(f.a, f.va, f.va > f.vb, f.fine and f.va < f.vb),
            text(9pt, weight: "bold", fill: giallo1)[vs],
            lato(f.b, f.vb, f.vb > f.va, f.fine and f.vb < f.va))
          let gg = f.at("gare", default: ())
          if gg.len() > 0 {
            v(7pt)
            block(width: 100%, inset: (x: 8pt, y: 5pt), radius: 5pt, fill: white.transparentize(92%), {
              set text(10pt, fill: white.transparentize(20%))
              grid(columns: (auto, 1fr, auto, auto, auto), column-gutter: 6pt, row-gutter: 3pt, align: (left, left, right, center, left),
                ..gg.map(g => (
                  text(fill: giallo1, weight: "bold")[G#g.n],
                  text()[#g.p],
                  text(weight: if g.v == "a" { "bold" } else { "regular" }, fill: if g.v == "" { rgb("#FF8A80") } else { white })[#g.pa],
                  text()[–],
                  text(weight: if g.v == "b" { "bold" } else { "regular" }, fill: if g.v == "" { rgb("#FF8A80") } else { white })[#g.pb],
                )).flatten())
            })
          }
          v(4pt)
          text(9pt, fill: white.transparentize(30%))[#f.nota]
        }
      ],
      text(30pt)[🏆])
  ])
}
#block(width: 100%, inset: (x: 14pt, top: 14pt, bottom: 10pt))[
  #conf(d.ovest, true)
  #v(6pt)
  #finale
  #v(6pt)
  #conf(d.est, false)
]

#block(width: 100%, fill: crema, inset: (x: 16pt, y: 8pt), stroke: (top: .8pt + bordo))[
  #text(9pt, fill: grigio)[#d.regole_nota]
]
