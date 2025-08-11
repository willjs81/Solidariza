from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import Organization


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Gerente"
        USER = "USER", "Usuário"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)

    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    def is_manager(self) -> bool:
        return self.role in {self.Role.ADMIN, self.Role.MANAGER}


