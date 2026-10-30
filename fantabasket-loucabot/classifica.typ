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
#set text(font: ("Liberation Sans", "Noto Color Emoji"), size: if full { 10pt } else { 10pt })

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

// migliore in verde, peggiore in rosso (Luca, 28/10): r.col.<colonna> = "best" | "worst" (classifica.colori)
#let c_best = rgb("#1B8A4B")
#let c_worst = rgb("#C62828")
#let col(r, k, c) = {
  let s = r.at("col", default: (:)).at(k, default: "")
  if s == "best" { text(fill: c_best, weight: "bold")[#c] } else if s == "worst" { text(fill: c_worst, weight: "bold")[#c] } else { c }
}

#let colonne = if full {
  (
    ("#", r => [#r.pos]), ("", r => logo(r.logo)), ("Squadra", r => text(weight: "bold")[#r.nome]),
    ("V", r => [#r.w]), ("S", r => [#r.l]), ("Punti\nfatti", r => col(r, "pf", [#r.pf])), ("Punti\nsubiti", r => col(r, "ps", [#r.ps])),
    ("Diff.", r => col(r, "diff", [#r.diff])), ("Media\npunti", r => col(r, "media", text(weight: "bold")[#r.media])), (dati.ult.replace(". ", ".\n"), r => col(r, "media_ult", [#r.media_ult])),
    ("Striscia", r => striscia(r.striscia)), ("Migliore\ndi giornata", r => col(r, "migliore", [#r.migliore])),
    ("Massimo\npunti", r => col(r, "max", [#r.max])), ("Minimo\npunti", r => col(r, "min", [#r.min])), ("Età\nmedia", r => col(r, "eta", [#r.eta])),
    ("Record +\nsubiti", r => col(r, "rec_pos", [#r.rec_pos])), ("Record −\nsubiti", r => col(r, "rec_neg", [#r.rec_neg])), ("Coeff.\nvariaz.", r => col(r, "cv", [#r.cv])),
    ("FP media\nroster", r => col(r, "fp_roster", [#r.fp_roster])), ("FP media\nquintetto", r => col(r, "fp_q", [#r.fp_q])),
    ("% giocate\nroster", r => col(r, "gioc_roster", [#r.gioc_roster])), ("% giocate\nquintetto", r => col(r, "gioc_q", [#r.gioc_q])),
    ("Età\nquintetto", r => col(r, "eta_q", [#r.eta_q])), ("Vantaggio\nmedio V", r => col(r, "vantaggio", [#r.vantaggio])),
    ("Svantaggio\nmedio S", r => col(r, "svantaggio", [#r.svantaggio])), ("Supple-\nmentari", r => [#r.supp]),
  )
} else {
  (
    ("#", r => [#r.pos]), ("", r => logo(r.logo)), ("Squadra", r => text(weight: "bold")[#r.nome]),
    ("V", r => text(weight: "bold")[#r.w]), ("S", r => [#r.l]), ("PF", r => col(r, "pf", [#r.pf])), ("PS", r => col(r, "ps", [#r.ps])),
    ("Media", r => col(r, "media", [#r.media])), ("Striscia", r => striscia(r.striscia)),
  ) + if "sezioni" in dati { (("Gen.", r => text(fill: rgb("#5A6478"))[#r.gen]),) } else { () }
}

#let larghezze = colonne.enumerate().map(((i, c)) => if i == 2 { 1fr } else if i == 1 { 22pt } else { auto })

#let tabella(righe) = table(
  columns: larghezze,
  stroke: (x, y) => (bottom: 0.5pt + c_line),
  inset: (x: 5pt, y: 4.5pt),
  align: (x, y) => if x == 2 { left + horizon } else { center + horizon },
  fill: (x, y) => if y == 0 { c_head } else if calc.odd(y) { c_r1 } else { c_r2 },
  table.header(..colonne.map(c => intest(c.at(0)))),
  ..righe.map(r => colonne.map(c => (c.at(1))(r))).flatten(),
)

#if "sezioni" in dati {
  for sez in dati.sezioni {
    block(width: 100%, fill: c_sub)[#pad(x: 12pt, y: 5pt)[#text(11pt, weight: "bold", fill: c_head)[#sez.nome]]]
    tabella(sez.righe)
  }
} else {
  tabella(dati.righe)
}

#block(width: 100%, fill: c_head)[
  #pad(x: 12pt, y: 5pt)[
    #set par(justify: false)
    #text(7pt, fill: white)[#text(fill: rgb("#7EE2A0"), weight: "bold")[verde] il migliore e #text(fill: rgb("#FF8A80"), weight: "bold")[rosso] il peggiore di ogni colonna · Punti col bonus casa · a parità di vittorie: scontri diretti (solo V/S), poi media punti, poi differenza#if "sezioni" in dati [ · ordine della classifica generale (Gen.), filtrato per conference]#if full [ · Record +/− subiti: volte in cui l'avversario ha fatto contro di te il suo massimo/minimo della stagione · roster di adesso, quintetto = il migliore possibile per fantapunti (uno per ruolo)]]
  ]
]
