// /rendimento (shared/rendimento.py). v7.6.2 (Luca, 11/11, variante A): sul viola di Yahoo come /partita e
// /giocatori, quattro riquadri nella testata, una barra per partita dall'asse 0. /rendimento_carriera ha il suo
// template, rendimento_carriera.typ, col disegno di prima.
// Stagione: barre del colore della squadra del fantabasket (grigio: libero), la migliore in oro, play-in e playoff
// col bordo dorato, chi non ha giocato una tacca grigia; linea spessa = media delle ultime 5, tratteggiata = media
// della stagione; sull'asse i mesi, sotto una striscia per squadra del fantabasket. Dati in sys.inputs.dati (JSON).
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
#set page(width: 620pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: testo)

#let W = 548pt
#let H = 190pt
#let fmt(x) = str(calc.round(x, digits: 2)).replace(".", ",")

// ── testata ──
#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 16pt, top: 14pt, bottom: 12pt))[
  #grid(columns: (auto, 1fr), column-gutter: 12pt, align: horizon,
    box(width: 52pt, height: 52pt, radius: 50%, clip: true, fill: lilla, stroke: 2pt + white.transparentize(40%),
      // stesse proporzioni di /carriera: foto 520×380 alta 1,2 volte il tondo, centrata, un filo più su
      if d.foto != "" { place(top + left, dx: -16.5pt, dy: -2.5pt, image(d.foto, height: 62pt, width: 85pt)) }
      else { align(center + horizon, text(17pt, weight: "bold", fill: viola_scuro)[#d.iniziali]) }),
    stack(spacing: 4pt,
      text(16pt, weight: "bold", fill: white)[#d.nome],
      text(8.5pt, fill: white.transparentize(20%))[#d.sotto · #d.titolo]))
  #v(10pt)
  #let riquadro(r) = box(fill: white.transparentize(88%), radius: 6pt, inset: (x: 10pt, y: 6pt), width: 100%,
    stack(spacing: 3pt, text(6.5pt, weight: "bold", fill: white.transparentize(30%), tracking: 0.6pt)[#upper(r.t)],
      text(15pt, weight: "bold", fill: white)[#r.v], text(6.5pt, fill: white.transparentize(30%))[#r.s]))
  #grid(columns: (1fr,) * d.riquadri.len(), column-gutter: 8pt, ..d.riquadri.map(riquadro))
]

#let griglia(hi, passo, ys) = {
  let v = 0
  while v <= hi {
    place(dx: 0pt, dy: ys(v), line(length: W, stroke: 0.4pt + bordo))
    place(dx: -26pt, dy: ys(v) - 5pt, box(width: 20pt, align(right, text(7pt, fill: grigio)[#v])))
    v += passo
  }
}
#let linea_media(m, ys) = {
  place(dx: 0pt, dy: ys(m), line(length: W, stroke: (paint: viola_medio, thickness: 0.8pt, dash: "dashed")))
  place(dx: W + 3pt, dy: ys(m) - 5pt, text(6.5pt, weight: "bold", fill: viola_medio)[#fmt(m)])
}

#if d.modo == "stagione" {
  let P = d.partite
  let n = P.len()
  let hi = d.y_barre
  let passo = if hi > 70 { 20 } else { 10 }
  let ys(v) = H - v / hi * H
  let slot = W / n
  let xc(i) = slot * (i + 0.5)
  let col(sq) = rgb(d.squadre.at(sq).colore)
  pad(x: 36pt, top: 16pt, bottom: 2pt, box(width: W, height: H + 40pt, {
    griglia(hi, passo, ys)
    // play-in e playoff: da dove cominciano
    if d.post != none {
      let x0 = xc(d.post) - slot / 2
      place(dx: x0, dy: 0pt, line(length: H, angle: 90deg, stroke: (paint: oro, thickness: 0.8pt, dash: "dotted")))
      // l'etichetta a destra della linea, o a sinistra se non c'è spazio
      if W - x0 > 92pt { place(dx: x0 + 3pt, dy: 2pt, text(6.5pt, weight: "bold", fill: oro_scuro, tracking: 0.5pt)[PLAY-IN E PLAYOFF]) }
      else { place(dx: x0 - 93pt, dy: 2pt, box(width: 90pt, align(right, text(6.5pt, weight: "bold", fill: oro_scuro, tracking: 0.5pt)[PLAY-IN E PLAYOFF →]))) }
    }
    linea_media(d.media_val, ys)
    let bw = calc.min(slot * 0.64, 14pt)
    for (i, p) in P.enumerate() {
      if p.fp == none {
        // non ha giocato: una tacca grigia sull'asse
        place(dx: xc(i) - bw / 2, dy: H - 2pt, rect(width: bw, height: 2pt, fill: rgb("#C9C2D9")))
      } else {
        let h = calc.max(H - ys(p.fp), 0.8pt)
        let migliore = i == d.migliore.i and d.migliore.t != ""
        place(dx: xc(i) - bw / 2, dy: H - h, rect(width: bw, height: h, radius: (top: 1.5pt),
          fill: if migliore { oro } else { col(p.sq).transparentize(15%) },
          stroke: if p.tipo == "post" and not migliore { 1pt + oro } else { none }))
      }
    }
    // media delle ultime 5
    let pts = P.enumerate().filter(((i, p)) => p.mobile != none).map(((i, p)) => (xc(i), ys(p.mobile)))
    for k in range(1, pts.len()) {
      place(line(start: pts.at(k - 1), end: pts.at(k), stroke: (paint: viola_scuro, thickness: 2pt, cap: "round")))
    }
    // la migliore
    if d.migliore.t != "" {
      let b = d.migliore.i
      place(dx: calc.min(calc.max(xc(b) - 30pt, 0pt), W - 60pt), dy: ys(P.at(b).fp) - 12pt,
        box(width: 60pt, align(center, text(7pt, weight: "bold", fill: oro_scuro)[#fmt(P.at(b).fp)])))
    }
    // asse x: i mesi
    for m in d.mesi {
      let x = xc(m.i) - slot / 2
      place(dx: x, dy: H, line(length: 4pt, angle: 90deg, stroke: 0.6pt + grigio))
      place(dx: x + 3pt, dy: H + 4pt, text(7.5pt, weight: "bold", fill: grigio)[#m.lbl])
    }
    // le squadre del fantabasket
    for f in d.fasce {
      let x0 = xc(f.da) - slot / 2
      let x1 = xc(f.a) + slot / 2
      let c = col(f.sq)
      place(dx: x0, dy: H + 18pt, rect(width: calc.max(x1 - x0 - 2pt, 2pt), height: 4pt, radius: 2pt, fill: c))
      if x1 - x0 >= 40pt {
        place(dx: x0, dy: H + 25pt, box(width: x1 - x0, clip: true, text(7.5pt)[#text(weight: "bold", fill: c)[#d.squadre.at(f.sq).nome] #text(fill: grigio)[· #f.media su #f.g]]))
      }
    }
  }))
  pad(x: 16pt, top: 6pt, bottom: 12pt, text(7pt, fill: grigio)[
    ▮ fantapunti, col colore della squadra del fantabasket (grigio libero, oro la migliore, bordo dorato playoff, tacca grigia non ha giocato)
    #h(4pt) #box(width: 14pt, height: 2pt, fill: viola_scuro, baseline: -2pt) media delle ultime 5
    #h(4pt) #box(width: 14pt, height: 0pt, stroke: (top: (paint: viola_medio, thickness: 0.8pt, dash: "dashed")), baseline: -2pt) media della stagione])
}
