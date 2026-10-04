from rest_framework_simplejwt.authentication import JWTAuthentication

from core.audit import set_actor


class AuditingJWTAuthentication(JWTAuthentication):
    """JWT authentication that also records the authenticated user as the audit actor."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _token = result
            set_actor(user)
        return result
