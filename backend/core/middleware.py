from core.audit import clear_actor, set_actor


class RequestActorMiddleware:
    """
    Resets the audit actor for every request and sets it to the session user when there is
    one (Django admin). API requests are attributed by core.authentication.AuditingJWTAuthentication.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_actor()
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            set_actor(user)
        else:
            set_actor(None, label="anonymous")
        try:
            return self.get_response(request)
        finally:
            clear_actor()
