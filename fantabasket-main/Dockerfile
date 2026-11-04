FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev gcc curl postgresql-client fonts-liberation fonts-noto-color-emoji && \
    rm -rf /var/lib/apt/lists/*

# Typst: la libreria Python in requirements.txt (v6.24.0; prima il programma statico, che i font li trovava solo
# con TYPST_FONT_PATHS). I font sono quelli installati qui sopra (typst_compila.FONT)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "bot.py"]
