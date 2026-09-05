from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Blocker,
    ChangeOrder,
    DailyReport,
    Inspection,
    MaterialRequest,
    PaymentRecord,
    PaymentSchedule,
    PreconstructionItem,
    ProblemReport,
    Selection,
    SiteVisit,
)


class SiteVisitForm(forms.ModelForm):
    class Meta:
        model = SiteVisit
        fields = [
            "assigned_to",
            "scheduled_at",
            "address",
            "scope",
            "measurements",
            "client_requests",
            "existing_conditions",
            "potential_additional_work",
            "notes",
        ]
        widgets = {
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "scope": forms.Textarea(attrs={"rows": 4}),
            "measurements": forms.Textarea(attrs={"rows": 3}),
            "client_requests": forms.Textarea(attrs={"rows": 3}),
            "existing_conditions": forms.Textarea(attrs={"rows": 3}),
            "potential_additional_work": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class BlockerForm(forms.ModelForm):
    class Meta:
        model = Blocker
        fields = ["title", "description", "category", "severity", "assigned_to", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class PreconstructionItemForm(forms.ModelForm):
    class Meta:
        model = PreconstructionItem
        fields = ["owner", "due_date", "notes"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class ChangeOrderForm(forms.ModelForm):
    class Meta:
        model = ChangeOrder
        fields = ["title", "description", "price_impact", "schedule_impact_days"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "price_impact": forms.NumberInput(attrs={"step": "0.01"}),
            "schedule_impact_days": forms.NumberInput(attrs={"min": "0", "step": "1"}),
        }

    def clean_price_impact(self):
        value = self.cleaned_data["price_impact"]
        if abs(value) > Decimal("9999999999.99"):
            raise ValidationError("Price impact is outside the supported range.")
        return value

    def clean_schedule_impact_days(self):
        value = self.cleaned_data["schedule_impact_days"]
        if value < 0:
            raise ValidationError("Schedule impact cannot be negative.")
        return value


class SelectionForm(forms.ModelForm):
    class Meta:
        model = Selection
        fields = [
            "category",
            "item_name",
            "description",
            "vendor",
            "allowance",
            "client_choice",
            "due_date",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "client_choice": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "allowance": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }


class PaymentRecordForm(forms.ModelForm):
    class Meta:
        model = PaymentRecord
        fields = ["schedule", "amount", "received_on", "method", "reference", "notes"]
        widgets = {
            "received_on": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, schedule_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if schedule_queryset is not None:
            self.fields["schedule"].queryset = schedule_queryset

    def clean_amount(self):
        value = self.cleaned_data["amount"]
        if value <= 0:
            raise ValidationError("Payment amount must be greater than zero.")
        return value


class DailyReportForm(forms.ModelForm):
    class Meta:
        model = DailyReport
        fields = [
            "report_date",
            "summary",
            "work_completed",
            "labor_count",
            "hours_worked",
            "weather",
            "equipment",
            "notes",
        ]
        widgets = {
            "report_date": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 4}),
            "work_completed": forms.Textarea(attrs={"rows": 4}),
            "equipment": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "hours_worked": forms.NumberInput(attrs={"min": "0", "step": "0.25"}),
        }


class MaterialRequestForm(forms.ModelForm):
    class Meta:
        model = MaterialRequest
        fields = ["description", "quantity", "needed_by", "vendor", "notes"]
        widgets = {
            "needed_by": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class ProblemReportForm(forms.ModelForm):
    class Meta:
        model = ProblemReport
        fields = ["title", "description", "severity"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class InspectionResultForm(forms.ModelForm):
    class Meta:
        model = Inspection
        fields = ["status", "result_notes", "corrective_action", "rescheduled_at"]
        widgets = {
            "result_notes": forms.Textarea(attrs={"rows": 3}),
            "corrective_action": forms.Textarea(attrs={"rows": 3}),
            "rescheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
