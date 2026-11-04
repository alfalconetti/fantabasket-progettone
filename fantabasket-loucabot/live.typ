// Tabellone live della giornata (live.py → dati_immagine), sul canale al posto del messaggio di testo
// (mockup approvato da Luca il 23/10; banda NBA in alto dalla v6.13.0, mockup del 31/10). Emoji dal font Noto Color Emoji (fonts-noto-color-emoji nel Dockerfile, v53).
#let d = json(bytes(sys.inputs.at("dati")))
#let viola = rgb("#5F01D1")
#let viola_scuro = rgb("#39007D")
#let lilla = rgb("#EFE7FD")
#let lilla2 = rgb("#F7F3FE")
#let bordo = rgb("#D6C8F5")
#let grigio = rgb("#6B6480")
#let rosso = rgb("#C0392B")
#let verde = rgb("#1B8A4B")
#let blu = rgb("#1F5FAF")
#set page(width: 560pt, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: 9pt, fill: rgb("#1D1630"))

#let logo(s, dd) = if s.logo != "" {
  box(clip: true, radius: 50%, width: dd, height: dd, image(s.logo, width: dd, height: dd, fit: "cover"))
} else {
  box(width: dd, height: dd, radius: 50%, fill: rgb(s.colore),
    align(center + horizon, text(dd * 0.4, weight: "bold", fill: white)[#s.iniziale]))
}
#let pill(t, c) = box(fill: c.lighten(85%), radius: 3pt, inset: (x: 3.5pt, y: 1.5pt), text(6.8pt, weight: "bold", fill: c)[#t])

// v6.23.0 (Luca, 04/11): lo stesso tabellone a giornata calcolata o convalidata (/giornata, prima pagina di
// /pdf_giornata): «modo» finale, etichetta dello stato al posto di LIVE, niente etichette dei titolari né legenda
#let finale = d.at("modo", default: "live") == "finale"

// ── testata ──
#block(width: 100%, fill: gradient.linear(viola_scuro, viola, angle: 0deg), inset: (x: 14pt, y: 11pt))[
  #grid(columns: (1fr, auto), align: horizon,
    [#text(15pt, weight: "bold", fill: white)[Giornata #d.n] #h(6pt) #if finale {
       box(fill: rgb(d.colore_stato), radius: 3pt, inset: (x: 5pt, y: 2.5pt), text(8pt, weight: "bold", fill: white)[#d.etichetta])
     } else { box(fill: rosso, radius: 3pt, inset: (x: 5pt, y: 2.5pt), text(8pt, weight: "bold", fill: white)[● LIVE]) } \
     #v(3pt) #text(8.5pt, fill: white.transparentize(25%))[#d.date#if d.notte != "" [ · notte #d.notte]]],
    align(right)[#text(7pt, fill: white.transparentize(30%), tracking: 0.5pt)[#d.at("ora_label", default: "AGGIORNATO")] \ #text(13pt, weight: "bold", fill: white)[#d.ora]])
]


// ── banda NBA (v6.13.0, Luca 31/10): le partite vere della notte, tutte; in corso col bordo rosso ──
#let lnba(t, dd) = if t.logo != "" {
  box(width: dd, height: dd, radius: 50%, fill: white, align(center + horizon, image(t.logo, width: dd * 0.82, height: dd * 0.82, fit: "contain")))
} else {
  box(width: dd, height: dd, radius: 50%, fill: rgb(t.colore), align(center + horizon, text(dd * 0.32, weight: "bold", fill: white)[#t.sigla]))
}
#let mini(p) = {
  let live = p.stato == "live"
  let fin = p.stato == "finale"
  let ci = p.pt != "" and p.pc != ""
  let vt = ci and int(p.pt) > int(p.pc)
  let vc = ci and int(p.pc) > int(p.pt)
  let riga(t, pts, v) = grid(columns: (auto, 1fr, auto), column-gutter: 4pt, align: horizon,
    lnba(t, 13pt), text(7.5pt, weight: if v { "bold" } else { "regular" }, fill: white)[#t.sigla],
    text(8.5pt, weight: if v { "bold" } else { "regular" }, fill: if fin and not v { white.transparentize(40%) } else { white })[#pts])
  box(width: 100%, fill: white.transparentize(if live { 82% } else { 90% }), radius: 5pt, inset: (x: 5pt, y: 4pt),
    stroke: if live { 0.8pt + rgb("#FF6B6B") } else { none })[
    #riga(p.tras, p.pt, vt)
    #v(2.5pt)
    #riga(p.casa, p.pc, vc)
    #v(3pt)
    #align(center, text(6.3pt, weight: "bold", tracking: 0.3pt,
      fill: if live { rgb("#FFB3B3") } else { white.transparentize(35%) })[#if live [● ]#p.testo])
  ]
}
#if d.at("nba", default: ()).len() > 0 {
  block(width: 100%, fill: viola_scuro, inset: (x: 10pt, top: 7pt, bottom: 9pt))[
    #text(6.5pt, weight: "bold", fill: white.transparentize(30%), tracking: 0.6pt)[NBA#if d.at("nba_notte", default: "") != "" [ · NOTTE DEL #d.nba_notte] else [ STANOTTE]]
    #v(5pt)
    #grid(columns: (1fr,) * d.nba_colonne, column-gutter: 5pt, row-gutter: 5pt, ..d.nba.map(mini))
  ]
}

// ── una squadra nella scheda ──
#let riga(s, avanti) = grid(columns: (auto, 1fr, auto), column-gutter: 6pt, align: horizon,
  logo(s, 20pt),
  stack(spacing: 2.5pt,
    text(9pt, weight: if avanti { "bold" } else { "regular" })[#s.nome],
    if not finale {
      if s.finito { pill("✅ finito", verde); h(2pt) } else {
        if s.campo > 0 { pill("🏀 " + str(s.campo), rosso); h(2pt) }
        if s.giocare > 0 { pill("⏳ " + str(s.giocare), grigio); h(2pt) }
        if s.rigiocare > 0 { pill("🔁 " + str(s.rigiocare) + " · " + s.finora, viola); h(2pt) }
      }
      if s.media > 0 { pill("📈 " + str(s.media), blu) }
    }),
  text(14pt, weight: if avanti { "bold" } else { "regular" }, fill: if avanti { viola_scuro } else { grigio })[#s.punti])

#let scheda(p) = box(width: 100%, fill: white, stroke: 0.7pt + bordo, radius: 7pt, clip: true)[
  #block(width: 100%, fill: lilla2, inset: (x: 8pt, y: 4pt))[
    #text(6.5pt, weight: "bold", fill: grigio, tracking: 0.5pt)[PARTITA #p.k]
    #h(1fr)
    #if p.nota != "" { text(6.5pt, weight: "bold", fill: viola)[#p.nota] }
  ]
  #block(inset: (x: 8pt, y: 6pt))[
    #riga(p.casa, p.avanti == "casa")
    #v(5pt)
    #riga(p.tras, p.avanti == "trasferta")
  ]
]

#pad(x: 10pt, y: 10pt, grid(columns: (1fr, 1fr), column-gutter: 8pt, row-gutter: 8pt, ..d.partite.map(scheda)))

// ── legenda, bella evidente (Luca, 25/10), sempre al plurale ──
#let voce(p, t) = box(width: 100%, height: 30pt, fill: white, stroke: 0.7pt + bordo, radius: 5pt, inset: (x: 7pt, y: 4pt),
  align(horizon, grid(columns: (auto, 1fr), column-gutter: 6pt, align: horizon, text(10pt)[#p], text(8.5pt, fill: rgb("#1D1630"))[#t])))
#if finale {
  block(width: 100%, fill: lilla, inset: (x: 10pt, y: 9pt))[
    #text(7.5pt, fill: grigio)[#d.nota_finale]
  ]
} else [
#block(width: 100%, fill: lilla, inset: (x: 10pt, top: 9pt, bottom: 10pt))[
  #text(8pt, weight: "bold", fill: viola_scuro, tracking: 0.8pt)[LEGENDA]
  #v(6pt)
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 6pt, row-gutter: 6pt,
    voce(pill("🏀 2", rosso), [sono in campo adesso]),
    voce(pill("⏳ 2", grigio), [devono giocare]),
    voce(pill("🔁 1 · 30,50", viola), [devono rigiocare, coi punti già fatti]),
    voce(pill("✅ finito", verde), [hanno finito tutti]),
    voce(pill("📈 1", blu), [prendono media: la loro squadra NBA non gioca]),
    voce(text(11pt, weight: "bold", fill: viola_scuro)[123,45], [in grassetto chi è avanti adesso]))
  #v(6pt)
  #text(7.5pt, fill: grigio)[*HANNO GIOCATO IN MENO DI #d.soglia*: ancora nessuno avanti, troppi titolari devono giocare · *SI VA AI SUPPL.*: pari, col punteggio dei supplementari #linebreak()
    Provvisori, sui tabellini live di ESPN con le regole del calcolo (bonus casa +#d.bonus, FADD, supplementari): li convalida un admin. Il testo completo con /live\_results nel bot.]
]
]
