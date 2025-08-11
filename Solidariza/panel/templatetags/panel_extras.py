from django import template
from datetime import date, timedelta
from core.middleware import get_active_organization
from core.models import Organization

register = template.Library()


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except Exception:  # noqa: BLE001
        return None


@register.filter
def calculate_age(birth_date):
    if birth_date:
        today = date.today()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return None


@register.filter
def add_days(value, days):
    """Adiciona dias a uma data."""
    if value:
        return value + timedelta(days=days)
    return None


@register.filter
def get_identification(beneficiary):
    """
    Retorna a melhor identificação disponível para um beneficiário.
    Prioridade: identifier > document > documento do responsável (se menor) > ID
    """
    # Se tem identificador (CPF ou outro), usar ele
    if beneficiary.identifier:
        return beneficiary.identifier
    
    # Se tem documento, usar ele
    if beneficiary.document:
        return beneficiary.document
    
    # Se é menor de idade, buscar documento do responsável
    if beneficiary.birth_date:
        today = date.today()
        age = today.year - beneficiary.birth_date.year - (
            (today.month, today.day) < (beneficiary.birth_date.month, beneficiary.birth_date.day)
        )
        
        if age < 18:
            # Buscar responsável na família
            for family_link in beneficiary.family_links.all():
                if family_link.family:
                    for member in family_link.family.members.all():
                        if member.is_guardian and member.beneficiary.identifier:
                            return f"Resp: {member.beneficiary.identifier}"
    
    # Fallback para ID
    return f"ID: #{beneficiary.id}"


@register.filter
def get_identification_type(beneficiary):
    """
    Retorna o tipo de identificação (para styling).
    """
    if beneficiary.identifier:
        return "primary"
    elif beneficiary.document:
        return "info"
    elif beneficiary.birth_date:
        today = date.today()
        age = today.year - beneficiary.birth_date.year - (
            (today.month, today.day) < (beneficiary.birth_date.month, beneficiary.birth_date.day)
        )
        if age < 18:
            return "warning"  # Responsável
    return "light"  # ID apenas


@register.filter
def subtract(value, arg):
    """Subtrai dois números."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0


@register.simple_tag(takes_context=True)
def active_organization_name(context):
    """Retorna o nome da organização ativa para o request corrente.

    - Para admin global sem ONG ativa, retorna "Toda a Rede".
    - Para usuário comum sem vínculo (caso raro), retorna string vazia.
    """
    request = context.get("request")
    if not request or not request.user.is_authenticated:
        return ""

    org = get_active_organization(request)
    if org:
        return org.name

    if getattr(request.user, "is_superuser", False):
        return "Toda a Rede"

    return ""


@register.simple_tag(takes_context=True)
def list_all_organizations(context):
    """Retorna todas as organizações para o seletor do admin global."""
    try:
        return Organization.objects.all().order_by("name")
    except Exception:
        return []


@register.filter
def proper_name(value: str) -> str:
    """Formata nomes próprios com iniciais maiúsculas, preservando preposições comuns.

    Ex.: "maria das dores e silva" -> "Maria das Dores e Silva"
    """
    if not value:
        return value
    small_words = {"da", "de", "do", "das", "dos", "e"}
    parts = str(value).strip().lower().split()
    formatted = []
    for index, word in enumerate(parts):
        if index > 0 and word in small_words:
            formatted.append(word)
        else:
            formatted.append(word[:1].upper() + word[1:])
    return " ".join(formatted)


@register.filter
def org_names(beneficiary) -> str:
    """Retorna nomes das organizações vinculadas ao beneficiário, separados por vírgula."""
    try:
        names = [ob.organization.name for ob in beneficiary.organizations.all() if getattr(ob, "organization", None)]
        return ", ".join(names)
    except Exception:  # noqa: BLE001
        return ""


@register.filter
def family_org_names(family) -> str:
    """Retorna nomes distintos das organizações associadas aos membros da família."""
    try:
        names = set()
        for m in family.members.all():
            if getattr(m, "beneficiary", None):
                for ob in m.beneficiary.organizations.all():
                    if getattr(ob, "organization", None) and ob.organization.name:
                        names.add(ob.organization.name)
        return ", ".join(sorted(names))
    except Exception:  # noqa: BLE001
        return ""

@register.filter
def guardian_id(members) -> int | None:
    """Recebe um queryset/lista de FamilyMember e retorna o id do beneficiário titular (is_guardian=True)."""
    try:
        for m in members:
            if getattr(m, "is_guardian", False):
                return getattr(getattr(m, "beneficiary", None), "id", None)
    except Exception:  # noqa: BLE001
        return None
    return None

