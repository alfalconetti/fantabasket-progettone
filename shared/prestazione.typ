// /prestazione (v7.31.0, Luca 26/11; mockup approvato): la singola notte di un giocatore, sul viola di /player.
// Dati da shared/prestazione.py (dati): testata con foto, avversario, data, risultato; i riquadri (i fantapunti
// accesi); i badge; il tabellino con la media e la differenza; i tiri; come nascono i fantapunti; prima e dopo.
// Se non ha giocato: 0 col motivo e la partita prima e dopo.
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#5F01D1")
#let viola_scuro = rgb("#39007D")
#let lilla = rgb("#EFE7FD")
#let lilla2 = rgb("#F7F3FE")
#let bordo = rgb("#E4DAF7")
#let grigio = rgb("#6B6480")
#let testo = rgb("#1D1630")
#let verde = rgb("#1E9E5A")
#let rosso = rgb("#D64545")
#set page(width: 520pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: testo)
// klra (v7.41.0): filigrana «NON UFFICIALE» e striscia rossa in cima, solo se nei dati (come confronto.typ)
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
#let etichetta(t) = text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[#upper(t)]
#let pill(t, f: white, c: viola_scuro) = box(fill: f, radius: 3pt, inset: (x: 5pt, y: 2.5pt), text(8pt, weight: "bold", fill: c)[#t])

#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 16pt, top: 14pt, bottom: 12pt))[
  #grid(columns: (auto, 1fr, auto), column-gutter: 14pt, align: horizon,
    box(width: 64pt, height: 64pt, radius: 50%, clip: true, fill: lilla, stroke: 2.5pt + white.transparentize(40%),
      if d.foto != "" { place(top + left, dx: -21pt, dy: -3pt, image(d.foto, height: 77pt, width: 106pt)) }
      else { align(center + horizon, text(22pt, weight: "bold", fill: viola_scuro)[#d.iniziali]) }),
    stack(spacing: 5pt,
      text(17pt, weight: "bold", fill: white)[#d.nome],
      [#if d.sq != "" { pill(d.sq) } #h(4pt) #text(9pt, fill: white, weight: "bold")[#d.contro] #h(4pt) #text(8.5pt, fill: white.transparentize(15%))[#d.data]],
      if d.sotto != "" { text(8pt, fill: white.transparentize(15%))[#d.sotto] }),
    if d.esito != "" { stack(spacing: 4pt, align(right, pill(d.esito, f: if d.vinta { verde } else { rosso }, c: white)),
      align(right, text(7.5pt, fill: white.transparentize(25%))[#d.punteggio])) })
  #v(12pt)
  #let riq(r, acceso) = box(fill: if acceso { gradient.linear(rgb("#FFD23F"), rgb("#FF9F1C"), angle: 0deg) } else { white.transparentize(88%) },
    radius: 6pt, inset: (x: 9pt, y: 6pt), width: 100%,
    stack(spacing: 3pt, text(6.5pt, weight: "bold", fill: if acceso { viola_scuro.transparentize(20%) } else { white.transparentize(30%) }, tracking: 0.6pt)[#upper(r.t)],
      text(15pt, weight: "bold", fill: if acceso { viola_scuro } else { white })[#r.v],
      text(6.5pt, fill: if acceso { viola_scuro.transparentize(25%) } else { white.transparentize(30%) })[#r.s]))
  #grid(columns: if d.riquadri.len() == 4 { (1.15fr, 0.85fr, 1fr, 1fr) } else { (1fr,) * d.riquadri.len() }, column-gutter: 6pt,
    ..d.riquadri.enumerate().map(((i, r)) => riq(r, i == 0 and d.giocato)))
  // v7.31.2 (Luca, 26/11): la squadra del fantabasket in evidenza, in una fascia sua
  #v(6pt)
  #box(width: 100%, fill: white, radius: 6pt, inset: (x: 10pt, y: 7pt),
    grid(columns: (auto, 1fr, auto), column-gutter: 10pt, align: horizon,
      text(6.5pt, weight: "bold", fill: grigio, tracking: 0.6pt)[FANTABASKET],
      text(13pt, weight: "bold", fill: viola_scuro)[#d.fanta.squadra],
      text(8.5pt, fill: viola_scuro)[#{ (d.fanta.giornata, d.fanta.ruolo).filter(x => x != "").join(" · ") }]))
  #if d.badge.len() > 0 {
    v(8pt)
    d.badge.enumerate().map(((i, b)) => box(fill: if i == 0 { rgb("#FFD23F") } else { white.transparentize(80%) }, radius: 10pt, inset: (x: 7pt, y: 3pt),
      text(7.5pt, weight: "bold", fill: if i == 0 { viola_scuro } else { white })[#b])).join(h(4pt))
  }
]

#if d.giocato [
  #block(inset: (x: 16pt, top: 12pt, bottom: 4pt))[#etichetta("Tabellino")]
  #block(inset: (x: 16pt))[
    #table(columns: (auto,) + (1fr,) * d.tabella.len(), stroke: none, inset: (x: 3pt, y: 5pt), align: (left,) + (center,) * d.tabella.len(),
      fill: (x, y) => if y == 0 { lilla } else if y == 1 { lilla2 } else if y == 3 { lilla2.transparentize(50%) } else { none },
      [], ..d.tabella.map(c => text(7pt, weight: "bold", fill: grigio)[#c.t]),
      text(7.5pt, weight: "bold")[Notte], ..d.tabella.map(c => text(11pt, weight: "bold")[#c.v]),
      // v7.31.1: la media fino a quella notte e quella di tutta la stagione, ognuna con la differenza
      ..range(2).map(i => (
        text(7pt, fill: grigio)[#d.medie.at(i)], ..d.tabella.map(c => {
          let x = c.righe.at(i)
          stack(spacing: 2pt, text(8pt, fill: grigio)[#x.m],
            text(7.5pt, weight: "bold", fill: if x.buono { verde } else { rosso })[#x.d]) }))).flatten())
    #v(8pt)
    #grid(columns: (1fr, 1fr, 1fr), column-gutter: 6pt,
      ..d.tiri.map(x => box(fill: lilla2, stroke: 0.6pt + bordo, radius: 5pt, inset: (x: 8pt, y: 6pt), width: 100%,
          stack(spacing: 3pt, etichetta(x.t), text(13pt, weight: "bold")[#x.v], text(7pt, fill: grigio)[#x.s]))))
  ]
  // v7.35.0: la composizione dei fantapunti, la notte e (barra chiara) la media della stagione intera
  #if d.at("composizione", default: none) != none {
    let co = d.composizione
    let colori = (rgb("#5B21B6"), rgb("#0E7490"), rgb("#047857"), rgb("#B45309"), rgb("#9D174D"))
    let barra(chiave, h, chiara) = box(width: 100%, height: h, radius: 3pt, clip: true, stack(dir: ltr,
      ..co.voci.enumerate().filter(((i, x)) => x.at(chiave) > 0).map(((i, x)) => box(width: x.at(chiave) * 100%, height: 100%,
        fill: if chiara { colori.at(i).transparentize(55%) } else { colori.at(i) },
        align(center + horizon, text(if chiara { 6.5pt } else { 7.5pt }, weight: "bold", fill: white)[#if x.at(chiave) > 0.08 [#calc.round(x.at(chiave) * 100)%]])))))
    block(inset: (x: 16pt, top: 14pt, bottom: 4pt))[#etichetta("Composizione dei fantapunti")]
    block(inset: (x: 16pt))[
      #grid(columns: (52pt, 1fr), column-gutter: 6pt, row-gutter: 3pt, align: (right + horizon, left),
        text(7pt, weight: "bold", fill: grigio)[Notte], barra("q", 20pt, false),
        ..if co.barra_media { (text(7pt, weight: "bold", fill: grigio)[Media stag.], barra("qm", 11pt, true)) } else { () })
      #v(7pt)
      #grid(columns: (52pt, 1fr), column-gutter: 6pt, [],
        grid(columns: (1fr,) * 6, column-gutter: 6pt,
          ..co.voci.enumerate().map(((i, x)) => stack(spacing: 2.5pt,
            box(width: 7pt, height: 7pt, fill: colori.at(i), radius: 1.5pt) + h(3pt) + text(7.5pt, weight: "bold")[#x.n],
            text(10pt, weight: "bold", fill: if x.pos { colori.at(i) } else { rosso })[#x.v],
            text(6.5pt, fill: grigio)[media #x.m #if x.d != "" [· #text(weight: "bold", fill: if x.meglio { verde } else { rosso })[#x.d]]],
            text(6.3pt, fill: grigio)[#x.det])),
          stack(spacing: 2.5pt,
            box(width: 7pt, height: 7pt, fill: rosso.transparentize(30%), radius: 1.5pt) + h(3pt) + text(7.5pt, weight: "bold")[Perse],
            text(10pt, weight: "bold", fill: rosso)[#co.perse.v],
            text(6.5pt, fill: grigio)[media #co.perse.m #if co.perse.d != "" [· #text(weight: "bold", fill: if co.perse.meglio { verde } else { rosso })[#co.perse.d]]],
            text(6.3pt, fill: grigio)[#co.perse.det])))
      #v(8pt)
      #align(right, text(7.5pt, fill: grigio)[#co.conto])
    ]
  }
  #block(inset: (x: 16pt, top: 14pt, bottom: 4pt))[#etichetta("Come nascono i fantapunti")]
  #block(inset: (x: 16pt))[
    #grid(columns: (92pt, 1fr, 44pt), row-gutter: 4pt, column-gutter: 6pt, align: (right + horizon, left + horizon, right + horizon),
      ..d.voci.map(v => (
        text(8pt)[#v.n #text(fill: grigio)[(#v.q)]],
        box(width: 100%, height: 9pt, place(left, box(width: v.w * 100%, height: 9pt, radius: 2pt,
          fill: if v.p >= 0 { verde.transparentize(15%) } else { rosso.transparentize(15%) }))),
        text(8pt, weight: "bold", fill: if v.p >= 0 { verde } else { rosso })[#v.pt])).flatten())
    #v(6pt)
    #align(right, text(9pt)[Totale #text(weight: "bold")[#d.totale] fantapunti])
    #if d.correzione != "" { align(right, text(7pt, style: "italic", fill: grigio)[#d.correzione]) }
  ]
] else [
  #block(width: 100%, inset: (x: 16pt, top: 14pt, bottom: 4pt))[
    #box(fill: lilla2, stroke: 0.6pt + bordo, radius: 6pt, inset: 10pt, width: 100%,
      stack(spacing: 4pt, etichetta("Non ha giocato"), text(11pt, weight: "bold")[#d.motivo]))
  ]
]

#block(width: 100%, inset: (x: 16pt, top: 12pt, bottom: 12pt))[
  #line(length: 100%, stroke: 0.6pt + bordo)
  #v(8pt)
  #grid(columns: (1fr, 1fr), align: (left, right),
    text(7.5pt, fill: grigio)[#if d.prima != "" [◀ #d.prima] else [Nessuna partita giocata prima]],
    text(7.5pt, fill: grigio)[#if d.dopo != "" [#d.dopo ▶] else [Nessuna partita giocata dopo]])
]
