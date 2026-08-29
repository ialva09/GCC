from types import MethodType

from django.contrib import admin

from unfold.admin import ModelAdmin


admin.site.site_header = "Grand Coast Administration"
admin.site.site_title = "Grand Coast Administration"
admin.site.index_title = "Administration"


def _operations_admin_permission(self, request):
    if not request.user.is_active or not request.user.is_staff:
        return False
    if request.user.is_superuser:
        return True
    roles = set(request.user.groups.values_list("name", flat=True))
    return not roles.intersection({"Field"})


admin.site.has_permission = MethodType(_operations_admin_permission, admin.site)

from .models import (
    Activity,
    Client,
    ClientInvite,
    ClientMessage,
    EmployeeInvite,
    EmployeeProfile,
    Estimate,
    EstimateLineItem,
    Lead,
    LeadAttachment,
    MediaAsset,
    Milestone,
    ProcessStep,
    Project,
    ProjectDocument,
    ProjectUpdate,
    ScheduleEvent,
    Service,
    SiteSettings,
    Task,
    TimeEntry,
)


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name", "email", "user", "updated_at")
    search_fields = ("name", "email", "company")


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(ModelAdmin):
    list_display = ("user", "job_title", "phone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "job_title")


@admin.register(EmployeeInvite)
class EmployeeInviteAdmin(ModelAdmin):
    list_display = ("email", "group", "purpose", "expires_at", "accepted_at")
    list_filter = ("purpose", "accepted_at", "group")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("token_hash", "accepted_at")


@admin.register(ClientInvite)
class ClientInviteAdmin(ModelAdmin):
    list_display = ("client", "expires_at", "accepted_at", "created_at")
    list_filter = ("accepted_at",)
    search_fields = ("client__name", "client__email")
    readonly_fields = ("token_hash",)


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = ("name", "service", "location", "status", "assigned_to", "priority", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("name", "email", "service", "location", "assigned_to__username", "assigned_to__first_name", "assigned_to__last_name")


@admin.register(Estimate)
class EstimateAdmin(ModelAdmin):
    list_display = ("number", "title", "client", "status", "deposit_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "client__name", "lead__name")
    readonly_fields = ("sent_at", "accepted_at", "declined_at", "accepted_by")


@admin.register(EstimateLineItem)
class EstimateLineItemAdmin(ModelAdmin):
    list_display = ("estimate", "description", "quantity", "unit_price", "line_total")
    search_fields = ("description", "estimate__title")


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ("title", "client", "status", "is_published", "updated_at")
    list_filter = ("status", "is_published")
    search_fields = ("title", "location", "client__name", "assigned_staff__username")


@admin.register(Milestone)
class MilestoneAdmin(ModelAdmin):
    list_display = ("project", "title", "sort_order", "is_complete")
    list_filter = ("is_complete",)


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = ("title", "assigned_to", "project", "lead", "status", "priority", "due_date")
    list_filter = ("status", "priority")
    search_fields = ("title", "description", "project__title", "lead__name", "assigned_to__username")


@admin.register(ProjectUpdate)
class ProjectUpdateAdmin(ModelAdmin):
    list_display = ("project", "title", "visibility", "created_at")
    list_filter = ("visibility",)
    search_fields = ("project__title", "title", "body")


@admin.register(MediaAsset)
class MediaAssetAdmin(ModelAdmin):
    list_display = ("title", "project", "media_type", "visibility", "created_at")
    list_filter = ("media_type", "visibility")
    search_fields = ("title", "caption", "project__title")


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(ModelAdmin):
    list_display = ("title", "project", "category", "visibility", "uploaded_by", "created_at")
    list_filter = ("visibility", "category")
    search_fields = ("title", "description", "project__title")


@admin.register(Activity)
class ActivityAdmin(ModelAdmin):
    list_display = ("message", "detail", "actor", "created_at")
    search_fields = ("message", "detail")
    readonly_fields = ("created_at",)


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ("title", "slug", "sort_order", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ProcessStep)
class ProcessStepAdmin(ModelAdmin):
    list_display = ("title", "key", "sort_order")


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    list_display = ("__str__", "updated_at")


admin.site.register(LeadAttachment, ModelAdmin)
admin.site.register(ClientMessage, ModelAdmin)
admin.site.register(ScheduleEvent, ModelAdmin)
admin.site.register(TimeEntry, ModelAdmin)
