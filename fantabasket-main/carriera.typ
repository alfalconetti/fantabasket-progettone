// /carriera (handlers/carriera.py): due timeline in parallelo, fantabasket (sinistra) e NBA reale (destra), dal 25/07/2026.
// Toni blu (Luca, 23/10). Dati in sys.inputs.dati (JSON).
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#1D4ED8")      // blu (i nomi restano quelli di partita.typ)
#let viola_scuro = rgb("#0B2A6B")
#let lilla = rgb("#E6EEFB")
#let lilla2 = rgb("#F3F7FD")
#let bordo = rgb("#C9D7F2")
#let grigio = rgb("#5E6B82")
#let testo = rgb("#111C33")
#set page(width: 400pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: 9pt, fill: testo)

// logo: segnaposto tondo col colore della squadra e la sigla (i loghi veri si caricano dopo)
#let logo(sq, dd) = if sq.at("logo", default: "") != "" {
  box(width: dd, height: dd, radius: 50%, clip: true, fill: white, stroke: 1pt + rgb(sq.colore), image(sq.logo, width: dd, height: dd, fit: "contain"))
} else {
  box(width: dd, height: dd, radius: 50%, fill: rgb(sq.colore), stroke: 1pt + white,
    align(center + horizon, text(dd * 0.34, weight: "bold", fill: white)[#sq.sigla]))
}
#let tag(t, c) = box(fill: c, radius: 3pt, inset: (x: 4pt, y: 2pt), text(6.5pt, weight: "bold", fill: white, tracking: 0.4pt)[#upper(t)])
#let colori_tipo = (
  "draft": rgb("#1565C0"), "avvio": grigio, "firma": rgb("#1B8A4B"), "trade": rgb("#6A1B9A"), "taglio": rgb("#C0392B"),
  "rinnovo": rgb("#00838F"), "dpe": rgb("#C62828"), "10-day": rgb("#00838F"), "scadenza": grigio, "rookie": rgb("#1565C0"))

// ── testata ── (stretta: il contratto sotto il nome, non in una terza colonna)
#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 12pt, y: 12pt))[
  #grid(columns: (auto, 1fr), column-gutter: 10pt, align: horizon,
    box(width: 56pt, height: 56pt, radius: 50%, clip: true, fill: lilla, stroke: 2pt + white.transparentize(40%),
      // stesse proporzioni di /partita (Luca, 24/10): foto alta 1,2 volte il tondo (520×380), centrata, un filo più su
      if d.foto != "" { place(top + left, dx: -17.9pt, dy: -2.8pt, image(d.foto, height: 67.2pt, width: 91.8pt)) }
      else { align(center + horizon, text(19pt, weight: "bold", fill: viola_scuro)[#d.iniziali]) }),
    stack(spacing: 4pt,
      text(15pt, weight: "bold", fill: white)[#d.nome],
      text(8pt, fill: white.transparentize(25%))[#d.posizioni#if d.eta != none [ · #d.eta anni]],
      text(8pt, fill: white)[🏆 *#d.ora.fanta* #h(6pt) 🏀 *#d.ora.nba*],
      text(8pt, fill: white)[📝 *#d.ora.contratto* #text(7pt, fill: white.transparentize(30%))[· #d.ora.fino]]),
  )
]

// ── intestazione delle due colonne ──
#block(width: 100%, fill: lilla, inset: (x: 10pt, y: 6pt))[
  #grid(columns: (1fr, 46pt, 1fr), align: (right, center, left),
    text(8pt, weight: "bold", fill: viola_scuro, tracking: 0.8pt)[FANTABASKET],
    text(6pt, fill: grigio)[dal 25/07],
    text(8pt, weight: "bold", fill: viola_scuro, tracking: 0.8pt)[NBA])
]

// ── un evento ──
#let carta(ev, lato) = {
  let c = colori_tipo.at(ev.tipo, default: grigio)
  // stretta: il logo piccolo accanto all'etichetta, sotto nome e dettaglio a tutta larghezza della scheda
  let testa = if lato == "sx" { [#tag(ev.etichetta, c) #h(3pt) #box(baseline: 30%, logo(ev.sq, 17pt))] }
              else { [#box(baseline: 30%, logo(ev.sq, 17pt)) #h(3pt) #tag(ev.etichetta, c)] }
  let dentro = align(if lato == "sx" { right } else { left }, stack(spacing: 3pt, testa,
    text(8.5pt, weight: "bold")[#ev.titolo], text(6.8pt, fill: grigio)[#ev.dettaglio]))
  box(width: 100%, fill: white, stroke: 0.7pt + bordo, radius: 5pt, inset: 5.5pt, dentro)
}
// la barra della squadra di quel periodo, attaccata alla colonna centrale
#let barra(sq) = if sq == none { box(width: 5pt, height: 100%) } else { box(width: 5pt, height: 100%, fill: rgb(sq.colore)) }

#pad(x: 10pt, top: 3pt, bottom: 6pt, table(
  columns: (1fr, 4pt, 46pt, 4pt, 1fr),
  stroke: none, inset: (x: 0pt, y: 0pt), align: horizon,
  ..d.righe.map(r => {
    let sx = if r.fanta != none { pad(right: 5pt, y: 4pt, carta(r.fanta, "sx")) } else { pad(right: 5pt, y: 4pt)[#align(right, text(6.8pt, fill: grigio.lighten(30%))[#r.fanta_resta])] }
    let dx = if r.nba != none { pad(left: 5pt, y: 4pt, carta(r.nba, "dx")) } else { pad(y: 4pt, left: 5pt)[#text(6.8pt, fill: grigio.lighten(30%))[#r.nba_resta]] }
    (sx,
     table.cell(fill: if r.fanta_sq != none { rgb(r.fanta_sq.colore) } else { none })[],
     if r.at("mostra_data", default: true) { align(center, stack(spacing: 2pt, text(8pt, weight: "bold", fill: viola_scuro)[#r.giorno], text(6pt, fill: grigio)[#r.anno])) } else { [] },
     table.cell(fill: if r.nba_sq != none { rgb(r.nba_sq.colore) } else { none })[],
     dx)
  }).flatten()
))

// ── in breve ──
#block(width: 100%, fill: lilla2, inset: (x: 10pt, y: 8pt), stroke: (top: 0.6pt + bordo))[
  #grid(columns: (1fr, 1fr), column-gutter: 12pt,
    [#text(6.5pt, weight: "bold", fill: viola_scuro, tracking: 0.6pt)[NEL FANTABASKET] \ #v(2pt) #text(7.5pt)[#d.breve.fanta]],
    [#text(6.5pt, weight: "bold", fill: viola_scuro, tracking: 0.6pt)[NELLA NBA] \ #v(2pt) #text(7.5pt)[#d.breve.nba]])
]
#pad(x: 10pt, y: 6pt, text(5.8pt, fill: grigio)[Dal 25/07/2026, quando è nato il bot. NBA: roster ESPN e Basketball-Reference. #h(1fr) #d.aggiornato])
