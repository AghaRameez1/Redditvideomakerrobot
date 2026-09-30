# Script Studio: web app image. Build: docker build -t scriptstudio .
# Run with docker compose (see docker-compose.yml and README, "Deploying with Docker").
FROM python:3.12-slim

# ffmpeg renders the videos. Deno is the JavaScript runtime yt-dlp needs to download
# YouTube backgrounds. fonts-dejavu is a fallback font for anything Roboto can't draw.
COPY --from=denoland/deno:bin-2.5.6 /deno /usr/local/bin/deno
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    APP_ENV=production DATABASE_PATH=/data/instance/app.db RESULTS_DIR=/data/results

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Run as a normal user. /data holds the database and videos; assets/ caches backgrounds.
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /data/instance /data/results /app/assets/backgrounds /app/assets/temp \
 && chown -R app:app /data /app/assets
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login', timeout=4)"

# One worker, several threads: render and upload progress live in this process's memory.
# Long timeout: a request never renders, but big video downloads can take a while.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--bind", "0.0.0.0:8000", "--timeout", "300", \
     "--access-logfile", "-", "wsgi:app"]
