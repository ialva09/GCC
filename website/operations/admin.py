from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.contrib import admin
from django.contrib.admin.helpers import ActionForm
from django.urls import reverse
from django.utils.html import format_html

from unfold.admin import ModelAdmin

from .admin_site import GrandCoastAdminSite
from .forms import user_choice_label
from .models import (
    Activity,
    AdminAccessBlock,
    AdminSecurityEvent,
    CalendarDayOverride,
    Client,
    ClientInvite,
    ClientMessage,
    EmployeeInvite,
    EmployeeProfile,
    EmployeeNotification,
    EmployeeScheduleOverride,
    EmployeeWeeklySchedule,
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
    MobilePushDevice,
    PushDelivery,
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

    @staticmethod
    def _label_user_field(db_field, formfield):
        if (
            formfield is not None
            and db_field.remote_field
            and db_field.remote_field.model == get_user_model()
        ):
            formfield.label_from_instance = user_choice_label
        return formfield

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        return self._label_user_field(db_field, formfield)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        return self._label_user_field(db_field, formfield)


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
    inlines = []


class LeadAttachmentInline(admin.TabularInline):
    model = LeadAttachment
    extra = 0
    can_delete = False
    fields = ("original_name", "protected_file", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="File")
    def protected_file(self, obj):
        if not obj or not obj.pk or not obj.file:
            return "No file"
        filename = obj.original_name or obj.file.name.rsplit("/", 1)[-1]
        return format_html(
            '<a href="{}">Download {}</a>',
            reverse("operations:lead-attachment-file", kwargs={"pk": obj.pk}),
            filename,
        )


LeadAdmin.inlines = [LeadAttachmentInline]


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


@admin.register(AdminSecurityEvent, site=grand_coast_admin_site)
class AdminSecurityEventAdmin(GrandCoastModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "outcome",
        "ip_address",
        "user",
        "email_status",
        "reviewed_at",
    )
    list_filter = ("event_type", "outcome", "email_status", "reviewed_at")
    search_fields = (
        "ip_address",
        "attempted_identifier",
        "user__username",
        "user__email",
        "user_agent",
        "path",
        "detail",
    )
    readonly_fields = (
        "id",
        "event_type",
        "outcome",
        "attempted_identifier",
        "user",
        "ip_address",
        "user_agent",
        "path",
        "detail",
        "reviewed_at",
        "reviewed_by",
        "email_status",
        "email_attempt_count",
        "email_last_attempt_at",
        "email_sent_at",
        "email_error",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdminAccessBlock, site=grand_coast_admin_site)
class AdminAccessBlockAdmin(GrandCoastModelAdmin):
    list_display = (
        "created_at",
        "scope",
        "ip_address",
        "user",
        "is_active",
        "created_by",
        "revoked_at",
    )
    list_filter = ("scope", "is_active")
    search_fields = ("ip_address", "user__username", "user__email", "reason")
    readonly_fields = (
        "id",
        "scope",
        "ip_address",
        "user",
        "reason",
        "is_active",
        "created_by",
        "created_at",
        "revoked_by",
        "revoked_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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


@admin.register(LeadAttachment, site=grand_coast_admin_site)
class LeadAttachmentAdmin(GrandCoastModelAdmin):
    list_display = ("lead", "original_name", "lead_message", "protected_file", "created_at")
    list_select_related = ("lead",)
    search_fields = ("original_name", "lead__name", "lead__email", "lead__note")
    fields = ("lead", "original_name", "lead_message", "protected_file", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    @admin.display(description="Contact message")
    def lead_message(self, obj):
        return obj.lead.note or "No message provided."

    @admin.display(description="File")
    def protected_file(self, obj):
        if not obj or not obj.pk or not obj.file:
            return "No file"
        filename = obj.original_name or obj.file.name.rsplit("/", 1)[-1]
        return format_html(
            '<a href="{}">Download {}</a>',
            reverse("operations:lead-attachment-file", kwargs={"pk": obj.pk}),
            filename,
        )
grand_coast_admin_site.register(ClientMessage, GrandCoastModelAdmin)
grand_coast_admin_site.register(ScheduleEvent, GrandCoastModelAdmin)
grand_coast_admin_site.register(TimeEntry, GrandCoastModelAdmin)
grand_coast_admin_site.register(CalendarDayOverride, GrandCoastModelAdmin)
grand_coast_admin_site.register(EmployeeWeeklySchedule, GrandCoastModelAdmin)
grand_coast_admin_site.register(EmployeeScheduleOverride, GrandCoastModelAdmin)
grand_coast_admin_site.register(MobilePushDevice, GrandCoastModelAdmin)
grand_coast_admin_site.register(EmployeeNotification, GrandCoastModelAdmin)
grand_coast_admin_site.register(PushDelivery, GrandCoastModelAdmin)

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
