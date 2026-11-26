// /pick ANNO [GIRO] (bot principale, anche loucabot; v7.22.0, mockup approvato da Luca il 22/11): tutte le pick di un
// draft, una riga per squadra a cui spettavano, chi ce l'ha adesso e le protezioni; stile /pick_lega.
// Dati in sys.inputs.dati (JSON, handlers/pick.dati_anno).
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
#let ng = dati.giri.len()
#set page(width: 380pt + ng * 120pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: inchiostro)
#let logo(s, d) = if s.at("logo", default: "") != "" {
  box(clip: true, radius: 50%, width: d, height: d, image(s.logo, width: d, height: d, fit: "cover"))
} else {
  box(width: d, height: d, radius: 50%, fill: rgb(s.colore), align(center + horizon, text(d * 0.42, weight: "bold", fill: white)[#s.sigla.clusters().first()]))
}
#let cella(x) = {
  if x.k == "nessuna" { (fill: none, body: []) }
  else if x.k == "usata" { let s = dati.squadre.at(x.a); (fill: usata, body: box(grid(columns: (auto, auto), column-gutter: 4pt, align: horizon,
    logo(s, 13pt), text(8pt, fill: grigio)[#x.usata · l'ha usata #s.nome]))) }
  else if x.k == "propria" { let s = dati.squadre.at(x.a); (fill: none, body: box(grid(columns: (auto, auto), column-gutter: 4pt, align: horizon, logo(s, 13pt), text(8pt, fill: grigio)[sua]))) }
  else { let s = dati.squadre.at(x.a); (fill: scambiata, body: box(grid(columns: (auto, auto), column-gutter: 4pt, align: horizon, logo(s, 13pt),
    stack(spacing: 1.5pt, text(8.5pt, weight: "bold")[#s.nome], if x.prot != "" { text(7pt, fill: oro, weight: "bold")[🛡 #x.prot] })))) }
}
#block(width: 100%, fill: gradient.linear(inchiostro, petrolio, angle: 0deg), inset: (x: 16pt, y: 12pt))[
  #grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
    [#text(17pt, weight: "bold", fill: white)[Pick del draft #dati.anno] \ #text(9pt, fill: white.transparentize(30%))[chi ha in mano la pick di ogni squadra#if ng == 1 [, #dati.giri.first()° giro] else [, 1° e 2° giro]]],
    text(8.5pt, fill: white.transparentize(30%))[#if dati.at("quando", default: "") != "" { text(weight: "bold", fill: white)[#dati.quando] } else [aggiornato al #dati.aggiornato]])
]
#pad(x: 12pt, top: 10pt, bottom: 4pt, table(
  columns: (auto,) + (1fr,) * ng + (auto,),
  align: (left + horizon,) + (left + horizon,) * ng + (center + horizon,),
  inset: (x: 6pt, y: 4pt),
  stroke: (x, y) => (bottom: if y == 0 { 1pt + petrolio } else { 0.5pt + bordo }, left: if x >= 1 { 0.4pt + bordo } else { 0pt }),
  fill: (x, y) => if y == 0 { petrolio_chiaro } else if calc.rem(y, 2) == 1 { riga2 } else { white },
  text(8pt, weight: "bold", fill: petrolio)[Pick di],
  ..dati.giri.map(g => text(8pt, weight: "bold", fill: petrolio)[#g° giro: ce l'ha]),
  text(8pt, weight: "bold", fill: petrolio)[In mano \ #dati.giri.map(g => [#g°]).join([ · ])],
  ..dati.righe.map(r => {
    let s = dati.squadre.at(r.team)
    let nome = (box(grid(columns: (auto, auto), column-gutter: 5pt, align: horizon, logo(s, 16pt), text(8.5pt, weight: "bold")[#s.nome])),)
    let celle = r.celle.map(x => { let y = cella(x); table.cell(fill: y.fill)[#y.body] })
    nome + celle + ([#r.mano.map(m => text(8.5pt, weight: "bold")[#m]).join(text(fill: grigio)[ · ])],)
  }).flatten(),
))
#pad(x: 14pt, top: 4pt, bottom: 10pt)[#text(7.5pt, fill: grigio)[
  #box(width: 9pt, height: 9pt, fill: scambiata, stroke: 0.4pt + bordo, radius: 1.5pt) ce l'ha un'altra squadra · «sua»: ce l'ha ancora lei ·
  #text(fill: oro, weight: "bold")[🛡] protezione · #box(width: 9pt, height: 9pt, fill: usata, stroke: 0.4pt + bordo, radius: 1.5pt) già usata (numero e giocatore) ·
  In mano = pick di quel draft che la squadra ha adesso, sue e di altri · storia di una pick con /pick SQUADRA GIRO ANNO]]
