# Solidariza

Sistema Django para gestão de cestas, beneficiários e distribuições.

## Desenvolvimento (Docker)

1. Copie `.env.example` para `.env`
2. Suba os serviços:

```bash
docker compose -f docker-compose.dev.yml up --build
```

3. Crie dados iniciais (exemplo):

```bash
docker compose -f docker-compose.dev.yml exec web python manage.py migrate
docker compose -f docker-compose.dev.yml exec web python manage.py shell -c "
from core.models import Organization, Product
from accounts.models import User
org = Organization.objects.create(name='ONG Exemplo')
User.objects.create_superuser(username='admin', password='admin123', organization=org, role='ADMIN')
Product.objects.create(organization=org, name='Cesta Básica', is_bundle=True)
print('OK')
"
```

4. Acesse: http://localhost:8000 (admin/admin123)

## Produção

Ver instruções no escopo do projeto. Compose de produção: `docker-compose.prod.yml` com Nginx + Gunicorn.


