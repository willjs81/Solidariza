from django.contrib import admin

from .models import Organization, Guardian, Beneficiary, Event, Attendance, Product, StockMovement, Distribution


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    verbose_name = "Organização"
    verbose_name_plural = "Organizações"


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "document", "phone")
    search_fields = ("name", "document")


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ("name", "identifier", "organization", "active")
    list_filter = ("organization", "active")
    search_fields = ("name", "identifier", "document")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "date")
    list_filter = ("organization", "date")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("event", "beneficiary", "present")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_bundle")
    list_filter = ("organization", "is_bundle")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "organization", "kind", "quantity", "created_at")
    list_filter = ("organization", "product", "kind")


@admin.register(Distribution)
class DistributionAdmin(admin.ModelAdmin):
    list_display = ("beneficiary", "organization", "product", "period_month", "delivered_at")
    list_filter = ("organization", "period_month")


