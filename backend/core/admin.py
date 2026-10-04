from django.contrib import admin

from core.models import AuditLog, Job, ProcessedEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "actor_label", "action", "content_type", "object_id", "object_repr"]
    list_filter = ["action", "content_type"]
    search_fields = ["object_id", "object_repr", "actor_label", "action"]
    date_hierarchy = "created_at"


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(ReadOnlyAdmin):
    list_display = ["received_at", "provider", "event_id", "note"]
    list_filter = ["provider"]
    search_fields = ["event_id"]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "status", "run_after", "attempts", "max_attempts", "locked_by", "finished_at"]
    list_filter = ["status", "name"]
    search_fields = ["name", "dedupe_key"]
    readonly_fields = [f.name for f in Job._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
