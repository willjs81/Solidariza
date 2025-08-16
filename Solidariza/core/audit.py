from __future__ import annotations

from django.utils import timezone
from .models import AuditLog
from . import get_client_ip


def log_action(user, request, action: str, *, model_name: str = "", object_id: str = "", description: str = "", organization=None) -> None:
	try:
		AuditLog.objects.create(
			user=user,
			organization=organization,
			action=action,
			model_name=model_name,
			object_id=str(object_id or ""),
			description=description or "",
			ip_address=get_client_ip(request),
			user_agent=request.META.get("HTTP_USER_AGENT", ""),
			created_at=timezone.now(),
		)
	except Exception:
		# auditoria não deve quebrar fluxo
		return
