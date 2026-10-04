from django.apps import AppConfig


class StoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'store'

    def ready(self):
        from store import jobs  # noqa: F401  (draft expiry, payment reconcile, review requests)
        from store import emails  # noqa: F401  (registers the order-email jobs)
