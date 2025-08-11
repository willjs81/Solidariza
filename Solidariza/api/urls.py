from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BeneficiaryViewSet, DistributionViewSet

router = DefaultRouter()
router.register(r"beneficiaries", BeneficiaryViewSet, basename="beneficiary")
router.register(r"distributions", DistributionViewSet, basename="distribution")

urlpatterns = [
    path("", include(router.urls)),
]


