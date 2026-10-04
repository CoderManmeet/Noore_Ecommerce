from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Core platform"

    def ready(self):
        from core import signals  # noqa: F401  (registers audit signal handlers)
        from core import builtin_jobs  # noqa: F401  (registers built-in periodic jobs)
