FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev gcc curl xz-utils postgresql-client fonts-liberation fonts-noto-color-emoji && \
    rm -rf /var/lib/apt/lists/*

# Typst — binario statico, nessuna dipendenza
RUN curl -sL https://github.com/typst/typst/releases/download/v0.13.1/typst-x86_64-unknown-linux-musl.tar.xz \
    | tar -xJ --strip-components=1 -C /usr/local/bin typst-x86_64-unknown-linux-musl/typst
# Il binario statico cerca i font di sistema tramite /etc/fonts (fontconfig), che nell'immagine slim non c'è:
# senza questa riga Typst non vede né Liberation Sans né Noto Color Emoji (testo in serif, emoji a quadratini)
ENV TYPST_FONT_PATHS=/usr/share/fonts

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "bot.py"]
