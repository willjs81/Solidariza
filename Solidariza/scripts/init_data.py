from core.models import Organization, Product, StockMovement
from accounts.models import User

org, _ = Organization.objects.get_or_create(name="ONG Exemplo")

user = User.objects.filter(username="admin").first()
if not user:
    user = User.objects.create_superuser(
        username="admin", password="admin123", organization=org, role="ADMIN"
    )

product, _ = Product.objects.get_or_create(
    organization=org, name="Cesta Básica", defaults={"is_bundle": True}
)

if not StockMovement.objects.filter(product=product, kind="IN").exists():
    StockMovement.objects.create(
        organization=org, product=product, kind="IN", quantity=100, reason="Carga inicial"
    )

print("OK")


