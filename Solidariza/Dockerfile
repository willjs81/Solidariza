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

# Garantir diretórios de estáticos esperados pelo settings (silencia W004)
# BASE_DIR aponta para /app/Solidariza, então criamos ambos por segurança
RUN mkdir -p /app/Solidariza/static /app/static
# Copia imagem diretamente para staticfiles (estratégia pós-collectstatic)
RUN echo "=== Preparando diretório final ===" \
    && mkdir -p /app/staticfiles/img

# Coleta de estáticos no build (evita custo em cada cold start)
RUN python manage.py collectstatic --noinput --verbosity=2 \
    && echo "=== Copiando imagem personalizada pós-collectstatic ===" \
    && find /app -name "login-bg.*" -type f \
    && echo "=== Priorizando .jpg, depois .jpeg ===" \
    && if [ -f "/app/static/img/login-bg.jpg" ]; then \
           cp -f /app/static/img/login-bg.jpg /app/staticfiles/img/login-bg.jpeg && echo "✅ login-bg.jpg copiado como login-bg.jpeg"; \
       elif [ -f "/app/static/img/login-bg.jpeg" ]; then \
           cp -f /app/static/img/login-bg.jpeg /app/staticfiles/img/login-bg.jpeg && echo "✅ login-bg.jpeg copiado"; \
       else \
           echo "❌ Nenhum arquivo login-bg encontrado"; \
       fi \
    && echo "=== Verificando resultado final ===" \
    && ls -la /app/staticfiles/img/ || echo "Diretório img não encontrado"

# Comando padrão para ambientes como Render/Heroku-like
CMD sh -c "(python manage.py migrate || (python manage.py migrate core 0009 --fake && python manage.py migrate core 0010 --fake && python manage.py migrate)) && (python manage.py createsuperuser --noinput || true) && gunicorn project.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"
