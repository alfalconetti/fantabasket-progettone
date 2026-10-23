// La foto del giocatore per /player (player.py): la foto ESPN (PNG trasparente) su uno sfondo viola,
// così Telegram non la mostra su fondo nero e ha una misura buona per la didascalia sotto.
#let d = json(bytes(sys.inputs.at("dati")))
#set page(width: 640pt, height: 420pt, margin: 0pt,
  fill: gradient.linear(rgb("#39007D"), rgb("#5F01D1"), rgb("#7B3FE4"), angle: 30deg))
#set text(font: "Liberation Sans", fill: white)
#place(bottom + center, image(d.foto, height: 400pt, fit: "contain"))
#place(top + left, dx: 18pt, dy: 16pt)[
  #text(26pt, weight: "bold")[#d.nome]
  #if d.sotto != "" [ \ #text(13pt, fill: white.transparentize(20%))[#d.sotto]]
]
