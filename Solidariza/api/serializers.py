from rest_framework import serializers

from core.models import Beneficiary, Distribution, Product


class BeneficiarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Beneficiary
        fields = [
            "id",
            "name",
            "identifier",
            "document",
            "birth_date",
            "cep",
            "address",
            "address_number",
            "address_complement",
            "district",
            "city",
            "state",
            "active",
        ]
        read_only_fields = ["id"]


class DistributionSerializer(serializers.ModelSerializer):
    beneficiary = BeneficiarySerializer(read_only=True)
    beneficiary_id = serializers.PrimaryKeyRelatedField(
        queryset=Beneficiary.objects.all(), source="beneficiary", write_only=True
    )
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), source="product")

    class Meta:
        model = Distribution
        fields = [
            "id",
            "beneficiary",
            "beneficiary_id",
            "product_id",
            "period_month",
            "delivered_at",
        ]


