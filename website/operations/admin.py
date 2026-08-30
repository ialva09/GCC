from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.contrib import admin
from django.contrib.admin.helpers import ActionForm

from unfold.admin import ModelAdmin

from .admin_site import GrandCoastAdminSite
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


grand_coast_admin_site = GrandCoastAdminSite(name="admin")


class GrandCoastActionForm(ActionForm):
    """Keep Unfold's action controls synchronized with its Alpine state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["action"].widget.attrs["x-model"] = "action"
        self.fields["select_across"].widget.attrs["x-model"] = "selectAcross"


class GrandCoastModelAdmin(ModelAdmin):
    action_form = GrandCoastActionForm


@admin.register(Client, site=grand_coast_admin_site)
class ClientAdmin(GrandCoastModelAdmin):
    list_display = ("name", "email", "user", "updated_at")
    search_fields = ("name", "email", "company")


@admin.register(EmployeeProfile, site=grand_coast_admin_site)
class EmployeeProfileAdmin(GrandCoastModelAdmin):
    list_display = ("user", "job_title", "phone", "is_active")
    list_filter = ("is_active",)
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "job_title",
    )


@admin.register(EmployeeInvite, site=grand_coast_admin_site)
class EmployeeInviteAdmin(GrandCoastModelAdmin):
    list_display = ("email", "group", "purpose", "expires_at", "accepted_at")
    list_filter = ("purpose", "accepted_at", "group")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("token_hash", "accepted_at")


@admin.register(ClientInvite, site=grand_coast_admin_site)
class ClientInviteAdmin(GrandCoastModelAdmin):
    list_display = ("client", "expires_at", "accepted_at", "created_at")
    list_filter = ("accepted_at",)
    search_fields = ("client__name", "client__email")
    readonly_fields = ("token_hash",)


@admin.register(Lead, site=grand_coast_admin_site)
class LeadAdmin(GrandCoastModelAdmin):
    list_display = (
        "name",
        "service",
        "location",
        "status",
        "assigned_to",
        "priority",
        "created_at",
    )
    list_filter = ("status", "priority")
    search_fields = (
        "name",
        "email",
        "service",
        "location",
        "assigned_to__username",
        "assigned_to__first_name",
        "assigned_to__last_name",
    )


@admin.register(Estimate, site=grand_coast_admin_site)
class EstimateAdmin(GrandCoastModelAdmin):
    list_display = (
        "number",
        "title",
        "client",
        "status",
        "deposit_amount",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("title", "client__name", "lead__name")
    readonly_fields = ("sent_at", "accepted_at", "declined_at", "accepted_by")


@admin.register(EstimateLineItem, site=grand_coast_admin_site)
class EstimateLineItemAdmin(GrandCoastModelAdmin):
    list_display = ("estimate", "description", "quantity", "unit_price", "line_total")
    search_fields = ("description", "estimate__title")


@admin.register(Project, site=grand_coast_admin_site)
class ProjectAdmin(GrandCoastModelAdmin):
    list_display = ("title", "client", "status", "is_published", "updated_at")
    list_filter = ("status", "is_published")
    search_fields = ("title", "location", "client__name", "assigned_staff__username")


@admin.register(Milestone, site=grand_coast_admin_site)
class MilestoneAdmin(GrandCoastModelAdmin):
    list_display = ("project", "title", "sort_order", "is_complete")
    list_filter = ("is_complete",)


@admin.register(Task, site=grand_coast_admin_site)
class TaskAdmin(GrandCoastModelAdmin):
    list_display = (
        "title",
        "assigned_to",
        "project",
        "lead",
        "status",
        "priority",
        "due_date",
    )
    list_filter = ("status", "priority")
    search_fields = (
        "title",
        "description",
        "project__title",
        "lead__name",
        "assigned_to__username",
    )


@admin.register(ProjectUpdate, site=grand_coast_admin_site)
class ProjectUpdateAdmin(GrandCoastModelAdmin):
    list_display = ("project", "title", "visibility", "created_at")
    list_filter = ("visibility",)
    search_fields = ("project__title", "title", "body")


@admin.register(MediaAsset, site=grand_coast_admin_site)
class MediaAssetAdmin(GrandCoastModelAdmin):
    list_display = ("title", "project", "media_type", "visibility", "created_at")
    list_filter = ("media_type", "visibility")
    search_fields = ("title", "caption", "project__title")


@admin.register(ProjectDocument, site=grand_coast_admin_site)
class ProjectDocumentAdmin(GrandCoastModelAdmin):
    list_display = (
        "title",
        "project",
        "category",
        "visibility",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("visibility", "category")
    search_fields = ("title", "description", "project__title")


@admin.register(Activity, site=grand_coast_admin_site)
class ActivityAdmin(GrandCoastModelAdmin):
    list_display = ("message", "detail", "actor", "created_at")
    search_fields = ("message", "detail")
    readonly_fields = ("created_at",)


@admin.register(Service, site=grand_coast_admin_site)
class ServiceAdmin(GrandCoastModelAdmin):
    list_display = ("title", "slug", "sort_order", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ProcessStep, site=grand_coast_admin_site)
class ProcessStepAdmin(GrandCoastModelAdmin):
    list_display = ("title", "key", "sort_order")


@admin.register(SiteSettings, site=grand_coast_admin_site)
class SiteSettingsAdmin(GrandCoastModelAdmin):
    list_display = ("__str__", "updated_at")


grand_coast_admin_site.register(LeadAttachment, GrandCoastModelAdmin)
grand_coast_admin_site.register(ClientMessage, GrandCoastModelAdmin)
grand_coast_admin_site.register(ScheduleEvent, GrandCoastModelAdmin)
grand_coast_admin_site.register(TimeEntry, GrandCoastModelAdmin)

# Keep the lower-level Django user/group records available in the same private
# Unfold site. Security settings for administrators are deliberately managed
# through the branded /gccad/security/ page rather than exposing hashes or
# authenticator secrets in a model form.
class GrandCoastUserAdmin(UserAdmin):
    action_form = GrandCoastActionForm


class GrandCoastGroupAdmin(GroupAdmin):
    action_form = GrandCoastActionForm


grand_coast_admin_site.register(get_user_model(), GrandCoastUserAdmin)
grand_coast_admin_site.register(Group, GrandCoastGroupAdmin)
