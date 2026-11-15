// /confronto e /confronto_carriera (shared/confronto.py). v7.9.7 (Luca, 15/11): nelle grafiche nuove.
// Modo «stagione», come /rendimento sul viola: solo linee (pallini e linea sottile per le partite, linea spessa per la
// media delle ultime 5, tratteggiata per la media della stagione), A viola e B arancione; fascia gialla sulle giornate
// dei nostri playoff; play-in e playoff NBA solo segnati (linea grigia, contorno grigio), per conoscenza.
// Modo «carriera», come /rendimento_carriera sul blu: barre affiancate per stagione di carriera, la migliore di
// ognuno in oro, quella in corso più chiara, le fantamedie in carriera tratteggiate.
// In testata quattro riquadri a due valori (il migliore pieno, l'altro sbiadito); sotto, una tabella con il resto.
#let d = json(bytes(sys.inputs.at("dati")))
#let stagione = d.modo == "stagione"
#let scuro = if stagione { rgb("#39007D") } else { rgb("#0B2A6B") }
#let chiaro = if stagione { rgb("#5F01D1") } else { rgb("#1D4ED8") }
#let lilla = if stagione { rgb("#EFE7FD") } else { rgb("#E6EEFB") }
#let bordo = if stagione { rgb("#E4DAF7") } else { rgb("#C9D7F2") }
#let grigio = if stagione { rgb("#6B6480") } else { rgb("#5E6B82") }
#let testo = if stagione { rgb("#1D1630") } else { rgb("#111C33") }
#let oro = rgb("#E0A21B")
#let oro_scuro = rgb("#9A6A00")
#let ca = if stagione { rgb("#7B3FE4") } else { rgb("#2F4A8A") }
#let cb = if stagione { rgb("#FF8A00") } else { rgb("#E07B12") }
#let ca_s = if stagione { rgb("#39007D") } else { rgb("#2F4A8A") }
#let cb_s = rgb("#B35A00")
#let ca_chip = if stagione { ca } else { rgb("#5B7BD5") }
#set page(width: 620pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: testo)
#let W = 548pt
#let H = 180pt
#let fmt(x) = str(calc.round(x, digits: 2)).replace(".", ",")

#let tondo(g, c) = box(width: 46pt, height: 46pt, radius: 50%, clip: true, fill: lilla, stroke: 2.5pt + c,
  if g.foto != "" { place(top + left, dx: -15pt, dy: -2.5pt, image(g.foto, height: 55pt, width: 75pt)) }
  else { align(center + horizon, text(15pt, weight: "bold", fill: scuro)[#g.iniziali]) })
#let lato(g, c, dx) = {
  let nome = stack(spacing: 4pt, text(14pt, weight: "bold", fill: white)[#g.nome], text(7.5pt, fill: white.transparentize(25%))[#g.sotto])
  if dx { grid(columns: (1fr, auto), column-gutter: 8pt, align: horizon, align(right, nome), tondo(g, c)) }
  else { grid(columns: (auto, 1fr), column-gutter: 8pt, align: horizon, tondo(g, c), nome) }
}

// ── testata ──
#block(width: 100%, fill: gradient.linear(scuro, chiaro, angle: 0deg), inset: (x: 16pt, top: 12pt, bottom: 12pt))[
  #align(center, text(7.5pt, weight: "bold", fill: white.transparentize(25%), tracking: 0.8pt)[#upper(d.titolo)])
  #v(6pt)
  #grid(columns: (1fr, auto, 1fr), column-gutter: 10pt, align: horizon,
    lato(d.a, ca_chip, false), text(15pt, weight: "bold", fill: white.transparentize(35%))[VS], lato(d.b, cb, true))
  #v(10pt)
  #let val(v, c, meglio) = box(fill: if meglio { c } else { white.transparentize(85%) }, radius: 4pt, inset: (x: 6pt, y: 3pt),
    text(12pt, weight: "bold", fill: if meglio { white } else { white.transparentize(35%) })[#v])
  #let riquadro(r) = box(fill: white.transparentize(88%), radius: 6pt, inset: (x: 8pt, y: 6pt), width: 100%,
    stack(spacing: 5pt, text(6.5pt, weight: "bold", fill: white.transparentize(30%), tracking: 0.6pt)[#upper(r.t)],
      grid(columns: (auto, 1fr, auto), align: horizon, val(r.a, ca_chip, r.m == "a"), [], val(r.b, cb, r.m == "b")),
      text(6.3pt, fill: white.transparentize(30%))[#r.s]))
  #grid(columns: (1fr,) * d.riquadri.len(), column-gutter: 8pt, ..d.riquadri.map(riquadro))
]

#let griglia(lo, hi, passo, ys) = {
  let v = lo
  while v <= hi {
    place(dx: 0pt, dy: ys(v), line(length: W, stroke: 0.4pt + bordo))
    place(dx: -26pt, dy: ys(v) - 5pt, box(width: 20pt, align(right, text(7pt, fill: grigio)[#v])))
    v += passo
  }
}
#let medie(ys) = for (m, t, c) in ((d.media_a, d.media_a_t, ca), (d.media_b, d.media_b_t, cb)) {
  place(dx: 0pt, dy: ys(m), line(length: W, stroke: (paint: c, thickness: 0.8pt, dash: "dashed")))
  place(dx: W + 3pt, dy: ys(m) - 5pt, text(6.5pt, weight: "bold", fill: c)[#t])
}

#if stagione {
  let lo = d.y_min
  let hi = d.y_max
  let ys(v) = H - (v - lo) / (hi - lo) * H
  let xs(f) = 6pt + f * (W - 12pt)
  pad(x: 36pt, top: 16pt, bottom: 2pt, box(width: W, height: H + 22pt, {
    if d.fanta != none {
      let f0 = xs(d.fanta.x0) - 4pt
      let f1 = xs(d.fanta.x1) + 4pt
      place(dx: f0, dy: 0pt, rect(width: f1 - f0, height: H, fill: rgb("#FFF3C4").transparentize(15%)))
      place(dx: f0 + 3pt, dy: 2pt, box(width: calc.max(f1 - f0, 130pt), text(6.5pt, weight: "bold", fill: oro_scuro, tracking: .5pt)[🏆 I NOSTRI PLAYOFF · #d.fanta.lbl]))
    }
    griglia(lo, hi, d.y_passo, ys)
    if d.post_x != none {
      let x0 = xs(d.post_x) - 4pt
      place(dx: x0, dy: 0pt, line(length: H, angle: 90deg, stroke: (paint: grigio, thickness: 0.7pt, dash: "dotted")))
      if W - x0 > 100pt { place(dx: x0 + 3pt, dy: H - 12pt, text(6pt, weight: "bold", fill: grigio, tracking: .4pt)[PLAY-IN E PLAYOFF NBA]) }
      else { place(dx: x0 - 103pt, dy: H - 12pt, box(width: 100pt, align(right, text(6pt, weight: "bold", fill: grigio, tracking: .4pt)[PLAY-IN E PLAYOFF NBA →]))) }
    }
    medie(ys)
    let n = d.punti_a.len() + d.punti_b.len()
    let r = if n > 120 { 1.6pt } else if n > 70 { 1.9pt } else { 2.2pt }
    for (pp, c) in ((d.punti_a, ca), (d.punti_b, cb)) {
      let g = pp.filter(p => p.fp != none)
      for k in range(1, g.len()) {
        place(line(start: (xs(g.at(k - 1).x), ys(g.at(k - 1).fp)), end: (xs(g.at(k).x), ys(g.at(k).fp)), stroke: (paint: c.transparentize(55%), thickness: 0.8pt)))
      }
      for p in g {
        place(dx: xs(p.x) - r, dy: ys(p.fp) - r, circle(radius: r, fill: c, stroke: if p.post { 1pt + grigio } else { 0.5pt + white }))
      }
    }
    for (pp, cs) in ((d.punti_a, ca_s), (d.punti_b, cb_s)) {
      let m = pp.filter(p => p.mobile != none)
      for k in range(1, m.len()) {
        place(line(start: (xs(m.at(k - 1).x), ys(m.at(k - 1).mobile)), end: (xs(m.at(k).x), ys(m.at(k).mobile)), stroke: (paint: cs, thickness: 2.4pt, cap: "round")))
      }
    }
    for m in d.mesi {
      let x = xs(m.x)
      place(dx: x, dy: H, line(length: 4pt, angle: 90deg, stroke: 0.6pt + grigio))
      place(dx: x + 3pt, dy: H + 4pt, text(7.5pt, weight: "bold", fill: grigio)[#m.lbl])
    }
  }))
  pad(x: 16pt, top: 4pt, bottom: 8pt, text(7pt, fill: grigio)[
    #box(width: 7pt, height: 7pt, fill: ca, baseline: -1pt) #d.a.nome #h(3pt) #box(width: 7pt, height: 7pt, fill: cb, baseline: -1pt) #d.b.nome
    · pallini e linea sottile: i fantapunti di ogni partita, sulle date (contorno grigio: play-in e playoff NBA)
    · #box(width: 12pt, height: 2pt, fill: ca_s, baseline: -2pt) #box(width: 12pt, height: 2pt, fill: cb_s, baseline: -2pt) media delle ultime 5
    · - - - media della stagione (regular season e play-in, come /player)#if d.fanta != none [ · fascia gialla: le giornate dei nostri playoff]])
} else {
  let S = d.stagioni
  let n = S.len()
  let hi = d.y_max
  let ys(v) = H - v / hi * H
  let slot = W / n
  let xc(i) = slot * (i + 0.5)
  let molte = n > 14
  pad(x: 36pt, top: 16pt, bottom: 2pt, box(width: W, height: H + 34pt, {
    griglia(0, hi, d.y_passo, ys)
    medie(ys)
    let bw = calc.min(slot * 0.38, 16pt)
    for (i, s) in S.enumerate() {
      for (k, (v, c, picco, corso)) in ((s.a, ca, s.pa, s.ca), (s.b, cb, s.pb, s.cb)).enumerate() {
        if v != none {
          let x = xc(i) - bw - 0.5pt + k * (bw + 1pt)
          let h = calc.max(H - ys(calc.max(v, 0)), .8pt)
          place(dx: x, dy: H - h, rect(width: bw, height: h, radius: (top: 1.5pt), fill: if picco { oro } else if corso { c.lighten(40%) } else { c }))
          if picco { place(dx: x - 12pt, dy: H - h - 10pt, box(width: bw + 24pt, align(center, text(6.5pt, weight: "bold", fill: oro_scuro)[#fmt(v)]))) }
        }
      }
      place(dx: xc(i) - slot / 2, dy: H + 3pt, box(width: slot, align(center, stack(spacing: 2pt,
        text(if molte { 6pt } else { 7pt }, weight: "bold")[#s.n],
        if not molte or calc.rem(i, 2) == 0 { text(5.5pt, fill: ca)[#s.sa] },
        if not molte or calc.rem(i, 2) == 0 { text(5.5pt, fill: cb)[#s.sb] }))))
    }
  }))
  pad(x: 16pt, top: 2pt, bottom: 8pt, text(7pt, fill: grigio)[
    #box(width: 7pt, height: 7pt, fill: ca, baseline: -1pt) #d.a.nome #h(3pt) #box(width: 7pt, height: 7pt, fill: cb, baseline: -1pt) #d.b.nome
    · fantamedia di ogni stagione, allineate per stagione di carriera (1ª, 2ª…), sotto le stagioni vere · oro: la stagione
    migliore di ognuno · più chiara: la stagione in corso · - - - fantamedia in carriera · Basketball-Reference (regular
    season, dal 1979-80), la stagione in corso dai tabellini ESPN, come /player])
}

// ── tabella ──
#pad(x: 60pt, bottom: 14pt, {
  set text(9pt)
  table(columns: (1fr, auto, 1fr), stroke: (x, y) => (bottom: 0.6pt + bordo), inset: (x: 8pt, y: 5pt), align: (right, center, left),
    ..d.tabella.map(r => (
      text(weight: if r.m == "a" { "bold" } else { "regular" }, fill: if r.m == "a" { ca_s } else { testo })[#r.a],
      text(7.5pt, fill: grigio, tracking: .5pt)[#upper(r.t)],
      text(weight: if r.m == "b" { "bold" } else { "regular" }, fill: if r.m == "b" { cb_s } else { testo })[#r.b])).flatten())
})
