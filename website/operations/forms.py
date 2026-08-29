from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import (
    Client,
    ClientMessage,
    EmployeeInvite,
    EmployeeProfile,
    Estimate,
    EstimateLineItem,
    Lead,
    MediaAsset,
    ProjectDocument,
    Project,
    ProjectUpdate,
    ScheduleEvent,
    Service,
    Task,
    TimeEntry,
    validate_uploaded_media,
)


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            cleaned = [single_file_clean(item, initial) for item in data]
        else:
            cleaned = [single_file_clean(data, initial)]
        for upload in cleaned:
            validate_uploaded_media(upload)
        return cleaned


class ContactLeadForm(forms.Form):
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    email = forms.EmailField()
    phone = forms.CharField(max_length=40, required=False)
    project_type = forms.CharField(max_length=120)
    location = forms.CharField(max_length=160)
    message = forms.CharField(widget=forms.Textarea)
    photos = MultipleFileField(required=False)


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["name", "email", "phone", "service", "location", "budget", "timeline", "source", "note", "status", "priority", "assigned_to"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, staff_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = staff_queryset if staff_queryset is not None else get_user_model().objects.filter(is_staff=True)


class LeadStatusForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["status"]


class LeadNoteForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}


class QuickTaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "due_date", "assigned_to", "priority"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, staff_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = staff_queryset if staff_queryset is not None else get_user_model().objects.filter(is_staff=True)


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "lead", "project", "milestone", "assigned_to", "watchers", "status", "priority", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "watchers": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *args, staff_queryset=None, project_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        staff = staff_queryset if staff_queryset is not None else get_user_model().objects.filter(is_staff=True)
        self.fields["assigned_to"].queryset = staff
        self.fields["watchers"].queryset = staff
        self.fields["project"].queryset = project_queryset if project_queryset is not None else Project.objects.all()


class LeadAssignmentForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["assigned_to"]

    def __init__(self, *args, staff_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = staff_queryset if staff_queryset is not None else get_user_model().objects.filter(is_staff=True)


class EstimateCreateForm(forms.ModelForm):
    class Meta:
        model = Estimate
        fields = ["lead", "title", "deposit_amount"]
        widgets = {"deposit_amount": forms.NumberInput(attrs={"min": "0", "step": "0.01"})}

    def __init__(self, *args, lead_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if lead_queryset is not None:
            self.fields["lead"].queryset = lead_queryset

    def clean(self):
        cleaned = super().clean()
        lead = cleaned.get("lead")
        if lead and not lead.client_id:
            raise ValidationError("Convert this lead into a client before creating an estimate.")
        return cleaned


class EstimateForm(forms.ModelForm):
    class Meta:
        model = Estimate
        fields = ["title", "status", "deposit_amount", "notes"]
        widgets = {
            "deposit_amount": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_deposit_amount(self):
        value = self.cleaned_data["deposit_amount"] or Decimal("0.00")
        if value < 0:
            raise ValidationError("Deposit amount cannot be negative.")
        return value


class EstimateLineItemForm(forms.ModelForm):
    class Meta:
        model = EstimateLineItem
        fields = ["description", "quantity", "unit_price", "sort_order"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "unit_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "sort_order": forms.HiddenInput(),
        }

    def clean(self):
        cleaned = super().clean()
        if not self.has_changed():
            return cleaned
        if not cleaned.get("description") and not self.cleaned_data.get("DELETE"):
            raise ValidationError("Add a description for each line item.")
        return cleaned


class BaseEstimateLineItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        remaining = [
            form
            for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE")
            and (form.instance.pk or form.has_changed())
        ]
        if not remaining:
            raise ValidationError("An estimate needs at least one line item.")


EstimateLineItemFormSet = inlineformset_factory(
    Estimate,
    EstimateLineItem,
    form=EstimateLineItemForm,
    formset=BaseEstimateLineItemFormSet,
    extra=1,
    can_delete=True,
    max_num=50,
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["title", "client", "lead", "assigned_staff", "location", "project_type", "status", "next_step", "summary", "is_published", "start_date", "target_date"]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "assigned_staff": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *args, staff_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_staff"].queryset = staff_queryset if staff_queryset is not None else get_user_model().objects.filter(is_staff=True)

    def clean(self):
        cleaned = super().clean()
        lead = cleaned.get("lead")
        if lead and self.instance._state.adding and not lead.estimates.filter(status=Estimate.Status.ACCEPTED).exists():
            raise ValidationError("Lead-derived projects require an accepted estimate.")
        return cleaned


class ProjectUpdateForm(forms.ModelForm):
    class Meta:
        model = ProjectUpdate
        fields = ["title", "body", "visibility"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}


class MediaEditForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ["caption", "visibility", "project"]
        widgets = {"caption": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, project_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = project_queryset if project_queryset is not None else Project.objects.all()


class MediaUploadForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none())
    visibility = forms.ChoiceField(choices=MediaAsset.Visibility.choices)
    files = MultipleFileField(required=True)

    def __init__(self, *args, project_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = project_queryset if project_queryset is not None else Project.objects.none()


class ContentStudioForm(forms.Form):
    headline = forms.CharField(max_length=180)
    subheadline = forms.CharField(widget=forms.Textarea, max_length=1000)
    featured_title = forms.CharField(max_length=180)
    featured_body = forms.CharField(widget=forms.Textarea, max_length=1200)
    google_review_url = forms.URLField(required=False, assume_scheme="https", max_length=500)

    def __init__(self, *args, services=None, process_steps=None, **kwargs):
        super().__init__(*args, **kwargs)
        for service in services or Service.objects.filter(is_active=True):
            self.fields[f"service_{service.slug}_title"] = forms.CharField(max_length=120)
            self.fields[f"service_{service.slug}_copy"] = forms.CharField(widget=forms.Textarea, max_length=500)
        for step in process_steps or []:
            self.fields[f"step_{step.key}"] = forms.CharField(max_length=120)


class ClientMessageForm(forms.ModelForm):
    class Meta:
        model = ClientMessage
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4, "placeholder": "How can the team help?"})}


class StaffMessageForm(forms.ModelForm):
    class Meta:
        model = ClientMessage
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Reply to the client..."})}


class EmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        fields = ["job_title", "phone", "is_active"]

    def __init__(self, *args, allow_status=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not allow_status:
            self.fields.pop("is_active", None)


class EmployeeInviteForm(forms.ModelForm):
    class Meta:
        model = EmployeeInvite
        fields = ["email", "first_name", "last_name", "group"]

    def __init__(self, *args, group_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = group_queryset if group_queryset is not None else Group.objects.filter(name__in=["Manager", "Office", "Field"])


class ScheduleEventForm(forms.ModelForm):
    class Meta:
        model = ScheduleEvent
        fields = ["title", "assignees", "project", "task", "start_at", "end_at", "location", "notes"]
        widgets = {
            "assignees": forms.SelectMultiple(attrs={"size": 4}),
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, staff_queryset=None, project_queryset=None, task_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignees"].queryset = staff_queryset if staff_queryset is not None else get_user_model().objects.filter(is_staff=True)
        self.fields["project"].queryset = project_queryset if project_queryset is not None else Project.objects.all()
        self.fields["task"].queryset = task_queryset if task_queryset is not None else Task.objects.all()


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ["project", "task", "clock_in", "clock_out", "note"]
        widgets = {
            "clock_in": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "clock_out": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, project_queryset=None, task_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = project_queryset if project_queryset is not None else Project.objects.all()
        self.fields["task"].queryset = task_queryset if task_queryset is not None else Task.objects.all()


class ProjectDocumentForm(forms.ModelForm):
    class Meta:
        model = ProjectDocument
        fields = ["project", "title", "category", "description", "file", "visibility"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, project_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = project_queryset if project_queryset is not None else Project.objects.all()


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "company", "email", "phone"]


class EmployeeInviteAcceptForm(forms.Form):
    username = forms.CharField(max_length=150, required=False)
    first_name = forms.CharField(max_length=80, required=False)
    last_name = forms.CharField(max_length=80, required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, purpose=EmployeeInvite.Purpose.ONBOARDING, **kwargs):
        super().__init__(*args, **kwargs)
        self.purpose = purpose
        if purpose == EmployeeInvite.Purpose.PASSWORD_RESET:
            self.fields.pop("username")
            self.fields.pop("first_name")
            self.fields.pop("last_name")
        else:
            self.fields["username"].required = True
            self.fields["first_name"].required = True
            self.fields["last_name"].required = True

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if username and get_user_model().objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already in use.")
        return username

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") and cleaned.get("password1") != cleaned.get("password2"):
            raise ValidationError("Passwords do not match.")
        return cleaned


class ClientInviteAcceptForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already in use.")
        return username

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") and cleaned.get("password1") != cleaned.get("password2"):
            raise ValidationError("Passwords do not match.")
        return cleaned
