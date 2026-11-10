// /rendimento e /rendimento_carriera (shared/rendimento.py, v7.4.0, mockup approvato da Luca il 09/11): la stagione
// partita per partita (fantapunti, media delle ultime 5 e dall'inizio, fasce delle squadre del fantabasket, play-in e
// playoff in fondo dorato) o la carriera stagione per stagione (fantamedia di Basketball-Reference, la stagione in
// corso dai tabellini ESPN). Stile di /carriera (toni blu). Dati in sys.inputs.dati (JSON).
#let d = json(bytes(sys.inputs.at("dati")))
#let blu = rgb("#1D4ED8")
#let blu_scuro = rgb("#0B2A6B")
#let lilla = rgb("#E6EEFB")
#let lilla2 = rgb("#F3F7FD")
#let bordo = rgb("#C9D7F2")
#let grigio = rgb("#5E6B82")
#let testo = rgb("#111C33")
#let libero = rgb("#A7B0C0")
#set page(width: 620pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 9pt, fill: testo)

#let W = 560pt
#let H = 210pt

// ── testata ──
#block(width: 100%, fill: gradient.linear(blu_scuro, blu, angle: 0deg), inset: (x: 14pt, y: 12pt))[
  #grid(columns: (auto, 1fr, auto), column-gutter: 10pt, align: horizon,
    box(width: 50pt, height: 50pt, radius: 50%, clip: true, fill: lilla, stroke: 2pt + white.transparentize(40%),
      // stesse proporzioni di /carriera: foto 520×380 alta 1,2 volte il tondo, centrata, un filo più su
      if d.foto != "" { place(top + left, dx: -16pt, dy: -2.5pt, image(d.foto, height: 60pt, width: 82pt)) }
      else { align(center + horizon, text(17pt, weight: "bold", fill: blu_scuro)[#d.iniziali]) }),
    stack(spacing: 4pt,
      text(15pt, weight: "bold", fill: white)[#d.nome],
      text(8.5pt, fill: white.transparentize(20%))[#d.sotto]),
    align(right, stack(spacing: 3pt,
      text(8pt, weight: "bold", fill: white.transparentize(15%), tracking: 0.8pt)[#upper(d.titolo)],
      text(20pt, weight: "bold", fill: white)[#d.media_big],
      text(7.5pt, fill: white.transparentize(25%))[#d.media_sotto])))
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
  let n = d.partite.len()
  let xs(i) = 14pt + i * (W - 28pt) / calc.max(n - 1, 1)
  pad(x: 30pt, top: 14pt, bottom: 4pt, box(width: W, height: H + 64pt, {
    // griglia e valori dell'asse y
    for v in asse_y(lo, hi, d.y_passo) {
      place(dx: 0pt, dy: ys(v, lo, hi), line(length: W, stroke: 0.4pt + bordo))
      place(dx: -24pt, dy: ys(v, lo, hi) - 5pt, box(width: 20pt, align(right, text(7pt, fill: grigio)[#v])))
    }
    // fase finale (play-in e playoff): fondo leggero da dove comincia
    if d.post != none {
      let x0 = (xs(d.post - 1) + xs(d.post)) / 2
      place(dx: x0, dy: 0pt, rect(width: W - x0, height: H, fill: rgb("#FFF6E0")))
      place(dx: x0 + 4pt, dy: 3pt, text(7pt, weight: "bold", fill: rgb("#B7791F"), tracking: 0.6pt)[PLAY-IN E PLAYOFF])
    }
    // media progressiva (dall'inizio della stagione fino a quella partita)
    let pp = d.partite.enumerate().filter(((i, p)) => p.prog != none).map(((i, p)) => (xs(i), ys(p.prog, lo, hi)))
    for k in range(1, pp.len()) { place(line(start: pp.at(k - 1), end: pp.at(k), stroke: (paint: rgb("#7FA4F0"), thickness: 1.4pt, dash: "dashed"))) }
    // media mobile (ultime 5)
    let pm = d.partite.enumerate().filter(((i, p)) => p.mobile != none).map(((i, p)) => (xs(i), ys(p.mobile, lo, hi)))
    for k in range(1, pm.len()) { place(line(start: pm.at(k - 1), end: pm.at(k), stroke: 1.8pt + blu_scuro)) }
    // punti
    for (i, p) in d.partite.enumerate() {
      let c = rgb(d.squadre.at(p.sq).colore)
      if p.fp == none {
        place(dx: xs(i) - 2.5pt, dy: ys(0, lo, hi) - 5pt, text(7pt, fill: grigio)[×])
      } else {
        let r = if n > 60 { 2.3pt } else if n > 35 { 2.8pt } else { 3.2pt }
        if p.tipo == "rs" { place(dx: xs(i) - r, dy: ys(p.fp, lo, hi) - r, circle(radius: r, fill: c, stroke: 0.7pt + white)) }
        else { place(dx: xs(i) - r * 1.25, dy: ys(p.fp, lo, hi) - r * 1.25, rotate(45deg, rect(width: r * 1.75, height: r * 1.75, fill: c, stroke: 0.7pt + white))) }
      }
    }
    // migliore
    let b = d.migliore
    if b.t != "" { place(dx: calc.min(calc.max(xs(b.i) - 35pt, 0pt), W - 70pt), dy: ys(b.fp, lo, hi) - 16pt, box(width: 70pt, align(center, text(7pt, weight: "bold", fill: testo)[#b.t]))) }
    // date sull'asse x
    for (i, p) in d.partite.enumerate() {
      if p.data_lbl != "" { place(dx: xs(i) - 14pt, dy: H + 4pt, box(width: 28pt, align(center, text(6.5pt, fill: grigio)[#p.data_lbl]))) }
    }
    // fascia delle squadre del fantabasket
    for f in d.fasce {
      let x0 = if f.da == 0 { 0pt } else { (xs(f.da - 1) + xs(f.da)) / 2 }
      let x1 = if f.a == n - 1 { W } else { (xs(f.a) + xs(f.a + 1)) / 2 }
      let c = rgb(d.squadre.at(f.sq).colore)
      place(dx: x0, dy: H + 18pt, box(width: x1 - x0 - 2pt, height: 30pt, radius: 3pt, fill: c.transparentize(82%), stroke: 0.8pt + c,
        align(center + horizon, if x1 - x0 < 90pt { stack(spacing: 3pt,
          text(7pt, weight: "bold", fill: c.darken(20%))[#d.squadre.at(f.sq).nome], text(7pt, fill: testo)[*#f.media*]) } else { stack(spacing: 3pt,
          text(7.5pt, weight: "bold", fill: c.darken(20%))[#d.squadre.at(f.sq).nome],
          text(7pt, fill: testo)[media *#f.media* · #f.g partite]) })))
    }
  }))
  pad(x: 16pt, top: 2pt, bottom: 10pt, text(7pt, fill: grigio)[
    ● fantapunti di ogni partita, del colore della squadra del fantabasket in cui era (grigio: libero) · ◆ play-in e playoff · × non ha giocato ·
    #box(width: 14pt, height: 2pt, fill: blu_scuro, baseline: -2pt) media delle ultime 5 · #box(width: 14pt, height: 1.4pt, stroke: (dash: "dashed", paint: rgb("#7FA4F0"), thickness: 1.4pt), baseline: -2pt) media dall'inizio della stagione])
} else {
  // ── carriera: una barra per stagione (fantamedia di Basketball-Reference) ──
  let lo = 0
  let hi = d.y_max
  let n = d.stagioni.len()
  let bw = (W - 20pt) / n
  let righe_sotto = calc.max(..d.stagioni.map(s => s.team.len() + s.fanta.len()), 1)
  pad(x: 30pt, top: 18pt, bottom: 4pt, box(width: W, height: H + 40pt + righe_sotto * 9pt, {
    for v in asse_y(0, hi, d.y_passo) {
      place(dx: 0pt, dy: ys(v, lo, hi), line(length: W, stroke: 0.4pt + bordo))
      place(dx: -24pt, dy: ys(v, lo, hi) - 5pt, box(width: 20pt, align(right, text(7pt, fill: grigio)[#v])))
    }
    for (i, s) in d.stagioni.enumerate() {
      let w = calc.min(bw * 0.64, 70pt)
      let x = 10pt + i * bw + (bw - w) / 2
      let h = s.fm / hi * H
      let c = if s.in_corso { blu } else { blu_scuro.lighten(15%) }
      place(dx: x, dy: H - h, rect(width: w, height: h, radius: (top: 3pt), fill: if s.in_corso { gradient.linear(blu, blu.lighten(35%), angle: 90deg) } else { c }))
      let fitto = n > 14                         // tante stagioni: numeri più piccoli, senza minuti
      place(dx: x - 6pt, dy: H - h - 13pt, box(width: w + 12pt, align(center, text(if fitto { 6.8pt } else { 8pt }, weight: "bold")[#s.fm_t])))
      // sotto: stagione, partite, (minuti), squadra
      place(dx: x - 8pt, dy: H + 5pt, box(width: w + 16pt, align(center, stack(spacing: 3pt,
        text(if fitto { 6.5pt } else { 7.5pt }, weight: "bold")[#s.lbl],
        text(6.5pt, fill: grigio)[#s.g G#if not fitto [ · #s.min']],
        ..s.team.map(x => text(6.5pt, fill: grigio)[#x]),
        // le squadre del fantabasket della stagione, col loro colore (Luca, 10/11)
        ..s.fanta.map(f => text(6.3pt, weight: "bold", fill: rgb(f.colore))[#f.nome])))))
      if s.in_corso { place(dx: x - 6pt, dy: H - h - 25pt, box(width: w + 12pt, align(center, text(6pt, weight: "bold", fill: blu, tracking: 0.5pt)[IN CORSO]))) }
      // un tondo per squadra del fantabasket, dal basso in su (in ordine)
      let dd = calc.min(14pt, w * 0.9)
      for (k, f) in s.fanta.enumerate() {
        place(dx: x + w / 2 - dd / 2, dy: H - (dd + 3pt) * (k + 1), if f.logo != "" {
          box(width: dd, height: dd, radius: 50%, clip: true, fill: white, stroke: 1pt + white, image(f.logo, width: dd, height: dd, fit: "cover"))
        } else {
          box(width: dd, height: dd, radius: 50%, fill: rgb(f.colore), stroke: 1pt + white,
            align(center + horizon, text(dd * 0.36, weight: "bold", fill: white)[#f.sigla]))
        })
      }
    }
  }))
  pad(x: 16pt, top: 2pt, bottom: 10pt, text(7pt, fill: grigio)[#d.nota])
}
