from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Organização & Papel", {"fields": ("organization", "role")}),
    )
    list_display = ("username", "email", "organization", "role", "is_staff")


