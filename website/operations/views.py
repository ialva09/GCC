from __future__ import annotations

import calendar as calendar_module
import mimetypes
from datetime import date
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    ClientInviteAcceptForm,
    ClientMessageForm,
    ContentStudioForm,
    ContactLeadForm,
    ClientForm,
    EstimateCreateForm,
    EstimateForm,
    EstimateLineItemFormSet,
    EmployeeInviteForm,
    EmployeeInviteAcceptForm,
    EmployeeProfileForm,
    LeadForm,
    LeadAssignmentForm,
    LeadNoteForm,
    LeadStatusForm,
    MediaEditForm,
    MediaUploadForm,
    ProjectDocumentForm,
    ProjectForm,
    ProjectUpdateForm,
    PublicAuthenticationForm,
    QuickTaskForm,
    ScheduleEventForm,
    StaffMessageForm,
    TeamTaskUpdateForm,
    TaskForm,
    TimeEntryForm,
)
from .models import (
    Activity,
    Client,
    ClientMessage,
    Estimate,
    EstimateLineItem,
    EmployeeInvite,
    EmployeeProfile,
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
from .services import (
    complete_client_invite,
    complete_employee_invite,
    create_client_invite,
    create_employee_invite,
    find_invite,
    find_employee_invite,
    get_or_create_client_for_lead,
    record_activity,
)


PUBLIC_PAGES = {"home", "services", "projects", "process", "contact"}
DASHBOARD_SECTIONS = {"overview", "clients", "leads", "estimates", "projects", "tasks", "calendar", "time", "media", "documents", "team", "content"}
TEAM_SECTIONS = {"overview", "projects", "tasks", "calendar", "time", "media", "profile"}
EMPLOYEE_GROUPS = {"Manager", "Office", "Field"}
LEADERSHIP_GROUPS = {"Owner", "Manager"}


def pwa_manifest(request):
    return JsonResponse(
        {
            "name": "Grand Coast Construction",
            "short_name": "Grand Coast",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#f5f7fa",
            "theme_color": "#31518c",
            "description": "Grand Coast Construction Inc. project and client workspace.",
            "icons": [
                {
                    "src": static("operations/images/gcc-logo.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
                {
                    "src": static("operations/images/gcc-logo.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
        },
        content_type="application/manifest+json",
    )


def pwa_service_worker(request):
    response = HttpResponse(
        render_to_string("operations/service-worker.js"),
        content_type="application/javascript",
    )
    response["Cache-Control"] = "no-cache"
    return response


def pwa_offline(request):
    return render(request, "operations/offline.html")


def _staff_users():
    return get_user_model().objects.filter(
        is_staff=True,
        is_active=True,
    ).filter(
        Q(is_superuser=True) | Q(groups__name__in=EMPLOYEE_GROUPS)
    ).filter(
        Q(employee_profile__isnull=True) | Q(employee_profile__is_active=True)
    ).order_by("first_name", "last_name", "username").distinct()


def _group_names(user):
    if not user.is_authenticated:
        return set()
    return set(user.groups.values_list("name", flat=True))


def _is_owner(user):
    return bool(user.is_superuser or "Owner" in _group_names(user))


def _is_active_staff(user):
    if not user.is_authenticated or not user.is_staff or not user.is_active:
        return False
    return not EmployeeProfile.objects.filter(user=user, is_active=False).exists()


def _is_active_client(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and not user.is_staff
        and Client.objects.filter(user=user).exists()
    )


def _can_access_dashboard(user):
    return bool(_is_active_staff(user) and user.is_superuser)


def _can_manage_team(user):
    return _can_access_dashboard(user)


def _can_manage_schedule(user):
    return _can_access_dashboard(user)


def _can_manage_content(user):
    return _can_access_dashboard(user)


def _is_field_employee(user):
    return bool(user.is_staff and "Field" in _group_names(user) and not _can_access_dashboard(user))


def _can_access_team(user):
    roles = _group_names(user)
    if not _is_active_staff(user):
        return False
    return bool(user.is_superuser or roles & EMPLOYEE_GROUPS)


def _can_view_clients(user):
    return _can_access_dashboard(user)


def _can_manage_tasks(user):
    return _can_access_dashboard(user)


def _can_manage_documents(user):
    return _can_access_dashboard(user)


def _can_manage_messages(user):
    return _can_access_dashboard(user)


def _visible_projects_for_user(user):
    if _can_access_dashboard(user):
        return Project.objects.all()
    return Project.objects.filter(assigned_staff=user).distinct()


def _visible_tasks_for_user(user):
    if _can_access_dashboard(user):
        return Task.objects.all()
    return Task.objects.filter(
        Q(assigned_to=user)
        | Q(watchers=user)
        | Q(project__assigned_staff=user)
        | Q(lead__assigned_to=user)
    ).distinct()


def _visible_schedule_for_user(user):
    if _can_access_dashboard(user):
        return ScheduleEvent.objects.all()
    return ScheduleEvent.objects.filter(assignees=user).distinct()


def _visible_team_schedule_for_user(user):
    if _can_access_dashboard(user) or _group_names(user) & LEADERSHIP_GROUPS:
        return ScheduleEvent.objects.all()
    return ScheduleEvent.objects.filter(assignees=user).distinct()


def _visible_time_for_user(user):
    if _can_access_dashboard(user):
        return TimeEntry.objects.all()
    return TimeEntry.objects.filter(employee=user)


def _visible_clients_for_user(user):
    if _can_access_dashboard(user):
        return Client.objects.all()
    return Client.objects.filter(projects__assigned_staff=user).distinct()


def _site_settings():
    site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
    return site_settings


def _asset(path):
    if not path:
        return ""
    if path.startswith(("http://", "https://", "/")):
        return path
    return static(path)


def _project_image(project):
    if project and project.cover:
        return reverse("operations:project-cover", kwargs={"pk": project.pk})
    return _asset(project.fallback_image) if project else ""


def _public_context():
    site_settings = _site_settings()
    services = list(Service.objects.filter(is_active=True))
    process_steps = list(ProcessStep.objects.all())
    for service in services:
        service.display_image = _asset(service.image_path)
    projects = list(
        Project.objects.filter(is_published=True)
        .select_related("client")
        .prefetch_related("media_assets")
    )
    for project in projects:
        project.display_image = _project_image(project)
    featured_project = site_settings.featured_project
    public_featured_project = featured_project if featured_project and featured_project.is_published else None
    return {
        "site_settings": site_settings,
        "services": services,
        "process_steps": process_steps,
        "public_projects": projects,
        "featured_project": public_featured_project,
        "featured_project_image": (
            _project_image(public_featured_project)
            if public_featured_project
            else static("operations/images/project-bathroom.png")
        ),
    }


def _logout_admin_from_public_site(request):
    if request.user.is_authenticated and request.user.is_superuser:
        logout(request)


def _public_dashboard_url(user):
    if _can_access_team(user) and not user.is_superuser:
        return reverse("operations:team")
    if _is_active_client(user):
        return reverse("operations:portal")
    return ""


def public_page(request, page="home"):
    _logout_admin_from_public_site(request)
    if page not in PUBLIC_PAGES:
        page = "home"
    context = _public_context()
    context["page"] = page
    context["public_dashboard_url"] = _public_dashboard_url(request.user)
    context["contact_form"] = ContactLeadForm()
    if page == "contact" and request.method == "POST":
        form = ContactLeadForm(request.POST, request.FILES)
        context["contact_form"] = form
        if form.is_valid():
            full_name = f"{form.cleaned_data['first_name'].strip()} {form.cleaned_data['last_name'].strip()}".strip()
            with transaction.atomic():
                lead = Lead.objects.create(
                    name=full_name,
                    email=form.cleaned_data["email"],
                    phone=form.cleaned_data["phone"],
                    service=form.cleaned_data["project_type"],
                    location=form.cleaned_data["location"],
                    note=form.cleaned_data["message"],
                    source="Website form",
                )
                for upload in request.FILES.getlist("photos"):
                    LeadAttachment.objects.create(lead=lead, file=upload, original_name=upload.name)
                record_activity("New lead received", f"{lead.name} · Website form", lead=lead)
            messages.success(request, "Thanks for sharing your project. We will be in touch soon.")
            return redirect("operations:contact")
    return render(request, "operations/public.html", context)


def staff_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not _can_access_dashboard(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def team_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not _can_access_team(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def staff_or_field_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not _can_access_team(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def client_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff:
            if not _can_access_dashboard(request.user):
                raise PermissionDenied
        elif not _is_active_client(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


class GrandCoastLoginView(LoginView):
    template_name = "operations/login.html"
    authentication_form = PublicAuthenticationForm

    def get_success_url(self):
        if self.request.user.is_staff:
            return reverse("operations:dashboard") if _can_access_dashboard(self.request.user) else reverse("operations:team")
        return reverse("operations:portal")


class GrandCoastPasswordChangeView(PasswordChangeView):
    template_name = "operations/password_change.html"

    def get_success_url(self):
        if self.request.user.is_staff:
            return reverse("operations:dashboard") if _can_access_dashboard(self.request.user) else reverse("operations:team")
        return reverse("operations:portal")


def _dashboard_redirect(section, **params):
    url = reverse("operations:dashboard-section", kwargs={"section": section})
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    return redirect(f"{url}?{urlencode(clean_params)}" if clean_params else url)


def _content_form(instance, services, process_steps, data=None):
    initial = {
        "headline": instance.headline,
        "subheadline": instance.subheadline,
        "featured_title": instance.featured_title,
        "featured_body": instance.featured_body,
        "google_review_url": instance.google_review_url,
    }
    for service in services:
        initial[f"service_{service.slug}_title"] = service.title
        initial[f"service_{service.slug}_copy"] = service.description
    for step in process_steps:
        initial[f"step_{step.key}"] = step.title
    return ContentStudioForm(data=data, initial=initial, services=services, process_steps=process_steps)


def _dashboard_context(request, section, form_overrides=None):
    form_overrides = form_overrides or {}
    site_settings = _site_settings()
    services = list(Service.objects.filter(is_active=True))
    process_steps = list(ProcessStep.objects.all())

    leads_query = request.GET.get("q", "").strip()
    leads_status = request.GET.get("status", "all")
    leads_qs = Lead.objects.all().prefetch_related("tasks", "estimates")
    if leads_query:
        from django.db.models import Q

        leads_qs = leads_qs.filter(
            Q(name__icontains=leads_query)
            | Q(service__icontains=leads_query)
            | Q(location__icontains=leads_query)
            | Q(email__icontains=leads_query)
            | Q(phone__icontains=leads_query)
            | Q(client__name__icontains=leads_query)
            | Q(client__email__icontains=leads_query)
            | Q(client__company__icontains=leads_query)
        )
    if leads_status != "all" and leads_status in dict(Lead.Status.choices):
        leads_qs = leads_qs.filter(status=leads_status)
    leads = list(leads_qs)
    selected_lead = None
    if request.GET.get("lead"):
        selected_lead = Lead.objects.prefetch_related("tasks", "estimates").filter(pk=request.GET["lead"]).first()
    if selected_lead is None and leads:
        selected_lead = leads[0]

    estimates = list(
        Estimate.objects.select_related("lead", "client")
        .prefetch_related("line_items", "projects")
        .all()
    )
    selected_estimate = None
    if request.GET.get("estimate"):
        selected_estimate = next((item for item in estimates if str(item.pk) == request.GET["estimate"]), None)
    if selected_estimate is None and estimates:
        selected_estimate = estimates[0]

    projects = list(
        Project.objects.select_related("estimate", "lead", "client")
        .prefetch_related("milestones", "updates", "media_assets", "documents")
        .all()
    )
    selected_project = None
    if request.GET.get("project"):
        selected_project = next((item for item in projects if str(item.pk) == request.GET["project"]), None)
    if selected_project is None and projects:
        selected_project = projects[0]
    for project in projects:
        project.display_image = _project_image(project)

    media_visibility = request.GET.get("visibility", "all")
    media_project = request.GET.get("media_project", "all")
    media_qs = MediaAsset.objects.select_related("project").all()
    if media_visibility in dict(MediaAsset.Visibility.choices):
        media_qs = media_qs.filter(visibility=media_visibility)
    if media_project != "all":
        media_qs = media_qs.filter(project_id=media_project)
    media_assets = list(media_qs)
    for media in media_assets:
        media.display_url = reverse("operations:media-file", kwargs={"pk": media.pk})

    if selected_lead:
        selected_lead.estimate = selected_lead.estimates.order_by("-created_at").first()
    if selected_estimate:
        selected_estimate.display_total = selected_estimate.total
        selected_estimate.project = selected_estimate.projects.order_by("-created_at").first()
    if selected_project:
        selected_project.progress = selected_project.progress_percent

    pipeline = [
        ("New", [Lead.Status.NEW]),
        ("In conversation", [Lead.Status.CONTACTED, Lead.Status.QUALIFIED]),
        ("Quoted", [Lead.Status.QUOTED]),
        ("Won", [Lead.Status.WON]),
    ]
    all_leads = list(Lead.objects.all())
    pipeline_columns = [
        {"title": title, "won": title == "Won", "leads": [lead for lead in all_leads if lead.status in statuses]}
        for title, statuses in pipeline
    ]

    new_type = request.GET.get("new", "")
    initial_lead = selected_lead if new_type == "estimate" else None
    dashboard_forms = {
        "lead_form": LeadForm(staff_queryset=_staff_users()),
        "estimate_create_form": EstimateCreateForm(
            lead_queryset=Lead.objects.exclude(status=Lead.Status.LOST),
            client_queryset=Client.objects.all(),
            initial={"lead": initial_lead.pk if initial_lead else None},
        ),
        "estimate_form": EstimateForm(instance=selected_estimate) if selected_estimate else EstimateForm(),
        "estimate_line_formset": (
            EstimateLineItemFormSet(instance=selected_estimate, prefix="lines")
            if selected_estimate and selected_estimate.status != Estimate.Status.ACCEPTED
            else None
        ),
        "project_form": (
            ProjectForm(instance=selected_project, staff_queryset=_staff_users())
            if selected_project and new_type != "project"
            else ProjectForm(staff_queryset=_staff_users())
        ),
        "project_document_form": ProjectDocumentForm(
            project_queryset=Project.objects.all(),
            initial={"project": selected_project.pk} if selected_project else None,
        ),
        "can_manage_documents": _can_manage_documents(request.user),
        "project_update_form": ProjectUpdateForm(),
        "media_upload_form": MediaUploadForm(project_queryset=Project.objects.all()),
        "content_form": _content_form(site_settings, services, process_steps),
        "lead_note_form": LeadNoteForm(instance=selected_lead, prefix="note") if selected_lead else LeadNoteForm(prefix="note"),
        "lead_assignment_form": LeadAssignmentForm(instance=selected_lead, staff_queryset=_staff_users()) if selected_lead else LeadAssignmentForm(staff_queryset=_staff_users()),
        "follow_up_form": QuickTaskForm(prefix="followup", staff_queryset=_staff_users()),
    }
    dashboard_forms.update(form_overrides)
    content_form = dashboard_forms["content_form"]
    content_service_fields = [
        {
            "service": service,
            "title": content_form[f"service_{service.slug}_title"],
            "copy": content_form[f"service_{service.slug}_copy"],
        }
        for service in services
    ]
    content_step_fields = [
        {"step": step, "field": content_form[f"step_{step.key}"]}
        for step in process_steps
    ]

    active_projects = [project for project in projects if project.status != Project.Status.COMPLETE]
    pending_estimates = [estimate for estimate in estimates if estimate.status in {Estimate.Status.DRAFT, Estimate.Status.SENT}]
    open_leads = [lead for lead in all_leads if lead.status not in {Lead.Status.WON, Lead.Status.LOST}]
    open_tasks_count = Task.objects.filter(
        status__in=[Task.Status.OPEN, Task.Status.IN_PROGRESS, Task.Status.BLOCKED]
    ).count()
    unread_messages_count = ClientMessage.objects.filter(
        is_read=False,
        sent_by__is_staff=False,
    ).count()
    upcoming_events_count = ScheduleEvent.objects.filter(start_at__gte=timezone.now()).count()
    activities = list(Activity.objects.select_related("actor").all()[:8])
    for activity in activities:
        activity.when = activity.created_at.strftime("%b %d · %I:%M %p") if activity.created_at else ""

    return {
        "active_section": section,
        "leads": leads,
        "selected_lead": selected_lead,
        "estimates": estimates,
        "selected_estimate": selected_estimate,
        "projects": projects,
        "selected_project": selected_project,
        "media_assets": media_assets,
        "media_visibility": media_visibility,
        "media_project": media_project,
        "pipeline_columns": pipeline_columns,
        "overview_projects": active_projects[:4],
        "activities": activities,
        "open_leads_count": len(open_leads),
        "pending_estimates_count": len(pending_estimates),
        "active_projects_count": len(active_projects),
        "open_tasks_count": open_tasks_count,
        "unread_messages_count": unread_messages_count,
        "upcoming_events_count": upcoming_events_count,
        "can_manage_team": _can_manage_team(request.user),
        "lead_status_choices": Lead.Status.choices,
        "estimate_status_choices": Estimate.Status.choices,
        "project_status_choices": Project.Status.choices,
        "media_visibility_choices": MediaAsset.Visibility.choices,
        "content_services": services,
        "content_process_steps": process_steps,
        "content_service_fields": content_service_fields,
        "content_step_fields": content_step_fields,
        "site_settings": site_settings,
        "new_type": new_type,
        "last_invite_url": request.session.pop("last_invite_url", ""),
        **dashboard_forms,
    }


@staff_required
def dashboard(request, section="overview"):
    if section not in DASHBOARD_SECTIONS:
        section = "overview"
    if section == "content" and not _can_manage_content(request.user):
        raise PermissionDenied
    if section in {"clients", "tasks", "calendar", "time", "documents", "team"}:
        return render(request, "operations/workspace.html", _workspace_context(request, section))
    return render(request, "operations/dashboard.html", _dashboard_context(request, section))


def _workspace_redirect(request, section, **params):
    route = "operations:team-section" if request.path.startswith("/team/") or _is_field_employee(request.user) else "operations:dashboard-section"
    url_name = "section"
    url = reverse(route, kwargs={url_name: section})
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    return redirect(f"{url}?{urlencode(clean_params)}" if clean_params else url)


def _workspace_context(request, section, team_mode=False, form_overrides=None):
    form_overrides = form_overrides or {}
    projects_qs = _visible_projects_for_user(request.user).select_related("client", "lead", "estimate").prefetch_related("milestones", "assigned_staff")
    projects = list(projects_qs)
    for project in projects:
        project.display_image = _project_image(project)

    tasks_qs = _visible_tasks_for_user(request.user).select_related("lead", "project", "milestone", "assigned_to").prefetch_related("watchers")
    task_query = request.GET.get("q", "").strip()
    task_status = request.GET.get("status", "all")
    task_priority = request.GET.get("priority", "all")
    task_project = request.GET.get("project_filter", "all")
    task_employee = request.GET.get("employee", "all")
    task_due = request.GET.get("due", "all")
    if task_query:
        tasks_qs = tasks_qs.filter(Q(title__icontains=task_query) | Q(description__icontains=task_query) | Q(project__title__icontains=task_query) | Q(lead__name__icontains=task_query))
    if task_status in dict(Task.Status.choices):
        tasks_qs = tasks_qs.filter(status=task_status)
    if task_priority in dict(Task.Priority.choices):
        tasks_qs = tasks_qs.filter(priority=task_priority)
    if task_project != "all":
        try:
            project_is_visible = projects_qs.filter(pk=task_project).exists()
        except (TypeError, ValueError):
            project_is_visible = False
        if project_is_visible:
            tasks_qs = tasks_qs.filter(project_id=task_project)
        else:
            task_project = "all"
    if task_employee != "all" and _can_access_dashboard(request.user):
        try:
            employee_is_visible = _staff_users().filter(pk=task_employee).exists()
        except (TypeError, ValueError):
            employee_is_visible = False
        if employee_is_visible:
            tasks_qs = tasks_qs.filter(assigned_to_id=task_employee)
        else:
            task_employee = "all"
    if task_due == "overdue":
        tasks_qs = tasks_qs.filter(due_date__lt=timezone.localdate()).exclude(status=Task.Status.COMPLETE)
    elif task_due == "today":
        tasks_qs = tasks_qs.filter(due_date=timezone.localdate())
    elif task_due == "upcoming":
        tasks_qs = tasks_qs.filter(due_date__gte=timezone.localdate()).exclude(status=Task.Status.COMPLETE)
    tasks = list(tasks_qs)

    schedule_queryset = _visible_team_schedule_for_user(request.user) if team_mode else _visible_schedule_for_user(request.user)
    events = list(schedule_queryset.select_related("project", "task", "created_by").prefetch_related("assignees"))
    today = timezone.localdate()
    requested_month = request.GET.get("month", "")
    try:
        month_anchor = date.fromisoformat(f"{requested_month}-01") if len(requested_month) == 7 else today.replace(day=1)
    except ValueError:
        month_anchor = today.replace(day=1)
    calendar_weeks = []
    events_by_day = {}
    for event in events:
        event_day = timezone.localtime(event.start_at).date()
        events_by_day.setdefault(event_day, []).append(event)
    for week in calendar_module.Calendar(firstweekday=6).monthdatescalendar(month_anchor.year, month_anchor.month):
        calendar_weeks.append([
            {
                "date": day,
                "events": events_by_day.get(day, []),
                "is_current_month": day.month == month_anchor.month,
                "is_today": day == today,
            }
            for day in week
        ])
    previous_month = month_anchor.month - 1 or 12
    previous_year = month_anchor.year - (1 if month_anchor.month == 1 else 0)
    next_month = month_anchor.month + 1 if month_anchor.month < 12 else 1
    next_year = month_anchor.year + (1 if month_anchor.month == 12 else 0)
    event_id = request.GET.get("event")
    selected_event = next((event for event in events if str(event.pk) == event_id), None) if event_id else None
    selected_task_id = request.GET.get("task")
    selected_task = next((task for task in tasks if str(task.pk) == selected_task_id), None) if selected_task_id else (tasks[0] if tasks else None)

    clients_qs = _visible_clients_for_user(request.user).prefetch_related("leads", "projects")
    client_query = request.GET.get("client_q", "").strip()
    if client_query:
        clients_qs = clients_qs.filter(Q(name__icontains=client_query) | Q(company__icontains=client_query) | Q(email__icontains=client_query) | Q(phone__icontains=client_query))
    clients = list(clients_qs)
    selected_client_id = request.GET.get("client")
    selected_client = next((client for client in clients if str(client.pk) == selected_client_id), None) if selected_client_id else (clients[0] if clients else None)

    documents_qs = ProjectDocument.objects.select_related("project", "uploaded_by").filter(project__in=projects_qs)
    document_project = request.GET.get("project", "")
    if document_project:
        try:
            document_project_is_visible = projects_qs.filter(pk=document_project).exists()
        except (TypeError, ValueError):
            document_project_is_visible = False
        if document_project_is_visible:
            documents_qs = documents_qs.filter(project_id=document_project)
    if team_mode and _is_field_employee(request.user):
        documents_qs = documents_qs.filter(project__assigned_staff=request.user)
    documents = list(documents_qs)
    selected_project_id = request.GET.get("project")
    selected_project = next((project for project in projects if str(project.pk) == selected_project_id), None) if selected_project_id else (projects[0] if projects else None)

    media_visibility = request.GET.get("media_visibility", "all")
    media_qs = MediaAsset.objects.select_related("project", "uploaded_by").filter(project__in=projects_qs)
    if media_visibility in dict(MediaAsset.Visibility.choices):
        media_qs = media_qs.filter(visibility=media_visibility)
    media_assets = list(media_qs)
    for media in media_assets:
        media.display_url = reverse("operations:media-file", kwargs={"pk": media.pk})

    time_entries = list(_visible_time_for_user(request.user).select_related("employee", "project", "task")[:50])
    active_time_entry = TimeEntry.objects.filter(employee=request.user, clock_out__isnull=True).first()
    selected_time_entry_id = request.GET.get("time_entry")
    selected_time_entry = next((entry for entry in time_entries if str(entry.pk) == selected_time_entry_id), None) if selected_time_entry_id else None
    staff_users = list(_staff_users()) if _can_access_dashboard(request.user) else [request.user]
    employee_profiles = list(EmployeeProfile.objects.select_related("user").filter(user__in=staff_users))
    if team_mode:
        task_form = TeamTaskUpdateForm(
            instance=selected_task if request.GET.get("edit") == "task" else None,
        )
    else:
        task_form = TaskForm(
            instance=selected_task if request.GET.get("edit") == "task" else None,
            staff_queryset=_staff_users(),
            project_queryset=projects_qs,
        )
    event_form = ScheduleEventForm(
        instance=selected_event if request.GET.get("edit") == "event" else None,
        staff_queryset=_staff_users(),
        project_queryset=projects_qs,
        # Keep the editor's task choices independent from the currently active
        # task filters. An event can remain editable even when its task is not
        # part of the filtered task list.
        task_queryset=_visible_tasks_for_user(request.user),
    )
    client_form = ClientForm(instance=selected_client if request.GET.get("edit") == "client" else None)
    document_form = ProjectDocumentForm(project_queryset=projects_qs)
    media_upload_form = MediaUploadForm(project_queryset=projects_qs)
    time_form = TimeEntryForm(project_queryset=projects_qs, task_queryset=tasks_qs)
    time_edit_form = (
        TimeEntryForm(instance=selected_time_entry, project_queryset=projects_qs, task_queryset=tasks_qs)
        if selected_time_entry and _can_manage_team(request.user)
        else None
    )
    project_update_form = ProjectUpdateForm()
    profile = getattr(request.user, "employee_profile", None)
    profile_form = (
        EmployeeProfileForm(instance=profile, allow_status=_can_manage_team(request.user))
        if profile
        else EmployeeProfileForm(allow_status=_can_manage_team(request.user))
    )
    invite_form = EmployeeInviteForm(group_queryset=Group.objects.filter(name__in=["Manager", "Office", "Field"]))
    client_form = form_overrides.get("client_form", client_form)
    task_form = form_overrides.get("task_form", task_form)
    event_form = form_overrides.get("event_form", event_form)
    document_form = form_overrides.get("document_form", document_form)
    media_upload_form = form_overrides.get("media_upload_form", media_upload_form)
    time_form = form_overrides.get("time_form", time_form)
    time_edit_form = form_overrides.get("time_edit_form", time_edit_form)
    project_update_form = form_overrides.get("project_update_form", project_update_form)
    profile_form = form_overrides.get("profile_form", profile_form)
    invite_form = form_overrides.get("invite_form", invite_form)
    selected_messages = []
    if selected_client:
        selected_messages = list(ClientMessage.objects.filter(client=selected_client).select_related("project", "sent_by")[:25])
    unread_messages_count = ClientMessage.objects.filter(is_read=False, sent_by__is_staff=False).count()
    if team_mode:
        unread_messages_count = 0
    upcoming_events = [event for event in events if event.start_at >= timezone.now()][:5]
    can_view_full_team_calendar = bool(
        team_mode
        and (_can_access_dashboard(request.user) or _group_names(request.user) & LEADERSHIP_GROUPS)
    )
    can_edit_selected_task = bool(
        selected_task
        and (
            (not team_mode and _can_manage_tasks(request.user))
            or (team_mode and selected_task.assigned_to_id == request.user.id)
        )
    )
    return {
        "active_section": section,
        "team_mode": team_mode,
        "projects": projects,
        "selected_project": selected_project,
        "tasks": tasks,
        "selected_task": selected_task,
        "task_status_choices": Task.Status.choices,
        "task_priority_choices": Task.Priority.choices,
        "task_status": task_status,
        "task_priority": task_priority,
        "task_project": task_project,
        "task_employee": task_employee,
        "task_due": task_due,
        "clients": clients,
        "selected_client": selected_client,
        "documents": documents,
        "media_assets": media_assets,
        "media_visibility": media_visibility,
        "media_visibility_choices": MediaAsset.Visibility.choices,
        "events": events,
        "calendar_weeks": calendar_weeks,
        "calendar_month_label": month_anchor.strftime("%B %Y"),
        "calendar_previous": f"{previous_year:04d}-{previous_month:02d}",
        "calendar_next": f"{next_year:04d}-{next_month:02d}",
        "selected_event": selected_event,
        "time_entries": time_entries,
        "active_time_entry": active_time_entry,
        "selected_time_entry": selected_time_entry,
        "employee_profiles": employee_profiles,
        "staff_users": staff_users,
        "invite_form": invite_form,
        "profile_form": profile_form,
        "profile": profile,
        "task_form": task_form,
        "event_form": event_form,
        "client_form": client_form,
        "document_form": document_form,
        "media_upload_form": media_upload_form,
        "time_form": time_form,
        "time_edit_form": time_edit_form,
        "project_update_form": project_update_form,
        "selected_messages": selected_messages,
        "staff_message_form": form_overrides.get("staff_message_form", StaffMessageForm()),
        "unread_messages_count": unread_messages_count,
        "upcoming_events": upcoming_events,
        "open_tasks_count": Task.objects.filter(status__in=[Task.Status.OPEN, Task.Status.IN_PROGRESS, Task.Status.BLOCKED]).count() if _can_access_dashboard(request.user) else _visible_tasks_for_user(request.user).exclude(status=Task.Status.COMPLETE).count(),
        "can_manage_team": _can_manage_team(request.user),
        "can_access_dashboard": _can_access_dashboard(request.user),
        "can_manage_schedule": _can_manage_schedule(request.user),
        "can_manage_tasks": _can_manage_tasks(request.user),
        "can_manage_documents": _can_manage_documents(request.user),
        "can_manage_messages": _can_manage_messages(request.user),
        "is_field_employee": _is_field_employee(request.user),
        "can_view_full_team_calendar": can_view_full_team_calendar,
        "can_edit_selected_task": can_edit_selected_task,
        "last_employee_invite_url": request.session.pop("last_employee_invite_url", ""),
        "last_reset_url": request.session.pop("last_reset_url", ""),
    }


def _render_dashboard_form_error(request, section, form_overrides=None, *, selections=None, new=None, edit=None):
    query = request.GET.copy()
    for key, value in (selections or {}).items():
        if value not in (None, ""):
            query[key] = str(value)
    if new:
        query["new"] = new
    if edit:
        query["edit"] = edit
    request.GET = query
    return render(request, "operations/dashboard.html", _dashboard_context(request, section, form_overrides=form_overrides))


def _render_workspace_form_error(request, section, form_overrides=None, *, selections=None, new=None, edit=None):
    query = request.GET.copy()
    for key, value in (selections or {}).items():
        if value not in (None, ""):
            query[key] = str(value)
    if new:
        query["new"] = new
    if edit:
        query["edit"] = edit
    request.GET = query
    team_mode = request.path.startswith("/team/")
    return render(request, "operations/workspace.html", _workspace_context(request, section, team_mode=team_mode, form_overrides=form_overrides))


@team_required
def team(request, section="overview"):
    if section not in TEAM_SECTIONS:
        section = "overview"
    return render(request, "operations/workspace.html", _workspace_context(request, section, team_mode=True))


@require_POST
@staff_required
def client_create(request):
    form = ClientForm(request.POST)
    if form.is_valid():
        client = form.save()
        record_activity("Client created", client.name, actor=request.user)
        messages.success(request, f"{client.name} was added to Clients.")
        return _workspace_redirect(request, "clients", client=client.pk)
    messages.error(request, "Please correct the client details and try again.")
    return _render_workspace_form_error(request, "clients", {"client_form": form}, new="client")


@require_POST
@staff_required
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST, instance=client)
    if form.is_valid():
        form.save()
        record_activity("Client details updated", client.name, actor=request.user)
        messages.success(request, "Client details saved.")
    else:
        messages.error(request, "Please correct the client details and try again.")
        return _render_workspace_form_error(request, "clients", {"client_form": form}, selections={"client": client.pk}, edit="client")
    return _workspace_redirect(request, "clients", client=client.pk)


@require_POST
@staff_required
def client_create_invite(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if client.user_id:
        messages.info(request, "This client already has portal access.")
    else:
        invite, raw_token = create_client_invite(client, actor=request.user)
        request.session["last_invite_url"] = request.build_absolute_uri(reverse("operations:client-invite", kwargs={"token": raw_token}))
        record_activity("Client portal invite created", client.name, actor=request.user)
        messages.success(request, "A one-time client invite link is ready to copy.")
    return _workspace_redirect(request, "clients", client=client.pk)


@require_POST
@staff_required
def client_revoke_access(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if client.user_id:
        client.user = None
        client.save(update_fields=["user", "updated_at"])
        client.invites.filter(accepted_at__isnull=True).update(expires_at=timezone.now())
        record_activity("Client portal access revoked", client.name, actor=request.user)
        messages.success(request, "Client portal access was revoked.")
    else:
        messages.info(request, "This client does not have active portal access.")
    return _workspace_redirect(request, "clients", client=client.pk)


@require_POST
@staff_required
def lead_convert_client(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    client = get_or_create_client_for_lead(lead, actor=request.user)
    record_activity("Lead converted to client", f"{lead.name} · {client.email}", actor=request.user, lead=lead)
    messages.success(request, f"{lead.name} is now a client record.")
    return _workspace_redirect(request, "clients", client=client.pk)


@require_POST
@staff_required
def task_create(request):
    if not _can_manage_tasks(request.user):
        raise PermissionDenied
    projects_qs = _visible_projects_for_user(request.user)
    form = TaskForm(request.POST, staff_queryset=_staff_users(), project_queryset=projects_qs)
    if form.is_valid():
        task = form.save(commit=False)
        task.created_by = request.user
        if task.status == Task.Status.COMPLETE:
            task.completed_at = timezone.now()
        task.save()
        form.save_m2m()
        record_activity("Task created", task.title, actor=request.user, lead=task.lead, project=task.project)
        messages.success(request, f"{task.title} was added to Tasks.")
        return _workspace_redirect(request, "tasks", task=task.pk)
    messages.error(request, "Please correct the task details and try again.")
    return _render_workspace_form_error(request, "tasks", {"task_form": form}, new="task")


@require_POST
@team_required
def task_update(request, pk):
    team_mode = request.path.startswith("/team/")
    if team_mode:
        task = get_object_or_404(
            _visible_tasks_for_user(request.user).select_related("project", "lead"),
            pk=pk,
            assigned_to=request.user,
        )
        form = TeamTaskUpdateForm(request.POST, instance=task)
    else:
        if not _can_manage_tasks(request.user):
            raise PermissionDenied
        task = get_object_or_404(Task, pk=pk)
        form = TaskForm(
            request.POST,
            instance=task,
            staff_queryset=_staff_users(),
            project_queryset=_visible_projects_for_user(request.user),
        )
    if form.is_valid():
        task = form.save(commit=False)
        task.completed_at = timezone.now() if task.status == Task.Status.COMPLETE else None
        task.save()
        if not team_mode:
            form.save_m2m()
        record_activity("Task updated", task.title, actor=request.user, lead=task.lead, project=task.project)
        messages.success(request, "Task changes saved.")
        return _workspace_redirect(request, "tasks", task=task.pk)
    messages.error(request, "Please correct the task details and try again.")
    return _render_workspace_form_error(request, "tasks", {"task_form": form}, selections={"task": task.pk}, edit="task")


@require_POST
@team_required
def task_set_status(request, pk):
    task = get_object_or_404(Task.objects.select_related("project", "lead"), pk=pk)
    if request.path.startswith("/team/"):
        if task.assigned_to_id != request.user.id:
            raise PermissionDenied
    elif not _can_manage_tasks(request.user):
        raise PermissionDenied
    status = request.POST.get("status")
    if status not in dict(Task.Status.choices):
        messages.error(request, "That task status is not valid.")
    else:
        task.status = status
        task.completed_at = timezone.now() if status == Task.Status.COMPLETE else None
        task.save(update_fields=["status", "completed_at", "updated_at"])
        record_activity("Task status updated", f"{task.title} · {task.get_status_display()}", actor=request.user, lead=task.lead, project=task.project)
        messages.success(request, "Task status updated.")
    return _workspace_redirect(request, "tasks", task=task.pk)


@require_POST
@team_required
def schedule_create(request):
    if not _can_manage_schedule(request.user):
        raise PermissionDenied
    form = ScheduleEventForm(
        request.POST,
        staff_queryset=_staff_users(),
        project_queryset=_visible_projects_for_user(request.user),
        task_queryset=_visible_tasks_for_user(request.user),
    )
    if form.is_valid():
        event = form.save(commit=False)
        event.created_by = request.user
        event.save()
        form.save_m2m()
        record_activity('Calendar event created', event.title, actor=request.user, project=event.project)
        messages.success(request, f"{event.title} was added to the calendar.")
        return _workspace_redirect(request, "calendar", event=event.pk)
    messages.error(request, "Please correct the calendar event details.")
    return _render_workspace_form_error(request, "calendar", {"event_form": form}, new="event")


@require_POST
@team_required
def schedule_update(request, pk):
    if not _can_manage_schedule(request.user):
        raise PermissionDenied
    event = get_object_or_404(ScheduleEvent, pk=pk)
    form = ScheduleEventForm(
        request.POST,
        instance=event,
        staff_queryset=_staff_users(),
        project_queryset=_visible_projects_for_user(request.user),
        task_queryset=_visible_tasks_for_user(request.user),
    )
    if form.is_valid():
        event = form.save(commit=False)
        event.save()
        form.save_m2m()
        record_activity('Calendar event updated', event.title, actor=request.user, project=event.project)
        messages.success(request, "Calendar event updated.")
        return _workspace_redirect(request, "calendar", event=event.pk)
    messages.error(request, "Please correct the calendar event details.")
    return _render_workspace_form_error(request, "calendar", {"event_form": form}, selections={"event": event.pk}, edit="event")


@require_POST
@team_required
def schedule_delete(request, pk):
    if not _can_manage_schedule(request.user):
        raise PermissionDenied
    event = get_object_or_404(ScheduleEvent, pk=pk)
    event_title = event.title
    record_activity(
        "Calendar event deleted",
        event_title,
        actor=request.user,
        project=event.project,
    )
    event.delete()
    messages.success(request, f"{event_title} was removed from the calendar.")
    return _workspace_redirect(request, "calendar")


@require_POST
@team_required
def time_clock(request):
    employee = request.user
    if _can_access_dashboard(request.user) and request.POST.get("employee"):
        if not _can_manage_team(request.user):
            raise PermissionDenied
        employee = get_object_or_404(get_user_model(), pk=request.POST["employee"], is_staff=True)
    now = timezone.now()
    try:
        with transaction.atomic():
            active = TimeEntry.objects.select_for_update().filter(employee=employee, clock_out__isnull=True).first()
            if active:
                active.clock_out = now
                active.note = request.POST.get("note", active.note)
                active.save(update_fields=["clock_out", "note", "updated_at"])
                activity = ("Clocked out", employee.get_username(), active.project)
            else:
                project = None
                task = None
                if request.POST.get("project"):
                    project = get_object_or_404(_visible_projects_for_user(request.user), pk=request.POST["project"])
                if request.POST.get("task"):
                    task = get_object_or_404(_visible_tasks_for_user(request.user), pk=request.POST["task"])
                    if task.project_id and (not project or task.project_id != project.pk):
                        raise ValidationError("The selected task must belong to the selected project.")
                TimeEntry.objects.create(
                    employee=employee,
                    project=project,
                    task=task,
                    clock_in=now,
                    note=request.POST.get("note", ""),
                )
                activity = ("Clocked in", employee.get_username(), project)
    except (IntegrityError, ValidationError) as exc:
        messages.error(request, str(exc) or "This employee already has an active time entry.")
    else:
        record_activity(activity[0], activity[1], actor=request.user, project=activity[2])
        messages.success(request, f"{employee.get_username()} {"clocked out." if activity[0] == "Clocked out" else "is clocked in."}")
    return _workspace_redirect(request, "time")


@require_POST
@staff_required
def time_update(request, pk):
    if not _can_manage_team(request.user):
        raise PermissionDenied
    entry = get_object_or_404(TimeEntry, pk=pk)
    form = TimeEntryForm(request.POST, instance=entry, project_queryset=_visible_projects_for_user(request.user), task_queryset=_visible_tasks_for_user(request.user))
    if form.is_valid():
        entry = form.save(commit=False)
        entry.adjusted_by = request.user
        entry.adjusted_at = timezone.now()
        entry.save()
        record_activity('Time entry corrected', entry.employee.get_username(), actor=request.user, project=entry.project)
        messages.success(request, "Time entry corrected.")
    else:
        messages.error(request, "Please correct the time entry.")
        return _render_workspace_form_error(request, "time", {"time_edit_form": form}, selections={"time_entry": entry.pk})
    return _workspace_redirect(request, "time")


@require_POST
@team_required
def document_upload(request):
    if not _can_manage_documents(request.user):
        raise PermissionDenied
    form = ProjectDocumentForm(request.POST, request.FILES, project_queryset=_visible_projects_for_user(request.user))
    if form.is_valid():
        document = form.save(commit=False)
        if not _visible_projects_for_user(request.user).filter(pk=document.project_id).exists():
            raise PermissionDenied
        document.uploaded_by = request.user
        document.save()
        record_activity("Project document uploaded", f"{document.project.title} · {document.title}", actor=request.user, project=document.project)
        messages.success(request, "Project document uploaded.")
        return _workspace_redirect(request, "documents", project=document.project_id)
    messages.error(request, "Please choose a valid document and project.")
    return _render_workspace_form_error(request, "documents", {"document_form": form}, selections={"project": request.POST.get("project")})


@require_GET
@login_required
def document_file(request, pk):
    document = get_object_or_404(ProjectDocument.objects.select_related("project", "project__client"), pk=pk)
    project = document.project
    is_staff_allowed = (
        request.user.is_staff
        and (
            _can_access_dashboard(request.user)
            or (
                _can_access_team(request.user)
                and project.assigned_staff.filter(pk=request.user.pk).exists()
            )
        )
    )
    is_client_allowed = bool(
        _is_active_client(request.user)
        and document.visibility == ProjectDocument.Visibility.CLIENT
        and project.client_id
        and project.client.user_id == request.user.id
    )
    if not (is_staff_allowed or is_client_allowed):
        if not request.user.is_authenticated:
            return redirect(f"{reverse("operations:login")}?{urlencode({"next": request.path})}")
        raise PermissionDenied
    try:
        opened = document.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    response = FileResponse(opened, content_type=mimetypes.guess_type(document.file.name)[0] or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{document.file.name.rsplit("/", 1)[-1]}"'
    return response


@require_POST
@staff_required
def staff_message_reply(request, client_pk):
    if not _can_manage_messages(request.user):
        raise PermissionDenied
    client = get_object_or_404(Client, pk=client_pk)
    project = get_object_or_404(Project, pk=request.POST["project"], client=client) if request.POST.get("project") else None
    form = StaffMessageForm(request.POST)
    if form.is_valid():
        client_message = form.save(commit=False)
        client_message.client = client
        client_message.project = project
        client_message.sent_by = request.user
        client_message.is_read = False
        client_message.save()
        record_activity("Staff message sent", client.name, actor=request.user, project=project)
        messages.success(request, "Your reply was added to the conversation.")
    else:
        messages.error(request, "Please write a message before replying.")
        return _render_workspace_form_error(request, "clients", {"staff_message_form": form}, selections={"client": client.pk})
    return _workspace_redirect(request, "clients", client=client.pk)


@require_POST
@staff_required
def staff_mark_message_read(request, pk):
    if not _can_manage_messages(request.user):
        raise PermissionDenied
    client_message = get_object_or_404(ClientMessage, pk=pk)
    client_message.is_read = True
    client_message.save(update_fields=["is_read"])
    return _workspace_redirect(request, "clients", client=client_message.client_id)


@require_POST
@staff_required
def employee_invite_create(request):
    if not _can_manage_team(request.user):
        raise PermissionDenied
    form = EmployeeInviteForm(request.POST, group_queryset=Group.objects.filter(name__in=["Manager", "Office", "Field"]))
    if form.is_valid():
        invite, raw_token = create_employee_invite(
            email=form.cleaned_data["email"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            group=form.cleaned_data["group"],
            actor=request.user,
        )
        request.session["last_employee_invite_url"] = request.build_absolute_uri(reverse("operations:employee-invite", kwargs={"token": raw_token}))
        record_activity('Employee invitation created', form.cleaned_data['email'], actor=request.user)
        messages.success(request, "Employee invitation created. Copy the one-time link below.")
    else:
        messages.error(request, "Please correct the employee invitation details.")
        return _render_workspace_form_error(request, "team", {"invite_form": form})
    return _workspace_redirect(request, "team")


@require_POST
@team_required
def employee_profile_update(request, pk):
    team_mode = request.path.startswith("/team/")
    if not team_mode and not _can_access_dashboard(request.user):
        raise PermissionDenied
    if not _can_manage_team(request.user) and str(getattr(getattr(request.user, "employee_profile", None), "pk", "")) != str(pk):
        raise PermissionDenied
    profile = get_object_or_404(EmployeeProfile.objects.select_related("user"), pk=pk)
    form = EmployeeProfileForm(
        request.POST,
        instance=profile,
        allow_status=_can_manage_team(request.user),
    )
    if form.is_valid():
        form.save()
        record_activity('Employee profile updated', str(profile), actor=request.user)
        messages.success(request, f"{profile} profile updated.")
    else:
        messages.error(request, "Please correct the employee profile.")
        return _render_workspace_form_error(request, "team", {"profile_form": form})
    return _workspace_redirect(request, "team")


@require_POST
@staff_required
def employee_password_reset_create(request, pk):
    if not _can_manage_team(request.user):
        raise PermissionDenied
    profile = get_object_or_404(EmployeeProfile.objects.select_related("user"), pk=pk)
    group = profile.user.groups.filter(name__in=["Manager", "Office", "Field"]).first()
    if group is None:
        group = Group.objects.get_or_create(name="Field")[0]
    invite, raw_token = create_employee_invite(
        email=profile.user.email,
        first_name=profile.user.first_name,
        last_name=profile.user.last_name,
        group=group,
        actor=request.user,
        employee=profile,
        purpose=EmployeeInvite.Purpose.PASSWORD_RESET,
    )
    request.session["last_reset_url"] = request.build_absolute_uri(reverse("operations:employee-invite", kwargs={"token": raw_token}))
    messages.success(request, "A one-time password reset link is ready to copy.")
    return _workspace_redirect(request, "team")


def employee_invite(request, token):
    invite = find_employee_invite(token)
    if invite is None:
        return render(request, "operations/invite_invalid.html", {"invite_kind": "employee"}, status=410)
    form = EmployeeInviteAcceptForm(
        request.POST or None,
        purpose=invite.purpose,
        initial={
            "username": invite.email,
            "first_name": invite.first_name,
            "last_name": invite.last_name,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            user = complete_employee_invite(invite, form)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            login(request, user)
            messages.success(request, "Your Grand Coast employee account is ready.")
            return redirect("operations:team")
    return render(request, "operations/employee_invite.html", {"form": form, "invite": invite})


@require_POST
@staff_required
def lead_create(request):
    form = LeadForm(request.POST, staff_queryset=_staff_users())
    if form.is_valid():
        lead = form.save(commit=False)
        lead.created_by = request.user
        lead.save()
        record_activity("New lead added", f"{lead.name} · Lead pipeline", actor=request.user, lead=lead)
        messages.success(request, f"{lead.name} was added to the lead pipeline.")
        return _dashboard_redirect("leads", lead=lead.pk)
    messages.error(request, "Please correct the lead details and try again.")
    return _render_dashboard_form_error(request, "leads", {"lead_form": form}, new="lead")


@require_POST
@staff_required
def lead_update_status(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadStatusForm(request.POST, instance=lead)
    if form.is_valid():
        lead = form.save()
        record_activity(f"{lead.name} moved to {lead.get_status_display()}", "Lead pipeline", actor=request.user, lead=lead)
        messages.success(request, "Lead status updated.")
    return _dashboard_redirect("leads", lead=lead.pk)


@require_POST
@staff_required
def lead_assign(request, pk):
    if not _can_manage_tasks(request.user):
        raise PermissionDenied
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadAssignmentForm(request.POST, instance=lead, staff_queryset=_staff_users())
    if form.is_valid():
        lead = form.save()
        assignee = lead.assigned_to.get_full_name() if lead.assigned_to else "Unassigned"
        record_activity("Lead assignment updated", f"{lead.name} · {assignee}", actor=request.user, lead=lead)
        messages.success(request, "Lead assignment updated.")
    else:
        messages.error(request, "That employee cannot be assigned to this lead.")
    return _dashboard_redirect("leads", lead=lead.pk)


@require_POST
@staff_required
def lead_toggle_priority(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    lead.priority = not lead.priority
    lead.save(update_fields=["priority", "updated_at"])
    record_activity(
        f"{lead.name} marked as {'priority' if lead.priority else 'standard'}",
        "Lead pipeline",
        actor=request.user,
        lead=lead,
    )
    messages.success(request, "Lead priority updated.")
    return _dashboard_redirect("leads", lead=lead.pk)


@require_POST
@staff_required
def lead_update_note(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadNoteForm(request.POST, instance=lead, prefix="note")
    if form.is_valid():
        lead = form.save()
        record_activity("Lead note updated", f"{lead.name} · Lead record", actor=request.user, lead=lead)
        messages.success(request, "Lead note saved.")
    else:
        messages.error(request, "Please correct the lead note and try again.")
        return _render_dashboard_form_error(
            request,
            "leads",
            {"lead_note_form": form},
            selections={"lead": lead.pk},
        )
    return _dashboard_redirect("leads", lead=lead.pk)


@require_POST
@staff_required
def lead_create_followup(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    form = QuickTaskForm(request.POST, prefix="followup", staff_queryset=_staff_users(), lead=lead)
    if form.is_valid():
        task = form.save(commit=False)
        task.lead = lead
        task.created_by = request.user
        task.save()
        record_activity("Task added", f"{lead.name} · {task.title}", actor=request.user, lead=lead)
        messages.success(request, "Task saved.")
    else:
        messages.error(request, "Please correct the task details and try again.")
        return _render_dashboard_form_error(
            request,
            "leads",
            {"follow_up_form": form},
            selections={"lead": lead.pk},
        )
    return _dashboard_redirect("leads", lead=lead.pk)


def _estimate_from_form(form, request):
    estimate = form.save(commit=False)
    estimate.created_by = request.user
    lead = form.cleaned_data.get("lead")
    if lead:
        estimate.client = lead.client
    else:
        estimate.client = form.cleaned_data.get("client")
    estimate.save()
    EstimateLineItem.objects.create(
        estimate=estimate,
        description="Initial project scope",
        quantity=Decimal("1.00"),
        unit_price=Decimal("0.00"),
        sort_order=0,
    )
    if lead and lead.status not in {Lead.Status.WON, Lead.Status.LOST}:
        lead.status = Lead.Status.QUOTED
        lead.save(update_fields=["status", "updated_at"])
    return estimate


@require_POST
@staff_required
def estimate_create(request):
    form = EstimateCreateForm(
        request.POST,
        lead_queryset=Lead.objects.exclude(status=Lead.Status.LOST),
        client_queryset=Client.objects.all(),
    )
    if form.is_valid():
        with transaction.atomic():
            estimate = _estimate_from_form(form, request)
            record_activity(
                f"Estimate #{estimate.number} created",
                f"{estimate.client or 'Unassigned client'} · just now",
                actor=request.user,
                lead=estimate.lead,
                estimate=estimate,
            )
        messages.success(request, f"Estimate #{estimate.number} created.")
        return _dashboard_redirect("estimates", estimate=estimate.pk)
    messages.error(request, "Please provide an estimate title and lead or client.")
    return _render_dashboard_form_error(
        request,
        "estimates",
        {"estimate_create_form": form},
        new="estimate",
    )


def _estimate_formset_total(formset):
    total = Decimal("0.00")
    for form in formset.forms:
        if not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue
        total += form.cleaned_data.get("quantity", Decimal("0")) * form.cleaned_data.get("unit_price", Decimal("0"))
    return total.quantize(Decimal("0.01"))


def _apply_estimate_status(estimate, previous_status, actor):
    now = timezone.now()
    if estimate.status == Estimate.Status.SENT and not estimate.sent_at:
        estimate.sent_at = now
    if estimate.status == Estimate.Status.ACCEPTED and not estimate.accepted_at:
        estimate.accepted_at = now
        estimate.accepted_by = actor
    if estimate.status == Estimate.Status.DECLINED and not estimate.declined_at:
        estimate.declined_at = now
    estimate.save(update_fields=["status", "sent_at", "accepted_at", "accepted_by", "declined_at", "updated_at"])
    if previous_status != estimate.status:
        record_activity(
            f"Estimate #{estimate.number} moved to {estimate.get_status_display()}",
            estimate.title,
            actor=actor,
            lead=estimate.lead,
            estimate=estimate,
        )


@require_POST
@staff_required
def estimate_update(request, pk):
    estimate = get_object_or_404(Estimate.objects.select_related("lead", "client"), pk=pk)
    if estimate.status == Estimate.Status.ACCEPTED:
        messages.error(request, "Accepted estimates are locked. Create a new revision to make changes.")
        return _dashboard_redirect("estimates", estimate=estimate.pk)
    form = EstimateForm(request.POST, instance=estimate)
    formset = EstimateLineItemFormSet(request.POST, instance=estimate, prefix="lines")
    if form.is_valid() and formset.is_valid():
        total = _estimate_formset_total(formset)
        if form.cleaned_data["deposit_amount"] > total:
            form.add_error("deposit_amount", "Deposit amount cannot exceed the updated estimate total.")
        else:
            with transaction.atomic():
                previous_status = estimate.status
                estimate = form.save(commit=False)
                estimate.save()
                formset.save()
                _apply_estimate_status(estimate, previous_status, request.user)
                record_activity(
                    f"Estimate #{estimate.number} updated",
                    f"{estimate.title} · just now",
                    actor=request.user,
                    lead=estimate.lead,
                    estimate=estimate,
                )
            messages.success(request, "Estimate changes saved.")
            return _dashboard_redirect("estimates", estimate=estimate.pk)
    messages.error(request, "Please correct the estimate fields and line items.")
    return _render_dashboard_form_error(
        request,
        "estimates",
        {"estimate_form": form, "estimate_line_formset": formset},
        selections={"estimate": estimate.pk},
    )


@require_POST
@staff_required
def estimate_send(request, pk):
    estimate = get_object_or_404(Estimate.objects.select_related("lead", "client"), pk=pk)
    if estimate.status == Estimate.Status.ACCEPTED:
        messages.info(request, "This estimate has already been accepted.")
        return _dashboard_redirect("estimates", estimate=estimate.pk)

    # The dashboard uses the same form for Save and Mark ready. Persist the
    # submitted scope before changing visibility in the client portal.
    has_editor_payload = "title" in request.POST or "lines-TOTAL_FORMS" in request.POST
    form = EstimateForm(request.POST, instance=estimate) if has_editor_payload else None
    formset = (
        EstimateLineItemFormSet(request.POST, instance=estimate, prefix="lines")
        if has_editor_payload
        else None
    )
    if has_editor_payload and (not form.is_valid() or not formset.is_valid()):
        messages.error(request, "Please correct the estimate fields and line items before sending.")
        return _render_dashboard_form_error(
            request,
            "estimates",
            {"estimate_form": form, "estimate_line_formset": formset},
            selections={"estimate": estimate.pk},
        )

    if form is not None:
        total = _estimate_formset_total(formset)
        if form.cleaned_data["deposit_amount"] > total:
            form.add_error("deposit_amount", "Deposit amount cannot exceed the estimate total.")
            messages.error(request, "Please correct the estimate fields and line items before sending.")
            return _render_dashboard_form_error(
                request,
                "estimates",
                {"estimate_form": form, "estimate_line_formset": formset},
                selections={"estimate": estimate.pk},
            )

    with transaction.atomic():
        estimate = Estimate.objects.select_for_update().get(pk=estimate.pk)
        previous_status = estimate.status
        if form is not None:
            # The form was validated before the row lock. Copy its cleaned
            # values onto the locked instance explicitly so the submitted
            # title, notes, and deposit are not lost when marking it ready.
            for field_name in EstimateForm.Meta.fields:
                setattr(estimate, field_name, form.cleaned_data[field_name])
            estimate.status = Estimate.Status.SENT
            estimate.save()
            formset.instance = estimate
            formset.save()
        else:
            estimate.status = Estimate.Status.SENT
            estimate.save(update_fields=["status", "updated_at"])
        _apply_estimate_status(estimate, previous_status, request.user)
    messages.success(request, f"Estimate #{estimate.number} is ready in the client portal.")
    return _dashboard_redirect("estimates", estimate=estimate.pk)


@require_POST
@staff_required
def project_create(request):
    form = ProjectForm(request.POST, staff_queryset=_staff_users())
    if form.is_valid():
        project = form.save(commit=False)
        if project.lead_id and not project.estimate_id:
            project.estimate = project.lead.estimates.filter(status=Estimate.Status.ACCEPTED).order_by("-accepted_at").first()
        if project.lead_id and not project.client_id:
            project.client = project.lead.client
        if project.estimate_id and not project.client_id:
            project.client = project.estimate.client
        project.created_by = request.user
        project.save()
        # ModelForm.save(commit=False) postpones the many-to-many write. The
        # assigned team is part of project creation, so persist it now.
        form.save_m2m()
        _create_default_milestones(project)
        record_activity("Project created", f"{project.title} · just now", actor=request.user, project=project)
        messages.success(request, f"{project.title} was created.")
        return _dashboard_redirect("projects", project=project.pk)
    messages.error(request, "Please correct the project details and try again.")
    return _render_dashboard_form_error(request, "projects", {"project_form": form}, new="project")


def _create_default_milestones(project, approved=False):
    completed_through = 2 if approved else 1
    for index, title in enumerate(["Walkthrough", "Estimate approved", "Selections", "Construction", "Final walkthrough"], start=1):
        Milestone.objects.create(
            project=project,
            title=title,
            sort_order=index,
            is_complete=index <= completed_through,
        )


@require_POST
@staff_required
def estimate_create_project(request, pk):
    estimate = get_object_or_404(Estimate.objects.select_related("lead", "client"), pk=pk)
    if estimate.status != Estimate.Status.ACCEPTED:
        messages.error(request, "Only accepted estimates can become projects.")
        return _dashboard_redirect("estimates", estimate=estimate.pk)
    existing = estimate.projects.order_by("-created_at").first()
    if existing:
        return _dashboard_redirect("projects", project=existing.pk)
    client = estimate.client or (get_or_create_client_for_lead(estimate.lead, actor=request.user) if estimate.lead else None)
    project = Project.objects.create(
        estimate=estimate,
        lead=estimate.lead,
        client=client,
        title=estimate.title,
        location=estimate.lead.location if estimate.lead else "",
        project_type="renovation",
        status=Project.Status.PLANNING,
        next_step="Schedule project kickoff",
        summary=estimate.notes,
        created_by=request.user,
        fallback_image="operations/images/progress-kitchen.png",
    )
    _create_default_milestones(project, approved=True)
    if estimate.lead and estimate.lead.status != Lead.Status.WON:
        estimate.lead.status = Lead.Status.WON
        estimate.lead.save(update_fields=["status", "updated_at"])
    record_activity("Project created from accepted estimate", project.title, actor=request.user, estimate=estimate, project=project)
    messages.success(request, f"{project.title} is now in Projects.")
    return _dashboard_redirect("projects", project=project.pk)


@require_POST
@staff_required
def project_update(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form_data = request.POST.copy()
    for field_name in ("location", "project_type", "start_date", "target_date"):
        if field_name not in form_data:
            value = getattr(project, field_name)
            form_data[field_name] = str(value or "")
    if "is_published" not in form_data:
        # An unchecked checkbox is intentionally absent from POST data. The
        # owner must be able to take a published project off the public site.
        form_data["is_published"] = ""
    if "assigned_staff" not in form_data:
        # An empty multi-select is intentionally absent from POST data too;
        # treat it as clearing assignments rather than preserving stale ones.
        form_data.setlist("assigned_staff", [])
    if "lead" not in form_data and project.lead_id:
        form_data["lead"] = str(project.lead_id)
    form = ProjectForm(form_data, instance=project, staff_queryset=_staff_users())
    if form.is_valid():
        project = form.save()
        record_activity("Project details updated", f"{project.title} · just now", actor=request.user, project=project)
        messages.success(request, "Project details saved.")
    else:
        messages.error(request, "Please correct the project fields and try again.")
        return _render_dashboard_form_error(
            request,
            "projects",
            {"project_form": form},
            selections={"project": project.pk},
        )
    return _dashboard_redirect("projects", project=project.pk)


@require_POST
@staff_required
def milestone_toggle(request, pk):
    milestone = get_object_or_404(Milestone.objects.select_related("project"), pk=pk)
    milestone.is_complete = request.POST.get("is_complete") == "on"
    milestone.completed_at = timezone.now() if milestone.is_complete else None
    milestone.save(update_fields=["is_complete", "completed_at"])
    record_activity(
        f"{milestone.project.title}: {milestone.title}",
        "Milestone complete" if milestone.is_complete else "Milestone reopened",
        actor=request.user,
        project=milestone.project,
    )
    messages.success(request, "Milestone updated.")
    return _dashboard_redirect("projects", project=milestone.project.pk)


@require_POST
@staff_or_field_required
def project_add_update(request, pk):
    team_mode = request.path.startswith("/team/")
    if not team_mode and not _can_access_dashboard(request.user):
        raise PermissionDenied
    project = get_object_or_404(_visible_projects_for_user(request.user), pk=pk)
    if team_mode and not project.assigned_staff.filter(pk=request.user.pk).exists():
        raise PermissionDenied
    form = ProjectUpdateForm(request.POST)
    if form.is_valid():
        update = form.save(commit=False)
        if team_mode:
            update.visibility = ProjectUpdate.Visibility.INTERNAL
        update.project = project
        update.created_by = request.user
        update.save()
        if not team_mode:
            project.next_step = update.title
            project.save(update_fields=["next_step", "updated_at"])
        record_activity(
            "Project update added",
            f"{project.title} · {update.get_visibility_display()}",
            actor=request.user,
            project=project,
        )
        messages.success(request, "Project update published to the selected audience.")
    else:
        messages.error(request, "Please add a title and update message.")
        return _render_workspace_form_error(
            request,
            "projects",
            {"project_update_form": form},
            selections={"project": project.pk},
        )
    return _workspace_redirect(request, "projects", project=project.pk)


@require_POST
@staff_required
def project_create_invite(request, pk):
    project = get_object_or_404(Project.objects.select_related("client"), pk=pk)
    if not project.client:
        messages.error(request, "This project needs a client contact before an invite can be created.")
        return _dashboard_redirect("projects", project=project.pk)
    invite, raw_token = create_client_invite(project.client, actor=request.user)
    invite_url = request.build_absolute_uri(reverse("operations:client-invite", kwargs={"token": raw_token}))
    request.session["last_invite_url"] = invite_url
    record_activity("Client portal invite created", project.client.name, actor=request.user, project=project)
    messages.success(request, "A one-time client invite link is ready to copy.")
    return _dashboard_redirect("projects", project=project.pk)


@require_POST
@staff_or_field_required
def media_upload(request):
    team_mode = request.path.startswith("/team/")
    if not team_mode and not _can_access_dashboard(request.user):
        raise PermissionDenied
    project_queryset = _visible_projects_for_user(request.user)
    form = MediaUploadForm(request.POST, request.FILES, project_queryset=project_queryset)
    if form.is_valid():
        project = form.cleaned_data["project"]
        visibility = MediaAsset.Visibility.INTERNAL if team_mode else form.cleaned_data["visibility"]
        created = []
        for upload in form.cleaned_data["files"]:
            content_type = (getattr(upload, "content_type", "") or "").lower()
            media_type = MediaAsset.MediaType.VIDEO if content_type.startswith("video/") else MediaAsset.MediaType.PHOTO
            asset = MediaAsset.objects.create(
                project=project,
                title=upload.name.rsplit(".", 1)[0],
                file=upload,
                media_type=media_type,
                visibility=visibility,
                uploaded_by=request.user,
            )
            created.append(asset)
        record_activity("Project media uploaded", f"{len(created)} file(s) · {project.title}", actor=request.user, project=project)
        messages.success(request, f"{len(created)} media file(s) added to {project.title}.")
        return _workspace_redirect(request, "media", media_project=project.pk)
    messages.error(request, "Please choose a project and valid media files.")
    return _render_workspace_form_error(
        request,
        "media",
        {"media_upload_form": form},
        selections={"media_project": request.POST.get("project")},
    )


@require_POST
@staff_or_field_required
def media_edit(request, pk):
    team_mode = request.path.startswith("/team/")
    if not team_mode and not _can_access_dashboard(request.user):
        raise PermissionDenied
    asset = get_object_or_404(MediaAsset, pk=pk)
    project_queryset = _visible_projects_for_user(request.user)
    if team_mode and (
        not asset.project_id
        or not project_queryset.filter(pk=asset.project_id).exists()
    ):
        raise PermissionDenied
    form = MediaEditForm(request.POST, instance=asset, project_queryset=project_queryset)
    if form.is_valid():
        if team_mode:
            asset.caption = form.cleaned_data["caption"]
            asset.save(update_fields=["caption", "updated_at"])
        else:
            asset = form.save()
        record_activity("Media details updated", f"{asset.title} · {asset.get_visibility_display()}", actor=request.user, project=asset.project)
        messages.success(request, "Media details saved.")
    else:
        messages.error(request, "Please correct the media details and try again.")
        return _render_workspace_form_error(
            request,
            "media",
            {"media_edit_form": form},
            selections={"media_project": asset.project_id},
        )
    return _workspace_redirect(request, "media", media_project=asset.project_id)


@require_POST
@staff_required
def content_update(request):
    if not _can_manage_content(request.user):
        raise PermissionDenied
    instance = _site_settings()
    services = list(Service.objects.filter(is_active=True))
    process_steps = list(ProcessStep.objects.all())
    form = _content_form(instance, services, process_steps, data=request.POST)
    if form.is_valid():
        instance.headline = form.cleaned_data["headline"]
        instance.subheadline = form.cleaned_data["subheadline"]
        instance.featured_title = form.cleaned_data["featured_title"]
        instance.featured_body = form.cleaned_data["featured_body"]
        instance.google_review_url = form.cleaned_data["google_review_url"]
        instance.save()
        for service in services:
            service.title = form.cleaned_data[f"service_{service.slug}_title"]
            service.description = form.cleaned_data[f"service_{service.slug}_copy"]
            service.save(update_fields=["title", "description"])
        for step in process_steps:
            step.title = form.cleaned_data[f"step_{step.key}"]
            step.save(update_fields=["title"])
        record_activity("Public content updated", "Content studio", actor=request.user)
        messages.success(request, "Public website content updated.")
    else:
        messages.error(request, "Please correct the content fields and try again.")
        return _render_dashboard_form_error(request, "content", {"content_form": form})
    return _dashboard_redirect("content")


@require_GET
def public_project_detail(request, pk):
    _logout_admin_from_public_site(request)
    project = get_object_or_404(
        Project.objects.select_related("client").prefetch_related("milestones", "updates", "media_assets"),
        pk=pk,
        is_published=True,
    )
    public_media = list(project.media_assets.filter(visibility=MediaAsset.Visibility.PUBLIC))
    for media_item in public_media:
        media_item.display_url = reverse("operations:media-file", kwargs={"pk": media_item.pk})
    project.display_image = _project_image(project)
    return render(request, "operations/project_detail.html", {
        "project": project,
        "public_media": public_media,
        "site_settings": _site_settings(),
        "public_dashboard_url": _public_dashboard_url(request.user),
    })


@require_GET
def project_cover_file(request, pk):
    project = get_object_or_404(Project.objects.select_related("client"), pk=pk)
    allowed = bool(project.is_published)
    if request.user.is_authenticated and request.user.is_staff:
        allowed = bool(
            _can_access_dashboard(request.user)
            or (
                _can_access_team(request.user)
                and project.assigned_staff.filter(pk=request.user.pk).exists()
            )
        )
    elif (
        _is_active_client(request.user)
        and project.client_id
        and project.client
        and project.client.user_id == request.user.id
    ):
        allowed = True
    if not allowed:
        if not request.user.is_authenticated:
            return redirect(f"{reverse('operations:login')}?{urlencode({'next': request.path})}")
        raise PermissionDenied
    if not project.cover:
        raise Http404
    try:
        opened = project.cover.open("rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    response = FileResponse(
        opened,
        content_type=mimetypes.guess_type(project.cover.name)[0] or "application/octet-stream",
    )
    response["Content-Disposition"] = f'inline; filename="{project.cover.name.rsplit("/", 1)[-1]}"'
    return response


def _portal_client(request):
    if request.user.is_staff:
        requested = request.GET.get("client")
        if requested:
            client = Client.objects.filter(pk=requested).first()
            if client:
                return client
        return (
            Client.objects.filter(
                estimates__status__in=[Estimate.Status.SENT, Estimate.Status.ACCEPTED]
            )
            .order_by("name")
            .first()
            or Client.objects.order_by("name").first()
        )
    return getattr(request.user, "client_record", None)


@client_required
def portal(request):
    client = _portal_client(request)
    if client is None:
        return render(request, "operations/portal.html", {"portal_client": None, "portal_projects": [], "portal_estimates": [], "portal_messages": []})
    projects = list(
        Project.objects.filter(client=client)
        .select_related("estimate")
        .prefetch_related("milestones", "updates", "media_assets", "documents", "messages")
    )
    portal_estimates = list(
        Estimate.objects.filter(client=client)
        .exclude(status=Estimate.Status.DRAFT)
        .select_related("lead")
        .prefetch_related("line_items", "projects")
    )
    for estimate in portal_estimates:
        estimate.portal_project = estimate.projects.order_by("-created_at").first()
    requested_estimate = next(
        (estimate for estimate in portal_estimates if str(estimate.pk) == request.GET.get("estimate")),
        None,
    ) if request.GET.get("estimate") else None
    selected_project = None
    if request.GET.get("project"):
        selected_project = next((project for project in projects if str(project.pk) == request.GET["project"]), None)
    elif requested_estimate and requested_estimate.portal_project:
        selected_project = next(
            (project for project in projects if project.pk == requested_estimate.portal_project.pk),
            None,
        )
    if selected_project is None and not requested_estimate and projects:
        selected_project = projects[0]
    updates = list(selected_project.updates.filter(visibility=ProjectUpdate.Visibility.CLIENT)[:8]) if selected_project else []
    media = list(
        selected_project.media_assets.filter(
            visibility__in=[MediaAsset.Visibility.PUBLIC, MediaAsset.Visibility.CLIENT]
        )[:8]
    ) if selected_project else []
    if selected_project:
        selected_project.progress = selected_project.progress_percent
        selected_project.display_image = _project_image(selected_project)
        for media_item in media:
            media_item.display_url = reverse("operations:media-file", kwargs={"pk": media_item.pk})
    portal_estimate = requested_estimate
    if portal_estimate is None and selected_project and selected_project.estimate:
        portal_estimate = next(
            (estimate for estimate in portal_estimates if estimate.pk == selected_project.estimate_id),
            None,
        )
    if portal_estimate is None and not selected_project and portal_estimates:
        portal_estimate = portal_estimates[0]
    portal_documents = list(selected_project.documents.filter(visibility=ProjectDocument.Visibility.CLIENT)[:12]) if selected_project else []
    # Conversations are client-wide, with an optional project relationship.
    # This keeps general questions and pre-project estimate discussions visible
    # to the same client without duplicating messages in the portal.
    portal_messages = list(client.messages.select_related("project", "sent_by")[:30])
    if not request.user.is_staff:
        ClientMessage.objects.filter(client=client, sent_by__is_staff=True, is_read=False).update(is_read=True)
    return render(request, "operations/portal.html", {
        "portal_client": client,
        "portal_projects": projects,
        "portal_estimates": portal_estimates,
        "portal_project": selected_project,
        "portal_estimate": portal_estimate,
        "portal_updates": updates,
        "portal_latest_update": updates[0] if updates else None,
        "portal_media": media,
        "portal_documents": portal_documents,
        "portal_messages": portal_messages,
        "google_review_url": _site_settings().google_review_url,
        "portal_message_form": ClientMessageForm(),
    })


def _client_can_access_estimate(request, estimate):
    client = _portal_client(request)
    return bool(client and estimate.client_id == client.id)


@require_POST
@login_required
def portal_accept_estimate(request, pk):
    if not _is_active_client(request.user):
        raise PermissionDenied
    estimate = get_object_or_404(Estimate.objects.select_related("client", "lead"), pk=pk)
    if not _client_can_access_estimate(request, estimate):
        raise PermissionDenied
    if estimate.status == Estimate.Status.SENT:
        with transaction.atomic():
            estimate = Estimate.objects.select_for_update().get(pk=estimate.pk)
            if estimate.status == Estimate.Status.SENT:
                estimate.status = Estimate.Status.ACCEPTED
                estimate.accepted_at = timezone.now()
                estimate.accepted_by = request.user
                estimate.save(update_fields=["status", "accepted_at", "accepted_by", "updated_at"])
                record_activity("Estimate accepted by client", f"Estimate #{estimate.number}", actor=request.user, estimate=estimate)
        messages.success(request, "Estimate accepted. Your project team will follow up with next steps.")
    else:
        messages.info(request, "This estimate is not currently awaiting acceptance.")
    portal_url = reverse("operations:portal")
    return redirect(f"{portal_url}?estimate={estimate.pk}")


@require_POST
@login_required
def portal_send_message(request):
    if not _is_active_client(request.user):
        raise PermissionDenied
    client = _portal_client(request)
    if client is None or client.user_id != request.user.id:
        raise PermissionDenied
    project = None
    if request.POST.get("project"):
        project = get_object_or_404(Project, pk=request.POST["project"], client=client)
    form = ClientMessageForm(request.POST)
    if form.is_valid():
        client_message = form.save(commit=False)
        client_message.client = client
        client_message.project = project
        client_message.sent_by = request.user
        client_message.save()
        record_activity("New client message", client.name, actor=request.user, project=project)
        messages.success(request, "Your message was added to the project conversation.")
    else:
        messages.error(request, "Please add a message before sending.")
    portal_url = reverse("operations:portal")
    query = {}
    if project:
        query["project"] = project.pk
    if request.POST.get("estimate"):
        query["estimate"] = request.POST["estimate"]
    return redirect(f"{portal_url}?{urlencode(query)}" if query else portal_url)


def client_invite(request, token):
    invite = find_invite(token)
    if invite is None:
        return render(request, "operations/invite_invalid.html", status=410)
    form = ClientInviteAcceptForm(request.POST or None, initial={
        "username": invite.client.email,
        "first_name": invite.client.name.split(" ")[0],
        "last_name": " ".join(invite.client.name.split(" ")[1:]),
    })
    if request.method == "POST" and form.is_valid():
        try:
            user = complete_client_invite(invite, form)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            login(request, user)
            messages.success(request, "Your client portal account is ready.")
            return redirect("operations:portal")
    return render(request, "operations/invite_accept.html", {"form": form, "invite": invite})


@require_GET
def media_file(request, pk):
    asset = get_object_or_404(MediaAsset.objects.select_related("project__client"), pk=pk)
    allowed = asset.visibility == MediaAsset.Visibility.PUBLIC
    if request.user.is_authenticated and request.user.is_staff:
        allowed = bool(
            _can_access_dashboard(request.user)
            or (
                _can_access_team(request.user)
                and asset.project_id
                and asset.project
                and asset.project.assigned_staff.filter(pk=request.user.pk).exists()
            )
        )
    if (
        _is_active_client(request.user)
        and asset.visibility == MediaAsset.Visibility.CLIENT
        and asset.project
        and asset.project.client
        and asset.project.client.user_id == request.user.id
    ):
        allowed = True
    if not allowed:
        if not request.user.is_authenticated:
            return redirect(f"{reverse('operations:login')}?{urlencode({'next': request.path})}")
        raise PermissionDenied
    if asset.file:
        try:
            opened = asset.file.open("rb")
        except FileNotFoundError as exc:
            raise Http404 from exc
        content_type = mimetypes.guess_type(asset.file.name)[0] or "application/octet-stream"
        response = FileResponse(opened, content_type=content_type)
        response["Content-Disposition"] = f'inline; filename="{asset.file.name.rsplit("/", 1)[-1]}"'
        return response
    if asset.fallback_image:
        return redirect(_asset(asset.fallback_image))
    raise Http404


def legacy_dashboard(request, section="overview"):
    if section not in DASHBOARD_SECTIONS:
        section = "overview"
    return redirect("operations:dashboard-section", section=section)


def legacy_portal(request):
    return redirect("operations:portal")
