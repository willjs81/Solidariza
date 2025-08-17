from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from .models import Organization, UserSession
from . import get_client_ip
from django.utils import timezone


class OrganizationAccessMiddleware:
    """
    Middleware para controlar acesso baseado na organização ativa do usuário.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # URLs que não precisam de verificação
        exempt_urls = [
            '/accounts/login/',
            '/accounts/logout/',
            '/accounts/password_reset/',
            '/admin/',
            '/static/',
            '/media/',
        ]
        
        # Verificar se a URL atual está isenta
        if any(request.path.startswith(url) for url in exempt_urls):
            response = self.get_response(request)
            return response
        
        # Se o usuário não está autenticado, deixar o Django resolver
        if not request.user.is_authenticated:
            response = self.get_response(request)
            return response
        
        # Admin global tem acesso irrestrito
        if request.user.is_superuser:
            # Para admin global, definir organização ativa se não existir
            if 'active_organization_id' not in request.session and request.user.organization:
                request.session['active_organization_id'] = request.user.organization.id
            response = self.get_response(request)
            return response
        
        # Para usuários normais, verificar organização ativa
        active_org_id = request.session.get('active_organization_id')
        
        if not active_org_id:
            # Se não há organização ativa, usar a organização do usuário
            if request.user.organization:
                request.session['active_organization_id'] = request.user.organization.id
            else:
                messages.error(request, 'Usuário não está vinculado a nenhuma organização.')
                return redirect('login')
        else:
            # Verificar se o usuário tem acesso à organização ativa
            try:
                active_org = Organization.objects.get(id=active_org_id)
                if request.user.organization != active_org:
                    messages.error(request, 'Acesso negado a esta organização.')
                    return redirect('login')
            except Organization.DoesNotExist:
                messages.error(request, 'Organização não encontrada.')
                return redirect('login')
        
        response = self.get_response(request)
        # Atualiza last_seen das sessões
        try:
            if request.user.is_authenticated and request.session.session_key:
                # ONG ativa da sessão
                org_id = request.session.get('active_organization_id')
                org = None
                if org_id:
                    try:
                        org = Organization.objects.get(id=org_id)
                    except Organization.DoesNotExist:
                        org = None
                UserSession.objects.update_or_create(
                    session_key=request.session.session_key,
                    defaults={
                        'user': request.user,
                        'organization': org,
                        'ip_address': get_client_ip(request),
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'last_seen': timezone.now(),
                        'is_active': True,
                    },
                )
        except Exception:
            # não bloqueia a request caso a auditoria falhe
            pass
        return response


def get_active_organization(request):
    """
    Função helper para obter a organização ativa do usuário.
    """
    if not request.user.is_authenticated:
        return None
    
    active_org_id = request.session.get('active_organization_id')
    if active_org_id:
        try:
            return Organization.objects.get(id=active_org_id)
        except Organization.DoesNotExist:
            pass
    
    # Fallback para a organização do usuário
    return request.user.organization
