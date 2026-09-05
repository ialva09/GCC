from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client as HttpClient
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .construction_services import (
    approve_change_order,
    advance_selection,
    create_lead,
    create_change_order,
    create_project_from_estimate,
    project_financial_summary,
    record_deposit,
    record_payment,
    send_estimate,
    submit_problem_report,
)
from .models import (
    Agreement,
    BudgetLine,
    ChangeOrder,
    Client,
    CloseoutItem,
    Commitment,
    CostEntry,
    Estimate,
    EstimateLineItem,
    Inspection,
    Lead,
    PaymentRecord,
    PaymentSchedule,
    Permit,
    PreconstructionItem,
    ProblemReport,
    Project,
    Selection,
    Subcontractor,
    SubcontractorAssignment,
    WorkflowEvent,
)


User = get_user_model()


class ConstructionOperatingSystemTests(TestCase):
    def setUp(self):
        self.http = HttpClient()
        self.owner = User.objects.create_user(
            username="owner",
            password="owner-password-123",
            email="owner@example.com",
            is_staff=True,
            is_superuser=True,
        )
        self.manager = User.objects.create_user(
            username="manager",
            password="manager-password-123",
            email="manager@example.com",
            is_staff=True,
        )
        self.manager.groups.add(Group.objects.get_or_create(name="Manager")[0])
        self.field = User.objects.create_user(
            username="field",
            password="field-password-123",
            email="field@example.com",
            is_staff=True,
        )
        self.field.groups.add(Group.objects.get_or_create(name="Field")[0])
        self.client_user = User.objects.create_user(
            username="homeowner",
            password="client-password-123",
            email="homeowner@example.com",
        )
        self.other_field = User.objects.create_user(
            username="other-field",
            password="other-password-123",
            email="other-field@example.com",
            is_staff=True,
        )
        self.other_field.groups.add(Group.objects.get_or_create(name="Field")[0])
        self.client_record = Client.objects.create(
            name="Homeowner",
            email=self.client_user.email,
            user=self.client_user,
        )
        self.lead = Lead.objects.create(
            client=self.client_record,
            assigned_to=self.manager,
            name="Homeowner",
            email=self.client_user.email,
            service="Kitchen renovation",
            location="Beachmont",
            budget_amount=Decimal("150000.00"),
        )
        self.estimate = Estimate.objects.create(
            client=self.client_record,
            lead=self.lead,
            title="Beachmont kitchen renovation",
            status=Estimate.Status.ACCEPTED,
            deposit_amount=Decimal("30000.00"),
        )
        EstimateLineItem.objects.create(
            estimate=self.estimate,
            description="Construction scope",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100000.00"),
            estimated_cost=Decimal("65000.00"),
        )

    def _create_project(self):
        project, created = create_project_from_estimate(self.estimate, actor=self.owner)
        self.assertTrue(created)
        project.assigned_staff.add(self.manager, self.field)
        return project

    def test_estimate_conversion_is_idempotent_and_seeds_operational_records(self):
        project = self._create_project()
        same_project, created = create_project_from_estimate(self.estimate, actor=self.owner)

        self.assertFalse(created)
        self.assertEqual(project.pk, same_project.pk)
        self.assertEqual(Project.objects.filter(estimate=self.estimate).count(), 1)
        self.assertEqual(PreconstructionItem.objects.filter(project=project).count(), 9)
        self.assertEqual(PaymentSchedule.objects.filter(project=project).count(), 1)
        self.assertTrue(WorkflowEvent.objects.filter(event_type="project_created_from_estimate").exists())
        self.assertFalse(project.is_published)

    def test_role_and_object_scope_hides_unassigned_project(self):
        project = self._create_project()
        self.http.force_login(self.other_field)

        response = self.http.get(reverse("operations-api:project-summary", kwargs={"pk": project.pk}))

        self.assertEqual(response.status_code, 404)

    def test_office_and_sales_scopes_do_not_cross_assignment_boundaries(self):
        project = self._create_project()
        office = User.objects.create_user(
            username="office",
            password="office-password-123",
            email="office@example.com",
            is_staff=True,
        )
        office.groups.add(Group.objects.get_or_create(name="Office")[0])
        self.http.force_login(office)
        project_response = self.http.get(
            reverse("operations-api:project-summary", kwargs={"pk": project.pk})
        )
        self.assertEqual(project_response.status_code, 404)

        sales = User.objects.create_user(
            username="sales",
            password="sales-password-123",
            email="sales@example.com",
            is_staff=True,
        )
        sales.groups.add(Group.objects.get_or_create(name="Sales")[0])
        self.http.force_login(sales)
        self.assertEqual(self.http.get(reverse("operations-api:estimates")).json()["results"], [])
        with self.assertRaises(PermissionDenied):
            send_estimate(self.estimate, actor=sales)

    def test_client_can_view_project_without_internal_financials(self):
        project = self._create_project()
        self.http.force_login(self.client_user)

        response = self.http.get(reverse("operations-api:project-summary", kwargs={"pk": project.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("financials", response.json()["project"])
        payments = self.http.get(reverse("operations-api:payments", kwargs={"pk": project.pk}))
        self.assertEqual(payments.status_code, 403)

    def test_client_project_serializer_hides_internal_notes_and_field_hides_co_price(self):
        project = self._create_project()
        project.health_note = "Internal budget risk."
        project.save(update_fields=["health_note", "updated_at"])
        readiness = project.readiness_items.first()
        readiness.notes = "Internal readiness note."
        readiness.save(update_fields=["notes", "updated_at"])
        Selection.objects.create(
            project=project,
            category="cabinets",
            item_name="Walnut cabinets",
            description="Internal vendor quote details",
            vendor="Private supplier",
            status=Selection.Status.SUBMITTED,
        )
        Inspection.objects.create(
            project=project,
            inspection_type="Rough framing",
            status=Inspection.Status.FAILED,
            result_notes="Internal inspector notes",
            corrective_action="Internal correction plan",
        )
        change_order, created = create_change_order(
            project,
            actor=self.owner,
            title="Add pantry wall",
            description="Frame and finish the pantry wall.",
            price_impact=Decimal("2500.00"),
            status=ChangeOrder.Status.SENT,
            idempotency_key="co-serializer-1",
        )
        self.assertTrue(created)

        self.http.force_login(self.client_user)
        client_payload = self.http.get(
            reverse("operations-api:project-summary", kwargs={"pk": project.pk})
        ).json()["project"]
        self.assertEqual(client_payload["health_note"], "")
        self.assertEqual(client_payload["readiness"][0]["notes"], "")
        self.assertEqual(client_payload["selections"][0]["vendor"], "")
        self.assertEqual(client_payload["inspections"][0]["corrective_action"], "")
        self.assertEqual(client_payload["change_orders"][0]["price_impact"], "2500.00")

        self.http.force_login(self.field)
        field_payload = self.http.get(
            reverse("operations-api:change-orders", kwargs={"pk": project.pk})
        ).json()["results"]
        self.assertEqual(field_payload[0]["price_impact"], None)
        self.assertEqual(change_order.status, ChangeOrder.Status.SENT)

    def test_field_cannot_approve_or_advance_client_selections(self):
        project = self._create_project()
        selection = Selection.objects.create(
            project=project,
            category="windows",
            item_name="Windows",
            status=Selection.Status.SUBMITTED,
        )
        with self.assertRaises(PermissionDenied):
            advance_selection(
                selection,
                actor=self.field,
                status=Selection.Status.APPROVED,
                idempotency_key="selection-field-1",
            )
        selection.refresh_from_db()
        self.assertEqual(selection.status, Selection.Status.SUBMITTED)

    def test_change_order_approval_updates_contract_and_cannot_be_edited(self):
        project = self._create_project()
        change_order, created = create_change_order(
            project,
            actor=self.owner,
            title="Add pantry wall",
            description="Frame and finish the pantry wall.",
            price_impact=Decimal("2500.00"),
            status=ChangeOrder.Status.SENT,
            idempotency_key="co-beachmont-1",
        )
        self.assertTrue(created)
        self.http.force_login(self.client_user)

        response = self.http.post(
            reverse("operations-api:change-order-approve", kwargs={"pk": change_order.pk}),
            data="{}",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="approve-beachmont-1",
        )

        self.assertEqual(response.status_code, 200)
        change_order.refresh_from_db()
        self.assertEqual(change_order.status, ChangeOrder.Status.APPROVED)
        self.assertEqual(project_financial_summary(project)["current_contract"], Decimal("102500.00"))
        change_order.title = "Changed after approval"
        with self.assertRaises(ValidationError):
            change_order.full_clean()

    def test_payment_retry_is_idempotent_and_decimal_safe(self):
        project = self._create_project()
        self.http.force_login(self.owner)
        schedule = project.payment_schedules.get(sequence=1)

        first, created = record_payment(
            project,
            actor=self.owner,
            amount=Decimal("10000.005"),
            schedule=schedule,
            idempotency_key="payment-beachmont-1",
        )
        second, retried = record_payment(
            project,
            actor=self.owner,
            amount=Decimal("999.99"),
            schedule=schedule,
            idempotency_key="payment-beachmont-1",
        )

        self.assertTrue(created)
        self.assertFalse(retried)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentRecord.objects.filter(project=project).count(), 1)
        self.assertEqual(project_financial_summary(project)["payments_received"], Decimal("10000.01"))

    def test_command_center_and_project_operations_are_additive_views(self):
        project = self._create_project()
        self.http.force_login(self.owner)

        dashboard = self.http.get(reverse("operations:dashboard"))
        command_center = self.http.get(reverse("operations:command-center"))
        legacy_overview = self.http.get(
            reverse("operations:dashboard-section", kwargs={"section": "overview"})
        )
        project_view = self.http.get(reverse("operations:project-operations", kwargs={"pk": project.pk}))

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "What needs my attention today?")
        self.assertRedirects(command_center, reverse("operations:dashboard"))
        self.assertEqual(legacy_overview.status_code, 200)
        self.assertContains(legacy_overview, "Here’s the shape of the work today.")
        self.assertEqual(project_view.status_code, 200)
        self.assertContains(project_view, "Ready for construction")

    @override_settings(
        GCC_OWNER_COMMAND_CENTER_ENABLED=False,
        GCC_OPERATING_SYSTEM_ENABLED=True,
    )
    def test_dashboard_feature_flag_falls_back_to_existing_overview(self):
        self.http.force_login(self.owner)

        response = self.http.get(reverse("operations:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Here’s the shape of the work today.")
        self.assertNotContains(response, "What needs my attention today?")

    def test_api_lead_creation_and_conversion_are_idempotent(self):
        self.http.force_login(self.owner)
        lead_response = self.http.post(
            reverse("operations-api:leads"),
            data='{"name":"New Homeowner","email":"new@example.com","service":"Addition","location":"Irvine","budget_amount":"210000.00"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="lead-create-1",
        )
        self.assertEqual(lead_response.status_code, 201)
        lead_id = lead_response.json()["lead"]["id"]
        retry = self.http.post(
            reverse("operations-api:leads"),
            data='{"name":"Different Payload","email":"different@example.com","service":"Addition","location":"Irvine"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="lead-create-1",
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["lead"]["id"], lead_id)
        convert_url = reverse("operations-api:lead-convert-client", kwargs={"pk": lead_id})
        converted = self.http.post(
            convert_url,
            data="{}",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="lead-convert-1",
        )
        self.assertEqual(converted.status_code, 200)
        converted_retry = self.http.post(
            convert_url,
            data="{}",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="lead-convert-1",
        )
        self.assertEqual(converted_retry.status_code, 200)
        self.assertEqual(converted_retry.json()["client"]["id"], converted.json()["client"]["id"])
        self.assertEqual(Client.objects.filter(email="new@example.com").count(), 1)

    def test_deposit_and_approved_records_are_immutable(self):
        project = self._create_project()
        payment, created = record_deposit(
            project,
            actor=self.owner,
            amount=Decimal("30000.00"),
            idempotency_key="deposit-beachmont-1",
        )
        self.assertTrue(created)
        self.assertEqual(payment.schedule.sequence, 1)
        payment.created_by = self.manager
        with self.assertRaises(ValidationError):
            payment.save()
        agreement = Agreement.objects.get(project=project)
        agreement.status = Agreement.Status.ACCEPTED
        agreement.locked_at = agreement.created_at
        agreement.save()
        agreement.status = Agreement.Status.ISSUED
        with self.assertRaises(ValidationError):
            agreement.save()
        event = WorkflowEvent.objects.order_by("created_at").first()
        event.event_type = "tampered"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()

    def test_cost_and_commitment_history_is_revision_or_void_only(self):
        project = self._create_project()
        budget_line = BudgetLine.objects.create(
            project=project,
            description="Materials",
            category=BudgetLine.Category.MATERIALS,
        )
        cost = CostEntry.objects.create(
            project=project,
            budget_line=budget_line,
            description="Tile deposit",
            amount=Decimal("125.00"),
            created_by=self.owner,
        )
        cost.amount = Decimal("250.00")
        with self.assertRaises(ValidationError):
            cost.save()
        cost.refresh_from_db()
        cost.is_void = True
        cost.voided_at = timezone.now()
        cost.voided_by = self.owner
        cost.save()
        cost.description = "Tampered cost"
        with self.assertRaises(ValidationError):
            cost.save()
        commitment = Commitment.objects.create(
            project=project,
            budget_line=budget_line,
            description="Cabinet subcontract",
            amount=Decimal("5000.00"),
            created_by=self.owner,
        )
        commitment.amount = Decimal("6000.00")
        with self.assertRaises(ValidationError):
            commitment.save()
        commitment.refresh_from_db()
        commitment.status = Commitment.Status.COMMITTED
        commitment.save()
        commitment.status = Commitment.Status.PLANNED
        with self.assertRaises(ValidationError):
            commitment.save()
        with self.assertRaises(ValidationError):
            commitment.delete()

    def test_cost_api_is_idempotent_and_voidable(self):
        project = self._create_project()
        self.http.force_login(self.owner)
        costs_url = reverse("operations-api:project-costs", kwargs={"pk": project.pk})
        created = self.http.post(
            costs_url,
            data='{"description":"Tile deposit","amount":"125.00","source":"invoice"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="cost-api-1",
        )
        self.assertEqual(created.status_code, 201)
        cost_id = created.json()["cost"]["id"]
        retry = self.http.post(
            costs_url,
            data='{"description":"Different text","amount":"999.00"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="cost-api-1",
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["cost"]["id"], cost_id)
        voided = self.http.post(
            reverse("operations-api:cost-void", kwargs={"pk": cost_id}),
            data="{}",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="cost-void-1",
        )
        self.assertEqual(voided.status_code, 200)
        self.assertTrue(voided.json()["cost"]["is_void"])
        self.http.force_login(self.field)
        hidden = self.http.get(costs_url)
        self.assertEqual(hidden.status_code, 403)

    def test_permits_problems_and_closeout_are_scoped_and_idempotent(self):
        project = self._create_project()
        permit_url = reverse("operations-api:project-permits", kwargs={"pk": project.pk})
        self.http.force_login(self.owner)
        missing_key = self.http.post(
            permit_url,
            data='{"permit_type":"Building"}',
            content_type="application/json",
        )
        self.assertEqual(missing_key.status_code, 400)
        permit_response = self.http.post(
            permit_url,
            data='{"permit_type":"Building","status":"submitted"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="permit-beachmont-1",
        )
        self.assertEqual(permit_response.status_code, 201)
        retry = self.http.post(
            permit_url,
            data='{"permit_type":"Changed"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="permit-beachmont-1",
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(Permit.objects.filter(project=project).count(), 1)
        self.http.force_login(self.field)
        problem_url = reverse("operations-api:project-problems", kwargs={"pk": project.pk})
        problem_response = self.http.post(
            problem_url,
            data='{"title":"Missing material","description":"The specified tile has not arrived.","severity":"high"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="12345678-1234-4234-8234-123456789012",
        )
        self.assertEqual(problem_response.status_code, 201)
        self.assertEqual(ProblemReport.objects.filter(project=project).count(), 1)
        closeout_response = self.http.get(
            reverse("operations-api:project-closeout", kwargs={"pk": project.pk})
        )
        self.assertEqual(closeout_response.status_code, 200)
        self.assertEqual(len(closeout_response.json()["results"]), 6)

    def test_subcontractor_sees_only_assigned_work(self):
        project = self._create_project()
        sub_user = User.objects.create_user(
            username="subcontractor",
            password="sub-password-123",
            email="sub@example.com",
        )
        subcontractor = Subcontractor.objects.create(
            company="Trusted Trade",
            contact_name="Trade Contact",
            email="sub@example.com",
            portal_user=sub_user,
        )
        assignment = SubcontractorAssignment.objects.create(
            project=project,
            subcontractor=subcontractor,
            work_package="Cabinet installation",
            scope="Install cabinets per approved plans.",
            status=SubcontractorAssignment.Status.ASSIGNED,
        )
        self.http.force_login(sub_user)
        response = self.http.get(
            reverse("operations-api:project-summary", kwargs={"pk": project.pk})
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["project"]
        self.assertNotIn("financials", payload)
        self.assertEqual(payload["assignments"][0]["id"], str(assignment.pk))
        self.assertEqual(payload["readiness"], [])
        self.assertEqual(payload["selections"], [])

    @override_settings(GCC_AI_ENABLED=True)
    def test_ask_grand_coast_is_read_only_and_permission_filtered(self):
        project = self._create_project()
        self.http.force_login(self.owner)
        response = self.http.post(
            reverse("operations-api:ask-grand-coast"),
            data='{"question":"What needs my attention today?"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["read_only"])
        self.assertEqual(response.json()["available_actions"], [])
        self.http.force_login(self.client_user)
        restricted = self.http.post(
            reverse("operations-api:ask-grand-coast"),
            data='{"question":"What is our cash flow?"}',
            content_type="application/json",
        )
        self.assertEqual(restricted.status_code, 200)
        self.assertEqual(restricted.json()["kind"], "restricted")
