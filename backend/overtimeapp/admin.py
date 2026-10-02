from django.contrib import admin
from .models import UserProfile, OvertimeRequest, EmployeeAssignment, SAPExport, EmailLog, AuditEvent, ExportBatch


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'department', 'created_at']
    list_filter = ['role', 'department']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class WorkflowReadOnlyAdmin(admin.ModelAdmin):
    """Workflow changes must pass through the audited application actions."""
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OvertimeRequest)
class OvertimeRequestAdmin(WorkflowReadOnlyAdmin):
    list_display = ['request_id', 'requester', 'department', 'status', 'total_hours', 'created_at']
    list_filter = ['status', 'department']
    search_fields = ['request_id', 'title']


@admin.register(EmailLog)
class EmailLogAdmin(WorkflowReadOnlyAdmin):
    list_display = ['recipient', 'email_type', 'status', 'attempts', 'next_attempt_at']
    list_filter = ['status', 'email_type']


for model in [EmployeeAssignment, SAPExport, AuditEvent, ExportBatch]:
    admin.site.register(model, WorkflowReadOnlyAdmin)
