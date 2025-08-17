from django.urls import path
from . import views

app_name = "panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("set-active-org/", views.set_active_organization, name="set_active_organization"),
    path("beneficiaries/", views.beneficiary_list, name="beneficiary_list"),
    path("beneficiaries/new/", views.beneficiary_create, name="beneficiary_create"),
    path("beneficiaries/<int:pk>/", views.beneficiary_detail, name="beneficiary_detail"),
    path("beneficiaries/<int:pk>/edit/", views.beneficiary_edit, name="beneficiary_edit"),
    path("distributions/", views.distribution_page, name="distribution_page"),
    path("organization/", views.organization_page, name="organization_page"),
    path("organizations/", views.organization_list, name="organization_list"),
    path("organizations/new/", views.organization_create, name="organization_create"),
    path("organizations/<int:pk>/", views.organization_detail, name="organization_detail"),
    path("organizations/<int:pk>/delete/", views.organization_delete, name="organization_delete"),
    path("organizations/<int:pk>/toggle/", views.organization_toggle_active, name="organization_toggle_active"),
    path("collaborators/", views.collaborators_page, name="collaborators_page"),
    path("collaborators/new/", views.collaborator_create, name="collaborator_create"),
    path("collaborators/<int:pk>/", views.collaborator_detail, name="collaborator_detail"),
    path("collaborators/<int:pk>/edit/", views.collaborator_edit, name="collaborator_edit"),
    path("collaborators/<int:pk>/delete/", views.collaborator_delete, name="collaborator_delete"),
    path("reports/", views.reports_page, name="reports_page"),
    path("families/", views.family_list, name="family_list"),
    path("families/new/", views.family_create, name="family_create"),
    path("events/", views.events_list, name="events_list"),
    path("events/new/", views.event_create, name="event_create"),
    path("events/<int:pk>/", views.event_attendance, name="event_attendance"),
    path("events/<int:pk>/summary/", views.event_summary, name="event_summary"),
    path("stock/", views.stock_page, name="stock_page"),
    path("distribuicoes-rede/", views.network_distributions, name="network_distributions"),
    path("sessions/", views.sessions_page, name="sessions_page"),
    path("sessions/terminate/", views.session_terminate, name="session_terminate"),
    path("audit/", views.audit_page, name="audit_page"),
]


