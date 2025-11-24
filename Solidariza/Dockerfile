FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# O requirements.txt está na raiz do contexto de build (pasta Solidariza)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/

# Garantir diretórios de estáticos esperados pelo settings
RUN mkdir -p /app/static /app/staticfiles /app/panel/static

# Comando padrão para ambientes como Render/Heroku-like
CMD gunicorn project.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 120
