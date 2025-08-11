from datetime import date

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Beneficiary, Distribution, Product, deliver_basket
from core.validators import normalize_identifier
from .serializers import BeneficiarySerializer, DistributionSerializer


class BeneficiaryViewSet(viewsets.ModelViewSet):
    serializer_class = BeneficiarySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Beneficiary.objects.filter(organizations__organization=user.organization)


class DistributionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DistributionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Distribution.objects.filter(organization=user.organization)

    @action(methods=["post"], detail=False)
    def deliver(self, request):
        user = request.user
        beneficiary_id = request.data.get("beneficiary_id")
        product_id = request.data.get("product_id")
        period_month = request.data.get("period_month")  # "YYYY-MM-01"

        try:
            beneficiary = Beneficiary.objects.get(id=beneficiary_id, organization=user.organization)
            product = Product.objects.get(id=product_id, organization=user.organization)
            period = date.fromisoformat(period_month)
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            distribution = deliver_basket(
                organization=user.organization,
                beneficiary=beneficiary,
                product=product,
                period_month=period,
                user=user,
            )
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(distribution)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(methods=["get"], detail=False, url_path="check-by-identifier")
    def check_by_identifier(self, request):
        identifier = normalize_identifier(request.query_params.get("identifier"))
        period_month = request.query_params.get("period_month")
        if not identifier or not period_month:
            return Response({"detail": "identifier e period_month são obrigatórios"}, status=400)
        try:
            period = date.fromisoformat(period_month)
        except Exception:  # noqa: BLE001
            return Response({"detail": "period_month inválido (YYYY-MM-01)"}, status=400)
        month_start = period.replace(day=1)
        try:
            b = Beneficiary.objects.get(identifier=identifier)
        except Beneficiary.DoesNotExist:
            return Response({"exists": False})
        exists = Distribution.objects.filter(beneficiary=b, period_month=month_start).exists()
        return Response({"exists": exists})


