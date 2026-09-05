from __future__ import annotations

from datetime import date
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import views as existing_views
from .construction_policies import (
    can_manage_construction,
    can_view_financials,
    feature_enabled,
    is_field,
    is_staff_user,
    visible_projects,
)
from .construction_services import (
    attention_feed,
    company_metrics,
    complete_readiness_item,
    create_change_order,
    project_financial_summary,
    request_material,
    submit_problem_report,
    submit_daily_report,
)
from .construction_forms import ChangeOrderForm, DailyReportForm, MaterialRequestForm, ProblemReportForm
from .models import (
    Blocker,
    ChangeOrder,
    DailyReport,
    Inspection,
    MaterialRequest,
    PaymentSchedule,
    PreconstructionItem,
    Project,
    Selection,
)


def _staff_context(request, *, active_section="command-center"):
    nav_counts = existing_views._operations_navigation_counts(request.user)
    return {
        "active_section": active_section,
        "operations_nav_role": "admin",
        "operations_nav_counts": nav_counts,
        "can_manage_team": existing_views._can_manage_team(request.user),
        "unread_messages_count": nav_counts["messages"],
    }


def _require_operating_system():
    if not feature_enabled("operating_system"):
        raise Http404


def _action_url(item):
    if item.get("project"):
        return reverse("operations:project-operations", kwargs={"pk": item["project"].pk})
    if item.get("lead"):
        return reverse("operations:dashboard-section", kwargs={"section": "leads"}) + f"?lead={item['lead'].pk}"
    return reverse("operations:dashboard", kwargs={})


def render_command_center(request):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    feed = attention_feed(request.user)
    for item in feed:
        item["action_url"] = _action_url(item)
        due = item.get("due_at")
        item["due_label"] = (
            due.strftime("%b %d").replace(" 0", " ")
            if hasattr(due, "strftime")
            else "No date"
        )
    projects = list(
        visible_projects(request.user)
        .exclude(status=Project.Status.COMPLETE)
        .select_related("client", "project_manager")
        .prefetch_related("milestones", "blockers")[:12]
    )
    metrics = company_metrics(request.user)
    for project in projects:
        project.open_blocker_count = project.blockers.filter(status=Blocker.Status.OPEN).count()
        project.health_display = project.get_health_status_display()
        if project.open_blocker_count and project.health_status == Project.HealthStatus.ON_TRACK:
            project.health_display = "Watch"
    context = _staff_context(request)
    context.update({
        "attention_items": feed,
        "command_projects": projects,
        "company_metrics": metrics,
        "show_financials": any(can_view_financials(request.user, project) for project in projects),
    })
    return render(request, "operations/construction_command_center.html", context)


@never_cache
@require_GET
@login_required
def command_center(request):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    return redirect("operations:dashboard")


@never_cache
@require_GET
@login_required
def project_operations(request, pk):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    project = get_object_or_404(
        visible_projects(request.user)
        .select_related("client", "project_manager", "estimate")
        .prefetch_related("milestones", "assigned_staff"),
        pk=pk,
    )
    financial_access = can_view_financials(request.user, project)
    readiness_queryset = project.readiness_items.select_related("owner", "completed_by")
    blockers_queryset = project.blockers.filter(status=Blocker.Status.OPEN).select_related("assigned_to")
    if is_field(request.user):
        readiness_queryset = readiness_queryset.filter(category="schedule")
        blockers_queryset = blockers_queryset.filter(
            Q(assigned_to=request.user)
            | Q(category__in=[
                Blocker.Category.INSPECTION,
                Blocker.Category.MATERIAL,
                Blocker.Category.SUBCONTRACTOR,
                Blocker.Category.SCHEDULE,
            ])
        )
    readiness = list(readiness_queryset)
    blockers = list(blockers_queryset)
    selections = list(project.selections.all())
    inspections = list(project.inspections.select_related("permit"))
    change_orders = list(project.change_orders.all())
    if is_field(request.user):
        change_orders = [
            item for item in change_orders
            if item.status != ChangeOrder.Status.DRAFT
        ]
    payment_schedules = (
        list(project.payment_schedules.prefetch_related("payments"))
        if financial_access
        else []
    )
    data = _staff_context(request, active_section="projects")
    data.update({
        "operations_project": project,
        "readiness_items": readiness,
        "blockers": blockers,
        "selections": selections,
        "inspections": inspections,
        "change_orders": change_orders,
        "payment_schedules": payment_schedules,
        "change_order_form": ChangeOrderForm(),
        "project_financials": project_financial_summary(project) if financial_access else None,
        "can_view_project_financials": financial_access,
        "show_inspection_details": not is_field(request.user),
        "can_edit_operations": can_manage_construction(request.user, project),
        "today": timezone.localdate(),
    })
    return render(request, "operations/construction_project_operations.html", data)


@require_POST
@login_required
def readiness_complete(request, pk):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    item = get_object_or_404(PreconstructionItem.objects.select_related("project"), pk=pk)
    if not visible_projects(request.user).filter(pk=item.project_id).exists():
        raise Http404
    try:
        complete_readiness_item(
            item,
            actor=request.user,
            notes=request.POST.get("notes"),
            idempotency_key=request.POST.get("idempotency_key") or None,
        )
    except (PermissionDenied, ValidationError):
        raise
    return redirect("operations:project-operations", pk=item.project_id)


@require_POST
@login_required
def project_change_order_create(request, pk):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    if not can_manage_construction(request.user, project):
        raise PermissionDenied
    form = ChangeOrderForm(request.POST)
    if not form.is_valid():
        raise ValidationError("Please provide a valid change order.")
    values = form.cleaned_data
    status = (
        ChangeOrder.Status.SENT
        if request.POST.get("send")
        else ChangeOrder.Status.DRAFT
    )
    idempotency_key = request.POST.get("idempotency_key") or str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"gcc:change-order:{request.user.pk}:{project.pk}:{values['title']}:{values['price_impact']}:{status}",
        )
    )
    change_order, created = create_change_order(
        project,
        actor=request.user,
        status=status,
        idempotency_key=idempotency_key,
        **values,
    )
    if created and status == ChangeOrder.Status.SENT and project.client_id:
        from .notifications import queue_client_notifications

        queue_client_notifications(
            [project.client],
            kind="change-order-ready",
            title=f"Change order CO-{change_order.number} is ready",
            body=f"{change_order.title} is waiting for your approval.",
            destination_url=existing_views._portal_notification_url(
                project.client,
                project=project,
            ),
            metadata={"change_order_id": str(change_order.pk)},
            created_by=request.user,
            project=project,
            exclude_clients=[project.client],
        )
    return redirect("operations:project-operations", pk=project.pk)


@never_cache
@require_GET
@login_required
def field_today(request):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    today = timezone.localdate()
    projects = list(
        visible_projects(request.user)
        .exclude(status=Project.Status.COMPLETE)
        .select_related("client", "project_manager")
        .prefetch_related("milestones", "assigned_staff")
    )
    visible_tasks = existing_views._visible_tasks_for_user(request.user)
    visible_events = existing_views._visible_team_schedule_for_user(request.user)
    for project in projects:
        project.today_tasks = list(
            visible_tasks.filter(project=project).exclude(status="complete").order_by("due_date", "-priority")[:12]
        )
        project.today_events = list(
            visible_events.filter(project=project, start_at__date=today).order_by("start_at")[:8]
        )
        project.material_count = project.material_requests.filter(status=MaterialRequest.Status.REQUESTED).count()
        project.recent_report = project.daily_reports.order_by("-report_date", "-created_at").first()
    nav_counts = existing_views._operations_navigation_counts(request.user, team_mode=True)
    context = {
        "active_section": "projects",
        "team_mode": True,
        "operations_nav_role": "employee",
        "operations_nav_counts": nav_counts,
        "can_manage_team": False,
        "unread_messages_count": 0,
        "field_projects": projects,
        "field_today": today,
        "daily_report_form": DailyReportForm(),
        "material_request_form": MaterialRequestForm(),
        "problem_report_form": ProblemReportForm(),
    }
    return render(request, "operations/construction_field_today.html", context)


@require_POST
@login_required
def field_daily_report(request, pk):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    form_data = request.POST.copy()
    form_data.setdefault("report_date", timezone.localdate().isoformat())
    form = DailyReportForm(form_data)
    if not form.is_valid():
        raise ValidationError("Please provide a valid daily report.")
    values = form.cleaned_data
    idempotency_key = request.POST.get("idempotency_key") or str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"gcc:daily-report:{request.user.pk}:{project.pk}:{values['report_date'].isoformat()}",
        )
    )
    submit_daily_report(
        project,
        actor=request.user,
        idempotency_key=idempotency_key,
        **values,
    )
    return redirect("operations:field-today")


@require_POST
@login_required
def field_material_request(request, pk):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    form = MaterialRequestForm(request.POST)
    if not form.is_valid():
        raise ValidationError("Please provide a valid material request.")
    values = form.cleaned_data
    idempotency_key = request.POST.get("idempotency_key") or str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "gcc:material-request:"
            f"{request.user.pk}:{project.pk}:{values['description']}:{values['quantity']}:"
            f"{values['needed_by'] or ''}",
        )
    )
    request_material(
        project,
        actor=request.user,
        idempotency_key=idempotency_key,
        **values,
    )
    return redirect("operations:field-today")


@require_POST
@login_required
def field_problem_report(request, pk):
    _require_operating_system()
    if not is_staff_user(request.user):
        raise PermissionDenied
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    form = ProblemReportForm(request.POST)
    if not form.is_valid():
        raise ValidationError("Please provide a valid problem report.")
    values = form.cleaned_data
    idempotency_key = request.POST.get("idempotency_key") or str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"gcc:problem-report:{request.user.pk}:{project.pk}:{values['title']}:{values['description']}",
        )
    )
    submit_problem_report(
        project,
        actor=request.user,
        idempotency_key=idempotency_key,
        **values,
    )
    return redirect("operations:field-today")
