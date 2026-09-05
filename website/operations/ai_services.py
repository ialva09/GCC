"""Read-only, permission-filtered command-bar queries.

This module is intentionally deterministic until Grand Coast configures an
approved model provider. It exposes a small allowlist of intents and returns
only data already visible to the requesting actor. It never executes a
business command or sends an external message.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError

from .construction_policies import (
    can_access_operating_system,
    can_view_financials,
    feature_enabled,
    is_client,
    is_subcontractor,
    visible_projects,
)
from .construction_services import attention_feed, company_metrics, weekly_project_review
from .models import Blocker, ChangeOrder, Inspection, Project, Selection


MAX_QUESTION_LENGTH = 2000
FINANCIAL_INTENTS = ("payment", "collect", "cash flow", "cashflow", "receivable", "budget", "margin", "profit")


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    return value


def _project_card(project):
    return {
        "id": str(project.pk),
        "title": project.title,
        "phase": project.operational_phase,
        "health": project.health_status,
        "next_action": project.next_step,
        "progress_percent": project.progress_percent,
        "target_date": project.target_date.isoformat() if project.target_date else None,
    }


def _attention_card(user, item):
    project = item.get("project")
    if item["kind"] in {"draw", "email_failure"} and (
        project is None or not can_view_financials(user, project)
    ):
        return None
    return {
        "kind": item["kind"],
        "title": item["title"],
        "description": item["description"],
        "priority": item["priority"],
        "due_at": item["due_at"].isoformat() if hasattr(item["due_at"], "isoformat") else None,
        "project_id": str(project.pk) if project else None,
        "source": item["source"],
    }


def _read_only_result(kind, answer, data=None):
    return {
        "kind": kind,
        "answer": answer,
        "data": data if data is not None else {},
        "read_only": True,
        "human_approval_required": False,
        "available_actions": [],
    }


def ask_grand_coast(user, question):
    if not feature_enabled("ai"):
        raise PermissionDenied("Ask Grand Coast is not enabled.")
    if not can_access_operating_system(user):
        raise PermissionDenied("Ask Grand Coast access denied.")
    question = str(question or "").strip()
    if not question:
        raise ValidationError("Ask a Grand Coast question.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise ValidationError("Questions must be 2,000 characters or fewer.")
    normalized = " ".join(question.casefold().split())
    projects = list(
        visible_projects(user)
        .exclude(status=Project.Status.COMPLETE)
        .select_related("client", "project_manager")
    )

    if any(term in normalized for term in ("attention", "handle today", "handle tomorrow", "needs my")):
        cards = [
            card
            for item in attention_feed(user, limit=120)
            if (card := _attention_card(user, item)) is not None
        ]
        return _read_only_result(
            "attention",
            f"I found {len(cards)} action item{'s' if len(cards) != 1 else ''} in your authorized workspace.",
            {"items": cards},
        )

    if "weekly" in normalized or "monday project review" in normalized:
        if is_client(user) or is_subcontractor(user):
            return _read_only_result(
                "unsupported",
                "Weekly company reviews are available to Grand Coast staff.",
                {"supported_questions": ["What is happening on my project?", "What is next?"]},
            )
        review = weekly_project_review(user)
        return _read_only_result(
            "weekly_review",
            f"Here is the action list for {review['week_of']}.",
            review,
        )

    if "cash" in normalized or any(term in normalized for term in FINANCIAL_INTENTS):
        financial_projects = [project for project in projects if can_view_financials(user, project)]
        if not financial_projects:
            return _read_only_result(
                "restricted",
                "Financial information is not available for your role or project assignments.",
            )
        metrics = {
            key: _json_value(value)
            for key, value in company_metrics(user).items()
        }
        return _read_only_result(
            "financials",
            "Here is the financial picture for the projects you are authorized to see.",
            metrics,
        )

    if "inspection" in normalized:
        inspections = Inspection.objects.filter(
            project__in=projects,
            status=Inspection.Status.SCHEDULED,
        ).select_related("project").order_by("scheduled_at")[:100]
        return _read_only_result(
            "inspections",
            f"There are {len(inspections)} scheduled inspections in your authorized projects.",
            {
                "inspections": [
                    {
                        "id": str(item.pk),
                        "project_id": str(item.project_id),
                        "project_title": item.project.title,
                        "inspection_type": item.inspection_type,
                        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
                    }
                    for item in inspections
                ]
            },
        )

    if "change order" in normalized:
        change_orders = ChangeOrder.objects.filter(
            project__in=projects,
        )
        if is_client(user):
            change_orders = change_orders.exclude(status=ChangeOrder.Status.DRAFT)
        if is_subcontractor(user):
            change_orders = change_orders.none()
        count = change_orders.count()
        return _read_only_result(
            "change_orders",
            f"I found {count} authorized change order{'s' if count != 1 else ''}.",
            {
                "change_orders": [
                    {
                        "id": str(item.pk),
                        "project_id": str(item.project_id),
                        "project_title": item.project.title,
                        "number": item.number,
                        "title": item.title,
                        "status": item.status,
                        "schedule_impact_days": item.schedule_impact_days,
                        "price_impact": (
                            str(item.price_impact)
                            if can_view_financials(user, item.project)
                            else None
                        ),
                    }
                    for item in change_orders.select_related("project")[:100]
                ]
            },
        )

    if "decision" in normalized or ("client" in normalized and "waiting" in normalized):
        selections = Selection.objects.filter(
            project__in=projects,
            status__in=[Selection.Status.PENDING, Selection.Status.SUBMITTED],
        ).select_related("project")[:100]
        return _read_only_result(
            "decisions",
            f"I found {len(selections)} project decision{'s' if len(selections) != 1 else ''} needing attention.",
            {
                "selections": [
                    {
                        "id": str(item.pk),
                        "project_id": str(item.project_id),
                        "project_title": item.project.title,
                        "category": item.category,
                        "item_name": item.item_name,
                        "status": item.status,
                        "due_date": item.due_date.isoformat() if item.due_date else None,
                    }
                    for item in selections
                ]
            },
        )

    if "holding up" in normalized or "blocker" in normalized:
        matches = [
            project for project in projects
            if all(token in project.title.casefold() for token in normalized.split() if len(token) > 3)
        ]
        if len(matches) != 1:
            matches = [
                project for project in projects
                if any(token in project.title.casefold() for token in normalized.split() if len(token) > 3)
            ]
        if len(matches) != 1:
            return _read_only_result(
                "projects",
                "I need an authorized project name to identify the blocker.",
                {"projects": [_project_card(project) for project in projects]},
            )
        project = matches[0]
        blockers = project.blockers.filter(status=Blocker.Status.OPEN)
        if is_client(user):
            blockers = blockers.filter(category=Blocker.Category.CLIENT_DECISION)
        elif is_subcontractor(user):
            blockers = blockers.none()
        count = blockers.count()
        return _read_only_result(
            "blockers",
            f"{project.title} has {count} authorized open blocker{'s' if count != 1 else ''}.",
            {
                "project": _project_card(project),
                "blockers": [
                    {
                        "id": str(item.pk),
                        "title": item.title,
                        "description": item.description,
                        "category": item.category,
                        "severity": item.severity,
                        "due_date": item.due_date.isoformat() if item.due_date else None,
                    }
                    for item in blockers[:100]
                ],
            },
        )

    if "project" in normalized or "projects" in normalized or "update me" in normalized:
        return _read_only_result(
            "projects",
            f"I found {len(projects)} active authorized project{'s' if len(projects) != 1 else ''}.",
            {"projects": [_project_card(project) for project in projects]},
        )

    return _read_only_result(
        "help",
        "I can answer authorized read-only questions about attention, projects, blockers, inspections, decisions, change orders, payments, and weekly reviews.",
        {
            "supported_questions": [
                "What needs my attention today?",
                "Give me an update on every active project.",
                "What's holding up [project name]?",
                "Which inspections are coming up?",
                "Which clients need decisions?",
                "What payments should we collect this week?",
                "Create my Monday project review.",
            ]
        },
    )
