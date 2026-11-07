// Classifica di un sistema di klra: come quella di loucabot (classifica.typ, verticale), con la banda del
// sistema e, se servono, le colonne P (pareggi) e PT (classifica a punti). Dati in sys.inputs.dati (JSON).
#let dati = json(bytes(sys.inputs.at("dati")))
#let c_head = rgb("#14213D")
#let c_sub = rgb("#FCA311")
#let c_r1 = rgb("#FFFFFF")
#let c_r2 = rgb("#EEF1F6")
#let c_line = rgb("#C9D1DE")
#let c_alt = rgb("#5B3FA0")
#let c_best = rgb("#1B8A4B")
#let c_worst = rgb("#C62828")
#set page(width: 440pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 10pt)

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
    #text(15pt, weight: "bold", fill: white)[#dati.titolo]
    #h(8pt)
    #text(9pt, fill: c_sub)[#dati.sotto]
  ]
]
#block(width: 100%, fill: c_alt)[#pad(x: 12pt, y: 5pt)[#text(9pt, weight: "bold", fill: white)[🧪 KLRA · #upper(dati.sistema)] #h(6pt) #text(8pt, fill: white.transparentize(20%))[#dati.regole]]]

#let striscia(s) = {
  let col = if s.ends-with("W") { c_best } else if s.ends-with("L") { c_worst } else { black }
  text(fill: col, weight: "bold")[#s]
}
#let logo(p) = if p != "" { image(p, width: 16pt, height: 16pt, fit: "contain") } else { [] }
#let intest(t) = text(7.5pt, weight: "bold", fill: white)[#t]
#let col(r, k, c) = {
  let s = r.at("col", default: (:)).at(k, default: "")
  if s == "best" { text(fill: c_best, weight: "bold")[#c] } else if s == "worst" { text(fill: c_worst, weight: "bold")[#c] } else { c }
}
#let colonne = (
  ("#", r => [#r.pos]), ("", r => logo(r.logo)), ("Squadra", r => text(weight: "bold")[#r.nome]),
  ("V", r => text(weight: if dati.punti { "regular" } else { "bold" })[#r.w]),
) + if dati.pareggi { (("P", r => [#r.p]),) } else { () } + (
  ("S", r => [#r.l]),
) + if dati.punti { (("PT", r => text(weight: "bold", fill: c_alt)[#r.pt]),) } else { () } + (
  ("PF", r => col(r, "pf", [#r.pf])), ("PS", r => col(r, "ps", [#r.ps])),
  ("Media", r => col(r, "media", [#r.media])), ("Striscia", r => striscia(r.striscia)),
)
#let colonne = if dati.at("cumulativa", default: false) { (
  ("#", r => [#r.pos]), ("", r => logo(r.logo)), ("Squadra", r => text(weight: "bold")[#r.nome]),
  ("PUNTI", r => text(weight: "bold", fill: c_alt)[#r.cumulati]), ("Media", r => [#r.media_cumulati]), ("G", r => [#r.g]),
) } else { colonne }
#let larghezze = colonne.enumerate().map(((i, c)) => if i == 2 { 1fr } else if i == 1 { 22pt } else { auto })
#table(
  columns: larghezze,
  stroke: (x, y) => (bottom: 0.5pt + c_line),
  inset: (x: 5pt, y: 4.5pt),
  align: (x, y) => if x == 2 { left + horizon } else { center + horizon },
  fill: (x, y) => if y == 0 { c_head } else if calc.odd(y) { c_r1 } else { c_r2 },
  table.header(..colonne.map(c => intest(c.at(0)))),
  ..dati.righe.map(r => colonne.map(c => (c.at(1))(r))).flatten(),
)
#block(width: 100%, fill: c_head)[
  #pad(x: 12pt, y: 5pt)[
    #set par(justify: false)
    #text(7pt, fill: white)[Risultati ricalcolati col sistema #dati.sistema sulle giornate convalidate dalla lega: quella vera resta la classifica di loucabot · #dati.ordine]
  ]
]
