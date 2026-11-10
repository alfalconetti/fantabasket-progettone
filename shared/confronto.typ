// /confronto e /confronto_carriera (shared/confronto.py, v7.4.3): due giocatori sovrapposti, stile di /rendimento.
// A in blu, B in arancione. Modo «stagione»: partite sulle date, media delle ultime 5 (piena) e dall'inizio
// (tratteggiata) per ognuno. Modo «carriera»: barre affiancate per stagione di carriera. Sotto, la tabella a
// confronto (il migliore in grassetto). Dati in sys.inputs.dati (JSON).
#let d = json(bytes(sys.inputs.at("dati")))
#let ca = rgb(d.colore_a)
#let cb = rgb(d.colore_b)
#let blu_scuro = rgb("#0B2A6B")
#let blu = rgb("#1D4ED8")
#let lilla = rgb("#E6EEFB")
#let bordo = rgb("#C9D7F2")
#let grigio = rgb("#5E6B82")
#let testo = rgb("#111C33")
#set page(width: 620pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 9pt, fill: testo)

#let W = 560pt
#let H = 200pt

#let tondo(g, c) = box(width: 46pt, height: 46pt, radius: 50%, clip: true, fill: lilla, stroke: 2.5pt + c,
  if g.foto != "" { place(top + left, dx: -15pt, dy: -2.5pt, image(g.foto, height: 55pt, width: 75pt)) }
  else { align(center + horizon, text(15pt, weight: "bold", fill: blu_scuro)[#g.iniziali]) })

#let lato(g, c, dx) = {
  let nome = stack(spacing: 3pt,
    text(13pt, weight: "bold", fill: white)[#g.nome],
    text(7.5pt, fill: white.transparentize(25%))[#g.sotto],
    box(fill: c, radius: 3pt, inset: (x: 5pt, y: 2.5pt), text(11pt, weight: "bold", fill: white)[#g.media]))
  if dx { grid(columns: (1fr, auto), column-gutter: 8pt, align: (right + horizon, horizon), align(right, nome), tondo(g, c)) }
  else { grid(columns: (auto, 1fr), column-gutter: 8pt, align: horizon, tondo(g, c), nome) }
}

// ── testata ──
#block(width: 100%, fill: gradient.linear(blu_scuro, blu, angle: 0deg), inset: (x: 14pt, top: 10pt, bottom: 12pt))[
  #align(center, text(8pt, weight: "bold", fill: white.transparentize(20%), tracking: 0.8pt)[#upper(d.titolo)])
  #v(6pt)
  #grid(columns: (1fr, auto, 1fr), column-gutter: 10pt, align: horizon,
    lato(d.a, ca, false),
    text(16pt, weight: "bold", fill: white.transparentize(30%))[VS],
    lato(d.b, cb, true))
]

#let asse_y(lo, hi, passo) = {
  let v = lo
  let out = ()
  while v <= hi { out.push(v); v += passo }
  out
}
#let ys(v, lo, hi) = H - (v - lo) / (hi - lo) * H

#if d.modo == "stagione" {
  let lo = d.y_min
  let hi = d.y_max
  let xs(f) = 10pt + f * (W - 20pt)
  pad(x: 30pt, top: 14pt, bottom: 4pt, box(width: W, height: H + 18pt, {
    for v in asse_y(lo, hi, d.y_passo) {
      place(dx: 0pt, dy: ys(v, lo, hi), line(length: W, stroke: 0.4pt + bordo))
      place(dx: -24pt, dy: ys(v, lo, hi) - 5pt, box(width: 20pt, align(right, text(7pt, fill: grigio)[#v])))
    }
    if d.post_x != none {
      let x0 = xs(d.post_x) - 4pt
      place(dx: x0, dy: 0pt, rect(width: W - x0, height: H, fill: rgb("#FFF6E0")))
      place(dx: calc.min(x0 + 4pt, W - 92pt), dy: -11pt, text(7pt, weight: "bold", fill: rgb("#B7791F"), tracking: 0.6pt)[PLAY-IN E PLAYOFF])
    }
    for (g, c) in ((d.a, ca), (d.b, cb)) {
      let pp = g.punti.filter(p => p.prog != none).map(p => (xs(p.x), ys(p.prog, lo, hi)))
      for k in range(1, pp.len()) { place(line(start: pp.at(k - 1), end: pp.at(k), stroke: (paint: c.lighten(25%), thickness: 1.2pt, dash: "dashed"))) }
      let pm = g.punti.filter(p => p.mobile != none).map(p => (xs(p.x), ys(p.mobile, lo, hi)))
      for k in range(1, pm.len()) { place(line(start: pm.at(k - 1), end: pm.at(k), stroke: 1.8pt + c.darken(10%))) }
    }
    let n = d.a.punti.len() + d.b.punti.len()
    let r = if n > 100 { 2.1pt } else if n > 60 { 2.6pt } else { 3pt }
    for (g, c) in ((d.a, ca), (d.b, cb)) {
      for p in g.punti {
        if p.fp != none {
          if p.tipo == "rs" { place(dx: xs(p.x) - r, dy: ys(p.fp, lo, hi) - r, circle(radius: r, fill: c, stroke: 0.6pt + white)) }
          else { place(dx: xs(p.x) - r * 1.25, dy: ys(p.fp, lo, hi) - r * 1.25, rotate(45deg, rect(width: r * 1.75, height: r * 1.75, fill: c, stroke: 0.6pt + white))) }
        }
      }
    }
    for l in d.date { place(dx: xs(l.x) - 14pt, dy: H + 4pt, box(width: 28pt, align(center, text(6.5pt, fill: grigio)[#l.t]))) }
  }))
} else {
  let hi = d.y_max
  let n = d.anni.len()
  let gw = (W - 20pt) / n
  let bw = calc.min(gw * 0.36, 26pt)
  let fitto = n > 14
  pad(x: 30pt, top: 18pt, bottom: 4pt, box(width: W, height: H + 40pt, {
    for v in asse_y(0, hi, d.y_passo) {
      place(dx: 0pt, dy: ys(v, 0, hi), line(length: W, stroke: 0.4pt + bordo))
      place(dx: -24pt, dy: ys(v, 0, hi) - 5pt, box(width: 20pt, align(right, text(7pt, fill: grigio)[#v])))
    }
    for (i, y) in d.anni.enumerate() {
      let cx = 10pt + i * gw + gw / 2
      for (s, c, off) in ((y.a, ca, -bw - 1pt), (y.b, cb, 1pt)) {
        if s != none {
          let h = s.fm / hi * H
          place(dx: cx + off, dy: H - h, rect(width: bw, height: h, radius: (top: 2pt), fill: if s.in_corso { c.lighten(30%) } else { c }))
          if not fitto { place(dx: cx + off - 8pt, dy: H - h - 11pt, box(width: bw + 16pt, align(center, text(6.3pt, weight: "bold", fill: c.darken(15%))[#s.t]))) }
        }
      }
      place(dx: cx - 20pt, dy: H + 4pt, box(width: 40pt, align(center, stack(spacing: 2.5pt,
        text(if fitto { 6.5pt } else { 7.5pt }, weight: "bold")[#y.k],
        if y.a != none { text(6pt, fill: ca)[#y.a.lbl] } else { text(6pt)[ ] },
        if y.b != none { text(6pt, fill: cb)[#y.b.lbl] } else { text(6pt)[ ] }))))
    }
  }))
}

// ── tabella a confronto ──
#pad(x: 60pt, top: 8pt, bottom: 4pt, table(
  columns: (1fr, auto, 1fr),
  align: (right + horizon, center + horizon, left + horizon),
  inset: (x: 8pt, y: 5pt),
  stroke: (x, y) => (bottom: 0.5pt + bordo),
  ..d.righe.map(r => (
    text(10pt, weight: if r.meglio == "a" { "bold" } else { "regular" }, fill: if r.meglio == "a" { ca } else { testo })[#r.a],
    text(7.5pt, fill: grigio, tracking: 0.3pt)[#upper(r.voce)],
    text(10pt, weight: if r.meglio == "b" { "bold" } else { "regular" }, fill: if r.meglio == "b" { cb } else { testo })[#r.b],
  )).flatten(),
))
#pad(x: 16pt, top: 4pt, bottom: 10pt, text(7pt, fill: grigio)[#d.nota])
