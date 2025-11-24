from django.contrib import admin
from django.urls import path, include
from panel.views import serve_login_background

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("api/", include("api.urls")),
    # Serve imagem de fundo diretamente
    path("static/img/login-bg.jpeg", serve_login_background, name="login_background"),
    path("", include("panel.urls", namespace="panel")),
]


