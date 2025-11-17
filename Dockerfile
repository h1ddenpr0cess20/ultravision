FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ultravision/pyproject.toml ./pyproject.toml
COPY ultravision/requirements.txt ./requirements.txt
COPY README.md ./README.md
COPY ultravision/LICENSE ./LICENSE
COPY ultravision/ultravision ./ultravision
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir . \
    && rm -rf /root/.cache

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--help"]
