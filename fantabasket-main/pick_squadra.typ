// /pick SQUADRA [ANNO] [GIRO] (bot principale, anche loucabot; v7.22.0, mockup approvato da Luca il 22/11): le pick che
// una squadra ha in mano, draft per draft e giro, coi colori della sua palette (/palette, come il roster), e le sue
// pick cedute. Dati in sys.inputs.dati (JSON, handlers/pick.dati_squadra).
#let dati = json(bytes(sys.inputs.at("dati")))
#let c = dati.colori
#let header = rgb(c.header)
#let dark = rgb(c.dark)
#let r1 = rgb(c.riga1)
#let r2 = rgb(c.riga2)
#let sez = rgb(c.sezione)
#let chip = rgb(c.pick)
#let grigio = rgb("#6E7F86")
#let oro = rgb("#C8962E")
#let usata = rgb("#ECECEC")
#let me = dati.squadre.at(dati.team)
#let ng = dati.giri.len()
#set page(width: 380pt + ng * 120pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: rgb("#14232B"))

#let logo(s, d) = if s.at("logo", default: "") != "" {
  box(clip: true, radius: 50%, width: d, height: d, image(s.logo, width: d, height: d, fit: "cover"))
} else {
  box(width: d, height: d, radius: 50%, fill: rgb(s.colore), stroke: 0.8pt + white, align(center + horizon, text(d * 0.42, weight: "bold", fill: white)[#s.sigla.clusters().first()]))
}

// una pick in mano: logo e nome di chi la cedeva (o «propria»), protezione, o il numero e il giocatore se è già usata
#let pick(p) = {
  let s = dati.squadre.at(p.orig)
  let fondo = if p.usata != "" { usata } else if p.propria { r2 } else { chip }
  let testo = if p.usata != "" { rgb("#14232B") } else if p.propria { rgb(c.t_riga2) } else { rgb(c.t_pick) }
  box(fill: fondo, stroke: 0.6pt + header.transparentize(55%), radius: 4pt, inset: (x: 6pt, y: 4pt),
    grid(columns: (auto, auto), column-gutter: 5pt, align: horizon,
      logo(s, 15pt),
      stack(spacing: 2pt,
        text(8.5pt, weight: "bold", fill: testo)[#if p.propria [propria] else [di #s.nome]],
        if p.usata != "" { text(7pt, fill: grigio)[usata: #p.usata] }
        else if p.prot != "" { text(7pt, fill: oro, weight: "bold")[🛡 protetta #p.prot] }
        else { text(7pt, fill: testo.transparentize(35%))[libera] })))
}

#let ceduta(p) = {
  let s = dati.squadre.at(p.a)
  box(inset: (y: 2pt), grid(columns: (auto, auto, auto), column-gutter: 4pt, align: horizon,
    text(8pt, fill: grigio)[#p.giro° giro →], logo(s, 12pt),
    text(8pt)[#s.nome#if p.usata != "" { text(fill: grigio)[ · usata #p.usata] } else if p.prot != "" { text(fill: oro)[ · #p.prot] }]))
}

#block(width: 100%, fill: gradient.linear(header, dark, angle: 0deg), inset: (x: 16pt, y: 12pt))[
  #grid(columns: (auto, 1fr, auto), column-gutter: 10pt, align: (horizon, left + horizon, right + horizon),
    logo(me, 40pt),
    [#text(17pt, weight: "bold", fill: rgb(c.t_header))[Le pick di #me.nome] \ #text(9pt, fill: rgb(c.t_header_m))[#dati.titolo]],
    text(8.5pt, fill: rgb(c.t_header_m))[aggiornato al #dati.aggiornato])
]

#show table.cell: it => {
  if it.y == 0 { it } else { set text(fill: if calc.rem(it.y, 2) == 1 { rgb(c.t_riga1) } else { rgb(c.t_riga2) }); it }
}
#pad(x: 12pt, top: 10pt, bottom: 4pt, table(
  columns: (46pt,) + (1fr,) * ng + (150pt,),
  align: (center + horizon,) + (left + horizon,) * ng + (left + horizon,),
  inset: (x: 6pt, y: 6pt),
  stroke: (x, y) => (bottom: 0.5pt + header.transparentize(70%), left: if x > 0 { 0.4pt + header.transparentize(70%) } else { 0pt }),
  fill: (x, y) => if y == 0 { sez } else if calc.rem(y, 2) == 1 { r1 } else { r2 },
  text(8pt, weight: "bold", fill: rgb(c.t_sezione))[Draft],
  ..dati.giri.map(g => text(8pt, weight: "bold", fill: rgb(c.t_sezione))[#g° giro]),
  text(8pt, weight: "bold", fill: rgb(c.t_sezione))[Le sue, cedute],
  ..dati.righe.map(r => (
    (text(12pt, weight: "bold")[#r.anno],)
    + r.giri.map(l => if l.len() == 0 { text(8pt, fill: grigio)[nessuna] } else { stack(spacing: 4pt, ..l.map(pick)) })
    + (if r.cedute.len() == 0 { text(8pt, fill: grigio)[—] } else { stack(spacing: 2pt, ..r.cedute.map(ceduta)) },)
  )).flatten(),
))

#block(width: 100%, fill: dark, inset: (x: 14pt, y: 7pt))[
  #text(7.5pt, fill: rgb(c.t_dark))[«propria»: la sua pick, ancora sua · «di …»: presa da un'altra squadra · 🛡 protetta: se esce in quelle posizioni torna a chi l'ha ceduta · la storia di una pick: /pick SQUADRA GIRO ANNO (la squadra a cui spettava)]
]
