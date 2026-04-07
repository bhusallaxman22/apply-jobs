FROM mcr.microsoft.com/playwright/python:v1.51.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /srv/job-agent

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fluxbox novnc python3-venv websockify x11vnc xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app /srv/job-agent/app
COPY docker/start.sh /srv/job-agent/docker/start.sh

RUN chmod +x /srv/job-agent/docker/start.sh

EXPOSE 8095 7900

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8095/health || exit 1

CMD ["/srv/job-agent/docker/start.sh"]
