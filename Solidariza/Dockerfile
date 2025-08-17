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
# Cria estrutura de estáticos antes do collectstatic
RUN echo "=== Preparando estrutura para collectstatic ===" \
    && mkdir -p /app/staticfiles/img \
    && mkdir -p /app/core/static/img \
    && echo "=== Copiando imagem para app core ===" \
    && if [ -f "/app/static/img/login-bg.jpg" ]; then \
           cp -f /app/static/img/login-bg.jpg /app/core/static/img/login-bg.jpeg && echo "✅ login-bg.jpg copiado para core/static"; \
       elif [ -f "/app/static/img/login-bg.jpeg" ]; then \
           cp -f /app/static/img/login-bg.jpeg /app/core/static/img/login-bg.jpeg && echo "✅ login-bg.jpeg copiado para core/static"; \
       else \
           echo "❌ Nenhum arquivo login-bg encontrado"; \
       fi

# Coleta de estáticos no build (evita custo em cada cold start)  
RUN python manage.py collectstatic --noinput --verbosity=2 \
    && echo "=== Verificando se collectstatic coletou a imagem ===" \
    && find /app/staticfiles -name "login-bg.*" -type f \
    && echo "=== Garantindo cópia manual final ===" \
    && if [ -f "/app/static/img/login-bg.jpg" ]; then \
           cp -f /app/static/img/login-bg.jpg /app/staticfiles/img/login-bg.jpeg && echo "✅ Cópia manual: login-bg.jpg → staticfiles"; \
       elif [ -f "/app/static/img/login-bg.jpeg" ]; then \
           cp -f /app/static/img/login-bg.jpeg /app/staticfiles/img/login-bg.jpeg && echo "✅ Cópia manual: login-bg.jpeg → staticfiles"; \
       fi \
    && echo "=== Status final ===" \
    && ls -la /app/staticfiles/img/ || echo "❌ Diretório img não existe"

# Comando padrão para ambientes como Render/Heroku-like
CMD sh -c "(python manage.py migrate || (python manage.py migrate core 0009 --fake && python manage.py migrate core 0010 --fake && python manage.py migrate)) && (python manage.py createsuperuser --noinput || true) && gunicorn project.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"
