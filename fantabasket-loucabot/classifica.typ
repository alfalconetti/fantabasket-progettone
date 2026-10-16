// Classifica del fantabasket (loucabot, classifica.py): verticale (/classifica) o orizzontale
// con tutte le statistiche (/classifica_full). Dati in sys.inputs.dati (JSON).
#let dati = json(bytes(sys.inputs.at("dati")))
#let full = sys.inputs.at("full", default: "") != ""

#let c_head = rgb("#14213D")
#let c_sub = rgb("#FCA311")
#let c_r1 = rgb("#FFFFFF")
#let c_r2 = rgb("#EEF1F6")
#let c_line = rgb("#C9D1DE")
#let c_po = rgb("#2E7D32")

#set page(width: if full { 1120pt } else { 420pt }, height: auto, margin: 0pt, fill: white)
#set block(spacing: 0pt)
#set text(font: "Liberation Sans", size: if full { 10pt } else { 10pt })

#block(width: 100%, fill: c_head)[
  #pad(x: 12pt, y: 9pt)[
    #text(15pt, weight: "bold", fill: white)[#dati.titolo]
    #h(8pt)
    #text(9pt, fill: c_sub)[#dati.sotto]
  ]
]

#let striscia(s) = {
  let col = if s.ends-with("W") { rgb("#2E7D32") } else if s.ends-with("L") { rgb("#C62828") } else { black }
  text(fill: col, weight: "bold")[#s]
}

#let logo(p) = if p != "" { image(p, width: 16pt, height: 16pt, fit: "contain") } else { [] }

#let intest(t) = text(7.5pt, weight: "bold", fill: white)[#t]

#let colonne = if full {
  (
    ("#", r => [#r.pos]), ("", r => logo(r.logo)), ("Squadra", r => text(weight: "bold")[#r.nome]),
    ("V", r => [#r.w]), ("S", r => [#r.l]), ("Punti\nfatti", r => [#r.pf]), ("Punti\nsubiti", r => [#r.ps]),
    ("Diff.", r => [#r.diff]), ("Media\npunti", r => text(weight: "bold")[#r.media]), (dati.ult.replace(". ", ".\n"), r => [#r.media_ult]),
    ("Striscia", r => striscia(r.striscia)), ("Migliore\ndi giornata", r => [#r.migliore]),
    ("Massimo\npunti", r => [#r.max]), ("Minimo\npunti", r => [#r.min]), ("Età\nmedia", r => [#r.eta]),
    ("Record +\nsubiti", r => [#r.rec_pos]), ("Record −\nsubiti", r => [#r.rec_neg]), ("Coeff.\nvariaz.", r => [#r.cv]),
    ("FP media\nroster", r => [#r.fp_roster]), ("FP media\nquintetto", r => [#r.fp_q]),
    ("% giocate\nroster", r => [#r.gioc_roster]), ("% giocate\nquintetto", r => [#r.gioc_q]),
    ("Età\nquintetto", r => [#r.eta_q]), ("Vantaggio\nmedio V", r => [#r.vantaggio]),
    ("Svantaggio\nmedio S", r => [#r.svantaggio]), ("Supple-\nmentari", r => [#r.supp]),
  )
} else {
  (
    ("#", r => [#r.pos]), ("", r => logo(r.logo)), ("Squadra", r => text(weight: "bold")[#r.nome]),
    ("V", r => text(weight: "bold")[#r.w]), ("S", r => [#r.l]), ("PF", r => [#r.pf]), ("PS", r => [#r.ps]),
    ("Media", r => [#r.media]), ("Striscia", r => striscia(r.striscia)),
  )
}

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
    #text(7pt, fill: white)[Punti col bonus casa · a parità di vittorie: scontri diretti (solo V/S), poi media punti, poi differenza#if full [ · Record +/− subiti: volte in cui l'avversario ha fatto il punteggio più alto/più basso della giornata · roster e quintetto di adesso, fantapunti e % di partite giocate della stagione]]
  ]
]
