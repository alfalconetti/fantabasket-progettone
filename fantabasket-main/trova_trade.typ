// /trova_trade (handlers/trova_trade.py, dati in `dati`): riassunto di una trade ufficiale. Stile di /carriera, in verde (Luca, 31/10).
// Una colonna per squadra (4 squadre: griglia 2×2); per ogni squadra «riceve» e «cede», ogni asset con da chi arriva /
// a chi va; cap e roster al momento della trade; in fondo il percorso (solo quello che è successo davvero).
#let d = json(bytes(sys.inputs.at("dati")))
#let blu = rgb("#15803D")
#let blu_scuro = rgb("#0B3D22")
#let azzurro = rgb("#E3F3E8")
#let azzurro2 = rgb("#F2FAF4")
#let bordo = rgb("#C3E2CD")
#let grigio = rgb("#5E6B82")
#let testo = rgb("#111C33")
#let verde = rgb("#1B8A4B")
#let rosso = rgb("#C0392B")
#set page(width: 520pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 8.5pt, fill: testo)
// emoji dal font Noto Color Emoji, installato nel container come in loucabot (fonts-noto-color-emoji nel Dockerfile)
#let due = d.squadre.len() == 2      // trade a due: basta «riceve», il resto si capisce da solo (Luca, 31/10)

#let logo(sq, dd) = if sq.at("logo", default: "") != "" {
  box(width: dd, height: dd, radius: 50%, clip: true, fill: white, stroke: 1pt + rgb(sq.colore), image(sq.logo, width: dd, height: dd, fit: "contain"))
} else {
  box(width: dd, height: dd, radius: 50%, fill: rgb(sq.colore), stroke: 1pt + white,
    align(center + horizon, text(dd * 0.34, weight: "bold", fill: white)[#sq.sigla]))
}
#let tag(t, c) = box(fill: c, radius: 3pt, inset: (x: 4pt, y: 2pt), text(6.5pt, weight: "bold", fill: white, tracking: 0.4pt)[#upper(t)])
#let stati = ("approvata": rgb("#0F9D58"), "annullata": rosso, "rifiutata": rosso, "in votazione": rgb("#B26A00"))
#let icone = ("giocatore": "🏀", "pick": "🎟️", "diritti": "📜")

// ── testata ──
#block(width: 100%, fill: gradient.linear(blu_scuro, blu, angle: 0deg), inset: (x: 14pt, y: 12pt))[
  #grid(columns: (1fr, auto), align: horizon,
    stack(spacing: 5pt,
      text(17pt, weight: "bold", fill: white)[#d.numero],
      text(8.5pt, fill: white.transparentize(20%))[#d.data · #d.squadre.len() squadre · #d.asset asset]),
    align(right, stack(spacing: 4pt,
      box(fill: stati.at(d.stato, default: grigio), radius: 4pt, inset: (x: 7pt, y: 4pt), text(9pt, weight: "bold", fill: white)[#upper(d.stato)]),
      if d.stato_nota != "" { text(7pt, fill: white.transparentize(25%))[#d.stato_nota] })))
]

// ── un asset ──
#let asset(a, verso) = box(width: 100%, fill: white, stroke: 0.6pt + bordo, radius: 4pt, inset: (x: 5pt, y: 4pt))[
  #grid(columns: (auto, 1fr), column-gutter: 4pt,
    text(9pt)[#icone.at(a.tipo, default: "•")],
    stack(spacing: 2.5pt,
      text(8.3pt, weight: "bold")[#a.nome],
      if a.dettaglio != "" { text(6.8pt, fill: grigio)[#a.dettaglio] },
      if not due { text(6.8pt, fill: blu)[#verso #box(baseline: 25%, logo(a.altra, 10pt)) #a.altra.nome] }))
]

#let sezione(titolo, c, lista, verso) = stack(spacing: 4pt,
  text(6.8pt, weight: "bold", fill: c, tracking: 0.8pt)[#titolo],
  ..if lista.len() == 0 { (text(7pt, fill: grigio)[—],) } else { lista.map(a => asset(a, verso)) })

// ── una squadra ──
#let colonna(sq) = box(width: 100%, fill: azzurro2, stroke: 0.7pt + bordo, radius: 6pt, inset: 7pt)[
  #stack(spacing: 7pt,
    grid(columns: (auto, 1fr), column-gutter: 6pt, align: horizon,
      logo(sq, 26pt),
      stack(spacing: 2pt, text(10pt, weight: "bold")[#sq.nome], if sq.gm != "" { text(7pt, fill: grigio)[GM #sq.gm] })),
    sezione("RICEVE", verde, sq.riceve, "da"),
    ..if not due { (sezione("CEDE", rosso, sq.cede, "a"),) } else { () },
    line(length: 100%, stroke: 0.5pt + bordo),
    grid(columns: (1fr, auto), row-gutter: 3pt,
      text(7pt, fill: grigio)[Cap], text(7.5pt)[#sq.cap.prima → *#sq.cap.dopo* #text(fill: if sq.cap.diff.starts-with("+") { rosso } else { verde })[(#sq.cap.diff)]],
      text(7pt, fill: grigio)[Roster], text(7.5pt)[#sq.roster.prima → *#sq.roster.dopo*]),
  )
]

#let n_col = if d.squadre.len() == 4 { 2 } else { d.squadre.len() }
#pad(x: 10pt, y: 10pt, grid(columns: (1fr,) * n_col, column-gutter: 7pt, row-gutter: 7pt, ..d.squadre.map(colonna)))

// ── il percorso della trade: chi l'ha scritta, chi ha accettato (se c'è passata), chi l'ha approvata o annullata ──
// Le strade possibili: proposta ai GM coinvolti → accettazioni → admin; mandata direttamente agli admin da un GM
// (senza accettazioni, o con alcune); scritta da un admin. Si mostra solo quello che è successo davvero.
#let segno = ("ok": text(fill: verde, weight: "bold")[✓], "no": text(fill: rosso, weight: "bold")[✗], "attesa": text(fill: grigio)[…],
              "scritta": text(fill: blu)[✎], "admin": text(fill: blu)[➜], "annullata": text(fill: rosso, weight: "bold")[↺])
#block(width: 100%, fill: azzurro, inset: (x: 12pt, y: 8pt))[
  #text(6.5pt, weight: "bold", fill: blu_scuro, tracking: 0.6pt)[PERCORSO]
  #v(4pt)
  #grid(columns: (auto, 1fr, auto), column-gutter: 6pt, row-gutter: 4pt,
    ..d.percorso.map(p => (segno.at(p.segno, default: [•]), text(8pt)[#p.testo], text(7pt, fill: grigio)[#p.quando])).flatten())
]
#block(width: 100%, fill: white, inset: (x: 12pt, y: 6pt))[
  #text(6.5pt, fill: grigio)[🏀 giocatore (ruolo, contratto di allora: importo × anni rimasti) · 🎟️ pick (anno, giro, di chi era, protezioni) · 📜 diritti rookie (giro, numero e anno del draft) · Cap e roster al momento della trade, subito prima e subito dopo, spalmature comprese · /trova_trade 014, o il nome di un giocatore per le trade ufficiali che lo riguardano]
]
