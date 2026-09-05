"""Transactional commands for the Grand Coast operating system.

Views, APIs, notifications, and future mobile/AI clients call these commands
instead of changing construction records directly. Every command is safe to
retry where an idempotency key is supplied and records an append-only event.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .construction_policies import (
    can_manage_construction,
    can_manage_sales,
    can_submit_field_work,
    can_view_financials,
    can_view_estimate,
    can_view_lead,
    can_view_project,
    is_staff_user,
    is_client,
    is_manager,
    is_owner,
    visible_leads,
    visible_projects,
)
from .models import (
    Agreement,
    Blocker,
    BudgetLine,
    ChangeOrder,
    CloseoutItem,
    Commitment,
    Client,
    CostEntry,
    DailyReport,
    EmailOutbox,
    Estimate,
    EstimateLineItem,
    Inspection,
    Lead,
    MaterialRequest,
    PaymentRecord,
    PaymentSchedule,
    Permit,
    ProblemReport,
    PreconstructionItem,
    Project,
    Selection,
    SiteVisit,
    Task,
    WarrantyItem,
    WorkflowEvent,
)
from .services import get_or_create_client_for_lead, record_activity


READINESS_TEMPLATE = (
    ("design", "design", "Architectural / design work"),
    ("engineering", "engineering", "Engineering complete"),
    ("permits", "permit", "Permits approved"),
    ("selections", "selection", "Client selections complete"),
    ("subcontractor-bids", "bid", "Subcontractor bids confirmed"),
    ("procurement", "procurement", "Material procurement plan"),
    ("long-lead-items", "long_lead", "Long-lead items ordered"),
    ("schedule", "schedule", "Construction schedule approved"),
    ("approvals", "approval", "Required approvals complete"),
)

CLOSEOUT_TEMPLATE = (
    ("final-inspection", "final_inspection", "Final inspection passed"),
    ("punch-list", "punch_list", "Punch list complete"),
    ("closeout-documents", "documents", "Closeout documents delivered"),
    ("client-walkthrough", "client_walkthrough", "Client final walkthrough"),
    ("final-invoice", "final_invoice", "Final invoice reconciled"),
    ("warranty", "warranty", "Warranty information delivered"),
)


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "pk"):
        return str(value.pk)
    return value


def state_snapshot(instance, fields):
    return {field: _json_value(getattr(instance, field, None)) for field in fields}


def _workflow_event_key(event_type, related, idempotency_key):
    """Bind a client retry key to the command and object it was meant for."""
    related_model = related.__class__.__name__ if related is not None else ""
    related_id = str(related.pk) if related is not None and getattr(related, "pk", None) else ""
    raw = f"{event_type}|{related_model}|{related_id}|{idempotency_key}"
    return f"evt:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _related_project(related=None, project=None):
    if project is not None:
        return project
    if isinstance(related, Project):
        return related
    project_id = getattr(related, "project_id", None)
    return Project.objects.filter(pk=project_id).first() if project_id else None


def record_workflow_event(
    event_type,
    *,
    actor=None,
    related=None,
    project=None,
    lead=None,
    estimate=None,
    source="web",
    before_state=None,
    after_state=None,
    metadata=None,
    idempotency_key=None,
):
    """Record a non-secret before/after event, returning an existing retry."""
    project = _related_project(related, project)
    if lead is None and isinstance(related, Lead):
        lead = related
    if estimate is None and isinstance(related, Estimate):
        estimate = related
    related_model = related.__class__.__name__ if related is not None else ""
    related_id = str(related.pk) if related is not None and getattr(related, "pk", None) else ""
    event_key = (
        _workflow_event_key(event_type, related, idempotency_key)
        if idempotency_key
        else str(uuid.uuid4())
    )
    if idempotency_key:
        existing = WorkflowEvent.objects.filter(idempotency_key=event_key).first()
        if existing:
            return existing
    defaults = {
        "event_type": event_type,
        "source": source,
        "actor": actor,
        "lead": lead,
        "estimate": estimate,
        "project": project,
        "related_model": related_model,
        "related_id": related_id,
        "before_state": before_state or {},
        "after_state": after_state or {},
        "metadata": metadata or {},
    }
    try:
        event, _created = WorkflowEvent.objects.get_or_create(
            idempotency_key=event_key,
            defaults=defaults,
        )
    except IntegrityError:
        event = WorkflowEvent.objects.get(idempotency_key=event_key)
    return event


def initialize_readiness(project, *, actor=None):
    if actor is not None and not can_manage_construction(actor, project):
        raise PermissionDenied("You cannot initialize readiness for this project.")
    created = []
    for key, category, label in READINESS_TEMPLATE:
        item, was_created = PreconstructionItem.objects.get_or_create(
            project=project,
            key=key,
            defaults={
                "category": category,
                "label": label,
                "owner": project.project_manager,
            },
        )
        if was_created:
            created.append(item)
    return created


def initialize_closeout(project, *, actor=None):
    if actor is not None and not can_manage_construction(actor, project):
        raise PermissionDenied("You cannot initialize closeout for this project.")
    created = []
    for key, category, label in CLOSEOUT_TEMPLATE:
        item, was_created = CloseoutItem.objects.get_or_create(
            project=project,
            key=key,
            defaults={
                "category": category,
                "label": label,
                "owner": project.project_manager,
            },
        )
        if was_created:
            created.append(item)
    return created


@transaction.atomic
def convert_lead(lead, *, actor, idempotency_key=None):
    if not can_manage_sales(actor):
        raise PermissionDenied("You cannot convert this lead.")
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if not visible_leads(actor).filter(pk=locked.pk).exists():
        raise PermissionDenied("You cannot access this lead.")
    event_key = (
        _workflow_event_key("lead_converted_to_client", locked, idempotency_key)
        if idempotency_key
        else None
    )
    if event_key and WorkflowEvent.objects.filter(idempotency_key=event_key).exists():
        locked.refresh_from_db()
        return locked.client, False
    existing = locked.client or Client.objects.filter(email__iexact=locked.email).first()
    client_was_created = existing is None
    client = get_or_create_client_for_lead(locked, actor=actor)
    before = state_snapshot(locked, ["client_id", "workflow_stage", "next_action"])
    if locked.workflow_stage == Lead.WorkflowStage.NEW:
        locked.workflow_stage = Lead.WorkflowStage.CONTACTED
        locked.next_action = locked.next_action or "Prepare estimate"
        locked.save(update_fields=["workflow_stage", "next_action", "updated_at"])
    record_workflow_event(
        "lead_converted_to_client",
        actor=actor,
        related=locked,
        lead=locked,
        after_state={
            **state_snapshot(locked, ["client_id", "workflow_stage", "next_action"]),
            "client_created": client_was_created,
            "client_id": str(client.pk),
        },
        before_state=before,
        idempotency_key=idempotency_key,
    )
    record_activity(
        "Lead converted to client",
        f"{locked.name} · {client.email}",
        actor=actor,
        lead=locked,
    )
    return client, client_was_created


@transaction.atomic
def create_lead(
    *,
    actor,
    name,
    email,
    phone="",
    service="",
    location="",
    budget="",
    budget_amount=None,
    timeline="",
    source="",
    note="",
    assigned_to=None,
    idempotency_key=None,
):
    if not can_manage_sales(actor):
        raise PermissionDenied("You cannot create leads.")
    if idempotency_key:
        existing = Lead.objects.filter(idempotency_key=str(idempotency_key)).first()
        if existing:
            if not can_view_lead(actor, existing):
                raise PermissionDenied("You cannot access the lead for this idempotency key.")
            return existing, False
    name = str(name or "").strip()
    email = str(email or "").strip().lower()
    service = str(service or "").strip()
    location = str(location or "").strip()
    if not name or len(name) > 160:
        raise ValidationError("A lead name of 160 characters or fewer is required.")
    try:
        validate_email(email)
    except ValidationError as exc:
        raise ValidationError("A valid lead email is required.") from exc
    if not service or len(service) > 120:
        raise ValidationError("A project type of 120 characters or fewer is required.")
    if not location or len(location) > 160:
        raise ValidationError("A project location of 160 characters or fewer is required.")
    if assigned_to is not None and not is_staff_user(assigned_to):
        raise ValidationError("Leads may only be assigned to active staff.")
    if budget_amount is not None:
        try:
            budget_amount = Decimal(str(budget_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise ValidationError("Budget amount must be a valid amount.") from exc
        if not budget_amount.is_finite() or budget_amount < 0 or budget_amount > Decimal("9999999999.99"):
            raise ValidationError("Budget amount is outside the supported range.")
    lead = Lead.objects.create(
        idempotency_key=str(idempotency_key) if idempotency_key else None,
        name=name,
        email=email,
        phone=str(phone or "").strip()[:40],
        service=service,
        location=location,
        budget=str(budget or "").strip()[:120],
        budget_amount=budget_amount,
        timeline=str(timeline or "").strip()[:120],
        source=str(source or "").strip()[:120] or "Operations",
        note=str(note or "").strip()[:20000],
        assigned_to=assigned_to,
        created_by=actor,
        workflow_stage=Lead.WorkflowStage.NEW,
    )
    record_workflow_event(
        "lead_created",
        actor=actor,
        related=lead,
        lead=lead,
        after_state={
            "lead_id": str(lead.pk),
            "workflow_stage": lead.workflow_stage,
            "assigned_to_id": str(assigned_to.pk) if assigned_to else None,
        },
        idempotency_key=idempotency_key,
    )
    record_activity("Lead created", f"{lead.name} · {lead.source}", actor=actor, lead=lead)
    return lead, True


@transaction.atomic
def create_site_visit(
    lead,
    *,
    actor,
    assigned_to=None,
    scheduled_at=None,
    address="",
    scope="",
    notes="",
    idempotency_key=None,
):
    if not can_manage_sales(actor):
        raise PermissionDenied("You cannot create site visits.")
    locked_lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if not visible_leads(actor).filter(pk=locked_lead.pk).exists():
        raise PermissionDenied("You cannot access this lead.")
    if idempotency_key:
        existing = SiteVisit.objects.filter(idempotency_key=str(idempotency_key)).first()
        if existing:
            if existing.lead_id != locked_lead.pk:
                raise ValidationError("Idempotency key is already used for another lead.")
            return existing, False
    if assigned_to is not None and not is_staff_user(assigned_to):
        raise ValidationError("Site visits may only be assigned to active staff.")
    visit = SiteVisit.objects.create(
        idempotency_key=str(idempotency_key) if idempotency_key else None,
        lead=locked_lead,
        assigned_to=assigned_to,
        scheduled_at=scheduled_at,
        address=str(address or "").strip()[:240],
        scope=str(scope or "").strip()[:10000],
        notes=str(notes or "").strip()[:10000],
        created_by=actor,
    )
    locked_lead.workflow_stage = Lead.WorkflowStage.SITE_VISIT
    locked_lead.next_action = "Complete site visit"
    locked_lead.next_action_due = scheduled_at.date() if scheduled_at else locked_lead.next_action_due
    locked_lead.save(update_fields=["workflow_stage", "next_action", "next_action_due", "updated_at"])
    record_workflow_event(
        "site_visit_created",
        actor=actor,
        related=visit,
        lead=locked_lead,
        after_state={
            "site_visit_id": str(visit.pk),
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "assigned_to_id": str(assigned_to.pk) if assigned_to else None,
        },
        idempotency_key=idempotency_key,
    )
    record_activity("Site visit scheduled", locked_lead.name, actor=actor, lead=locked_lead)
    return visit, True


@transaction.atomic
def complete_site_visit(site_visit, *, actor, updates=None, idempotency_key=None):
    if not (can_manage_sales(actor) or site_visit.assigned_to_id == getattr(actor, "pk", None)):
        raise PermissionDenied("You cannot complete this site visit.")
    visit = SiteVisit.objects.select_for_update().select_related("lead", "project").get(pk=site_visit.pk)
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("site_visit_completed", visit, idempotency_key),
    ).exists():
        return visit
    if visit.status == SiteVisit.Status.COMPLETED:
        return visit
    before = state_snapshot(
        visit,
        ["status", "scope", "measurements", "client_requests", "existing_conditions", "potential_additional_work"],
    )
    for field, value in (updates or {}).items():
        if field in {
            "scope",
            "measurements",
            "client_requests",
            "existing_conditions",
            "potential_additional_work",
            "notes",
            "address",
        }:
            setattr(visit, field, str(value or "").strip())
    visit.status = SiteVisit.Status.COMPLETED
    visit.completed_at = timezone.now()
    visit.save()
    if visit.lead.workflow_stage in {
        Lead.WorkflowStage.NEW,
        Lead.WorkflowStage.CONTACTED,
        Lead.WorkflowStage.SITE_VISIT,
    }:
        visit.lead.workflow_stage = Lead.WorkflowStage.ESTIMATING
        visit.lead.next_action = "Build estimate"
        visit.lead.next_action_due = None
        visit.lead.save(update_fields=["workflow_stage", "next_action", "next_action_due", "updated_at"])
    record_workflow_event(
        "site_visit_completed",
        actor=actor,
        related=visit,
        lead=visit.lead,
        project=visit.project,
        before_state=before,
        after_state=state_snapshot(visit, ["status", "completed_at", "scope", "measurements"]),
        source="field" if visit.assigned_to_id == getattr(actor, "pk", None) else "web",
        idempotency_key=idempotency_key,
    )
    record_activity("Site visit completed", visit.lead.name, actor=actor, lead=visit.lead, project=visit.project)
    return visit


@transaction.atomic
def send_estimate(estimate, *, actor, idempotency_key=None):
    if not can_manage_sales(actor):
        raise PermissionDenied("You cannot send estimates.")
    locked = Estimate.objects.select_for_update().select_related("lead", "client").get(pk=estimate.pk)
    if not can_view_estimate(actor, locked):
        raise PermissionDenied("You cannot send this estimate.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("estimate_sent", locked, idempotency_key),
    ).exists():
        return locked
    if locked.status == Estimate.Status.ACCEPTED:
        return locked
    before = state_snapshot(locked, ["status", "sent_at", "locked_at"])
    locked.status = Estimate.Status.SENT
    locked.sent_at = locked.sent_at or timezone.now()
    locked.save(update_fields=["status", "sent_at", "updated_at"])
    if locked.lead_id and locked.lead.workflow_stage not in {
        Lead.WorkflowStage.SOLD_SCHEDULED,
        Lead.WorkflowStage.LOST,
        Lead.WorkflowStage.ON_HOLD,
    }:
        locked.lead.workflow_stage = Lead.WorkflowStage.PROPOSAL_SENT
        locked.lead.next_action = "Follow up on proposal"
        locked.lead.next_action_due = timezone.localdate() + timedelta(days=3)
        locked.lead.save(update_fields=["workflow_stage", "next_action", "next_action_due", "updated_at"])
    record_workflow_event(
        "estimate_sent",
        actor=actor,
        related=locked,
        estimate=locked,
        lead=locked.lead,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "sent_at"]),
        idempotency_key=idempotency_key,
    )
    record_activity(
        f"Estimate #{locked.number} sent",
        locked.title,
        actor=actor,
        estimate=locked,
        lead=locked.lead,
    )
    return locked


@transaction.atomic
def accept_estimate(estimate, *, actor, request=None, idempotency_key=None):
    locked = Estimate.objects.select_for_update().select_related("lead", "client").get(pk=estimate.pk)
    is_client_acceptance = bool(
        locked.client_id
        and locked.client.user_id == getattr(actor, "pk", None)
        and not getattr(actor, "is_staff", False)
    )
    if not is_client_acceptance:
        raise PermissionDenied("Only the linked client can accept an estimate.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("estimate_accepted", locked, idempotency_key),
    ).exists():
        return locked, False
    if locked.status == Estimate.Status.ACCEPTED:
        return locked, False
    if locked.status != Estimate.Status.SENT:
        raise ValidationError("Only estimates sent to the client can be accepted.")
    before = state_snapshot(locked, ["status", "accepted_at", "accepted_by_id"])
    locked.status = Estimate.Status.ACCEPTED
    locked.accepted_at = timezone.now()
    locked.accepted_by = actor
    locked.locked_at = locked.accepted_at
    locked.save(update_fields=["status", "accepted_at", "accepted_by", "locked_at", "updated_at"])
    if locked.lead_id:
        locked.lead.workflow_stage = Lead.WorkflowStage.APPROVED
        locked.lead.next_action = "Prepare agreement and project"
        locked.lead.save(update_fields=["workflow_stage", "next_action", "updated_at"])
    record_workflow_event(
        "estimate_accepted",
        actor=actor,
        related=locked,
        estimate=locked,
        lead=locked.lead,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "accepted_at", "accepted_by_id", "locked_at"]),
        metadata={"request_ip": request.META.get("REMOTE_ADDR", "") if request else ""},
        idempotency_key=idempotency_key,
    )
    record_activity("Estimate accepted by client", f"Estimate #{locked.number}", actor=actor, estimate=locked)
    return locked, True


@transaction.atomic
def accept_agreement(agreement, *, actor, request=None, idempotency_key=None):
    locked = Agreement.objects.select_for_update().select_related("project", "project__client").get(pk=agreement.pk)
    project = locked.project
    is_client_acceptance = bool(
        project.client_id
        and project.client.user_id == getattr(actor, "pk", None)
        and not getattr(actor, "is_staff", False)
    )
    if not is_client_acceptance:
        raise PermissionDenied("Only the linked client can accept this agreement.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("agreement_accepted", locked, idempotency_key),
    ).exists():
        return locked, False
    if locked.status == Agreement.Status.ACCEPTED:
        return locked, False
    if locked.status != Agreement.Status.ISSUED:
        raise ValidationError("Only issued agreements can be accepted.")
    now = timezone.now()
    snapshot = locked.content_snapshot or {
        "project": str(project.pk),
        "contract_value": str(locked.contract_value),
        "deposit_amount": str(locked.deposit_amount),
    }
    acceptance_hash = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    before = state_snapshot(locked, ["status", "accepted_at", "accepted_by_id", "locked_at"])
    locked.status = Agreement.Status.ACCEPTED
    locked.accepted_at = now
    locked.accepted_by = actor
    locked.accepted_ip = request.META.get("REMOTE_ADDR") if request else None
    locked.accepted_user_agent = (request.META.get("HTTP_USER_AGENT", "") if request else "")[:500]
    locked.acceptance_hash = acceptance_hash
    locked.content_snapshot = snapshot
    locked.locked_at = now
    locked.save()
    project.operational_phase = Project.OperationalPhase.PRECONSTRUCTION
    project.next_step = project.next_step or "Complete readiness checklist"
    project.save(update_fields=["operational_phase", "next_step", "updated_at"])
    record_workflow_event(
        "agreement_accepted",
        actor=actor,
        related=locked,
        project=project,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "accepted_at", "accepted_by_id", "locked_at"]),
        metadata={"acceptance_hash": acceptance_hash},
        idempotency_key=idempotency_key,
    )
    record_activity("Agreement accepted by client", project.title, actor=actor, project=project)
    return locked, True


def _estimate_category(category):
    return {
        EstimateLineItem.Category.LABOR: BudgetLine.Category.LABOR,
        EstimateLineItem.Category.MATERIALS: BudgetLine.Category.MATERIALS,
        EstimateLineItem.Category.SUBCONTRACTOR: BudgetLine.Category.SUBCONTRACTOR,
        EstimateLineItem.Category.ALLOWANCE: BudgetLine.Category.MISCELLANEOUS,
        EstimateLineItem.Category.OWNER_PROVIDED: BudgetLine.Category.MISCELLANEOUS,
    }.get(category, BudgetLine.Category.MISCELLANEOUS)


def _ensure_milestones(project):
    titles = ["Walkthrough", "Estimate approved", "Selections", "Construction", "Final walkthrough"]
    for index, title in enumerate(titles, start=1):
        project.milestones.get_or_create(
            sort_order=index,
            defaults={"title": title, "is_complete": index <= 2},
        )


@transaction.atomic
def create_project_from_estimate(estimate, *, actor, idempotency_key=None):
    if not can_manage_sales(actor):
        raise PermissionDenied("You cannot create a project from this estimate.")
    locked = Estimate.objects.select_for_update().select_related("lead", "client").get(pk=estimate.pk)
    if not can_view_estimate(actor, locked):
        raise PermissionDenied("You cannot create a project from this estimate.")
    existing = locked.projects.order_by("-created_at").first()
    if existing:
        initialize_readiness(existing, actor=actor)
        return existing, False
    if locked.status != Estimate.Status.ACCEPTED:
        raise ValidationError("Only accepted estimates can become projects.")
    client = locked.client
    if client is None and locked.lead is not None:
        client = get_or_create_client_for_lead(locked.lead, actor=actor)
    if client is None:
        raise ValidationError("A client is required before creating a project.")
    lead = locked.lead
    project = Project.objects.create(
        estimate=locked,
        lead=lead,
        client=client,
        title=locked.title,
        location=lead.location if lead else "",
        address_line1=lead.address_line1 if lead else "",
        address_line2=lead.address_line2 if lead else "",
        city=lead.city if lead else "",
        state=lead.state if lead else "",
        postal_code=lead.postal_code if lead else "",
        project_type=lead.service if lead and lead.service else "renovation",
        status=Project.Status.PLANNING,
        operational_phase=Project.OperationalPhase.PRECONSTRUCTION,
        is_published=False,
        next_step="Assign project staff",
        summary=locked.notes,
        project_manager=lead.assigned_to if lead and lead.assigned_to_id else None,
        created_by=actor,
        fallback_image="operations/images/progress-kitchen.png",
    )
    _ensure_milestones(project)
    agreement, _ = Agreement.objects.get_or_create(
        project=project,
        defaults={
            "estimate": locked,
            "status": Agreement.Status.ISSUED,
            "contract_value": locked.total,
            "deposit_amount": locked.deposit_amount,
            "issued_at": timezone.now(),
            "content_snapshot": {
                "estimate_id": str(locked.pk),
                "estimate_number": locked.number,
                "contract_value": str(locked.total),
                "deposit_amount": str(locked.deposit_amount),
                "title": locked.title,
            },
            "created_by": actor,
        },
    )
    for line in locked.line_items.all():
        BudgetLine.objects.get_or_create(
            project=project,
            source_estimate_line=line,
            defaults={
                "description": line.description,
                "category": _estimate_category(line.category),
                "cost_code": line.cost_code,
                "original_budget": line.estimated_cost or line.line_total,
                "is_allowance": line.is_allowance,
                "created_by": actor,
            },
        )
    if locked.deposit_amount > 0:
        PaymentSchedule.objects.get_or_create(
            project=project,
            sequence=1,
            defaults={
                "description": "Initial deposit",
                "amount": locked.deposit_amount,
                "status": PaymentSchedule.Status.READY,
                "created_by": actor,
            },
        )
    next_sequence = 2
    for row in locked.payment_schedule or []:
        if not isinstance(row, dict):
            continue
        try:
            amount = Decimal(str(row.get("amount", "0")))
        except (TypeError, ValueError, ArithmeticError):
            continue
        if amount <= 0:
            continue
        PaymentSchedule.objects.get_or_create(
            project=project,
            sequence=next_sequence,
            defaults={
                "description": str(row.get("description") or f"Progress payment {next_sequence}")[:180],
                "amount": amount,
                "status": PaymentSchedule.Status.PENDING,
                "created_by": actor,
            },
        )
        next_sequence += 1
    initialize_readiness(project, actor=actor)
    initialize_closeout(project, actor=actor)
    if lead:
        lead.status = Lead.Status.WON
        lead.workflow_stage = Lead.WorkflowStage.SOLD_SCHEDULED
        lead.next_action = "Complete readiness checklist"
        lead.save(update_fields=["status", "workflow_stage", "next_action", "updated_at"])
    record_workflow_event(
        "project_created_from_estimate",
        actor=actor,
        related=project,
        project=project,
        estimate=locked,
        lead=lead,
        after_state={"project_id": str(project.pk), "agreement_id": str(agreement.pk)},
        idempotency_key=idempotency_key,
    )
    record_activity(
        "Project created from accepted estimate",
        project.title,
        actor=actor,
        estimate=locked,
        project=project,
    )
    return project, True


@transaction.atomic
def complete_readiness_item(item, *, actor, idempotency_key=None, notes=None):
    locked = PreconstructionItem.objects.select_for_update().select_related("project").get(pk=item.pk)
    if not can_manage_construction(actor, locked.project):
        raise PermissionDenied("You cannot update this readiness item.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("readiness_item_completed", locked, idempotency_key),
    ).exists():
        return locked
    if locked.status == PreconstructionItem.Status.COMPLETE:
        return locked
    before = state_snapshot(locked, ["status", "completed_at", "completed_by_id", "notes"])
    locked.status = PreconstructionItem.Status.COMPLETE
    locked.completed_at = timezone.now()
    locked.completed_by = actor
    if notes is not None:
        locked.notes = str(notes).strip()
    locked.save()
    if not locked.project.readiness_items.filter(
        required=True,
    ).exclude(status__in=[PreconstructionItem.Status.COMPLETE, PreconstructionItem.Status.SKIPPED]).exists():
        locked.project.construction_ready_at = timezone.now()
        locked.project.next_step = "Schedule construction start"
        locked.project.save(update_fields=["construction_ready_at", "next_step", "updated_at"])
    record_workflow_event(
        "readiness_item_completed",
        actor=actor,
        related=locked,
        project=locked.project,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "completed_at", "completed_by_id", "notes"]),
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def create_change_order(
    project,
    *,
    actor,
    title,
    description,
    price_impact=Decimal("0.00"),
    schedule_impact_days=0,
    status=ChangeOrder.Status.DRAFT,
    idempotency_key=None,
):
    if not can_manage_construction(actor, project):
        raise PermissionDenied("You cannot create a change order for this project.")
    if idempotency_key:
        existing = ChangeOrder.objects.filter(idempotency_key=str(idempotency_key)).first()
        if existing:
            if existing.project_id != project.pk:
                raise ValidationError("Idempotency key is already used for another project.")
            return existing, False
    title = str(title or "").strip()
    description = str(description or "").strip()
    if not title or not description:
        raise ValidationError("A change order title and description are required.")
    if len(title) > 180:
        raise ValidationError("Change order titles must be 180 characters or fewer.")
    if len(description) > 20000:
        raise ValidationError("Change order descriptions are too long.")
    try:
        price_impact = Decimal(str(price_impact)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("Price impact must be a valid amount.") from exc
    if not price_impact.is_finite() or abs(price_impact) > Decimal("9999999999.99"):
        raise ValidationError("Price impact is outside the supported range.")
    try:
        schedule_impact_days = int(schedule_impact_days or 0)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError("Schedule impact must be a whole number of days.") from exc
    if schedule_impact_days < 0 or schedule_impact_days > 3650:
        raise ValidationError("Schedule impact must be between 0 and 3650 days.")
    if status not in {ChangeOrder.Status.DRAFT, ChangeOrder.Status.SENT}:
        raise ValidationError("New change orders must be drafts or sent for client approval.")
    next_number = (
        ChangeOrder.objects.filter(project=project)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
        or 0
    ) + 1
    change_order = ChangeOrder.objects.create(
        idempotency_key=str(idempotency_key) if idempotency_key else None,
        project=project,
        number=next_number,
        title=title,
        description=description,
        price_impact=price_impact,
        schedule_impact_days=schedule_impact_days,
        status=status,
        sent_at=timezone.now() if status == ChangeOrder.Status.SENT else None,
        created_by=actor,
    )
    record_workflow_event(
        "change_order_created",
        actor=actor,
        related=change_order,
        project=project,
        after_state=state_snapshot(
            change_order,
            ["number", "status", "price_impact", "schedule_impact_days"],
        ),
        idempotency_key=f"change-order-event:{change_order.pk}",
    )
    return change_order, True


@transaction.atomic
def approve_change_order(change_order, *, actor, request=None, idempotency_key=None):
    locked = ChangeOrder.objects.select_for_update().select_related("project", "project__client").get(pk=change_order.pk)
    project = locked.project
    is_client_approval = bool(
        project.client_id
        and project.client.user_id == getattr(actor, "pk", None)
        and not getattr(actor, "is_staff", False)
    )
    if not is_client_approval:
        raise PermissionDenied("Only the linked client can approve a change order.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("change_order_approved", locked, idempotency_key),
    ).exists():
        return locked, False
    if locked.status == ChangeOrder.Status.APPROVED:
        return locked, False
    if locked.status != ChangeOrder.Status.SENT:
        raise ValidationError("Only change orders sent for approval can be approved.")
    now = timezone.now()
    before = state_snapshot(locked, ["status", "price_impact", "schedule_impact_days"])
    locked.status = ChangeOrder.Status.APPROVED
    locked.approved_at = now
    locked.approved_by = actor
    locked.approval_ip = request.META.get("REMOTE_ADDR") if request else None
    locked.approved_snapshot = {
        "number": locked.number,
        "title": locked.title,
        "description": locked.description,
        "price_impact": str(locked.price_impact),
        "schedule_impact_days": locked.schedule_impact_days,
        "approved_at": now.isoformat(),
    }
    locked.locked_at = now
    locked.save()
    budget_line = BudgetLine.objects.select_for_update().filter(
        project=project,
        cost_code="change-orders",
    ).first()
    if budget_line is None:
        budget_line = BudgetLine.objects.create(
            project=project,
            description="Approved change orders",
            category=BudgetLine.Category.MISCELLANEOUS,
            cost_code="change-orders",
            created_by=project.project_manager or project.created_by,
        )
    budget_line.approved_change = (
        budget_line.approved_change + locked.price_impact
    ).quantize(Decimal("0.01"))
    budget_line.save(update_fields=["approved_change", "updated_at"])
    if locked.price_impact > 0:
        next_sequence = (
            PaymentSchedule.objects.filter(project=project)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
            or 0
        ) + 1
        PaymentSchedule.objects.create(
            project=project,
            sequence=next_sequence,
            description=f"Change order CO-{locked.number}",
            amount=locked.price_impact,
            status=PaymentSchedule.Status.READY,
            created_by=actor,
        )
    record_workflow_event(
        "change_order_approved",
        actor=actor,
        related=locked,
        project=project,
        before_state=before,
        after_state=state_snapshot(
            locked,
            ["status", "approved_at", "approved_by_id", "price_impact"],
        ),
        metadata={"approval_ip": locked.approval_ip or ""},
        idempotency_key=idempotency_key,
    )
    record_activity(
        "Change order approved by client",
        f"CO-{locked.number}: {locked.title}",
        actor=actor,
        project=project,
    )
    return locked, True


@transaction.atomic
def record_payment(
    project,
    *,
    actor,
    amount,
    schedule=None,
    received_on=None,
    method=PaymentRecord.Method.OTHER,
    reference="",
    notes="",
    idempotency_key=None,
):
    if not can_view_financials(actor, project):
        raise PermissionDenied("You cannot record payments for this project.")
    if idempotency_key:
        existing = PaymentRecord.objects.filter(idempotency_key=str(idempotency_key)).first()
        if existing:
            if existing.project_id != project.pk:
                raise ValidationError("Idempotency key is already used for another project.")
            return existing, False
    try:
        amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("Payment amount must be a valid amount.") from exc
    if not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999.99"):
        raise ValidationError("Payment amount must be greater than zero.")
    if method not in {value for value, _label in PaymentRecord.Method.choices}:
        raise ValidationError("Choose a valid payment method.")
    if schedule is not None:
        schedule = PaymentSchedule.objects.select_for_update().get(pk=schedule.pk)
        if schedule.project_id != project.pk:
            raise ValidationError("The payment schedule must belong to this project.")
        if amount > schedule.remaining_amount:
            raise ValidationError("Payment cannot exceed the remaining scheduled balance.")
    payment = PaymentRecord.objects.create(
        idempotency_key=str(idempotency_key) if idempotency_key else None,
        project=project,
        schedule=schedule,
        amount=amount,
        received_on=received_on or timezone.localdate(),
        method=method,
        reference=str(reference).strip()[:120],
        notes=str(notes).strip()[:20000],
        created_by=actor,
    )
    if schedule:
        schedule.status = (
            PaymentSchedule.Status.PAID
            if schedule.remaining_amount <= 0
            else PaymentSchedule.Status.INVOICED
        )
        schedule.save(update_fields=["status", "updated_at"])
    record_workflow_event(
        "payment_recorded",
        actor=actor,
        related=payment,
        project=project,
        after_state={
            "payment_id": str(payment.pk),
            "amount": str(payment.amount),
            "schedule_id": str(schedule.pk) if schedule else "",
        },
        idempotency_key=f"payment-event:{payment.pk}",
    )
    record_activity("Payment recorded", f"${payment.amount:.2f}", actor=actor, project=project)
    return payment, True


@transaction.atomic
def record_cost(
    project,
    *,
    actor,
    amount,
    description,
    vendor="",
    incurred_on=None,
    source="manual",
    budget_line=None,
    idempotency_key=None,
):
    if not can_view_financials(actor, project):
        raise PermissionDenied("You cannot record costs for this project.")
    if idempotency_key:
        existing = CostEntry.objects.filter(idempotency_key=str(idempotency_key)).first()
        if existing:
            if existing.project_id != project.pk:
                raise ValidationError("Idempotency key is already used for another project.")
            return existing, False
    try:
        amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("Cost amount must be a valid amount.") from exc
    if not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999.99"):
        raise ValidationError("Cost amount must be greater than zero.")
    description = str(description or "").strip()
    if not description or len(description) > 180:
        raise ValidationError("A cost description of 180 characters or fewer is required.")
    vendor = str(vendor or "").strip()[:180]
    source = str(source or "manual").strip()[:40] or "manual"
    if budget_line is not None:
        budget_line = BudgetLine.objects.select_for_update().get(pk=budget_line.pk)
        if budget_line.project_id != project.pk:
            raise ValidationError("The budget line must belong to this project.")
    entry = CostEntry.objects.create(
        idempotency_key=str(idempotency_key) if idempotency_key else None,
        project=project,
        budget_line=budget_line,
        vendor=vendor,
        description=description,
        amount=amount,
        incurred_on=incurred_on or timezone.localdate(),
        source=source,
        created_by=actor,
    )
    if budget_line is not None:
        budget_line.actual = (budget_line.actual + amount).quantize(Decimal("0.01"))
        budget_line.save(update_fields=["actual", "updated_at"])
    record_workflow_event(
        "cost_recorded",
        actor=actor,
        related=entry,
        project=project,
        after_state={
            "cost_id": str(entry.pk),
            "amount": str(entry.amount),
            "budget_line_id": str(budget_line.pk) if budget_line else "",
        },
        idempotency_key=f"cost-event:{entry.pk}",
    )
    record_activity("Cost recorded", f"${entry.amount:.2f}", actor=actor, project=project)
    return entry, True


@transaction.atomic
def void_cost_entry(entry, *, actor, idempotency_key=None):
    locked = CostEntry.objects.select_for_update().select_related("project").get(pk=entry.pk)
    if not can_view_financials(actor, locked.project):
        raise PermissionDenied("You cannot void costs for this project.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("cost_voided", locked, idempotency_key),
    ).exists():
        return locked, False
    if locked.is_void:
        return locked, False
    locked.is_void = True
    locked.voided_at = timezone.now()
    locked.voided_by = actor
    locked.save()
    if locked.budget_line_id:
        budget_line = BudgetLine.objects.select_for_update().get(pk=locked.budget_line_id)
        budget_line.actual = max(
            (budget_line.actual - locked.amount).quantize(Decimal("0.01")),
            Decimal("0.00"),
        )
        budget_line.save(update_fields=["actual", "updated_at"])
    record_workflow_event(
        "cost_voided",
        actor=actor,
        related=locked,
        project=locked.project,
        after_state={
            "cost_id": str(locked.pk),
            "amount": str(locked.amount),
            "voided_at": locked.voided_at.isoformat(),
        },
        idempotency_key=idempotency_key,
    )
    record_activity("Cost voided", f"${locked.amount:.2f}", actor=actor, project=locked.project)
    return locked, True


@transaction.atomic
def record_deposit(
    project,
    *,
    actor,
    amount=None,
    received_on=None,
    method=PaymentRecord.Method.OTHER,
    reference="",
    notes="",
    idempotency_key=None,
):
    if not can_view_financials(actor, project):
        raise PermissionDenied("You cannot record a deposit for this project.")
    schedule = (
        PaymentSchedule.objects.select_for_update()
        .filter(project=project, sequence=1)
        .first()
    )
    agreement = Agreement.objects.filter(project=project).first()
    if amount in (None, ""):
        if schedule is not None:
            amount = schedule.remaining_amount
        elif agreement is not None:
            amount = agreement.deposit_amount
    if amount in (None, ""):
        raise ValidationError("A deposit amount is required.")
    payment, created = record_payment(
        project,
        actor=actor,
        amount=amount,
        schedule=schedule,
        received_on=received_on,
        method=method,
        reference=reference,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    lead = project.lead
    if lead is not None and lead.workflow_stage not in {
        Lead.WorkflowStage.SOLD_SCHEDULED,
        Lead.WorkflowStage.LOST,
        Lead.WorkflowStage.ON_HOLD,
    }:
        lead.workflow_stage = Lead.WorkflowStage.DEPOSIT
        lead.next_action = "Begin preconstruction"
        lead.next_action_due = None
        lead.save(update_fields=["workflow_stage", "next_action", "next_action_due", "updated_at"])
    record_workflow_event(
        "deposit_recorded",
        actor=actor,
        related=payment,
        project=project,
        after_state={
            "payment_id": str(payment.pk),
            "amount": str(payment.amount),
            "created": created,
        },
        idempotency_key=idempotency_key,
    )
    return payment, created


@transaction.atomic
def create_permit(
    project,
    *,
    actor,
    permit_type,
    jurisdiction="",
    permit_number="",
    status=Permit.Status.PENDING,
    expires_at=None,
    notes="",
    idempotency_key=None,
):
    if not can_manage_construction(actor, project):
        raise PermissionDenied("You cannot create permits for this project.")
    if idempotency_key:
        existing = Permit.objects.filter(idempotency_key=str(idempotency_key)).first()
        if existing:
            if existing.project_id != project.pk:
                raise ValidationError("Idempotency key is already used for another project.")
            return existing, False
    permit_type = str(permit_type or "").strip()
    if not permit_type or len(permit_type) > 140:
        raise ValidationError("A permit type of 140 characters or fewer is required.")
    if status not in {Permit.Status.PENDING, Permit.Status.SUBMITTED}:
        raise ValidationError("New permits may be pending or submitted.")
    now = timezone.now()
    permit = Permit.objects.create(
        idempotency_key=str(idempotency_key) if idempotency_key else None,
        project=project,
        permit_type=permit_type,
        jurisdiction=str(jurisdiction or "").strip()[:160],
        permit_number=str(permit_number or "").strip()[:100],
        status=status,
        submitted_at=now if status == Permit.Status.SUBMITTED else None,
        expires_at=expires_at,
        notes=str(notes or "").strip()[:20000],
        created_by=actor,
    )
    record_workflow_event(
        "permit_created",
        actor=actor,
        related=permit,
        project=project,
        after_state={
            "permit_id": str(permit.pk),
            "permit_type": permit.permit_type,
            "status": permit.status,
        },
        idempotency_key=idempotency_key,
    )
    return permit, True


@transaction.atomic
def record_permit_status(
    permit,
    *,
    actor,
    status,
    permit_number=None,
    expires_at=None,
    notes=None,
    idempotency_key=None,
):
    locked = Permit.objects.select_for_update().select_related("project").get(pk=permit.pk)
    if not can_manage_construction(actor, locked.project):
        raise PermissionDenied("You cannot update permits for this project.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("permit_status_recorded", locked, idempotency_key),
    ).exists():
        return locked
    if status not in {value for value, _label in Permit.Status.choices}:
        raise ValidationError("Choose a valid permit status.")
    before = state_snapshot(locked, ["status", "permit_number", "expires_at", "notes"])
    locked.status = status
    if permit_number is not None:
        locked.permit_number = str(permit_number).strip()[:100]
    if expires_at is not None:
        locked.expires_at = expires_at
    if notes is not None:
        locked.notes = str(notes).strip()[:20000]
    if status == Permit.Status.SUBMITTED and locked.submitted_at is None:
        locked.submitted_at = timezone.now()
    if status == Permit.Status.APPROVED and locked.approved_at is None:
        locked.approved_at = timezone.now()
    locked.save()
    record_workflow_event(
        "permit_status_recorded",
        actor=actor,
        related=locked,
        project=locked.project,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "permit_number", "expires_at", "notes"]),
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def submit_daily_report(
    project,
    *,
    actor,
    report_date,
    summary,
    work_completed="",
    labor_count=0,
    hours_worked=Decimal("0.00"),
    weather="",
    equipment="",
    notes="",
    idempotency_key=None,
):
    if not can_submit_field_work(actor, project):
        raise PermissionDenied("You cannot submit a field report for this project.")
    try:
        key = uuid.UUID(str(idempotency_key)) if idempotency_key else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("Field report idempotency key must be a UUID.") from exc
    if key:
        existing = DailyReport.objects.filter(idempotency_key=key).first()
        if existing:
            if existing.project_id != project.pk:
                raise ValidationError("Idempotency key is already used for another project.")
            return existing, False
    summary = str(summary or "").strip()
    if not summary:
        raise ValidationError("A daily report summary is required.")
    if len(summary) > 20000:
        raise ValidationError("Daily report summary is too long.")
    try:
        labor_count = int(labor_count or 0)
        hours_worked = Decimal(str(hours_worked or "0")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("Daily report labor values are invalid.") from exc
    if labor_count < 0 or labor_count > 1000:
        raise ValidationError("Labor count must be between 0 and 1000.")
    if not hours_worked.is_finite() or hours_worked < 0 or hours_worked > Decimal("24.00"):
        raise ValidationError("Hours worked must be between 0 and 24.")
    report = DailyReport.objects.create(
        idempotency_key=key or uuid.uuid4(),
        project=project,
        submitted_by=actor,
        report_date=report_date,
        summary=summary,
        work_completed=str(work_completed or "").strip()[:20000],
        labor_count=labor_count,
        hours_worked=hours_worked,
        weather=str(weather or "").strip()[:120],
        equipment=str(equipment or "").strip()[:10000],
        notes=str(notes or "").strip()[:20000],
    )
    record_workflow_event(
        "daily_report_submitted",
        actor=actor,
        related=report,
        project=project,
        after_state={"report_id": str(report.pk), "report_date": report.report_date.isoformat()},
        source="field",
        idempotency_key=f"daily-report-event:{report.pk}",
    )
    return report, True


@transaction.atomic
def request_material(
    project,
    *,
    actor,
    description,
    quantity="",
    needed_by=None,
    vendor="",
    notes="",
    idempotency_key=None,
):
    if not can_submit_field_work(actor, project):
        raise PermissionDenied("You cannot request materials for this project.")
    try:
        key = uuid.UUID(str(idempotency_key)) if idempotency_key else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("Material request idempotency key must be a UUID.") from exc
    if key:
        existing = MaterialRequest.objects.filter(idempotency_key=key).first()
        if existing:
            if existing.project_id != project.pk:
                raise ValidationError("Idempotency key is already used for another project.")
            return existing, False
    description = str(description or "").strip()
    if not description:
        raise ValidationError("A material description is required.")
    if len(description) > 180:
        raise ValidationError("Material descriptions must be 180 characters or fewer.")
    request = MaterialRequest.objects.create(
        idempotency_key=key or uuid.uuid4(),
        project=project,
        requested_by=actor,
        description=description,
        quantity=str(quantity or "").strip()[:80],
        needed_by=needed_by,
        vendor=str(vendor or "").strip()[:180],
        notes=str(notes or "").strip()[:20000],
    )
    record_workflow_event(
        "material_requested",
        actor=actor,
        related=request,
        project=project,
        after_state={"material_request_id": str(request.pk), "description": request.description},
        source="field",
        idempotency_key=f"material-request-event:{request.pk}",
    )
    return request, True


@transaction.atomic
def submit_problem_report(
    project,
    *,
    actor,
    title,
    description,
    severity=ProblemReport.Severity.NORMAL,
    task=None,
    idempotency_key=None,
):
    if not can_submit_field_work(actor, project):
        raise PermissionDenied("You cannot report problems for this project.")
    try:
        key = uuid.UUID(str(idempotency_key)) if idempotency_key else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("Problem report idempotency key must be a UUID.") from exc
    if key:
        existing = ProblemReport.objects.filter(idempotency_key=key).first()
        if existing:
            if existing.project_id != project.pk:
                raise ValidationError("Idempotency key is already used for another project.")
            return existing, False
    title = str(title or "").strip()
    description = str(description or "").strip()
    if not title or len(title) > 180:
        raise ValidationError("A problem title of 180 characters or fewer is required.")
    if not description or len(description) > 20000:
        raise ValidationError("A problem description of 20,000 characters or fewer is required.")
    if severity not in {value for value, _label in ProblemReport.Severity.choices}:
        raise ValidationError("Choose a valid problem severity.")
    if task is not None:
        task = Task.objects.get(pk=task.pk)
        if task.project_id != project.pk:
            raise ValidationError("The selected task must belong to this project.")
    report = ProblemReport.objects.create(
        idempotency_key=key or uuid.uuid4(),
        project=project,
        task=task,
        reported_by=actor,
        title=title,
        description=description,
        severity=severity,
    )
    record_workflow_event(
        "problem_reported",
        actor=actor,
        related=report,
        project=project,
        after_state={
            "problem_report_id": str(report.pk),
            "title": report.title,
            "severity": report.severity,
        },
        source="field",
        idempotency_key=f"problem-report-event:{report.pk}",
    )
    record_activity("Construction problem reported", report.title, actor=actor, project=project)
    return report, True


@transaction.atomic
def resolve_problem_report(
    report,
    *,
    actor,
    resolution,
    status=ProblemReport.Status.RESOLVED,
    idempotency_key=None,
):
    locked = ProblemReport.objects.select_for_update().select_related("project").get(pk=report.pk)
    if not can_manage_construction(actor, locked.project):
        raise PermissionDenied("You cannot resolve this construction problem.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("problem_report_resolved", locked, idempotency_key),
    ).exists():
        return locked
    if status not in {ProblemReport.Status.RESOLVED, ProblemReport.Status.DISMISSED}:
        raise ValidationError("A problem can only be resolved or dismissed by this command.")
    resolution = str(resolution or "").strip()
    if not resolution or len(resolution) > 20000:
        raise ValidationError("A problem resolution of 20,000 characters or fewer is required.")
    before = state_snapshot(locked, ["status", "resolution", "resolved_at", "resolved_by_id"])
    locked.status = status
    locked.resolution = resolution
    locked.resolved_at = timezone.now()
    locked.resolved_by = actor
    locked.save()
    record_workflow_event(
        "problem_report_resolved",
        actor=actor,
        related=locked,
        project=locked.project,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "resolution", "resolved_at", "resolved_by_id"]),
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def complete_closeout_item(item, *, actor, status=CloseoutItem.Status.COMPLETE, notes=None, idempotency_key=None):
    locked = CloseoutItem.objects.select_for_update().select_related("project").get(pk=item.pk)
    if not can_manage_construction(actor, locked.project):
        raise PermissionDenied("You cannot update closeout for this project.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("closeout_item_completed", locked, idempotency_key),
    ).exists():
        return locked
    if status not in {CloseoutItem.Status.COMPLETE, CloseoutItem.Status.NOT_APPLICABLE}:
        raise ValidationError("Closeout items can only be completed or marked not applicable.")
    if locked.status in {CloseoutItem.Status.COMPLETE, CloseoutItem.Status.NOT_APPLICABLE}:
        return locked
    before = state_snapshot(locked, ["status", "notes", "completed_at", "completed_by_id"])
    locked.status = status
    if notes is not None:
        locked.notes = str(notes).strip()[:20000]
    locked.completed_at = timezone.now()
    locked.completed_by = actor
    locked.save()
    if not locked.project.closeout_items.filter(
        required=True,
    ).exclude(status__in=[CloseoutItem.Status.COMPLETE, CloseoutItem.Status.NOT_APPLICABLE]).exists():
        locked.project.operational_phase = Project.OperationalPhase.WARRANTY
        locked.project.status = Project.Status.COMPLETE
        locked.project.next_step = "Warranty support"
        locked.project.save(update_fields=["operational_phase", "status", "next_step", "updated_at"])
    record_workflow_event(
        "closeout_item_completed",
        actor=actor,
        related=locked,
        project=locked.project,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "notes", "completed_at", "completed_by_id"]),
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def advance_selection(selection, *, actor, status, client_choice=None, idempotency_key=None):
    locked = Selection.objects.select_for_update().select_related("project", "project__client").get(pk=selection.pk)
    project = locked.project
    if is_client(actor):
        if not can_view_project(actor, project) or status != Selection.Status.SUBMITTED:
            raise PermissionDenied("Clients may only submit their own selection choices.")
        if not str(client_choice or "").strip():
            raise ValidationError("A selection choice is required.")
    elif not can_manage_construction(actor, project):
        raise PermissionDenied("Only assigned management may advance selections.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("selection_advanced", locked, idempotency_key),
    ).exists():
        return locked
    valid_statuses = {value for value, _label in Selection.Status.choices}
    if status not in valid_statuses:
        raise ValidationError("Choose a valid selection status.")
    if client_choice is not None and len(str(client_choice)) > 20000:
        raise ValidationError("Selection choices are too long.")
    if locked.status == status:
        return locked
    sequence = [
        Selection.Status.PENDING,
        Selection.Status.SUBMITTED,
        Selection.Status.APPROVED,
        Selection.Status.ORDERED,
        Selection.Status.RECEIVED,
        Selection.Status.INSTALLED,
    ]
    if status not in sequence or sequence.index(status) < sequence.index(locked.status):
        raise ValidationError("Selections can only move forward through their lifecycle.")
    before = state_snapshot(
        locked,
        ["status", "client_choice", "approved_at", "ordered_at", "received_at", "installed_at"],
    )
    locked.status = status
    if client_choice is not None:
        locked.client_choice = str(client_choice).strip()
    now = timezone.now()
    timestamp_fields = {
        Selection.Status.APPROVED: "approved_at",
        Selection.Status.ORDERED: "ordered_at",
        Selection.Status.RECEIVED: "received_at",
        Selection.Status.INSTALLED: "installed_at",
    }
    timestamp_field = timestamp_fields.get(status)
    if timestamp_field:
        setattr(locked, timestamp_field, now)
    if status == Selection.Status.APPROVED:
        locked.approved_by = actor
    locked.save()
    record_workflow_event(
        "selection_advanced",
        actor=actor,
        related=locked,
        project=project,
        before_state=before,
        after_state=state_snapshot(
            locked,
            ["status", "client_choice", "approved_at", "ordered_at", "received_at", "installed_at"],
        ),
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def record_inspection_result(
    inspection,
    *,
    actor,
    status,
    result_notes="",
    corrective_action="",
    rescheduled_at=None,
    idempotency_key=None,
):
    locked = Inspection.objects.select_for_update().select_related("project").get(pk=inspection.pk)
    if not can_manage_construction(actor, locked.project):
        raise PermissionDenied("You cannot record an inspection result.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("inspection_result_recorded", locked, idempotency_key),
    ).exists():
        return locked
    valid_statuses = {value for value, _label in Inspection.Status.choices}
    if status not in valid_statuses:
        raise ValidationError("Choose a valid inspection status.")
    if rescheduled_at is not None and not isinstance(rescheduled_at, datetime):
        raise ValidationError("Rescheduled time must be a valid date and time.")
    before = state_snapshot(locked, ["status", "result_notes", "corrective_action", "rescheduled_at"])
    locked.status = status
    locked.result_notes = str(result_notes or "").strip()[:20000]
    locked.corrective_action = str(corrective_action or "").strip()[:20000]
    locked.rescheduled_at = rescheduled_at
    locked.completed_by = actor
    locked.save()
    if status == Inspection.Status.FAILED:
        Blocker.objects.get_or_create(
            project=locked.project,
            title=f"Failed inspection: {locked.inspection_type}",
            status=Blocker.Status.OPEN,
            defaults={
                "category": Blocker.Category.INSPECTION,
                "severity": Blocker.Severity.HIGH,
                "description": locked.corrective_action or locked.result_notes,
                "assigned_to": locked.project.project_manager,
                "created_by": actor,
            },
        )
    record_workflow_event(
        "inspection_result_recorded",
        actor=actor,
        related=locked,
        project=locked.project,
        before_state=before,
        after_state=state_snapshot(
            locked,
            ["status", "result_notes", "corrective_action", "rescheduled_at", "completed_by_id"],
        ),
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def resolve_warranty_item(
    item,
    *,
    actor,
    resolution,
    status=WarrantyItem.Status.RESOLVED,
    idempotency_key=None,
):
    locked = WarrantyItem.objects.select_for_update().select_related("project").get(pk=item.pk)
    if not can_manage_construction(actor, locked.project):
        raise PermissionDenied("You cannot resolve this warranty item.")
    if idempotency_key and WorkflowEvent.objects.filter(
        idempotency_key=_workflow_event_key("warranty_item_resolved", locked, idempotency_key),
    ).exists():
        return locked
    if status not in {WarrantyItem.Status.RESOLVED, WarrantyItem.Status.CLOSED}:
        raise ValidationError("Warranty items can only be resolved or closed by this command.")
    resolution = str(resolution or "").strip()
    if not resolution:
        raise ValidationError("A warranty resolution is required.")
    if len(resolution) > 20000:
        raise ValidationError("Warranty resolution is too long.")
    before = state_snapshot(locked, ["status", "resolution", "resolved_at", "resolved_by_id"])
    locked.status = status
    locked.resolution = resolution
    locked.resolved_at = timezone.now()
    locked.resolved_by = actor
    locked.save()
    record_workflow_event(
        "warranty_item_resolved",
        actor=actor,
        related=locked,
        project=locked.project,
        before_state=before,
        after_state=state_snapshot(locked, ["status", "resolution", "resolved_at", "resolved_by_id"]),
        idempotency_key=idempotency_key,
    )
    return locked


def project_financial_summary(project):
    agreement = getattr(project, "agreement", None)
    original_contract = (
        agreement.contract_value
        if agreement
        else (project.estimate.total if project.estimate_id else Decimal("0.00"))
    )
    approved_changes = (
        project.change_orders.filter(status=ChangeOrder.Status.APPROVED)
        .aggregate(total=Sum("price_impact"))["total"]
        or Decimal("0.00")
    )
    current_contract = (original_contract + approved_changes).quantize(Decimal("0.01"))
    budget_total = sum(
        (line.current_budget for line in project.budget_lines.all()),
        Decimal("0.00"),
    )
    commitments = (
        project.commitments.filter(
            status__in=[Commitment.Status.PLANNED, Commitment.Status.COMMITTED]
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    cost_total = (
        project.cost_entries.filter(is_void=False).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    payments_received = (
        project.payment_records.filter(voided_at__isnull=True).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    outstanding = (current_contract - payments_received).quantize(Decimal("0.01"))
    forecast_cost = max(cost_total, Decimal("0.00")) + max(commitments, Decimal("0.00"))
    gross_profit = (current_contract - cost_total).quantize(Decimal("0.01"))
    forecast_profit = (current_contract - forecast_cost).quantize(Decimal("0.01"))
    gross_margin = (
        ((gross_profit / current_contract) * Decimal("100")).quantize(Decimal("0.01"))
        if current_contract
        else Decimal("0.00")
    )
    next_draw = sum(
        (
            schedule.remaining_amount
            for schedule in project.payment_schedules.all()
            if schedule.status in {
                PaymentSchedule.Status.READY,
                PaymentSchedule.Status.INVOICED,
                PaymentSchedule.Status.OVERDUE,
            }
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    return {
        "original_contract": original_contract.quantize(Decimal("0.01")),
        "approved_changes": approved_changes.quantize(Decimal("0.01")),
        "current_contract": current_contract,
        "budget_total": budget_total.quantize(Decimal("0.01")),
        "committed_costs": commitments.quantize(Decimal("0.01")),
        "actual_costs": cost_total.quantize(Decimal("0.01")),
        "payments_received": payments_received.quantize(Decimal("0.01")),
        "outstanding_balance": outstanding,
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "forecast_profit": forecast_profit,
        "budget_remaining": (budget_total - cost_total - commitments).quantize(Decimal("0.01")),
        "next_draw": next_draw,
    }


def _attention_item(
    *,
    kind,
    title,
    description="",
    priority="normal",
    due_at=None,
    project=None,
    lead=None,
    source="",
):
    return {
        "kind": kind,
        "title": title,
        "description": description,
        "priority": priority,
        "due_at": due_at,
        "project": project,
        "lead": lead,
        "source": source,
    }


def attention_feed(user, *, limit=80):
    """Build the role-specific action list from authorized querysets."""
    items = []
    projects = (
        visible_projects(user)
        .select_related("client", "project_manager")
        .prefetch_related("assigned_staff")
    )
    project_ids = list(projects.values_list("pk", flat=True))
    today = timezone.localdate()
    now = timezone.now()
    for blocker in Blocker.objects.filter(
        project_id__in=project_ids,
        status=Blocker.Status.OPEN,
    ).select_related("project", "assigned_to"):
        items.append(_attention_item(
            kind="blocker",
            title=blocker.title,
            description=blocker.description or blocker.get_category_display(),
            priority="urgent" if blocker.severity == Blocker.Severity.CRITICAL else blocker.severity,
            due_at=blocker.due_date,
            project=blocker.project,
            source="Blocker",
        ))
    for item in PreconstructionItem.objects.filter(
        project_id__in=project_ids,
        required=True,
        status__in=[PreconstructionItem.Status.OPEN, PreconstructionItem.Status.BLOCKED],
    ).select_related("project", "owner"):
        due = item.due_date
        items.append(_attention_item(
            kind="readiness",
            title=f"{item.project.title}: {item.label}",
            description="Required before construction can start.",
            priority="high" if item.status == PreconstructionItem.Status.BLOCKED or (due and due < today) else "normal",
            due_at=due,
            project=item.project,
            source="Ready for construction",
        ))
    inspection_filter = Q(status=Inspection.Status.FAILED) | Q(
        status=Inspection.Status.SCHEDULED,
        scheduled_at__lte=now + timedelta(days=14),
    )
    for inspection in Inspection.objects.filter(
        project_id__in=project_ids,
    ).filter(inspection_filter).select_related("project"):
        failed = inspection.status == Inspection.Status.FAILED
        items.append(_attention_item(
            kind="inspection",
            title=f"{inspection.project.title}: {'Correct failed inspection' if failed else 'Inspection coming up'}",
            description=inspection.corrective_action or inspection.inspection_type,
            priority="urgent" if failed else "high",
            due_at=inspection.scheduled_at,
            project=inspection.project,
            source="Inspection",
        ))
    for request in MaterialRequest.objects.filter(
        project_id__in=project_ids,
        status=MaterialRequest.Status.REQUESTED,
    ).select_related("project"):
        items.append(_attention_item(
            kind="material",
            title=f"{request.project.title}: Material request",
            description=request.description,
            priority="high" if request.needed_by and request.needed_by <= today else "normal",
            due_at=request.needed_by,
            project=request.project,
            source="Field request",
        ))
    for change_order in ChangeOrder.objects.filter(
        project_id__in=project_ids,
        status=ChangeOrder.Status.SENT,
    ).select_related("project"):
        items.append(_attention_item(
            kind="change_order",
            title=f"{change_order.project.title}: CO-{change_order.number} awaiting approval",
            description=change_order.title,
            priority="high",
            due_at=change_order.sent_at,
            project=change_order.project,
            source="Change order",
        ))
    if is_owner(user):
        financial_project_ids = set(project_ids)
    elif is_manager(user):
        financial_project_ids = set(
            projects.filter(
                Q(project_manager=user) | Q(assigned_staff=user)
            ).values_list("pk", flat=True).distinct()
        )
    else:
        financial_project_ids = set()
    for schedule in PaymentSchedule.objects.filter(
        project_id__in=financial_project_ids,
        status__in=[PaymentSchedule.Status.READY, PaymentSchedule.Status.OVERDUE],
    ).select_related("project"):
        items.append(_attention_item(
            kind="draw",
            title=f"{schedule.project.title}: Progress draw ready",
            description=schedule.description,
            priority="high" if schedule.status == PaymentSchedule.Status.OVERDUE else "normal",
            due_at=schedule.due_date,
            project=schedule.project,
            source="Payment schedule",
        ))
    for selection in Selection.objects.filter(
        project_id__in=project_ids,
        status__in=[Selection.Status.SUBMITTED, Selection.Status.PENDING],
    ).select_related("project"):
        if selection.status == Selection.Status.PENDING and selection.due_date and selection.due_date > today:
            continue
        items.append(_attention_item(
            kind="decision",
            title=f"{selection.project.title}: Decision needed for {selection.item_name}",
            description=selection.category,
            priority="high" if selection.due_date and selection.due_date <= today else "normal",
            due_at=selection.due_date,
            project=selection.project,
            source="Client selection",
        ))
    for task in Task.objects.filter(
        project_id__in=project_ids,
        status__in=[Task.Status.OPEN, Task.Status.IN_PROGRESS, Task.Status.BLOCKED],
        due_date__lt=today,
    ).select_related("project", "assigned_to"):
        items.append(_attention_item(
            kind="overdue_task",
            title=f"{task.project.title}: {task.title}",
            description="Task is overdue.",
            priority="high" if task.status == Task.Status.BLOCKED else "normal",
            due_at=task.due_date,
            project=task.project,
            source="Task",
        ))

    if can_manage_sales(user):
        leads = visible_leads(user).select_related("assigned_to", "client")
        for lead in leads.filter(next_action_due__lte=today).exclude(next_action_due=None):
            items.append(_attention_item(
                kind="lead_follow_up",
                title=f"Follow up with {lead.name}",
                description=lead.next_action or "Lead needs a next action.",
                priority="high" if lead.next_action_due < today else "normal",
                due_at=lead.next_action_due,
                lead=lead,
                source="Sales pipeline",
            ))
        for estimate in Estimate.objects.filter(
            Q(lead__in=leads) | Q(client_id__in=leads.values("client_id")),
            status=Estimate.Status.DRAFT,
        ).select_related("lead", "client")[:40]:
            items.append(_attention_item(
                kind="estimate",
                title=f"Estimate #{estimate.number} needs to be sent",
                description=estimate.title,
                priority="normal",
                due_at=estimate.updated_at,
                lead=estimate.lead,
                source="Estimate",
            ))
    if is_owner(user) or is_manager(user):
        for outbox in EmailOutbox.objects.filter(
            status=EmailOutbox.Status.FAILED,
        ).select_related("project")[:20]:
            items.append(_attention_item(
                kind="email_failure",
                title="Email delivery failed",
                description=outbox.subject,
                priority="high",
                due_at=outbox.next_attempt_at,
                project=outbox.project,
                source="Email outbox",
            ))
    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    items.sort(
        key=lambda item: (
            priority_order.get(item["priority"], 2),
            item["due_at"] is None,
            item["due_at"] or now,
        )
    )
    return items[:limit]


def weekly_project_review(user, *, week_of=None):
    """Return a role-scoped action list for the weekly project review."""
    if not is_staff_user(user):
        raise PermissionDenied("Weekly project reviews are available to staff only.")
    week_of = week_of or timezone.localdate()
    projects = list(
        visible_projects(user)
        .exclude(status=Project.Status.COMPLETE)
        .select_related("client", "project_manager")
    )
    feed = attention_feed(user, limit=400)
    actions_by_project = {}
    company_actions = []
    for item in feed:
        project = item.get("project")
        safe_action = {
            "kind": item["kind"],
            "title": item["title"],
            "description": item["description"],
            "priority": item["priority"],
            "due_at": item["due_at"].isoformat() if hasattr(item["due_at"], "isoformat") else None,
            "source": item["source"],
        }
        if project is not None:
            actions_by_project.setdefault(project.pk, []).append(safe_action)
        elif item.get("lead") is not None:
            company_actions.append(safe_action)
    reviews = []
    sensitive_events = {
        "payment_recorded",
        "deposit_recorded",
        "cost_recorded",
        "budget_updated",
    }
    for project in projects:
        actions = actions_by_project.get(project.pk, [])
        events = []
        for event in WorkflowEvent.objects.filter(project=project).order_by("-created_at")[:8]:
            if not can_view_financials(user, project) and event.event_type in sensitive_events:
                continue
            events.append({
                "type": event.event_type,
                "created_at": event.created_at.isoformat(),
            })
        review = {
            "project_id": str(project.pk),
            "project_title": project.title,
            "health_status": project.health_status,
            "current_phase": project.operational_phase,
            "next_action": project.next_step,
            "what_happened": events,
            "action_items": actions,
            "behind": project.health_status in {
                Project.HealthStatus.AT_RISK,
                Project.HealthStatus.BLOCKED,
            },
            "blocking": [
                action for action in actions
                if action["kind"] in {"blocker", "inspection", "material", "decision"}
            ],
            "next_payment": None,
        }
        if can_view_financials(user, project):
            summary = project_financial_summary(project)
            review["next_payment"] = {
                "amount": str(summary["next_draw"]),
                "outstanding_balance": str(summary["outstanding_balance"]),
            }
        reviews.append(review)
    return {
        "week_of": week_of.isoformat(),
        "generated_at": timezone.now().isoformat(),
        "projects": reviews,
        "company_actions": company_actions,
    }


def company_metrics(user):
    projects = list(visible_projects(user).select_related("estimate"))
    summaries = [
        project_financial_summary(project)
        for project in projects
        if can_view_financials(user, project)
    ]
    leads = visible_leads(user) if can_manage_sales(user) else Lead.objects.none()
    pipeline_value = (
        leads.exclude(status__in=[Lead.Status.WON, Lead.Status.LOST])
        .aggregate(total=Sum("budget_amount"))["total"]
        or Decimal("0.00")
    )
    return {
        "pipeline_value": pipeline_value.quantize(Decimal("0.01")),
        "active_contract_value": sum(
            (summary["current_contract"] for summary in summaries),
            Decimal("0.00"),
        ).quantize(Decimal("0.01")),
        "revenue_collected": sum(
            (summary["payments_received"] for summary in summaries),
            Decimal("0.00"),
        ).quantize(Decimal("0.01")),
        "outstanding_receivables": sum(
            (summary["outstanding_balance"] for summary in summaries),
            Decimal("0.00"),
        ).quantize(Decimal("0.01")),
        "upcoming_draws": sum(
            (summary["next_draw"] for summary in summaries),
            Decimal("0.00"),
        ).quantize(Decimal("0.01")),
        "forecast_profit": sum(
            (summary["forecast_profit"] for summary in summaries),
            Decimal("0.00"),
        ).quantize(Decimal("0.01")),
        "active_projects": len([
            project for project in projects
            if project.status != Project.Status.COMPLETE
        ]),
    }


def queue_email(
    *,
    recipient,
    subject,
    body,
    actor=None,
    project=None,
    client=None,
    idempotency_key=None,
):
    """Create an outbox entry; dispatch is deliberately separate from writes."""
    if not recipient:
        return None
    if idempotency_key:
        existing = EmailOutbox.objects.filter(
            idempotency_key=str(idempotency_key)
        ).first()
        if existing:
            return existing
    return EmailOutbox.objects.create(
        recipient=str(recipient).strip().lower(),
        subject=str(subject).strip()[:220],
        body=str(body),
        project=project,
        client=client,
        created_by=actor,
        idempotency_key=str(idempotency_key) if idempotency_key else None,
    )
