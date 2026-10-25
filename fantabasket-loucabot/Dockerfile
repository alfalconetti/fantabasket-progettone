FROM python:3.12-slim

WORKDIR /app

# font delle immagini (classifica, /partita, live), come il bot principale; le emoji a colori del tabellone live (v53)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-liberation fonts-noto-color-emoji && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
