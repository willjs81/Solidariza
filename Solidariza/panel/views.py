from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404

from core.models import (
    Beneficiary,
    Distribution,
    Product,
    StockMovement,
    deliver_basket,
    Organization,
    Family,
    FamilyMember,
    Event,
    Attendance,
)
from django.db import transaction
from core.middleware import get_active_organization
from accounts.models import User
from django.utils import timezone
from django.http import HttpResponseBadRequest
from django.contrib.sessions.models import Session
from core.models import UserSession
from core.audit import log_action


# --- Helpers de permissão ----------------------------------------------------
def require_admin(view_func):
    def _wrapped(request, *args, **kwargs):
        if request.user.is_superuser or (hasattr(request.user, "role") and request.user.role == User.Role.ADMIN):
            return view_func(request, *args, **kwargs)
        messages.error(request, "Acesso negado.")
        return redirect("panel:dashboard")
    return _wrapped


def require_manager_or_admin(view_func):
    def _wrapped(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if hasattr(request.user, "role") and request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return view_func(request, *args, **kwargs)
        messages.error(request, "Acesso negado.")
        return redirect("panel:dashboard")
    return _wrapped

@login_required
def dashboard(request):
    org = get_active_organization(request)
    
    # Verificar produtos com estoque baixo/crítico
    if org is None:
        products = Product.objects.all()
        total_beneficiaries = Beneficiary.objects.count()
    else:
        products = Product.objects.filter(organization=org)
        total_beneficiaries = Beneficiary.objects.filter(organizations__organization=org).count()
    critical_products = []
    low_products = []
    
    for product in products:
        current_stock = StockMovement.get_stock(product)
        # Nível crítico baseado na ONG do produto quando em visão de rede
        if org is None:
            org_beneficiaries = Beneficiary.objects.filter(organizations__organization=product.organization).count()
            critical_level = org_beneficiaries * 0.5
            low_level = org_beneficiaries
        else:
            critical_level = total_beneficiaries * 0.5  # 50% do necessário para 1 mês
            low_level = total_beneficiaries  # Necessário para 1 mês
        
        if current_stock == 0:
            critical_products.append({'name': product.name, 'stock': current_stock, 'status': 'Sem estoque'})
        elif current_stock <= critical_level:
            critical_products.append({'name': product.name, 'stock': current_stock, 'status': 'Crítico'})
        elif current_stock <= low_level:
            low_products.append({'name': product.name, 'stock': current_stock, 'status': 'Baixo'})
    
    # Eventos próximos e último realizado
    if org is None:
        upcoming_events = Event.objects.filter(date__gte=timezone.now().date()).order_by("date")[:5]
        last_event = Event.objects.filter(date__lt=timezone.now().date()).order_by("-date").first()
    else:
        upcoming_events = Event.objects.filter(organization=org, date__gte=timezone.now().date()).order_by("date")[:5]
        last_event = Event.objects.filter(organization=org, date__lt=timezone.now().date()).order_by("-date").first()

    if org is None:
        stock_map = {f"{p.name} - {p.organization.name}": StockMovement.get_stock(p) for p in products}
        beneficiaries_count = Beneficiary.objects.count()
        distributions_count = Distribution.objects.count()
    else:
        stock_map = {p.name: StockMovement.get_stock(p) for p in products}
        beneficiaries_count = Beneficiary.objects.filter(organizations__organization=org).count()
        distributions_count = Distribution.objects.filter(organization=org).count()

    context = {
        "beneficiaries": beneficiaries_count,
        "distributions": distributions_count,
        "stock": stock_map,
        "critical_products": critical_products,
        "low_products": low_products,
        "total_beneficiaries": total_beneficiaries,
        "upcoming_events": upcoming_events,
        "last_event": last_event,
        "org": org,
    }
    return render(request, "panel/dashboard.html", context)


@login_required
def set_active_organization(request):
    """Define ou limpa a organização ativa na sessão.

    - Apenas Admin Global pode usar livremente para qualquer organização.
    - Usuários comuns só podem setar a própria `request.user.organization`.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Método inválido")

    org_id = request.POST.get("organization_id")

    # Admin global pode escolher qualquer uma ou limpar (rede inteira)
    if request.user.is_superuser:
        if not org_id or org_id == "":
            request.session.pop("active_organization_id", None)
            messages.success(request, "Visualizando toda a rede.")
            log_action(request.user, request, "set_active_org", description="Toda a Rede")
            return redirect("panel:dashboard")
        try:
            org = Organization.objects.get(id=org_id)
            request.session["active_organization_id"] = org.id
            messages.success(request, f"Organização ativa: {org.name}")
            log_action(request.user, request, "set_active_org", model_name="Organization", object_id=org.id, description=org.name, organization=org)
        except Organization.DoesNotExist:
            messages.error(request, "Organização não encontrada.")
        return redirect("panel:dashboard")

    # Usuário não-superuser: só pode setar sua própria org
    if hasattr(request.user, "organization") and request.user.organization:
        request.session["active_organization_id"] = request.user.organization.id
        log_action(request.user, request, "set_active_org", model_name="Organization", object_id=request.user.organization.id, description=request.user.organization.name, organization=request.user.organization)
        return redirect("panel:dashboard")

    messages.error(request, "Sem organização vinculada ao usuário.")
    return redirect("panel:dashboard")


@login_required
def beneficiary_list(request):
    org = get_active_organization(request)
    # Mostra beneficiários vinculados à ONG com dados de família
    if org:
        beneficiaries = Beneficiary.objects.filter(organizations__organization=org)
    else:
        beneficiaries = Beneficiary.objects.all()
    beneficiaries = beneficiaries.prefetch_related(
        "family_links__family__members__beneficiary"
    ).order_by("name")
    
    # Estatísticas dos beneficiários
    total_beneficiaries = beneficiaries.count()
    active_beneficiaries = beneficiaries.filter(active=True).count()
    inactive_beneficiaries = total_beneficiaries - active_beneficiaries
    
    # Categorizar por idade
    minors = 0
    adults = 0
    seniors = 0
    without_birth_date = 0
    
    # Categorizar por identificador
    with_identifier = 0
    with_document = 0
    without_identification = 0
    
    # Categorizar por família
    in_families = 0
    guardians = 0
    
    # Distribuições recentes
    from datetime import datetime, timedelta
    recent_date = datetime.now().date() - timedelta(days=30)
    recent_distributions = Distribution.objects.filter(
        beneficiary__in=beneficiaries,
        delivered_at__gte=recent_date
    ).count()
    
    for beneficiary in beneficiaries:
        # Idade
        if beneficiary.birth_date:
            today = timezone.now().date()
            age = today.year - beneficiary.birth_date.year - (
                (today.month, today.day) < (beneficiary.birth_date.month, beneficiary.birth_date.day)
            )
            if age < 18:
                minors += 1
            elif age >= 60:
                seniors += 1
            else:
                adults += 1
        else:
            without_birth_date += 1
        
        # Identificação
        if beneficiary.identifier:
            with_identifier += 1
        elif beneficiary.document:
            with_document += 1
        else:
            without_identification += 1
        
        # Família
        if beneficiary.family_links.exists():
            in_families += 1
            # Verificar se é responsável
            for family_link in beneficiary.family_links.all():
                for member in family_link.family.members.all():
                    if member.beneficiary == beneficiary and member.is_guardian:
                        guardians += 1
                        break
    
    context = {
        "beneficiaries": beneficiaries,
        "total_beneficiaries": total_beneficiaries,
        "active_beneficiaries": active_beneficiaries,
        "inactive_beneficiaries": inactive_beneficiaries,
        "minors": minors,
        "adults": adults,
        "seniors": seniors,
        "without_birth_date": without_birth_date,
        "with_identifier": with_identifier,
        "with_document": with_document,
        "without_identification": without_identification,
        "in_families": in_families,
        "guardians": guardians,
        "not_in_families": total_beneficiaries - in_families,
        "recent_distributions": recent_distributions,
    }
    return render(request, "panel/beneficiary_list.html", context)


@login_required
def beneficiary_create(request):
    if request.method == "POST":
        name = request.POST.get("name")
        identifier = request.POST.get("identifier")
        cep = request.POST.get("cep")
        address = request.POST.get("address")
        address_number = request.POST.get("address_number")
        address_complement = request.POST.get("address_complement")
        district = request.POST.get("district")
        city = request.POST.get("city")
        state = request.POST.get("state")
        birth_date = request.POST.get("birth_date") or None
        # Converter string do input date para objeto date
        if birth_date:
            try:
                from datetime import date as _date
                birth_date = _date.fromisoformat(birth_date)
            except Exception:
                birth_date = None
        holder_id = request.POST.get("holder_id") or None
        is_family_responsible = request.POST.get("is_family_responsible") == "on"
        if name:
            b = Beneficiary(
                name=name,
                identifier=identifier,
                birth_date=birth_date,
                cep=cep or "",
                address=address or "",
                address_number=address_number or "",
                address_complement=address_complement or "",
                district=district or "",
                city=city or "",
                state=state or "",
            )
            try:
                # Validação leve: normaliza o identificador via clean() do modelo,
                # mas não barramos cadastro se o identificador não for um CPF válido
                try:
                    b.clean()
                except Exception:
                    pass
                # Se menor de idade, exigir família e responsável
                if b.birth_date and isinstance(b.birth_date, date) and (
                    timezone.now().date().year
                    - b.birth_date.year
                    - ((timezone.now().date().month, timezone.now().date().day) < (b.birth_date.month, b.birth_date.day))
                ) < 18:
                    if not holder_id:
                        messages.error(request, "Menor de idade requer um titular/responsável.")
                        org = get_active_organization(request)
                        return render(request, "panel/beneficiary_create.html", {"beneficiaries": Beneficiary.objects.filter(organizations__organization=org).order_by("name")})
                    b.save()
                    fam = Family.objects.create(name=f"Família de {b.name}")
                    holder = Beneficiary.objects.get(id=holder_id)
                    FamilyMember.objects.create(
                        family=fam, beneficiary=holder, relation=FamilyMember.Relation.SELF, is_guardian=True
                    )
                    FamilyMember.objects.create(
                        family=fam, beneficiary=b, relation=FamilyMember.Relation.CHILD, is_guardian=False
                    )
                else:
                    b.save()
                    # Se marcado como responsável, cria família automaticamente e o define como titular
                    if is_family_responsible:
                        fam = Family.objects.create(name=b.name)
                        FamilyMember.objects.create(
                            family=fam,
                            beneficiary=b,
                            relation=FamilyMember.Relation.SELF,
                            is_guardian=True,
                        )
                # Garante vínculo do beneficiário com a ONG atual
                from core.models import OrganizationBeneficiary
                org = get_active_organization(request)
                if org:
                    OrganizationBeneficiary.objects.get_or_create(organization=org, beneficiary=b)
                    log_action(request.user, request, "beneficiary_create", model_name="Beneficiary", object_id=b.id, description=b.name, organization=org)
                else:
                    # Se não há ONG ativa, tenta usar a organização do usuário logado (se houver)
                    if hasattr(request.user, 'organization') and request.user.organization:
                        OrganizationBeneficiary.objects.get_or_create(organization=request.user.organization, beneficiary=b)
                        log_action(request.user, request, "beneficiary_create", model_name="Beneficiary", object_id=b.id, description=b.name, organization=request.user.organization)
            except Exception as exc:  # noqa: BLE001
                messages.error(request, str(exc))
                org = get_active_organization(request)
                qs = Beneficiary.objects.all() if not org else Beneficiary.objects.filter(organizations__organization=org)
                return render(request, "panel/beneficiary_create.html", {"beneficiaries": qs.order_by("name")})
            messages.success(request, "Beneficiário criado.")
            return redirect("panel:beneficiary_list")
        messages.error(request, "Nome é obrigatório.")
    org = get_active_organization(request)
    qs = Beneficiary.objects.all() if not org else Beneficiary.objects.filter(organizations__organization=org)
    return render(request, "panel/beneficiary_create.html", {"beneficiaries": qs.order_by("name")})


@login_required
def beneficiary_detail(request, pk: int):
    org = get_active_organization(request)
    b = get_object_or_404(Beneficiary, pk=pk)
    
    # Verifica se o beneficiário está vinculado à organização do usuário
    is_own_beneficiary = b.organizations.filter(organization=org).exists()
    
    fam_link = b.family_links.select_related("family").first()
    # Todas as ONGs podem ver distribuições para controle da rede
    last_distributions = Distribution.objects.filter(beneficiary=b).order_by("-delivered_at")[:10]
    
    can_edit = is_own_beneficiary or request.user.is_superuser
    return render(
        request,
        "panel/beneficiary_detail.html",
        {
            "beneficiary": b, 
            "family": fam_link.family if fam_link else None, 
            "last_distributions": last_distributions,
            "is_own_beneficiary": is_own_beneficiary,
            "can_edit": can_edit,
        },
    )


@login_required
def beneficiary_edit(request, pk: int):
    org = get_active_organization(request)
    b = get_object_or_404(Beneficiary, pk=pk)
    # Permissão: Admin Global pode editar tudo; senão, somente se for da própria ONG
    if not (request.user.is_superuser or b.organizations.filter(organization=org).exists()):
        messages.error(request, "Sem permissão para editar este beneficiário.")
        return redirect("panel:beneficiary_detail", pk=pk)

    if request.method == "POST":
        b.name = request.POST.get("name") or b.name
        b.identifier = request.POST.get("identifier") or b.identifier
        b.address = request.POST.get("address") or b.address
        b.address_number = request.POST.get("address_number") or b.address_number
        b.address_complement = request.POST.get("address_complement") or b.address_complement
        b.district = request.POST.get("district") or b.district
        b.city = request.POST.get("city") or b.city
        b.state = request.POST.get("state") or b.state
        birth = request.POST.get("birth_date")
        if birth:
            try:
                from datetime import date as _date
                b.birth_date = _date.fromisoformat(birth)
            except Exception:
                pass
        try:
            b.clean()
            b.save()
            messages.success(request, "Beneficiário atualizado.")
            return redirect("panel:beneficiary_detail", pk=b.pk)
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))

    return render(request, "panel/beneficiary_edit.html", {"b": b})


@login_required
@require_manager_or_admin
def distribution_page(request):
    org = get_active_organization(request)
    if request.method == "POST":
        beneficiary_id = request.POST.get("beneficiary_id")
        product_id = request.POST.get("product_id")
        period = request.POST.get("period_month")
        try:
            beneficiary = Beneficiary.objects.get(id=beneficiary_id)
            product = Product.objects.get(id=product_id, organization=org)
            period_date = date.fromisoformat(period)
            try:
                deliver_basket(
                    organization=org, beneficiary=beneficiary, product=product, period_month=period_date, user=request.user
                )
                messages.success(request, "Entrega registrada.")
            except Exception as exc:  # noqa: BLE001
                messages.error(request, str(exc))
            return redirect("panel:distribution_page")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))

    beneficiaries = Beneficiary.objects.filter(organizations__organization=org, active=True).order_by("name")
    products = Product.objects.filter(organization=org).order_by("name")
    recent = Distribution.objects.filter(organization=org).order_by("-delivered_at")[:20]
    return render(
        request,
        "panel/distribution.html",
        {"beneficiaries": beneficiaries, "products": products, "recent": recent},
    )


@login_required
@require_manager_or_admin
def stock_page(request):
    org = get_active_organization(request)
    is_network_view = org is None

    # Em visão de rede (admin global sem ONG ativa), operações de POST não são permitidas
    if request.method == "POST":
        if is_network_view:
            messages.error(request, "Na visão 'Toda a Rede' as operações de estoque são somente leitura. Selecione uma organização para registrar movimentações ou cadastrar produtos.")
            return redirect("panel:stock_page")
        action = request.POST.get("action", "movement")
        if action == "create_product":
            name = (request.POST.get("product_name") or "").strip()
            is_bundle = request.POST.get("product_is_bundle") == "on"
            if not name:
                messages.error(request, "Informe o nome do produto.")
            else:
                try:
                    Product.objects.create(organization=org, name=name, is_bundle=is_bundle)
                    messages.success(request, f"Produto '{name}' cadastrado com sucesso.")
                    return redirect("panel:stock_page")
                except Exception as exc:  # noqa: BLE001
                    messages.error(request, f"Não foi possível cadastrar o produto: {exc}")
        else:
            product_id = request.POST.get("product_id")
            kind = request.POST.get("kind")
            quantity = int(request.POST.get("quantity") or 0)
            reason = request.POST.get("reason") or ""
            try:
                product = Product.objects.get(id=product_id, organization=org)
                if quantity <= 0:
                    messages.error(request, "Quantidade deve ser maior que zero.")
                elif kind not in (StockMovement.IN, StockMovement.OUT):
                    messages.error(request, "Tipo de movimentação inválido.")
                else:
                    StockMovement.objects.create(
                        organization=org, product=product, kind=kind, quantity=quantity, reason=reason, created_by=request.user
                    )
                    log_action(request.user, request, "stock_movement", model_name="StockMovement", object_id=product.id, description=f"{kind} {quantity} {product.name}", organization=org)
                    messages.success(request, "Movimentação registrada com sucesso.")
                    return redirect("panel:stock_page")
            except Exception as exc:  # noqa: BLE001
                messages.error(request, str(exc))
    # Buscar produtos com estatísticas
    if is_network_view:
        products = Product.objects.all().select_related("organization").order_by("organization__name", "name")
    else:
        products = Product.objects.filter(organization=org).order_by("name")
        # Se não houver produto cadastrado, cria um padrão para facilitar o primeiro uso
        if not products.exists():
            Product.objects.create(organization=org, name="Cesta Básica", is_bundle=True)
            messages.info(request, "Produto padrão 'Cesta Básica' criado para esta organização.")
            products = Product.objects.filter(organization=org).order_by("name")
    
    # Calcular estatísticas de estoque para cada produto
    stock_data = []
    total_beneficiaries = Beneficiary.objects.count() if is_network_view else Beneficiary.objects.filter(organizations__organization=org).count()
    
    for product in products:
        # Estoque atual
        current_stock = StockMovement.get_stock(product)
        
        # Total de entradas e saídas
        from django.db import models
        entries = StockMovement.objects.filter(
            product=product, kind=StockMovement.IN
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        
        exits = StockMovement.objects.filter(
            product=product, kind=StockMovement.OUT
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        
        # Calcular nível crítico (estimativa para 1 mês baseado no número de beneficiários)
        # Em visão de rede, o nível crítico considera a base de assistidos da própria organização do produto
        if is_network_view:
            org_beneficiaries = Beneficiary.objects.filter(organizations__organization=product.organization).count()
            critical_level = org_beneficiaries
            estimated_month_supply = int(org_beneficiaries * 1.2)
        else:
            critical_level = total_beneficiaries  # 1 unidade por beneficiário
            estimated_month_supply = int(total_beneficiaries * 1.2)  # 20% de margem
        
        # Status do estoque
        if current_stock == 0:
            status = "empty"
            status_text = "Sem estoque"
        elif current_stock <= critical_level * 0.5:  # 50% do nível crítico
            status = "critical"
            status_text = "Crítico"
        elif current_stock <= critical_level:
            status = "low"
            status_text = "Baixo"
        else:
            status = "good"
            status_text = "Adequado"
        
        # Dias de suprimento estimado
        days_supply = 0
        if total_beneficiaries > 0 and current_stock > 0:
            daily_consumption = total_beneficiaries / 30  # Assumindo consumo mensal distribuído
            days_supply = int(current_stock / daily_consumption) if daily_consumption > 0 else 999
        
        stock_data.append({
            'product': product,
            'current_stock': current_stock,
            'entries': entries,
            'exits': exits,
            'critical_level': critical_level,
            'estimated_month_supply': estimated_month_supply,
            'status': status,
            'status_text': status_text,
            'days_supply': days_supply
        })
    
    # Movimentos recentes (somente da ONG ativa; na visão de rede ocultamos no template)
    movements = [] if is_network_view else list(StockMovement.objects.filter(organization=org).select_related("product").order_by("-created_at")[:50])
    
    # Estatísticas gerais
    products_in_critical = sum(1 for item in stock_data if item['status'] in ['empty', 'critical'])
    products_low = sum(1 for item in stock_data if item['status'] == 'low')
    
    context = {
        "products": products,
        "stock_data": stock_data,
        "movements": movements,
        "StockMovement": StockMovement,
        "total_beneficiaries": total_beneficiaries,
        "products_in_critical": products_in_critical,
        "products_low": products_low,
        "is_network_view": is_network_view,
    }
    return render(request, "panel/stock.html", context)


@login_required
def network_distributions(request):
    """Visão global das distribuições da rede com próximas entregas."""
    from datetime import datetime, timedelta
    from django.db.models import Max, Count
    
    # Distribuições recentes (últimos 30 dias)
    recent_date = datetime.now().date() - timedelta(days=30)
    recent_distributions = Distribution.objects.filter(
        delivered_at__gte=recent_date
    ).select_related("beneficiary", "product", "organization").order_by("-delivered_at")
    
    # Beneficiários e sua última distribuição
    beneficiaries_with_last_distribution = Beneficiary.objects.annotate(
        last_distribution_date=Max("distribution__delivered_at"),
        total_distributions=Count("distribution")
    ).filter(
        last_distribution_date__isnull=False
    ).order_by("-last_distribution_date")
    
    # Estatísticas da rede
    total_beneficiaries = Beneficiary.objects.count()
    total_distributions = Distribution.objects.count()
    total_organizations = Organization.objects.count()
    
    context = {
        "recent_distributions": recent_distributions[:100],  # Limitar para performance
        "beneficiaries_with_last": beneficiaries_with_last_distribution[:50],
        "total_beneficiaries": total_beneficiaries,
        "total_distributions": total_distributions,
        "total_organizations": total_organizations,
    }
    return render(request, "panel/network_distributions.html", context)


@login_required
def sessions_page(request):
    if not request.user.is_superuser:
        messages.error(request, "Acesso negado.")
        return redirect("panel:dashboard")
    from datetime import timedelta
    now = timezone.now()
    rng = (request.GET.get("range") or "5").strip()
    valid = {"5": 5, "15": 15, "30": 30}
    if rng == "all":
        sessions = UserSession.objects.select_related("user", "organization").order_by("-last_seen")
    else:
        minutes = valid.get(rng, 5)
        online_threshold = now - timedelta(minutes=minutes)
        sessions = (
            UserSession.objects.select_related("user", "organization")
            .filter(last_seen__gte=online_threshold, is_active=True)
            .order_by("-last_seen")
        )
    return render(request, "panel/sessions.html", {"sessions": sessions, "now": now, "range": rng})


@login_required
def session_terminate(request):
    if not request.user.is_superuser:
        messages.error(request, "Acesso negado.")
        return redirect("panel:sessions_page")
    if request.method != "POST":
        return HttpResponseBadRequest("Método inválido")
    key = request.POST.get("session_key")
    if not key:
        messages.error(request, "Chave de sessão não informada.")
        return redirect("panel:sessions_page")
    # Encerrar: marca como inativa e apaga a sessão do Django se existir
    UserSession.objects.filter(session_key=key).update(is_active=False)
    try:
        Session.objects.filter(session_key=key).delete()
    except Exception:
        pass
    log_action(request.user, request, "session_terminate", model_name="UserSession", object_id=key, description="Encerrar sessão")
    messages.success(request, "Sessão encerrada.")
    return redirect("panel:sessions_page")


@login_required
def audit_page(request):
    if not request.user.is_superuser:
        messages.error(request, "Acesso negado.")
        return redirect("panel:dashboard")
    from core.models import AuditLog, Organization
    qs = AuditLog.objects.select_related("user", "organization").order_by("-created_at")
    org_id = request.GET.get("organization")
    start = request.GET.get("start")
    end = request.GET.get("end")
    if org_id:
        try:
            qs = qs.filter(organization_id=int(org_id))
        except Exception:
            pass
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    logs = qs[:500]
    orgs = Organization.objects.all().order_by("name")
    return render(request, "panel/audit.html", {"logs": logs, "organizations": orgs, "organization": org_id or "", "start": start or "", "end": end or ""})

@login_required
def organization_page(request):
    """Página de gestão da organização com colaboradores e assistidos."""
    org = get_active_organization(request)
    if not org:
        messages.error(request, "Usuário não está vinculado a uma organização.")
        return redirect("panel:dashboard")
    

    
    # Colaboradores da organização
    collaborators = User.objects.filter(organization=org).order_by("first_name", "last_name")
    
    # Assistidos vinculados à organização
    if org:
        beneficiaries = Beneficiary.objects.filter(organizations__organization=org).order_by("name")
    else:
        beneficiaries = Beneficiary.objects.all().order_by("name")
    
    # Estatísticas gerais
    total_collaborators = collaborators.count()
    total_beneficiaries = beneficiaries.count()
    
    # Estatísticas por papel
    admins = collaborators.filter(role=User.Role.ADMIN).count()
    managers = collaborators.filter(role=User.Role.MANAGER).count()
    users = collaborators.filter(role=User.Role.USER).count()
    
    # Estatísticas de beneficiários
    active_beneficiaries = beneficiaries.filter(active=True).count()
    inactive_beneficiaries = total_beneficiaries - active_beneficiaries
    
    # Distribuições recentes
    from datetime import datetime, timedelta
    recent_date = datetime.now().date() - timedelta(days=30)
    recent_distributions = Distribution.objects.filter(
        organization=org,
        delivered_at__gte=recent_date
    ).count()
    
    # Eventos recentes
    recent_events = Event.objects.filter(
        organization=org,
        date__gte=recent_date
    ).count()
    
    context = {
        "org": org,
        "collaborators": collaborators,
        "beneficiaries": beneficiaries,
        "total_collaborators": total_collaborators,
        "total_beneficiaries": total_beneficiaries,
        "admins": admins,
        "managers": managers,
        "users": users,
        "active_beneficiaries": active_beneficiaries,
        "inactive_beneficiaries": inactive_beneficiaries,
        "recent_distributions": recent_distributions,
        "recent_events": recent_events,
    }
    return render(request, "panel/organization.html", context)


@login_required
def organization_list(request):
    """Lista de organizações (só Admin Global)."""
    if not request.user.is_superuser:
        messages.error(request, "Acesso negado.")
        return redirect("panel:organization_page")
    
    orgs = Organization.objects.all().order_by("name")
    return render(request, "panel/organization_list.html", {"orgs": orgs})


@login_required
def organization_create(request):
    # Apenas admin global pode criar ONGs
    if not request.user.is_superuser:
        messages.error(request, "Apenas o administrador global pode criar organizações.")
        return redirect("panel:organization_page")
    
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            Organization.objects.create(name=name)
            messages.success(request, f"Organização '{name}' criada com sucesso.")
            return redirect("panel:organization_list")
        else:
            messages.error(request, "Nome da organização é obrigatório.")
    
    return render(request, "panel/organization_create.html")


@login_required
def organization_detail(request, pk):
    """Detalhe de uma organização específica (só Admin Global)."""
    if not request.user.is_superuser:
        messages.error(request, "Acesso negado.")
        return redirect("panel:organization_page")
    
    org = get_object_or_404(Organization, pk=pk)
    collaborators = User.objects.filter(organization=org).order_by("first_name", "last_name")
    beneficiaries = Beneficiary.objects.filter(organizations__organization=org).order_by("name")
    
    context = {
        "org": org,
        "collaborators": collaborators,
        "beneficiaries": beneficiaries,
        "total_collaborators": collaborators.count(),
        "total_beneficiaries": beneficiaries.count(),
    }
    return render(request, "panel/organization_detail.html", context)


@login_required
def organization_delete(request, pk: int):
    if not request.user.is_superuser:
        messages.error(request, "Apenas o administrador global pode excluir organizações.")
        return redirect("panel:organization_list")

    org = get_object_or_404(Organization, pk=pk)
    if request.method == "POST":
        name = org.name
        try:
            with transaction.atomic():
                # Remover dependências que podem proteger a exclusão (ordem importa)
                Distribution.objects.filter(organization=org).delete()
                StockMovement.objects.filter(organization=org).delete()
                Attendance.objects.filter(event__organization=org).delete()
                Event.objects.filter(organization=org).delete()
                Product.objects.filter(organization=org).delete()
                # Colaboradores vinculados à ONG
                # Preserva superusuários: apenas desvincula a organização
                User.objects.filter(organization=org, is_superuser=True).update(organization=None)
                # Remove demais colaboradores da ONG
                User.objects.filter(organization=org, is_superuser=False).delete()
                # Vínculos organização/beneficiário
                from core.models import OrganizationBeneficiary
                OrganizationBeneficiary.objects.filter(organization=org).delete()
                # Por fim, a própria organização
                org.delete()
            messages.success(request, f"Organização '{name}' excluída com sucesso.")
            return redirect("panel:organization_list")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"Não foi possível excluir a organização: {exc}")
            return redirect("panel:organization_detail", pk=org.pk)

    return render(request, "panel/organization_delete_confirm.html", {"org": org})


@login_required
def organization_toggle_active(request, pk: int):
    if not request.user.is_superuser:
        messages.error(request, "Apenas o administrador global pode alterar o status da organização.")
        return redirect("panel:organization_list")
    org = get_object_or_404(Organization, pk=pk)
    org.is_active = not org.is_active
    org.save(update_fields=["is_active"])
    status = "ativada" if org.is_active else "desativada"
    messages.success(request, f"Organização '{org.name}' {status}.")
    return redirect("panel:organization_detail", pk=org.pk)


@login_required
def collaborators_page(request):
    org = get_active_organization(request)
    collaborators = User.objects.filter(organization=org).order_by("username")
    return render(request, "panel/collaborators.html", {"collaborators": collaborators})


@login_required
@require_admin
def collaborator_create(request):
    if not (request.user.is_admin() or request.user.is_superuser):
        messages.error(request, "Apenas administradores podem criar colaboradores.")
        return redirect("panel:collaborators_page")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        role = request.POST.get("role")
        email = request.POST.get("email")
        org_id = request.POST.get("organization_id")
        try:
            org = Organization.objects.get(id=org_id)
        except Exception:
            org = get_active_organization(request)
        if username and password and role:
            u = User.objects.create_user(username=username, password=password, email=email, organization=org, role=role)
            messages.success(request, "Colaborador criado.")
            return redirect("panel:collaborator_detail", pk=u.pk)
        messages.error(request, "Preencha os campos obrigatórios.")
    orgs = Organization.objects.all().order_by("name")
    return render(request, "panel/collaborator_create.html", {"orgs": orgs})


@login_required
def collaborator_detail(request, pk: int):
    if request.user.is_superuser:
        u = get_object_or_404(User, pk=pk)
    else:
        u = get_object_or_404(User, pk=pk, organization=request.user.organization)
    return render(request, "panel/collaborator_detail.html", {"user_obj": u})


@login_required
@require_admin
def collaborator_edit(request, pk: int):
    if not (request.user.is_admin() or request.user.is_superuser):
        messages.error(request, "Apenas administradores podem editar colaboradores.")
        return redirect("panel:collaborators_page")
    u = User.objects.get(pk=pk)
    if request.method == "POST":
        org_id = request.POST.get("organization_id")
        role = request.POST.get("role")
        if org_id:
            try:
                u.organization = Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                pass
        if role:
            u.role = role
        u.save()
        messages.success(request, "Colaborador atualizado.")
        return redirect("panel:collaborator_detail", pk=u.pk)
    orgs = Organization.objects.all().order_by("name")
    return render(request, "panel/collaborator_edit.html", {"user_obj": u, "orgs": orgs})


@login_required
def reports_page(request):
    org = get_active_organization(request)
    # CSV simples: lista de distribuições por mês
    if request.GET.get("download") == "distributions_csv":
        if not (request.user.is_superuser or request.user.role in {User.Role.ADMIN, User.Role.MANAGER}):
            messages.error(request, "Acesso negado ao download.")
            return redirect("panel:reports_page")
        from django.http import HttpResponse
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=distribuicoes.csv"
        writer = csv.writer(response)
        writer.writerow(["Beneficiário", "Produto", "Mês", "Entregue em"])
        for d in Distribution.objects.filter(organization=org).order_by("-delivered_at"):
            writer.writerow([d.beneficiary.name, d.product.name, d.period_month.strftime("%Y-%m"), d.delivered_at])
        return response

    if request.GET.get("download") == "families_csv":
        if not (request.user.is_superuser or request.user.role in {User.Role.ADMIN, User.Role.MANAGER}):
            messages.error(request, "Acesso negado ao download.")
            return redirect("panel:reports_page")
        from django.http import HttpResponse
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=familias.csv"
        writer = csv.writer(response)
        writer.writerow(["Família", "Membro", "Relação", "Responsável?"])
        for fam in Family.objects.all():
            for m in fam.members.select_related("beneficiary"):
                writer.writerow([fam.name or f"Família #{fam.id}", m.beneficiary.name, m.relation, "sim" if m.is_guardian else "não"])
        return response

    if request.GET.get("download") == "minors_csv":
        if not (request.user.is_superuser or request.user.role in {User.Role.ADMIN, User.Role.MANAGER}):
            messages.error(request, "Acesso negado ao download.")
            return redirect("panel:reports_page")
        from django.http import HttpResponse
        import csv
        from datetime import date as dt

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=menores.csv"
        writer = csv.writer(response)
        writer.writerow(["Beneficiário", "Data de nascimento", "Idade", "Família"])
        today = dt.today()
        qs = Beneficiary.objects.filter(organization=org, birth_date__isnull=False)
        for b in qs:
            age = today.year - b.birth_date.year - ((today.month, today.day) < (b.birth_date.month, b.birth_date.day))
            if age < 18:
                fam_link = b.family_links.first()
                fam_name = fam_link.family.name if fam_link else ""
                writer.writerow([b.name, b.birth_date, age, fam_name])
        return response
    
    # CSV de eventos/presenças
    if request.GET.get("download") == "events_csv":
        if not (request.user.is_superuser or request.user.role in {User.Role.ADMIN, User.Role.MANAGER}):
            messages.error(request, "Acesso negado ao download.")
            return redirect("panel:reports_page")
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="eventos_presencas.csv"'
        response.write("\ufeff")
        
        writer = csv.writer(response)
        writer.writerow(["Evento", "Data", "ID", "Participante", "Identificador", "Status"])
        
        events_data = Event.objects.all().order_by("-date")
        for event in events_data:
            attendances = Attendance.objects.filter(event=event).select_related("beneficiary").prefetch_related(
                "beneficiary__family_links__family__members__beneficiary"
            )
            for attendance in attendances:
                # Usar a mesma lógica dos filtros
                identification = attendance.beneficiary.identifier or attendance.beneficiary.document or f"ID: #{attendance.beneficiary.id}"
                if not attendance.beneficiary.identifier and not attendance.beneficiary.document and attendance.beneficiary.birth_date:
                    from datetime import date as dt
                    today = dt.today()
                    age = today.year - attendance.beneficiary.birth_date.year - (
                        (today.month, today.day) < (attendance.beneficiary.birth_date.month, attendance.beneficiary.birth_date.day)
                    )
                    if age < 18:
                        # Buscar responsável
                        for family_link in attendance.beneficiary.family_links.all():
                            if family_link.family:
                                for member in family_link.family.members.all():
                                    if member.is_guardian and member.beneficiary.identifier:
                                        identification = f"Resp: {member.beneficiary.identifier}"
                                        break
                                break
                
                writer.writerow([
                    event.name,
                    event.date.strftime("%d/%m/%Y"),
                    attendance.beneficiary.id,
                    attendance.beneficiary.name,
                    identification,
                    "Presente" if attendance.present else "Ausente",
                ])
        
        return response

    # Tabelas na tela com filtros melhorados
    dist_qs = Distribution.objects.select_related("beneficiary", "product", "organization").order_by("-delivered_at")
    
    # Filtros
    filter_type = request.GET.get("filter_type", "all")  # all, org, name, cpf, id, events
    filter_value = request.GET.get("filter_value", "")
    start = request.GET.get("start")
    end = request.GET.get("end")
    organization_filter = request.GET.get("organization")
    event_filter = request.GET.get("event")
    selected_org = None
    if organization_filter:
        try:
            selected_org = Organization.objects.get(id=organization_filter)
        except Organization.DoesNotExist:
            selected_org = None
    
    # Aplicar filtros
    if filter_type == "cpf" and filter_value:
        dist_qs = dist_qs.filter(beneficiary__identifier__icontains=filter_value)
    elif filter_type == "name" and filter_value:
        dist_qs = dist_qs.filter(beneficiary__name__icontains=filter_value)
    elif filter_type == "id" and filter_value:
        try:
            dist_qs = dist_qs.filter(beneficiary__id=int(filter_value))
        except ValueError:
            pass
    elif filter_type == "org":
        dist_qs = dist_qs.filter(organization=org)
    elif filter_type == "events" and filter_value:
        # Filtrar beneficiários que participaram de eventos
        beneficiaries_in_events = Attendance.objects.filter(
            event__name__icontains=filter_value
        ).values_list('beneficiary_id', flat=True)
        dist_qs = dist_qs.filter(beneficiary_id__in=beneficiaries_in_events)
    
    if organization_filter:
        dist_qs = dist_qs.filter(organization_id=organization_filter)
    if event_filter:
        # Filtrar por evento específico
        beneficiaries_in_event = Attendance.objects.filter(
            event_id=event_filter
        ).values_list('beneficiary_id', flat=True)
        dist_qs = dist_qs.filter(beneficiary_id__in=beneficiaries_in_event)
    if start:
        dist_qs = dist_qs.filter(delivered_at__date__gte=start)
    if end:
        dist_qs = dist_qs.filter(delivered_at__date__lte=end)
    
    dist_qs = dist_qs[:200]

    # Famílias: respeitar organização escolhida ou ONG ativa
    if selected_org is not None:
        families = Family.objects.filter(
            members__beneficiary__organizations__organization=selected_org
        ).distinct().prefetch_related("members__beneficiary")[:50]
    elif org is not None:
        families = Family.objects.filter(
            members__beneficiary__organizations__organization=org
        ).distinct().prefetch_related("members__beneficiary")[:50]
    else:
        families = Family.objects.all().prefetch_related("members__beneficiary")[:50]

    organizations = Organization.objects.all().order_by("name")

    # Eventos: restringir à organização escolhida ou à ONG ativa; admin global sem filtro vê todos
    if selected_org is not None:
        events = Event.objects.filter(organization=selected_org).order_by("-date")
    elif org is not None:
        events = Event.objects.filter(organization=org).order_by("-date")
    else:
        events = Event.objects.all().order_by("-date")
    
    return render(request, "panel/reports.html", {
        "distributions": dist_qs, 
        "families": families,
        "organizations": organizations,
        "events": events,
        "filter_type": filter_type,
        "filter_value": filter_value,
        "start": start,
        "end": end,
        "organization_filter": organization_filter,
        "event_filter": event_filter,
    })


@login_required
def family_list(request):
    org = get_active_organization(request)
    if org is not None:
        families = (
            Family.objects.filter(
                members__beneficiary__organizations__organization=org
            )
            .distinct()
            .prefetch_related("members__beneficiary")
            .order_by("id")
        )
    else:
        # Visão de rede: listar todas as famílias
        families = (
            Family.objects.all()
            .prefetch_related("members__beneficiary")
            .order_by("id")
        )
    
    # Estatísticas das famílias
    total_families = families.count()
    total_members = 0
    families_with_minors = 0
    families_with_guardians = 0
    
    family_details = []
    for family in families:
        members = family.members.all()
        family_member_count = members.count()
        total_members += family_member_count
        
        has_minor = False
        has_guardian = False
        minors_count = 0
        adults_count = 0
        
        for member in members:
            if member.beneficiary.birth_date:
                today = timezone.now().date()
                age = today.year - member.beneficiary.birth_date.year - (
                    (today.month, today.day) < (member.beneficiary.birth_date.month, member.beneficiary.birth_date.day)
                )
                if age < 18:
                    has_minor = True
                    minors_count += 1
                else:
                    adults_count += 1
            else:
                adults_count += 1  # Se não tem data de nascimento, considera adulto
                
            if member.is_guardian:
                has_guardian = True
        
        if has_minor:
            families_with_minors += 1
        if has_guardian:
            families_with_guardians += 1
            
        family_details.append({
            'family': family,
            'members': members,
            'member_count': family_member_count,
            'minors_count': minors_count,
            'adults_count': adults_count,
            'has_guardian': has_guardian,
            'has_minor': has_minor,
        })
    
    context = {
        "families": families,
        "family_details": family_details,
        "total_families": total_families,
        "total_members": total_members,
        "families_with_minors": families_with_minors,
        "families_with_guardians": families_with_guardians,
        "avg_members_per_family": round(total_members / total_families, 1) if total_families > 0 else 0,
    }
    return render(request, "panel/family_list.html", context)


@login_required
def family_create(request):
    if request.method == "POST":
        name = request.POST.get("name") or ""
        titular_id = request.POST.get("holder_id")
        member_ids = request.POST.getlist("member_ids")
        org = get_active_organization(request)
        # Se não informar nome, usar o nome do titular automaticamente
        holder_name = None
        if titular_id:
            try:
                holder_name = Beneficiary.objects.get(id=titular_id).name
            except Beneficiary.DoesNotExist:
                holder_name = None
        family = Family.objects.create(name=name or (holder_name or ""))
        if titular_id:
            holder = Beneficiary.objects.get(id=titular_id)
            FamilyMember.objects.create(family=family, beneficiary=holder, relation=FamilyMember.Relation.SELF, is_guardian=True)
        for mid in member_ids:
            try:
                b = Beneficiary.objects.get(id=mid)
                FamilyMember.objects.create(family=family, beneficiary=b, relation=FamilyMember.Relation.OTHER)
            except Beneficiary.DoesNotExist:
                continue
        # Dependentes criados inline
        dep_names = request.POST.getlist("dep_name[]")
        dep_ids = request.POST.getlist("dep_identifier[]")
        dep_births = request.POST.getlist("dep_birth[]")
        for i, dep_name in enumerate(dep_names):
            if dep_name:
                b = Beneficiary.objects.create(
                    name=dep_name,
                    identifier=dep_ids[i] if i < len(dep_ids) else "",
                    birth_date=dep_births[i] if i < len(dep_births) else None,
                )
                # Vincular o beneficiário à organização através da tabela M2M
                from core.models import OrganizationBeneficiary
                OrganizationBeneficiary.objects.create(organization=org, beneficiary=b)
                FamilyMember.objects.create(family=family, beneficiary=b, relation=FamilyMember.Relation.CHILD)
        messages.success(request, "Família criada.")
        return redirect("panel:family_list")

    org = get_active_organization(request)
    beneficiaries = Beneficiary.objects.all().order_by("name") if not org else Beneficiary.objects.filter(organizations__organization=org).order_by("name")
    # Pré-seleção do titular via querystring (holder_id)
    preselected_holder = request.GET.get("holder_id")
    return render(request, "panel/family_create.html", {"beneficiaries": beneficiaries, "preselected_holder": preselected_holder})


@login_required
def events_list(request):
    org = get_active_organization(request)
    events = Event.objects.filter(organization=org).order_by("-date")
    return render(request, "panel/events_list.html", {"events": events})


@login_required
def event_summary(request, pk):
    """Resumo de participantes de um evento."""
    org = get_active_organization(request)
    event = get_object_or_404(Event, pk=pk, organization=org)
    
    # Presenças do evento com dados de família
    attendances = Attendance.objects.filter(event=event).select_related(
        "beneficiary"
    ).prefetch_related(
        "beneficiary__family_links__family__members__beneficiary"
    )
    total_attendances = attendances.count()
    
    # Estatísticas
    present_count = attendances.filter(present=True).count()
    absent_count = attendances.filter(present=False).count()
    
    context = {
        "event": event,
        "attendances": attendances,
        "total_attendances": total_attendances,
        "present_count": present_count,
        "absent_count": absent_count,
    }
    return render(request, "panel/event_summary.html", context)


@login_required
@require_manager_or_admin
def event_create(request):
    org = get_active_organization(request)
    if request.method == "POST":
        name = request.POST.get("name")
        date_str = request.POST.get("date")
        try:
            d = date.fromisoformat(date_str)
        except Exception:
            d = timezone.now().date()
        if name:
            Event.objects.create(organization=org, name=name, date=d)
            messages.success(request, "Evento criado.")
            return redirect("panel:events_list")
    return render(request, "panel/event_create.html")


@login_required
@require_manager_or_admin
def event_attendance(request, pk: int):
    org = get_active_organization(request)
    event = Event.objects.get(pk=pk, organization=org)
    if request.method == "POST":
        for b in Beneficiary.objects.filter(organizations__organization=org):
            present = request.POST.get(f"b_{b.id}") == "on"
            Attendance.objects.update_or_create(event=event, beneficiary=b, defaults={"present": present})
        messages.success(request, "Presenças salvas.")
        return redirect("panel:events_list")
    attendees = Attendance.objects.filter(event=event).select_related("beneficiary")
    existing = {a.beneficiary_id: a.present for a in attendees}
    if org:
        beneficiaries = Beneficiary.objects.filter(organizations__organization=org).order_by("name")
    else:
        beneficiaries = Beneficiary.objects.all().order_by("name")
    return render(
        request,
        "panel/event_attendance.html",
        {"event": event, "beneficiaries": beneficiaries, "existing": existing},
    )


