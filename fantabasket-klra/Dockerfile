FROM python:3.12-slim

WORKDIR /app

# font delle immagini, come loucabot (classifica, /partita, /giornata con la banda del sistema)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-liberation fonts-noto-color-emoji && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY klra ./klra
COPY CHANGELOG.md .

# il codice di calcolo di loucabot è montato in sola lettura in /louca (docker-compose.yml), shared/ in /app/shared
ENV PYTHONPATH=/app:/louca
CMD ["python", "-m", "klra.bot"]
