from __future__ import annotations

from datetime import date
import uuid
from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone
from .validators import normalize_identifier, is_valid_cpf
from django.core.exceptions import ValidationError


class UserSession(models.Model):
    """Sessões de usuários com last_seen real para auditoria.

    Mantém vínculo com a sessão do Django via session_key e registra
    última atividade para cálculo de "online".
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="active_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    organization = models.ForeignKey('Organization', on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    login_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user} @ {self.session_key}"

    class Meta:
        indexes = [
            models.Index(fields=["user", "last_seen"]),
        ]
        verbose_name = "Sessão de usuário"
        verbose_name_plural = "Sessões de usuários"

class Organization(models.Model):
    name = models.CharField("Nome da ONG", max_length=255)
    is_active = models.BooleanField("Ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    class Meta:
        verbose_name = "Organização"
        verbose_name_plural = "Organizações"


class Guardian(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, verbose_name="Organização")
    name = models.CharField("Responsável", max_length=255)
    document = models.CharField("CPF", max_length=50, blank=True)
    phone = models.CharField("Telefone", max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self) -> None:
        # Validação básica de CPF quando informado
        if self.document:
            from .validators import only_digits
            cpf = only_digits(self.document)
            if len(cpf) == 11 and not is_valid_cpf(cpf):
                raise ValidationError({"document": "CPF inválido."})
            self.document = cpf

    class Meta:
        verbose_name = "Responsável"
        verbose_name_plural = "Responsáveis"
    def clean(self) -> None:
        # Validação básica de CPF quando informado
        if self.document:
            from .validators import only_digits
            cpf = only_digits(self.document)
            if len(cpf) == 11 and not is_valid_cpf(cpf):
                raise models.ValidationError({"document": "CPF inválido."})
            self.document = cpf


class Family(models.Model):
    name = models.CharField("Nome da família", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name or f"Família #{self.pk}"

    class Meta:
        verbose_name = "Família"
        verbose_name_plural = "Famílias"


class FamilyMember(models.Model):
    class Relation(models.TextChoices):
        SELF = "SELF", "Titular"
        CHILD = "CHILD", "Filho(a)"
        SPOUSE = "SPOUSE", "Cônjuge"
        OTHER = "OTHER", "Outro"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="members")
    beneficiary = models.ForeignKey('Beneficiary', on_delete=models.CASCADE, related_name="family_links")
    relation = models.CharField(max_length=16, choices=Relation.choices, default=Relation.SELF)
    is_guardian = models.BooleanField("É responsável", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Um beneficiário pertence a no máximo uma família
            models.UniqueConstraint(fields=["beneficiary"], name="uniq_beneficiary_single_family"),
        ]
        verbose_name = "Membro da família"
        verbose_name_plural = "Membros da família"


class OrganizationBeneficiary(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="beneficiaries")
    beneficiary = models.ForeignKey('Beneficiary', on_delete=models.CASCADE, related_name="organizations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "beneficiary"], name="uniq_organization_beneficiary_membership"),
        ]
        verbose_name = "Vínculo organização/beneficiário"
        verbose_name_plural = "Vínculos organização/beneficiário"

class Beneficiary(models.Model):
    # Organização é opcional para compatibilidade; beneficiários são globais na rede
    organization = models.ForeignKey(
        Organization, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Organização"
    )
    guardian = models.ForeignKey(Guardian, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Responsável")
    name = models.CharField("Nome completo", max_length=255)
    identifier = models.CharField(
        "Identificador (CPF ou outro)", max_length=32, unique=True, db_index=True
    )
    document = models.CharField("Documento", max_length=50, blank=True)
    birth_date = models.DateField("Data de nascimento", null=True, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    address = models.CharField("Endereço", max_length=255, blank=True)
    address_number = models.CharField("Número", max_length=20, blank=True)
    address_complement = models.CharField("Complemento", max_length=100, blank=True)
    district = models.CharField("Bairro", max_length=100, blank=True)
    city = models.CharField("Cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self) -> None:
        ident = normalize_identifier(self.identifier)
        # Não bloquear cadastro por CPF inválido: o identificador pode ser outro documento
        # Apenas normalizamos o valor para armazenamento consistente
        self.identifier = ident

    class Meta:
        verbose_name = "Beneficiário"
        verbose_name_plural = "Beneficiários"


class Event(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, verbose_name="Organização")
    name = models.CharField("Nome do evento", max_length=255)
    date = models.DateField("Data", default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "name", "date")
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} - {self.date}"


class Attendance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, verbose_name="Evento")
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.CASCADE, verbose_name="Beneficiário")
    present = models.BooleanField("Presente", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "beneficiary")
        verbose_name = "Presença"
        verbose_name_plural = "Presenças"


class Product(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, verbose_name="Organização")
    name = models.CharField("Produto", max_length=255)
    is_bundle = models.BooleanField("Cesta", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "name")
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class StockMovement(models.Model):
    IN = "IN"
    OUT = "OUT"
    KIND_CHOICES = [(IN, "Entrada"), (OUT, "Saída")]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, verbose_name="Organização")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Produto")
    kind = models.CharField("Tipo", max_length=3, choices=KIND_CHOICES)
    quantity = models.PositiveIntegerField("Quantidade")
    reason = models.CharField("Motivo", max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="Criado por")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self) -> None:
        # Garante que a movimentação pertence à mesma organização do produto
        if self.product_id and self.organization_id:
            if self.product.organization_id != self.organization_id:
                raise ValidationError({
                    "organization": "A organização da movimentação deve ser a mesma do produto.",
                    "product": "Produto pertence a outra organização.",
                })

    def save(self, *args, **kwargs):  # noqa: D401
        # Valida antes de salvar para evitar inconsistência entre organizações
        self.full_clean()
        return super().save(*args, **kwargs)

    @staticmethod
    def get_stock(product: Product) -> int:
        totals = StockMovement.objects.filter(product=product).aggregate(
            total_in=Sum(models.Case(models.When(kind=StockMovement.IN, then="quantity"), default=0, output_field=models.IntegerField())),
            total_out=Sum(models.Case(models.When(kind=StockMovement.OUT, then="quantity"), default=0, output_field=models.IntegerField())),
        )
        total_in = totals.get("total_in") or 0
        total_out = totals.get("total_out") or 0
        return total_in - total_out

    class Meta:
        verbose_name = "Movimentação de estoque"
        verbose_name_plural = "Movimentações de estoque"


class Distribution(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, verbose_name="Organização")
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.CASCADE, verbose_name="Beneficiário")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="Produto")
    period_month = models.DateField("Mês de referência", help_text="Use o primeiro dia do mês, ex.: 2025-05-01")
    delivered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="Entregue por")
    delivered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Única por beneficiário/produto no mês (calendário) em toda a rede
            # Mantemos também um índice separado por (beneficiário, período) para relatórios rápidos, mas NÃO como unique.
            models.UniqueConstraint(
                fields=["beneficiary", "product", "period_month"],
                name="uniq_distribution_per_beneficiary_product_month_network",
            ),
        ]
        verbose_name = "Distribuição"
        verbose_name_plural = "Distribuições"

    def clean(self) -> None:
        # Garante coerência entre organização e produto
        if self.product_id and self.organization_id:
            if self.product.organization_id != self.organization_id:
                raise ValidationError({
                    "organization": "A organização da distribuição deve ser a mesma do produto.",
                    "product": "Produto pertence a outra organização.",
                })
        # Opcional: checa vínculo do beneficiário com a organização
        if self.beneficiary_id and self.organization_id:
            from .models import OrganizationBeneficiary  # import local para evitar ciclo
            linked = OrganizationBeneficiary.objects.filter(
                organization_id=self.organization_id, beneficiary_id=self.beneficiary_id
            ).exists()
            if not linked:
                raise ValidationError({
                    "beneficiary": "Beneficiário não está vinculado a esta organização.",
                })

    def save(self, *args, **kwargs):  # noqa: D401
        # Valida antes de salvar para evitar inconsistência entre organizações
        self.full_clean()
        return super().save(*args, **kwargs)


class StockError(Exception):
    pass


class UniqueMonthlyDeliveryError(Exception):
    pass


@transaction.atomic
def deliver_basket(*, organization: Organization, beneficiary: Beneficiary, product: Product, period_month: date, user) -> Distribution:
    month_start = period_month.replace(day=1)

    # Coerência entre organização e produto/beneficiário
    if product.organization_id != organization.id:
        raise ValidationError("Produto pertence a outra organização.")
    from .models import OrganizationBeneficiary as _OrgBen  # evitar import circular no topo
    if not _OrgBen.objects.filter(organization=organization, beneficiary=beneficiary).exists():
        raise ValidationError("Beneficiário não está vinculado a esta organização.")

    # Regra por produto na rede: não permitir repetir o MESMO produto dentro de 30 dias
    from datetime import timedelta
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    recent_same_product = Distribution.objects.select_for_update().filter(
        beneficiary=beneficiary,
        product=product,
        delivered_at__gte=thirty_days_ago,
    ).exists()
    if recent_same_product:
        raise UniqueMonthlyDeliveryError("Beneficiário já recebeu este produto nos últimos 30 dias na rede.")

    current_stock = StockMovement.get_stock(product)
    if current_stock < 1:
        raise StockError("Estoque insuficiente para realizar a entrega deste produto.")

    StockMovement.objects.create(
        organization=organization,
        product=product,
        kind=StockMovement.OUT,
        quantity=1,
        reason=f"Distribuição {month_start:%Y-%m}",
        created_by=user,
    )

    distribution = Distribution.objects.create(
        organization=organization,
        beneficiary=beneficiary,
        product=product,
        period_month=month_start,
        delivered_by=user,
    )

    event, _ = Event.objects.get_or_create(
        organization=organization, name="Distribuição", date=month_start
    )
    Attendance.objects.get_or_create(event=event, beneficiary=beneficiary, defaults={"present": True})

    return distribution


def generate_identifier() -> str:
    return uuid.uuid4().hex



# Auditoria simples de ações de usuário
class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=64)
    model_name = models.CharField(max_length=128, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"]) ]
        ordering = ["-created_at"]
        verbose_name = "Auditoria"
        verbose_name_plural = "Auditorias"

