// /quasi_cup (v7.9.0): qualificazione, tabellone con la finale in evidenza, premio. Dati da shared/quasi_cup.py (dati).
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#5F01D1")
#let viola_scuro = rgb("#39007D")
#let lilla = rgb("#EFE7FD")
#let lilla2 = rgb("#F7F3FE")
#let bordo = rgb("#E4DAF7")
#let grigio = rgb("#6B6480")
#let testo = rgb("#1D1630")
#let oro = rgb("#E0A21B")
#let oro_scuro = rgb("#8A5C00")
#let giallo_t = rgb("#FFD23F")
#let giallo = gradient.linear(rgb("#FFD23F"), rgb("#FF9F1C"), angle: 0deg)
#set page(width: 640pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: testo)

// logo tondo con anello; la sigla se manca
#let stemma(t, dd: 18pt, anello: white) = box(width: dd, height: dd, radius: 50%, clip: true,
  fill: rgb(t.colore), stroke: 1.2pt + anello,
  if t.logo != "" { image(t.logo, width: dd, height: dd, fit: "cover") }
  else { align(center + horizon, text(dd * 0.36, weight: "bold", fill: white)[#t.sigla]) })

#let badge(b) = if b == "LIVE" {
  box(fill: rgb("#E53935"), radius: 3pt, inset: (x: 4pt, y: 2pt), text(6pt, weight: "bold", fill: white)[● LIVE])
} else if b != "" {
  box(fill: grigio.transparentize(80%), radius: 3pt, inset: (x: 4pt, y: 2pt), text(6pt, weight: "bold", fill: grigio)[#b])
}

// ── testata ──
#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 18pt, y: 14pt))[
  #grid(columns: (auto, 1fr, auto), column-gutter: 12pt, align: horizon,
    text(30pt)[🏅],
    stack(spacing: 9pt,
      text(18pt, weight: "bold", fill: white)[Quasi NBA Cup #d.anno],
      text(8.5pt, fill: white.transparentize(20%))[#d.fase]),
    if d.chip != none {
      box(fill: giallo, radius: 6pt, inset: (x: 10pt, y: 6pt),
        stack(spacing: 5pt, text(6.5pt, weight: "bold", fill: viola_scuro.transparentize(20%), tracking: 0.6pt)[#upper(d.chip.t)],
          text(12pt, weight: "bold", fill: viola_scuro)[#d.chip.v]))
    })
]

// ── tabellone: SF1 · FINALE · SF2 ──
#let riga_sf(t) = box(width: 100%, radius: 4pt, inset: 2pt, fill: if t.avanti { rgb("#FFF1C2") } else { none },
  grid(columns: (auto, 1fr, auto), column-gutter: 5pt, align: horizon,
    stemma(t, dd: 20pt, anello: if t.avanti { oro } else { bordo }),
    [#text(8.5pt, weight: "bold")[#t.nome] #text(6.5pt, weight: "bold", fill: grigio)[#t.seed]],
    if t.punti != "" {
      align(right, stack(spacing: 2pt, text(11pt, weight: "bold", fill: if t.avanti { viola } else { grigio })[#t.punti],
        if t.supp != "" { text(6pt, fill: grigio)[#t.supp] }))
    }))
#let semi(x) = block(width: 100%, radius: 7pt, fill: lilla2, stroke: 0.7pt + bordo, inset: 8pt)[
  #align(center)[#text(7pt, weight: "bold", fill: viola, tracking: 0.5pt)[#upper(x.titolo)] \ #text(6.5pt, fill: grigio)[#x.quando]
    #if x.badge != "" [ \ #badge(x.badge)]]
  #v(7pt)
  #riga_sf(x.righe.at(0)) #v(4pt) #align(center, text(6.5pt, weight: "bold", fill: grigio)[vs]) #v(4pt) #riga_sf(x.righe.at(1))]
#let semi_vuota(k) = block(width: 100%, radius: 7pt, fill: lilla2, stroke: 0.7pt + bordo, inset: 8pt)[
  #align(center)[#text(7pt, weight: "bold", fill: viola, tracking: 0.5pt)[SEMIFINALE #k] \ #v(8pt)
    #text(7.5pt, fill: grigio)[ancora nessuna squadra in classifica]]]
#let freccia(s) = align(center + horizon, text(14pt, fill: oro)[#s])

#let posto_vuoto(etichetta) = stack(spacing: 4pt,
  box(width: 30pt, height: 30pt, radius: 50%, stroke: (paint: white.transparentize(40%), thickness: 1.2pt, dash: "dashed"),
    align(center + horizon, text(12pt, weight: "bold", fill: white.transparentize(40%))[?])),
  text(7pt, fill: white.transparentize(20%))[#etichetta])
#let finalista(t) = stack(spacing: 4pt,
  align(center, stemma(t, dd: 34pt, anello: if t.avanti { giallo_t } else { white.transparentize(50%) })),
  text(8pt, weight: "bold", fill: white)[#t.nome],
  if t.punti != "" { text(13pt, weight: "bold", fill: if t.avanti { giallo_t } else { white.transparentize(30%) })[#t.punti] },
  if t.supp != "" { text(6pt, fill: white.transparentize(30%))[#t.supp] })
#let f = d.finale
#let finale = block(width: 100%, radius: 10pt, fill: giallo, inset: 3pt,
  block(width: 100%, radius: 8pt, fill: viola_scuro, inset: (x: 10pt, y: 12pt))[
    #align(center)[
      #text(30pt)[🏆] \
      #v(2pt)
      #text(15pt, weight: "bold", fill: giallo_t, tracking: 1.5pt)[FINALE] \
      #v(3pt)
      #text(8pt, fill: white.transparentize(15%))[#f.quando]
      #if f.badge == "LIVE" [ \ #v(2pt) #badge(f.badge)] else if f.badge != "" [ \ #v(2pt)
        #box(fill: white.transparentize(80%), radius: 3pt, inset: (x: 4pt, y: 2pt), text(6pt, weight: "bold", fill: white)[#f.badge])]
      #v(10pt)
      #if f.campione != none [
        #stemma(f.campione, dd: 40pt, anello: giallo_t) \
        #v(4pt)
        #text(12pt, weight: "bold", fill: white)[#f.campione.nome] \
        #v(2pt)
        #text(8pt, weight: "bold", fill: giallo_t, tracking: 1.2pt)[CAMPIONE]
        #v(8pt)
      ]
      #if f.righe.len() == 2 {
        grid(columns: (1fr, auto, 1fr), align: horizon, column-gutter: 6pt,
          finalista(f.righe.at(0)), text(9pt, weight: "bold", fill: giallo_t)[vs], finalista(f.righe.at(1)))
      } else {
        grid(columns: (1fr, auto, 1fr), align: horizon, column-gutter: 6pt,
          posto_vuoto[vincente SF1], text(9pt, weight: "bold", fill: giallo_t)[vs], posto_vuoto[vincente SF2])
      }
    ]])

#block(width: 100%, fill: lilla, inset: (x: 14pt, top: 12pt, bottom: 14pt))[
  #align(center, text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[TABELLONE · #upper(d.tab_nota)])
  #v(10pt)
  #grid(columns: (1fr, 14pt, 1.25fr, 14pt, 1fr), align: horizon,
    if d.semi.len() > 0 { semi(d.semi.at(0)) } else { semi_vuota(1) },
    freccia[▶],
    finale,
    freccia[◀],
    if d.semi.len() > 1 { semi(d.semi.at(1)) } else { semi_vuota(2) })
]

// ── qualificazione: le prime 4 a sinistra, le altre a destra ──
#let riga_q(i, r) = {
  let su = i < 4
  grid(columns: (12pt, 22pt, 1fr, auto), column-gutter: 5pt, align: horizon,
    text(8pt, weight: "bold", fill: if su { viola } else { grigio })[#(i + 1)],
    stemma(r, dd: 20pt, anello: if su { oro } else { bordo }),
    [#text(8.5pt, weight: if su { "bold" } else { "regular" }, fill: if su { testo } else { grigio })[#r.nome] \
     #text(6.5pt, fill: grigio)[#r.dove · 2° #r.secondo]],
    text(11pt, weight: "bold", fill: if su { viola } else { grigio })[#r.max])
}
#let colonna(titolo, righe, base, su) = block(width: 100%, radius: 7pt,
  fill: if su { rgb("#FFF8E6") } else { white }, stroke: if su { 1pt + oro } else { 0.7pt + bordo }, inset: 8pt)[
  #text(6.5pt, weight: "bold", fill: if su { oro_scuro } else { grigio }, tracking: 0.5pt)[#upper(titolo)]
  #v(5pt)
  #stack(spacing: 6pt, ..righe.enumerate().map(((k, r)) => riga_q(base + k, r)))]

#block(width: 100%, inset: (x: 14pt, top: 12pt, bottom: 4pt))[
  #text(7pt, weight: "bold", fill: grigio, tracking: 0.7pt)[QUALIFICAZIONE · MIGLIOR PUNTEGGIO DI GIORNATA]
  #h(1fr) #text(7pt, fill: grigio)[#d.finestra]
  #v(7pt)
  #let cl = d.classifica
  #grid(columns: (1fr, 1fr), column-gutter: 10pt,
    colonna(d.q_titoli.at(0), cl.slice(0, calc.min(4, cl.len())), 0, true),
    if cl.len() > 4 { colonna(d.q_titoli.at(1), cl.slice(4), 4, false) })
  #v(5pt)
  #text(6.5pt, fill: grigio)[A pari miglior punteggio passa chi ha il secondo miglior punteggio più alto. Bonus casa compreso, supplementari no.]
]

// ── premio, centrato: due voci affiancate ──
#block(width: 100%, inset: (x: 14pt, top: 10pt, bottom: 14pt))[
  #block(width: 100%, radius: 9pt, fill: giallo, inset: (x: 14pt, y: 10pt))[
    #align(center, text(7.5pt, weight: "bold", fill: viola_scuro.transparentize(15%), tracking: 1.5pt)[🎁 PREMIO ALLA VINCITRICE])
    #v(9pt)
    #grid(columns: (1fr, 1fr), column-gutter: 10pt, align: center,
      stack(spacing: 6pt, text(11pt, weight: "bold", fill: viola_scuro)[Un cambio ruolo in più],
        text(7pt, fill: viola_scuro)[esclusivo della Cup, per il resto della stagione]),
      stack(spacing: 6pt, text(11pt, weight: "bold", fill: viola_scuro)[Vince ogni spareggio per il seed],
        text(7pt, fill: viola_scuro)[nella classifica di regular season, verso i playoff]))
  ]
  #v(6pt)
  #align(center, text(6.5pt, fill: grigio)[Semifinali (Q1) e finale (Q2) come una partita normale, con le formazioni della giornata: in casa la meglio classificata, col bonus casa.])
]
