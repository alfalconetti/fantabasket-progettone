// Tutte le pick della lega (bot principale, /pick_lega, v7.3.0, mockup approvato da Luca il 09/11, variante A):
// una riga per squadra (quella a cui spetta la pick in origine), per ogni anno del draft due caselle (1° e 2° giro)
// con logo e sigla di chi ce l'ha adesso: in grigio se ce l'ha ancora lei, in grassetto su fondo chiaro se è di
// un'altra squadra. * = protetta, grigio col numero = già usata. Dati in sys.inputs.dati (JSON, handlers/pick.py).
#let dati = json(bytes(sys.inputs.at("dati")))

#let inchiostro = rgb("#14232B")
#let petrolio = rgb("#0E4C5A")
#let petrolio_chiaro = rgb("#E3EEF0")
#let riga2 = rgb("#F5F8F9")
#let bordo = rgb("#C9D8DC")
#let grigio = rgb("#6E7F86")
#let oro = rgb("#C8962E")
#let scambiata = rgb("#FFF4DC")
#let usata = rgb("#ECECEC")

#let anni = dati.anni
#let na = anni.len()
#set page(width: 200pt + 2 * na * 52pt + 70pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: inchiostro)

#let logo(s, d) = if s.at("logo", default: "") != "" {
  box(clip: true, radius: 50%, width: d, height: d, image(s.logo, width: d, height: d, fit: "cover"))
} else {
  box(width: d, height: d, radius: 50%, fill: rgb(s.colore), align(center + horizon, text(d * 0.42, weight: "bold", fill: white)[#s.sigla.clusters().first()]))
}

#let cella(c) = {
  if c.k == "propria" { let s = dati.squadre.at(c.a); (fill: none, body: box(grid(columns: (auto, auto), column-gutter: 3pt, align: horizon, box(logo(s, 13pt)), text(7.5pt, fill: grigio)[#s.sigla]))) }
  else if c.k == "usata" { (fill: usata, body: text(fill: grigio, size: 7.5pt)[\##c.num]) }
  else if c.k == "nessuna" { (fill: none, body: []) }
  else {
    let s = dati.squadre.at(c.a)
    (fill: scambiata, body: box(grid(columns: (auto, auto), column-gutter: 3pt, align: horizon,
      logo(s, 13pt), text(7.5pt, weight: "bold")[#s.sigla#if c.prot { text(fill: oro)[\*] }])))
  }
}

#block(width: 100%, fill: gradient.linear(inchiostro, petrolio, angle: 0deg), inset: (x: 16pt, y: 12pt))[
  #grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
    [#text(17pt, weight: "bold", fill: white)[Pick della lega] \ #text(9pt, fill: white.transparentize(30%))[draft #anni.first()–#anni.last() · chi ha in mano la pick di ogni squadra]],
    text(8.5pt, fill: white.transparentize(30%))[aggiornato al #dati.aggiornato])
]

#pad(x: 12pt, top: 10pt, bottom: 4pt, table(
  columns: (auto,) + (1fr,) * (2 * na) + (auto,),
  align: (left + horizon,) + (center + horizon,) * (2 * na) + (center + horizon,),
  inset: (x: 4pt, y: 4pt),
  stroke: (x, y) => (
    bottom: if y == 1 { 1pt + petrolio } else { 0.5pt + bordo },
    left: if x >= 1 and calc.rem(x - 1, 2) == 0 { 1pt + petrolio.transparentize(50%) } else if x >= 1 { 0.4pt + bordo } else { 0pt },
  ),
  fill: (x, y) => if y <= 1 { petrolio_chiaro } else if calc.rem(y, 2) == 1 { riga2 } else { white },
  // intestazione: anni su due colonne, poi 1° e 2°
  table.cell(rowspan: 2, align: left + bottom)[#text(8pt, weight: "bold", fill: petrolio)[Pick di]],
  ..anni.map(a => table.cell(colspan: 2)[#text(9pt, weight: "bold", fill: petrolio)[#a]]),
  table.cell(rowspan: 2, align: center + bottom)[#text(8pt, weight: "bold", fill: petrolio)[In mano \ 1° · 2°]],
  ..anni.map(_ => ([#text(7.5pt, fill: grigio)[1°]], [#text(7.5pt, fill: grigio)[2°]])).flatten(),
  ..dati.righe.map(r => {
    let s = dati.squadre.at(r.team)
    let nome = (box(grid(columns: (auto, auto), column-gutter: 5pt, align: horizon, logo(s, 16pt), text(8.5pt, weight: "bold")[#s.nome])),)
    let celle = r.celle.map(c => { let x = cella(c); table.cell(fill: x.fill)[#x.body] })
    let mano = ([#text(8.5pt, weight: "bold")[#r.mano1] #text(fill: grigio)[·] #text(8.5pt, weight: "bold")[#r.mano2]],)
    nome + celle + mano
  }).flatten(),
))

#pad(x: 14pt, top: 4pt, bottom: 10pt)[
  #text(7.5pt, fill: grigio)[
    #box(width: 9pt, height: 9pt, fill: scambiata, stroke: 0.4pt + bordo, radius: 1.5pt) ce l'ha un'altra squadra (logo e sigla) ·
    logo e sigla in grigio: ce l'ha ancora lei ·
    #text(fill: oro, weight: "bold")[\*] protetta ·
    #box(width: 9pt, height: 9pt, fill: usata, stroke: 0.4pt + bordo, radius: 1.5pt) già usata (numero della scelta) ·
    In mano = pick che la squadra ha adesso per ogni giro, sue e di altri · storia di una pick con /pick SQUADRA GIRO ANNO]
]
