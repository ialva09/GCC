"""Additional versioned operating-system endpoints.

This module keeps the API surface grouped by construction control while
reusing the central API parser, authentication decorator, serializers, and
transactional commands.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .ai_services import ask_grand_coast
from .api import (
    _api_access,
    _body,
    _closeout_data,
    _date,
    _decimal,
    _error,
    _idempotency_key,
    _permit_data,
    _problem_data,
    _required_idempotency_key,
)
from .construction_policies import (
    can_view_closeout,
    can_view_financials,
    can_view_permit,
    can_view_project,
    is_client,
    is_field,
    is_subcontractor,
    is_staff_user,
    visible_projects,
)
from .construction_services import (
    complete_closeout_item,
    record_cost,
    create_permit,
    record_deposit,
    record_permit_status,
    resolve_problem_report,
    submit_problem_report,
    void_cost_entry,
)
from .models import (
    CloseoutItem,
    CostEntry,
    BudgetLine,
    Permit,
    ProblemReport,
    Project,
)


def _cost_data(entry):
    return {
        "id": str(entry.pk),
        "project_id": str(entry.project_id),
        "budget_line_id": str(entry.budget_line_id) if entry.budget_line_id else None,
        "description": entry.description,
        "vendor": entry.vendor,
        "amount": str(entry.amount),
        "incurred_on": entry.incurred_on.isoformat(),
        "source": entry.source,
        "is_void": entry.is_void,
    }


@never_cache
@require_POST
@_api_access
def api_v1_project_deposit(request, pk):
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        project = get_object_or_404(visible_projects(request.user), pk=pk)
        payment, created = record_deposit(
            project,
            actor=request.user,
            amount=_decimal(
                payload.get("amount"),
                required=False,
                minimum=None,
            ),
            received_on=_date(payload.get("received_on")),
            method=str(payload.get("method", "other")),
            reference=str(payload.get("reference") or "")[:120],
            notes=str(payload.get("notes") or ""),
            idempotency_key=key,
        )
        return JsonResponse({
            "created": created,
            "payment": {
                "id": str(payment.pk),
                "amount": str(payment.amount),
                "schedule_id": str(payment.schedule_id) if payment.schedule_id else None,
            },
        }, status=201 if created else 200)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_http_methods(["GET", "POST"])
@_api_access
def api_v1_project_costs(request, pk):
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    if request.method == "GET":
        if not can_view_financials(request.user, project):
            return _error("Financial access denied.", 403)
        return JsonResponse({
            "results": [
                _cost_data(entry)
                for entry in project.cost_entries.all()
            ]
        })
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        budget_line = None
        if payload.get("budget_line_id"):
            budget_line = get_object_or_404(
                BudgetLine,
                pk=payload["budget_line_id"],
                project=project,
            )
        entry, created = record_cost(
            project,
            actor=request.user,
            amount=_decimal(payload.get("amount"), minimum=Decimal("0.01")),
            description=payload.get("description"),
            vendor=payload.get("vendor"),
            incurred_on=_date(payload.get("incurred_on")),
            source=payload.get("source"),
            budget_line=budget_line,
            idempotency_key=key,
        )
        return JsonResponse({
            "created": created,
            "cost": _cost_data(entry),
        }, status=201 if created else 200)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_POST
@_api_access
def api_v1_cost_void(request, pk):
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        entry = get_object_or_404(
            CostEntry.objects.select_related("project"),
            pk=pk,
        )
        if not can_view_project(request.user, entry.project):
            return _error("Record not found.", 404)
        entry, created = void_cost_entry(
            entry,
            actor=request.user,
            idempotency_key=key,
        )
        return JsonResponse({
            "created": created,
            "cost": _cost_data(entry),
        })
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_http_methods(["GET", "POST"])
@_api_access
def api_v1_project_permits(request, pk):
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    if request.method == "GET":
        return JsonResponse({
            "results": [
                _permit_data(item, request.user)
                for item in project.permits.all()
                if can_view_permit(request.user, item)
            ]
        })
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        permit, created = create_permit(
            project,
            actor=request.user,
            permit_type=payload.get("permit_type"),
            jurisdiction=payload.get("jurisdiction"),
            permit_number=payload.get("permit_number"),
            status=str(payload.get("status", Permit.Status.PENDING)),
            expires_at=_date(payload.get("expires_at")),
            notes=payload.get("notes"),
            idempotency_key=key,
        )
        return JsonResponse({
            "created": created,
            "permit": _permit_data(permit, request.user),
        }, status=201 if created else 200)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_POST
@_api_access
def api_v1_permit_status(request, pk):
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        permit = get_object_or_404(Permit.objects.select_related("project"), pk=pk)
        if not can_view_project(request.user, permit.project):
            return _error("Record not found.", 404)
        permit = record_permit_status(
            permit,
            actor=request.user,
            status=str(payload.get("status", "")),
            permit_number=payload.get("permit_number"),
            expires_at=_date(payload.get("expires_at")),
            notes=payload.get("notes"),
            idempotency_key=key,
        )
        return JsonResponse({
            "permit": _permit_data(permit, request.user),
        })
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_http_methods(["GET", "POST"])
@_api_access
def api_v1_project_problems(request, pk):
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    if is_client(request.user):
        return _error("Problem reports are not available in this surface.", 403)
    if request.method == "GET":
        reports = project.problem_reports.select_related("reported_by", "assigned_to")
        if is_subcontractor(request.user):
            reports = reports.filter(reported_by=request.user)
        elif is_field(request.user):
            reports = reports.filter(
                reported_by=request.user,
            )
        return JsonResponse({
            "results": [_problem_data(item, request.user) for item in reports[:300]]
        })
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        task = None
        if payload.get("task_id"):
            task = get_object_or_404(project.tasks.all(), pk=payload["task_id"])
        report, created = submit_problem_report(
            project,
            actor=request.user,
            task=task,
            title=payload.get("title"),
            description=payload.get("description"),
            severity=str(payload.get("severity", ProblemReport.Severity.NORMAL)),
            idempotency_key=key,
        )
        return JsonResponse({
            "created": created,
            "problem_report": _problem_data(report, request.user),
        }, status=201 if created else 200)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_POST
@_api_access
def api_v1_problem_resolve(request, pk):
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        report = get_object_or_404(ProblemReport.objects.select_related("project"), pk=pk)
        if not can_view_project(request.user, report.project):
            return _error("Record not found.", 404)
        report = resolve_problem_report(
            report,
            actor=request.user,
            resolution=payload.get("resolution"),
            status=str(payload.get("status", ProblemReport.Status.RESOLVED)),
            idempotency_key=key,
        )
        return JsonResponse({
            "problem_report": _problem_data(report, request.user),
        })
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_GET
@_api_access
def api_v1_project_closeout(request, pk):
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    if is_subcontractor(request.user):
        return _error("Closeout access denied.", 403)
    return JsonResponse({
        "results": [
            _closeout_data(item, request.user)
            for item in project.closeout_items.all()
            if can_view_closeout(request.user, item)
        ]
    })


@never_cache
@require_POST
@_api_access
def api_v1_closeout_complete(request, pk):
    try:
        payload = _body(request)
        key = _required_idempotency_key(request, payload)
        item = get_object_or_404(CloseoutItem.objects.select_related("project"), pk=pk)
        if not can_view_project(request.user, item.project):
            return _error("Record not found.", 404)
        item = complete_closeout_item(
            item,
            actor=request.user,
            status=str(payload.get("status", CloseoutItem.Status.COMPLETE)),
            notes=payload.get("notes"),
            idempotency_key=key,
        )
        return JsonResponse({
            "item": _closeout_data(item, request.user),
        })
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)


@never_cache
@require_GET
@_api_access
def api_v1_project_assignments(request, pk):
    if is_client(request.user):
        return _error("Assignment access denied.", 403)
    project = get_object_or_404(visible_projects(request.user), pk=pk)
    assignments = project.subcontractor_assignments.select_related("task", "subcontractor")
    if is_subcontractor(request.user):
        assignments = assignments.filter(subcontractor__portal_user=request.user)
    return JsonResponse({
        "results": [
            {
                "id": str(item.pk),
                "project_id": str(item.project_id),
                "work_package": item.work_package,
                "scope": item.scope,
                "start_date": item.start_date.isoformat() if item.start_date else None,
                "end_date": item.end_date.isoformat() if item.end_date else None,
                "status": item.status,
                "task_id": str(item.task_id) if item.task_id else None,
            }
            for item in assignments[:300]
        ]
    })


@never_cache
@require_GET
@_api_access
def api_v1_weekly_review(request):
    if not is_staff_user(request.user):
        return _error("Weekly reviews are available to staff only.", 403)
    try:
        review = weekly_project_review(request.user, week_of=_date(request.GET.get("week_of")))
    except (PermissionDenied, ValidationError) as exc:
        return _error(exc, 403 if isinstance(exc, PermissionDenied) else 400)
    return JsonResponse(review)


@never_cache
@require_POST
@_api_access
def api_v1_ask_grand_coast(request):
    try:
        payload = _body(request)
        result = ask_grand_coast(request.user, payload.get("question"))
        return JsonResponse(result)
    except PermissionDenied as exc:
        return _error(exc, 403)
    except ValidationError as exc:
        return _error(exc, 400)
