// /rendimento_team (v7.14.0, Luca 15/11, mockup approvato): sul viola di /rendimento, una barra per giornata coi
// punti fatti (piena vinta, chiara persa, oro la migliore), il trattino dei punti dell'avversario, C/T sotto l'asse,
// media delle ultime 5 e della stagione, la linea arancio della panchina e la sua riga; fascia gialla sui nostri
// playoff. Dati in sys.inputs.dati (rendimento_team.dati).
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#5F01D1")
#let viola_scuro = rgb("#39007D")
#let viola_medio = rgb("#7B3FE4")
#let lilla = rgb("#EFE7FD")
#let bordo = rgb("#E4DAF7")
#let grigio = rgb("#6B6480")
#let testo = rgb("#1D1630")
#let oro = rgb("#E0A21B")
#let oro_scuro = rgb("#9A6A00")
#let arancio = rgb("#F57C00")
#let rosso = rgb("#C62828")
#set page(width: 620pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: testo)
#let W = 548pt
#let H = 200pt
#let fmt(x) = str(calc.round(x, digits: 1)).replace(".", ",")
#let col = rgb(d.colore)

#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 16pt, top: 14pt, bottom: 12pt))[
  #grid(columns: (auto, 1fr), column-gutter: 12pt, align: horizon,
    box(width: 52pt, height: 52pt, radius: 50%, clip: true, fill: col, stroke: 2pt + white.transparentize(40%),
      if d.logo != "" { image(d.logo, width: 52pt, height: 52pt, fit: "cover") }
      else { align(center + horizon, text(17pt, weight: "bold", fill: white)[#d.sigla]) }),
    stack(spacing: 4pt,
      text(16pt, weight: "bold", fill: white)[#d.nome],
      text(8.5pt, fill: white.transparentize(20%))[#d.sotto]))
  #v(10pt)
  #let riquadro(r) = box(fill: white.transparentize(88%), radius: 6pt, inset: (x: 10pt, y: 6pt), width: 100%,
    stack(spacing: 3pt, text(6.5pt, weight: "bold", fill: white.transparentize(30%), tracking: 0.6pt)[#upper(r.t)],
      text(15pt, weight: "bold", fill: white)[#r.v], text(6.5pt, fill: white.transparentize(30%))[#r.s]))
  #grid(columns: (1fr,) * d.riquadri.len(), column-gutter: 8pt, ..d.riquadri.map(riquadro))
]

#{
  let P = d.giornate
  let n = P.len()
  let lo = d.y_min
  let hi = d.y_max
  let ys(v) = H - (v - lo) / (hi - lo) * H
  let slot = W / n
  let xc(i) = slot * (i + 0.5)
  pad(x: 36pt, top: 16pt, bottom: 2pt, box(width: W, height: H + 30pt, {
    let v = lo
    while v <= hi {
      place(dx: 0pt, dy: ys(v), line(length: W, stroke: 0.4pt + bordo))
      place(dx: -30pt, dy: ys(v) - 5pt, box(width: 24pt, align(right, text(7pt, fill: grigio)[#v])))
      v += d.passo
    }
    let fp_ = d.at("fanta", default: none)
    if fp_ != none {
      let f0 = xc(fp_.da) - slot / 2
      let f1 = xc(fp_.a) + slot / 2
      place(dx: f0, dy: 0pt, rect(width: f1 - f0, height: H, fill: rgb("#FFF3C4").transparentize(15%)))
      place(dx: f0 + 3pt, dy: 2pt, text(6.5pt, weight: "bold", fill: oro_scuro, tracking: 0.5pt)[🏆 I NOSTRI PLAYOFF])
    }
    // media della stagione
    place(dx: 0pt, dy: ys(d.media), line(length: W, stroke: (paint: viola_medio, thickness: 0.8pt, dash: "dashed")))
    place(dx: W + 3pt, dy: ys(d.media) - 5pt, text(6.5pt, weight: "bold", fill: viola_medio)[#fmt(d.media)])
    let bw = calc.min(slot * 0.62, 16pt)
    for (i, p) in P.enumerate() {
      let h = calc.max(H - ys(p.fatti), 0.8pt)
      let migliore = i == d.migliore
      place(dx: xc(i) - bw / 2, dy: H - h, rect(width: bw, height: h, radius: (top: 1.5pt),
        fill: if migliore { oro } else if p.v { col } else { col.lighten(65%) },
        stroke: if p.v or migliore { none } else { 0.8pt + col }))
      // avversario: un trattino grigio all'altezza dei suoi punti
      place(dx: xc(i) - bw / 2 - 2pt, dy: ys(p.subiti) - 1pt, rect(width: bw + 4pt, height: 2pt, fill: testo.transparentize(35%)))
      // casa o trasferta, sotto l'asse
      place(dx: xc(i) - 10pt, dy: H + 3pt, box(width: 20pt, align(center, text(6.5pt, weight: "bold", fill: if p.casa { viola_scuro } else { grigio })[#if p.casa [C] else [T]])))
      if calc.rem(i, d.ogni) == 0 { place(dx: xc(i) - 10pt, dy: H + 13pt, box(width: 20pt, align(center, text(6.5pt, fill: grigio)[#p.cod]))) }
    }
    // panchina: linea arancio sottile coi punti della panchina (senza panchina mandata: niente punto)
    let pp = P.enumerate().filter(((i, p)) => p.panchina != none).map(((i, p)) => (xc(i), ys(p.panchina)))
    for k in range(1, pp.len()) {
      place(line(start: pp.at(k - 1), end: pp.at(k), stroke: (paint: arancio, thickness: 1pt)))
    }
    for q in pp { place(dx: q.at(0) - 1.6pt, dy: q.at(1) - 1.6pt, circle(radius: 1.6pt, fill: arancio)) }
    // media delle ultime 5
    let pts = P.enumerate().filter(((i, p)) => p.mobile != none).map(((i, p)) => (xc(i), ys(p.mobile)))
    for k in range(1, pts.len()) {
      place(line(start: pts.at(k - 1), end: pts.at(k), stroke: (paint: viola_scuro, thickness: 2pt, cap: "round")))
    }
    let b = d.migliore
    place(dx: calc.min(calc.max(xc(b) - 30pt, 0pt), W - 60pt), dy: ys(P.at(b).fatti) - 12pt,
      box(width: 60pt, align(center, text(7pt, weight: "bold", fill: oro_scuro)[#fmt(P.at(b).fatti)])))
  }))
}
#pad(x: 16pt, top: 8pt, bottom: 4pt, block(width: 100%, fill: lilla, radius: 6pt, inset: (x: 10pt, y: 7pt),
  grid(columns: (auto, 1fr), column-gutter: 8pt, align: horizon,
    box(width: 14pt, height: 3pt, fill: arancio, baseline: -2pt),
    text(8.5pt)[#text(weight: "bold")[Panchina] · #d.panchina])))
#pad(x: 16pt, top: 6pt, bottom: 12pt, text(7pt, fill: grigio)[
  ▮ punti fatti (pieno vinta, chiaro persa, oro la migliore) · #box(width: 12pt, height: 2pt, fill: testo.transparentize(35%), baseline: -2pt) punti dell'avversario · C/T casa o trasferta
  #h(4pt) #box(width: 14pt, height: 2pt, fill: viola_scuro, baseline: -2pt) media delle ultime 5
  #h(4pt) #box(width: 14pt, height: 0pt, stroke: (top: (paint: viola_medio, thickness: 0.8pt, dash: "dashed")), baseline: -2pt) media della stagione
  #h(4pt) #box(width: 14pt, height: 2pt, fill: arancio, baseline: -2pt) punti della panchina (i 5 panchinari)])
