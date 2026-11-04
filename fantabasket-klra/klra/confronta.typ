// /confronta di klra (mockup approvato da Luca il 04/11): classifica col sistema accanto a quella ufficiale,
// poi le partite che cambiano esito. Dati in sys.inputs.dati (JSON).
#let dati = json(bytes(sys.inputs.at("dati")))
#let c_head = rgb("#14213D")
#let c_sub = rgb("#FCA311")
#let c_r2 = rgb("#EEF1F6")
#let c_line = rgb("#C9D1DE")
#let c_su = rgb("#1B8A4B")
#let c_giu = rgb("#C62828")
#let c_alt = rgb("#5B3FA0")
#let c_grigio = rgb("#5A6478")
#set page(width: 520pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9.5pt)

// klra (sistemi di punteggio alternativi, v7.0.0): filigrana «NON UFFICIALE» e striscia rossa in cima, solo se nei dati
#let _filigrana = dati.at("filigrana", default: "")
#set page(foreground: if _filigrana != "" {
  // una scritta ogni 450pt circa di altezza (le immagini corte ne hanno una sola, /partita tre)
  layout(sz => {
    let n = calc.max(1, calc.floor(sz.height / 450pt))
    for i in range(n) { place(center + horizon, dy: sz.height * ((i + 0.5) / n - 0.5),
      rotate(-22deg, text(50pt, weight: "bold", fill: rgb("#C0392B").transparentize(84%))[#_filigrana])) }
  })
})
#if dati.at("striscia", default: "") != "" {
  block(width: 100%, fill: rgb("#C0392B"), inset: (x: 14pt, y: 6pt), align(center, text(9pt, weight: "bold", fill: white)[#dati.striscia]))
}

#block(width: 100%, fill: c_head)[
  #pad(x: 12pt, y: 9pt)[
    #text(15pt, weight: "bold", fill: white)[⚖️ Ufficiale #text(fill: c_sub)[vs] #dati.sistema]
    #h(8pt) #text(9pt, fill: c_sub)[#dati.sotto]
    #if dati.regole != "" [
      #v(4pt)
      #text(8.5pt, fill: rgb("#D9DEE8"))[#dati.regole]
    ]
  ]
]
#let freccia(d) = if d > 0 { text(fill: c_su, weight: "bold")[▲#d] } else if d < 0 { text(fill: c_giu, weight: "bold")[▼#(-d)] } else { text(fill: rgb("#8A93A6"))[=] }
#let logo(p) = if p != "" { image(p, width: 14pt, height: 14pt, fit: "contain") } else { [] }
#let h8(t, c: black) = text(8pt, weight: "bold", fill: c)[#t]
#let colonne_alt = (("V-S", r => [#r.rec]), ("supp.", r => [#r.supp])) + if dati.punti { (("PUNTI", r => text(weight: "bold", fill: c_alt)[#r.pt]),) } else { () }
#block(width: 100%)[
  #table(
    columns: (22pt, 30pt, 18pt, 1fr, 62pt, 8pt) + colonne_alt.map(_ => 46pt),
    stroke: (x, y) => if y == 1 { (bottom: 0.6pt + c_line) } else { none },
    fill: (x, y) => if y < 2 { white } else if calc.even(y) { c_r2 } else { white },
    inset: (x: 5pt, y: 4pt),
    align: (x, y) => if x == 3 { left + horizon } else { center + horizon },
    table.cell(colspan: 4)[], table.cell(fill: rgb("#E6E9F0"))[#h8[UFFICIALE]], [],
    table.cell(colspan: colonne_alt.len(), fill: rgb("#ECE6F7"))[#h8(upper(dati.sistema), c: c_alt)],
    h8[\#], h8[±], [], h8[Squadra], h8[pos · V-S], [], ..colonne_alt.map(c => h8(c.at(0), c: c_alt)),
    ..dati.righe.map(r => (
      text(weight: "bold")[#r.pos], freccia(r.diff), logo(r.logo), text(weight: "bold")[#r.nome],
      text(fill: c_grigio)[#r.pos_uff#super[a] · #r.rec_uff], [],
      ..colonne_alt.map(c => (c.at(1))(r)),
    )).flatten(),
  )
]
#block(width: 100%, fill: c_head)[#pad(x: 12pt, y: 6pt)[#text(10.5pt, weight: "bold", fill: white)[Partite che cambiano esito: #dati.cambiano.len() su #dati.partite]]]
#if dati.cambiano.len() > 0 {
  block(width: 100%, table(
    columns: (24pt, 1fr, 92pt, 1fr, 80pt, 84pt),
    stroke: (x, y) => if y == 0 { (bottom: 0.6pt + c_line) } else { none },
    fill: (x, y) => if y > 0 and calc.even(y) { c_r2 } else { white },
    inset: (x: 5pt, y: 4pt),
    align: (x, y) => if x == 1 { right + horizon } else if x == 3 { left + horizon } else { center + horizon },
    h8[G], h8[Casa], h8(dati.sistema, c: c_alt), h8[Trasferta], h8[Ufficiale], h8(dati.sistema, c: c_alt),
    ..dati.cambiano.map(x => (
      [G#x.giornata], text(weight: "bold")[#x.casa], [#x.punti], [#x.trasferta],
      text(fill: c_grigio)[#x.prima], text(weight: "bold", fill: c_alt)[#x.dopo],
    )).flatten(),
  ))
} else {
  block(width: 100%, pad(x: 12pt, y: 8pt, text(fill: c_grigio)[Nessuna: tutte le partite finiscono come nella realtà.]))
}
#block(width: 100%, fill: rgb("#F6F7FA"))[#pad(x: 12pt, y: 7pt)[#text(8pt, fill: c_grigio)[
  ± = posizioni guadagnate o perse rispetto all'Ufficiale · i punteggi sono quelli col sistema #dati.sistema, bonus casa compreso · solo le giornate convalidate dalla lega
]]]
