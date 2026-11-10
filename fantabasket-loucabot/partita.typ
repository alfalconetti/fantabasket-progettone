// Una sfida del fantabasket (loucabot, partita.py → /partita): verticale, tinte viola (Yahoo).
// Dati in sys.inputs.dati (JSON).
#let dati = json(bytes(sys.inputs.at("dati")))

#let viola = rgb("#5F01D1")        // il viola di Yahoo
#let viola_scuro = rgb("#39007D")
#let viola_medio = rgb("#7B3FE4")
#let lilla = rgb("#EFE7FD")        // righe chiare
#let lilla2 = rgb("#F7F3FE")
#let bordo = rgb("#D6C8F5")
#let grigio = rgb("#6B6480")
#let verde = rgb("#1B8A4B")
#let arancio = rgb("#C26A00")
#let rosso = rgb("#C0392B")

#set page(width: 560pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9.5pt, fill: rgb("#1D1630"))

#let logo(s, d) = if s.logo != "" {
  box(clip: true, radius: 50%, width: d, height: d, image(s.logo, width: d, height: d, fit: "cover"))
} else {
  box(width: d, height: d, radius: 50%, fill: white.transparentize(75%),
    align(center + horizon, text(size: d * 0.36, weight: "bold", fill: white)[#s.nome.clusters().first()]))
}

// ── tabellone ──
#let a = dati.squadre.at(0)
#let b = dati.squadre.at(1)
// chi vince alla fine (calcolata o convalidata) in grassetto, l'altra squadra no
#let finale = dati.stato == "convalidata" or dati.stato == "calcolata"
#let peso(s) = if not finale or s.vince { "bold" } else { "regular" }
#let lato(s, dx) = {
  let nome = [#text(13pt, weight: peso(s), fill: white)[#s.nome] \ #text(8.5pt, fill: white.transparentize(30%))[#if s.gm != "" [GM #s.gm · ]#if s.lato == "casa" [casa] else [trasferta]]]
  // record W-L della stagione sotto il logo (Luca, 09/11): campo facoltativo
  let rec = s.at("record", default: "")
  let prima = s.at("record_prima", default: "")
  let lg = if rec != "" { stack(spacing: 4pt, align(center, logo(s, 40pt)),
    align(center, text(9pt, weight: "bold", fill: white.transparentize(15%), tracking: 0.3pt)[#rec]),
    ..(if prima != "" { (align(center, box(width: 58pt, align(center, text(6.5pt, fill: white.transparentize(30%))[prima di questa partita: #text(weight: "bold")[#prima]]))),) } else { () })) } else { logo(s, 40pt) }
  if dx { grid(columns: (1fr, auto), column-gutter: 8pt, align: (right + horizon, horizon), align(right, nome), lg) }
  else { grid(columns: (auto, 1fr), column-gutter: 8pt, align: horizon, lg, nome) }
}
#let punti(s) = text(28pt, weight: peso(s), fill: if dati.stato == "da giocare" { white.transparentize(40%) } else if s.vince or not finale { white } else { white.transparentize(30%) })[#if dati.stato == "da giocare" [–] else [#s.punti]]
#let etichetta(t, c) = box(fill: c, radius: 4pt, inset: (x: 6pt, y: 2.5pt))[#text(8pt, weight: "bold", fill: white)[#t]]

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

#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 14pt, y: 12pt))[
  #align(center)[#text(9pt, weight: "bold", fill: white.transparentize(25%), tracking: 0.6pt)[#upper(dati.titolo) · #dati.date]]
  #v(12pt)
  #grid(columns: (1fr, auto, 1fr), column-gutter: 10pt, align: horizon,
    lato(a, false),
    align(center)[
      #punti(a) #h(4pt) #text(22pt, fill: white.transparentize(50%))[–] #h(4pt) #punti(b)
      // supplementari: centrati sotto i regolamentari, più piccoli ma leggibili (Luca, 23/10)
      #if dati.supplementari > 0 [
        #v(-6pt)
        #text(8pt, weight: "bold", fill: white.transparentize(30%), tracking: 0.5pt)[SUPPLEMENTARI#if dati.supplementari > 1 [ ×#dati.supplementari]] \
        #text(16pt, weight: peso(a), fill: white)[#a.supp] #h(3pt) #text(13pt, fill: white.transparentize(50%))[–] #h(3pt) #text(16pt, weight: peso(b), fill: white)[#b.supp]
      ]
    ],
    lato(b, true))
  #v(8pt)
  #align(center, {
    // klra (sistemi di punteggio alternativi): al posto dello stato, il nome del sistema
    if dati.at("sistema", default: "") != "" { etichetta("NON UFFICIALE · KLRA · " + upper(dati.sistema), rosso) }
    else if dati.stato == "convalidata" { etichetta("CONVALIDATA", verde) }
    else if dati.stato == "calcolata" { etichetta("CALCOLATA · DA CONVALIDARE", arancio) }
    else if dati.stato == "in corso" { etichetta("IN CORSO · PROVVISORIO", rosso) }
    else { etichetta("DA GIOCARE", viola_medio) }
    // quando sono stati scaricati gli ultimi tabellini della giornata (Luca, 01/11)
    if dati.at("dati_alle", default: "") != "" { block(above: 4pt, text(7.5pt, fill: white.transparentize(30%))[#dati.dati_alle]) }
  })
]

// squadre NBA che prendono la media nella giornata: subito sotto il tabellone (Luca, 23/10)
#if dati.media_nba != "" {
  block(width: 100%, fill: rgb("#FFF3E0"), inset: (x: 14pt, y: 7pt), stroke: (bottom: 0.5pt + rgb("#F0C890")))[
    #text(9pt, fill: arancio, weight: "bold")[PRENDONO LA MEDIA IN QUESTA GIORNATA] #h(6pt)
    #text(9pt, fill: rgb("#5A3A00"))[#dati.media_nba (squadre NBA senza partite: i loro giocatori prendono la media della stagione)]
  ]
}

// ── una squadra ──
#let cella(c) = {
  if c.k == "fp" { text(weight: "bold")[#c.t] }
  else if c.k == "live" { text(weight: "bold", fill: rosso)[#c.t] }
  else if c.k == "dnp" { text(fill: grigio)[DNP] }
  else if c.k == "prossima" {        // con l'orario di Roma sotto (Luca, 11/11)
    let o = c.at("o", default: "")
    if o != "" { [#text(fill: viola_medio, size: 8.5pt)[#c.t] \ #text(fill: grigio, size: 7pt)[#o]] } else { text(fill: viola_medio, size: 8.5pt)[#c.t] }
  }
  else if c.k == "rinviata" { text(fill: arancio, size: 8.5pt)[#c.t] }
  else { [] }
}
#let conta-base(r) = {
  let t = r.tag
  if t == "esce" { text(fill: grigio)[↓ FADD] }
  else if t == "entra" { text(fill: verde, weight: "bold")[↑ #r.conta] }
  else if t == "media" { text(fill: arancio, weight: "bold")[#r.conta #text(7pt)[MEDIA]] }
  else if t.starts-with("S") { text(fill: viola, weight: "bold")[#r.conta #text(7pt)[#t]] }
  else if t == "ceduto" { text(fill: grigio, size: 8pt)[ceduto] }
  else if t == "doppio" { text(fill: grigio)[0 #text(7pt)[ANCHE TITOLARE]] }
  else if t == "vuoto" { text(fill: grigio)[0 #text(7pt)[VUOTO]] }
  else { text(weight: "bold")[#r.conta] }
}
#let conta(r) = {
  let t = r.tag
  // klra: i bonus del sistema accanto ai punti (es. +5 TD)
  let bonus = r.at("bonus", default: "")
  if bonus != "" and t != "esce" and t != "ceduto" and t != "vuoto" { return [#conta-base(r) #text(6.5pt, fill: viola, weight: "bold")[#bonus]] }
  conta-base(r)
}

#let squadra(s) = {
  let nn = dati.notti.len()
  block(width: 100%, inset: (x: 14pt, top: 12pt, bottom: 6pt))[
    #grid(columns: (auto, 1fr), column-gutter: 8pt, align: horizon,
      box(width: 5pt, height: 16pt, fill: viola, radius: 2pt),
      [#text(12pt, weight: "bold")[#s.nome] #h(4pt) #text(8.5pt, fill: grigio)[#if s.lato == "casa" [casa] else [trasferta]]])
  ]
  pad(x: 14pt, table(
    columns: (24pt, 1fr, 30pt, 38pt) + (50pt,) * nn + (64pt,),
    align: (center + horizon, left + horizon, center + horizon, center + horizon) + (center + horizon,) * nn + (right + horizon,),
    inset: (x: 5pt, y: 4pt),
    stroke: (x, y) => (
      bottom: if y == 0 { 1pt + viola } else { 0.5pt + bordo },
      left: if x == 4 or x == 4 + nn { 1.5pt + viola.transparentize(40%) } else { 0pt },
    ),
    fill: (x, y) => if y == 0 { lilla } else if x >= 4 and x < 4 + nn { lilla2 } else { white },
    ..([], [Giocatore], [NBA], [Media]).map(t => text(7.5pt, weight: "bold", fill: viola_scuro)[#t]),
    ..dati.notti.map(t => text(7.5pt, weight: "bold", fill: viola_scuro)[#t]),
    text(7.5pt, weight: "bold", fill: viola_scuro)[Punti \ effettivi],
    ..s.righe.enumerate().map(((i, r)) => {
      let sep = if i == 5 { (table.cell(colspan: 5 + nn, fill: lilla, inset: (x: 5pt, y: 3pt))[#text(7pt, weight: "bold", fill: viola_scuro, tracking: 0.5pt)[PANCHINA]],) } else { () }
      let nome = if r.tag == "esce" { text(fill: grigio)[#strike[#r.nome]] } else if r.titolare or r.tag == "entra" { text(weight: "bold")[#r.nome] } else { [#r.nome] }
      let nome = if r.at("ruolo", default: "") != "" { [#nome #text(8pt, fill: grigio)[(#r.ruolo)]] } else { nome }
      // lo status dell'ultimo report infortuni (Luca, 11/11), finché la giornata si gioca
      let nome = if r.at("inf", default: "") != "" {
        let c = if r.inf_k == "out" { rosso } else { arancio }
        [#nome #h(3pt) #box(fill: c.transparentize(85%), stroke: 0.5pt + c, radius: 2pt, inset: (x: 3pt, y: 1.5pt), baseline: 1.5pt)[#text(6.5pt, weight: "bold", fill: c)[#r.inf]]]
      } else { nome }
      // headshot ESPN tondo accanto al nome (Luca, 23/10): la foto è un mezzo busto largo (520×380).
      // 24/10: meno ingrandita (si vede tutta la testa) e alzata di un filo; senza foto le iniziali
      let testa = if r.at("foto", default: "") != "" {
        box(width: 20pt, height: 20pt, radius: 50%, clip: true, fill: lilla, stroke: 0.6pt + bordo,
          place(top + left, dx: -6.4pt, dy: -1pt, image(r.foto, height: 24pt, width: 32.8pt)))
      } else {
        box(width: 20pt, height: 20pt, radius: 50%, fill: lilla, stroke: 0.6pt + bordo,
          align(center + horizon, text(7pt, weight: "bold", fill: viola)[#r.nome.split(" ").filter(p => p != "").map(p => p.clusters().first()).slice(0, calc.min(2, r.nome.split(" ").filter(p => p != "").len())).join()]))
      }
      // tondo e nome in una griglia centrata in verticale: con la foto e con le iniziali il nome sta alla
      // stessa altezza (prima, col box spostato sulla linea del testo, con le iniziali saliva)
      let nome = grid(columns: (auto, 1fr), column-gutter: 6pt, align: (center + horizon, left + horizon), testa, nome)
      sep + (
        text(8pt, fill: grigio, weight: "bold")[#r.posto], nome, text(8pt, fill: grigio)[#r.nba], text(8.5pt, fill: grigio)[#r.media],
        ..r.celle.map(cella), conta(r),
      )
    }).flatten(),
    // tribuna (Luca, 02/11): a roster ma né in quintetto né in panchina, in una riga sola (va a capo tra un giocatore
    // e l'altro, mai a metà), tra due righe viola, col punteggio della giornata
    ..(if s.at("tribuna", default: ()).len() > 0 { (table.cell(colspan: 5 + nn, align: left + horizon, fill: rgb("#F4F2F8"),
        inset: (x: 6pt, y: 5pt), stroke: (top: 1pt + viola))[
      #text(7pt, weight: "bold", fill: grigio, tracking: 0.5pt)[TRIBUNA] #h(6pt)
      #s.tribuna.map(x => box[#text(8pt, fill: rgb("#3A3150"))[#x.nome] #if x.k == "prossima" { text(8pt, fill: viola_medio)[#x.t] } else { text(8pt, weight: "bold", fill: if x.k == "fp" { rgb("#3A3150") } else { grigio })[#x.t] }]).join([#text(8pt, fill: bordo)[ · ] ])
    ],) } else { () }),
    // i totali in fondo, sotto «Punti effettivi» (Luca, 23/10)
    table.cell(colspan: 4 + nn, align: right, stroke: (top: 1pt + viola))[#text(8.5pt, fill: grigio)[Titolari]],
    table.cell(stroke: (top: 1pt + viola))[#text(9pt, weight: "bold")[#s.totale]],
    ..(if s.bonus != "" { (table.cell(colspan: 4 + nn, align: right)[#text(8.5pt, fill: grigio)[Bonus casa]], [#text(9pt)[+#s.bonus]]) } else { () }),
    table.cell(colspan: 4 + nn, align: right, fill: lilla)[#text(9.5pt, weight: "bold", fill: viola_scuro)[Totale]],
    table.cell(fill: lilla)[#text(11pt, weight: "bold", fill: viola)[#s.punti]],
    ..(if s.supp != "" { (table.cell(colspan: 4 + nn, align: right)[#text(8.5pt, fill: grigio)[Supplementari]], [#text(9.5pt, weight: "bold", fill: viola)[#s.supp]]) } else { () }),
  ))
}

#squadra(a)
#v(4pt)
#squadra(b)

// ── note ──
#if dati.note.len() > 0 {
  v(10pt)
  pad(x: 14pt, block(width: 100%, fill: lilla2, stroke: 0.5pt + bordo, radius: 6pt, inset: 9pt)[
    #set text(8pt, fill: rgb("#3A3150"))
    #for n in dati.note [• #n \ ]
  ])
}
#v(8pt)
#pad(x: 14pt, bottom: 10pt)[
  #text(7.5pt, fill: grigio)[
    #text(fill: verde, weight: "bold")[↑] entra per la FADD · #text(fill: grigio)[↓ FADD] esce ·
    #text(fill: viola, weight: "bold")[S1…] supplementari · #text(fill: arancio, weight: "bold")[MEDIA] prende la media ·
    #text(fill: viola_medio)[vs / \@] deve giocare · DNP non è entrato ·
    Media = media fantapunti della stagione all'inizio della giornata (la prende se la sua squadra NBA non gioca) ·
    Punti effettivi = quelli che contano: la media delle sue partite nella giornata · bonus casa +#dati.bonus #h(1fr) immagine del #dati.aggiornato]
]
