from django.contrib.auth import authenticate, login
from django.contrib.auth.views import LoginView
from django.shortcuts import render, redirect
from django.contrib import messages
from core.models import Organization


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Adicionar lista de organizações ativas para o dropdown
        context['organizations'] = Organization.objects.filter(is_active=True).order_by('name')
        return context
    
    def form_valid(self, form):
        """
        Processa o login com seleção de organização.
        """
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        selected_org_id = self.request.POST.get('organization')
        
        # Autenticar usuário
        user = authenticate(username=username, password=password)
        
        if user is not None:
            # Verificar se é admin global (pode acessar qualquer organização)
            if user.is_superuser:
                login(self.request, user)
                # Se selecionou uma organização específica, definir como organização ativa
                if selected_org_id:
                    try:
                        selected_org = Organization.objects.get(id=selected_org_id, is_active=True)
                        self.request.session['active_organization_id'] = selected_org.id
                    except Organization.DoesNotExist:
                        pass
                return redirect('panel:dashboard')
            
            # Para usuários não-superusuários, a seleção de organização é obrigatória
            if not selected_org_id:
                messages.error(self.request, 'Selecione a organização vinculada ao seu usuário para entrar.')
                return self.form_invalid(form)

            try:
                selected_org = Organization.objects.get(id=selected_org_id, is_active=True)
            except Organization.DoesNotExist:
                messages.error(self.request, 'Organização não encontrada.')
                return self.form_invalid(form)

            if user.organization != selected_org:
                messages.error(self.request, 'Você não tem permissão para acessar esta organização.')
                return self.form_invalid(form)

            login(self.request, user)
            # Para qualquer papel (ADMIN, MANAGER, USER), definir ONG ativa e seguir para o dashboard
            self.request.session['active_organization_id'] = selected_org.id
            return redirect('panel:dashboard')
        
        messages.error(self.request, 'Credenciais inválidas.')
        return self.form_invalid(form)
