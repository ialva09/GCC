from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import get_valid_filename

from .storage import ContactSubmissionStorage


MAX_UPLOAD_SIZE = 50 * 1024 * 1024
CALENDAR_TIME_ZONE = ZoneInfo('America/Los_Angeles')
CONTACT_MAX_FILES = 8
CONTACT_MAX_TOTAL_SIZE = 100 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".heic",
    ".mp4",
    ".mov",
    ".webm",
}


def validate_uploaded_media(upload):
    if not upload:
        return
    if upload.size > MAX_UPLOAD_SIZE:
        raise ValidationError("Files must be 50 MB or smaller.")
    name = upload.name.lower()
    if not any(name.endswith(extension) for extension in ALLOWED_UPLOAD_EXTENSIONS):
        raise ValidationError("Upload a JPG, PNG, WEBP, GIF, HEIC, MP4, MOV, or WEBM file.")


ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
}
ALLOWED_CONTACT_UPLOAD_EXTENSIONS = ALLOWED_UPLOAD_EXTENSIONS | ALLOWED_DOCUMENT_EXTENSIONS
CONTACT_UPLOAD_ACCEPT = ",".join(sorted(ALLOWED_CONTACT_UPLOAD_EXTENSIONS))


def sanitize_uploaded_name(name):
    filename = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    return get_valid_filename(filename) or "uploaded-file"


def _read_upload_header(upload, max_bytes=512):
    try:
        position = upload.tell()
    except (AttributeError, OSError):
        position = 0
    try:
        upload.seek(0)
        return upload.read(max_bytes) or b""
    except (AttributeError, OSError):
        return b""
    finally:
        try:
            upload.seek(position)
        except (AttributeError, OSError):
            pass


def _contact_file_signature_matches(upload, extension):
    header = _read_upload_header(upload)
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if extension == ".webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if extension == ".heic":
        return b"ftyp" in header[:32] and any(
            brand in header[:64] for brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")
        )
    if extension in {".mp4", ".mov"}:
        return b"ftyp" in header[:32]
    if extension == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if extension == ".pdf":
        return header.startswith(b"%PDF-")
    if extension in {".doc", ".xls"}:
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension in {".docx", ".xlsx"}:
        return header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    if extension in {".csv", ".txt"}:
        return b"\x00" not in header
    return False


def validate_contact_upload(upload):
    if not upload:
        return
    if upload.size > MAX_UPLOAD_SIZE:
        raise ValidationError("Files must be 50 MB or smaller.")
    extension = Path(str(upload.name)).suffix.lower()
    if extension not in ALLOWED_CONTACT_UPLOAD_EXTENSIONS:
        raise ValidationError(
            "Upload a JPG, PNG, WEBP, GIF, HEIC, MP4, MOV, WEBM, PDF, DOC, DOCX, XLS, XLSX, CSV, or TXT file."
        )
    if not _contact_file_signature_matches(upload, extension):
        raise ValidationError("The file contents do not match the selected file type.")


def validate_uploaded_document(upload):
    if not upload:
        return
    if upload.size > MAX_UPLOAD_SIZE:
        raise ValidationError("Documents must be 50 MB or smaller.")
    name = upload.name.lower()
    if not any(name.endswith(extension) for extension in ALLOWED_DOCUMENT_EXTENSIONS):
        raise ValidationError("Upload a PDF, DOC, DOCX, XLS, XLSX, CSV, or TXT file.")


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    company = models.CharField(max_length=160, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="client_record",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class ClientInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="invites")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_client_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_usable(self):
        from django.utils import timezone

        return self.accepted_at is None and self.expires_at > timezone.now()


class Lead(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        QUOTED = "quoted", "Quoted"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
    )
    name = models.CharField(max_length=160)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    service = models.CharField(max_length=120)
    location = models.CharField(max_length=160)
    budget = models.CharField(max_length=120, blank=True)
    timeline = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=120, default="Website form")
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    priority = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_leads",
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deleted_leads",
    )

    class Meta:
        ordering = ["-priority", "-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return self.name

    @property
    def follow_ups(self):
        "Compatibility accessor for older dashboard templates and integrations."
        return self.tasks


class Task(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        BLOCKED = "blocked", "Blocked"
        COMPLETE = "complete", "Complete"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    project = models.ForeignKey(
        "Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    milestone = models.ForeignKey(
        "Milestone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
    )
    watchers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="watched_tasks",
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_tasks",
    )

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        permissions = [
            ("manage_team_tasks", "Can manage team task assignments"),
        ]

    def clean(self):
        if self.milestone_id and (
            not self.project_id or self.milestone.project_id != self.project_id
        ):
            raise ValidationError('The selected milestone must belong to the selected project.')
        if not self.lead_id and not self.project_id:
            raise ValidationError("A task must be attached to a lead or project.")
        if self.milestone_id and self.project_id and self.milestone.project_id != self.project_id:
            raise ValidationError("The selected milestone must belong to the selected project.")

    @property
    def completed(self):
        return self.status == self.Status.COMPLETE

    def __str__(self):
        return self.title


class Estimate(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.PositiveIntegerField(unique=True)
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="estimates")
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name="estimates")
    title = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_estimates",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_estimates",
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.number:
            last_number = Estimate.objects.order_by("-number").values_list("number", flat=True).first()
            self.number = max(last_number or 1000, 1000) + 1
        super().save(*args, **kwargs)

    @property
    def total(self):
        return sum((item.line_total for item in self.line_items.all()), Decimal("0.00"))

    def __str__(self):
        return f"#{self.number} {self.title}"


class EstimateLineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name="line_items")
    description = models.CharField(max_length=180)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    @property
    def line_total(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})
        if self.unit_price < 0:
            raise ValidationError({"unit_price": "Unit price cannot be negative."})

    def __str__(self):
        return self.description


class Project(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        SELECTIONS = "selections", "Selections"
        CONSTRUCTION = "construction", "Construction"
        FINAL = "final", "Final walkthrough"
        COMPLETE = "complete", "Complete"
        ON_HOLD = "on_hold", "On hold"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estimate = models.ForeignKey(Estimate, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects")
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects")
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects")
    assigned_staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_projects",
    )
    title = models.CharField(max_length=180)
    location = models.CharField(max_length=160, blank=True)
    project_type = models.CharField(max_length=80, default="renovation")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PLANNING)
    next_step = models.CharField(max_length=180, blank=True)
    summary = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    cover = models.FileField(upload_to="projects/covers/", blank=True, validators=[validate_uploaded_media])
    fallback_image = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_projects",
    )

    class Meta:
        ordering = ["-updated_at", "title"]

    def __str__(self):
        return self.title

    @property
    def progress_percent(self):
        milestones = list(self.milestones.all())
        if not milestones:
            return 0
        return round(sum(1 for milestone in milestones if milestone.is_complete) / len(milestones) * 100)


class Milestone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)
    is_complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title


class ProjectUpdate(models.Model):
    class Visibility(models.TextChoices):
        CLIENT = "client", "Client-visible"
        INTERNAL = "internal", "Internal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="updates")
    title = models.CharField(max_length=180)
    body = models.TextField()
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.CLIENT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MediaAsset(models.Model):
    class MediaType(models.TextChoices):
        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        CLIENT = "client", "Client-only"
        INTERNAL = "internal", "Internal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.CASCADE, related_name="media_assets")
    title = models.CharField(max_length=180)
    file = models.FileField(upload_to="projects/media/%Y/%m/", blank=True, validators=[validate_uploaded_media])
    media_type = models.CharField(max_length=10, choices=MediaType.choices, default=MediaType.PHOTO)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.INTERNAL)
    caption = models.TextField(blank=True)
    fallback_image = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_media",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class LeadAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(
        storage=ContactSubmissionStorage,
        upload_to="contact-form/%Y/%m/",
        validators=[validate_contact_upload],
    )
    original_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ClientMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="messages")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    body = models.TextField()
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_client_messages",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Activity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.CharField(max_length=220)
    detail = models.CharField(max_length=220, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operations_activity",
    )
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    estimate = models.ForeignKey(Estimate, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class SiteSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    headline = models.CharField(max_length=180, default="Build with confidence.")
    subheadline = models.TextField(
        default="Thoughtful construction, clear communication, and a better experience from first walkthrough to final handoff."
    )
    google_review_url = models.URLField(blank=True, max_length=500)
    featured_title = models.CharField(max_length=180, default="Coastal Bathroom Renovation")
    featured_body = models.TextField(
        default="A calm, highly functional renovation shaped around durable materials, thoughtful storage, and the small details that make a space feel finished."
    )
    featured_project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="featured_on_site",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Grand Coast site settings"


class Service(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    description = models.TextField()
    image_path = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title


class ProcessStep(models.Model):
    key = models.SlugField(max_length=40, unique=True)
    title = models.CharField(max_length=120)
    description = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.title


class EmployeeProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    job_title = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class EmployeeInvite(models.Model):
    class Purpose(models.TextChoices):
        ONBOARDING = "onboarding", "Onboarding"
        PASSWORD_RESET = "password_reset", "Password reset"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        EmployeeProfile,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="access_invites",
    )
    email = models.EmailField()
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    group = models.ForeignKey(
        "auth.Group",
        on_delete=models.PROTECT,
        related_name="employee_invites",
    )
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.ONBOARDING)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_employee_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_usable(self):
        from django.utils import timezone

        return self.accepted_at is None and self.expires_at > timezone.now()


class ScheduleEvent(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    assignees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="schedule_events",
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="schedule_events",
    )
    task = models.ForeignKey(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedule_events",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    location = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_schedule_events",
    )

    class Meta:
        ordering = ["start_at"]

    def clean(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError("Schedule events must end after they start.")
        if self.task_id and self.task.project_id and (
            not self.project_id or self.task.project_id != self.project_id
        ):
            raise ValidationError("The selected task must belong to the selected project.")
        if self.start_at and self.end_at:
            conflicting_overrides = _calendar_overrides_conflicting_with_event(self)
            if conflicting_overrides:
                conflict_labels = ', '.join(
                    f'{override.date.isoformat()} ({override.get_status_display()})'
                    for override in conflicting_overrides
                )
                raise ValidationError(
                    {
                        'start_at': (
                            'This event conflicts with the following calendar day override(s): '
                            f'{conflict_labels}.'
                        )
                    }
                )

    def __str__(self):
        return self.title


class CalendarDayOverride(TimeStampedModel):
    class Status(models.TextChoices):
        SHORT = 'short', 'Short day'
        CLOSED = 'closed', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField(unique=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    short_start = models.TimeField(null=True, blank=True)
    short_end = models.TimeField(null=True, blank=True)
    reason = models.CharField(max_length=180, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_calendar_day_overrides',
    )

    class Meta:
        ordering = ['date']

    def clean(self):
        errors = {}
        if self.status == self.Status.SHORT:
            if not self.short_start:
                errors['short_start'] = 'Short days need a start time.'
            if not self.short_end:
                errors['short_end'] = 'Short days need an end time.'
            if self.short_start and self.short_end and self.short_end <= self.short_start:
                errors['short_end'] = 'The short-day end time must be after its start time.'
        elif self.short_start or self.short_end:
            errors['short_start'] = 'Only short days can have custom hours.'

        if errors:
            raise ValidationError(errors)

        if self.date and self.status:
            conflicting_events = _calendar_events_conflicting_with_override(self)
            if conflicting_events:
                event_labels = ', '.join(event.title for event in conflicting_events[:5])
                if len(conflicting_events) > 5:
                    event_labels += ', ...'
                raise ValidationError(
                    {
                        'date': (
                            'Resolve these scheduled events before applying this day override: '
                            f'{event_labels}.'
                        )
                    }
                )

    def __str__(self):
        return f'{self.date.isoformat()} - {self.get_status_display()}'


class EmployeeWeeklySchedule(TimeStampedModel):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='weekly_schedules',
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    is_working = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ['employee', 'weekday']
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'weekday'],
                name='unique_employee_weekday_schedule',
            ),
        ]

    def clean(self):
        errors = {}
        if self.is_working:
            if not self.start_time:
                errors['start_time'] = 'Working days need a start time.'
            if not self.end_time:
                errors['end_time'] = 'Working days need an end time.'
            if self.start_time and self.end_time and self.end_time <= self.start_time:
                errors['end_time'] = 'The end time must be after the start time.'
        elif self.start_time or self.end_time:
            errors['start_time'] = 'Not-scheduled days cannot have working hours.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.employee} - {self.get_weekday_display()}'


class EmployeeScheduleOverride(TimeStampedModel):
    class Status(models.TextChoices):
        WORKING = 'working', 'Working'
        OFF = 'off', 'Day off'

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schedule_overrides',
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    reason = models.CharField(max_length=180, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_employee_schedule_overrides',
    )

    class Meta:
        ordering = ['date', 'employee']
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'date'],
                name='unique_employee_schedule_override_date',
            ),
        ]

    def clean(self):
        errors = {}
        if self.status == self.Status.WORKING:
            if not self.start_time:
                errors['start_time'] = 'Working overrides need a start time.'
            if not self.end_time:
                errors['end_time'] = 'Working overrides need an end time.'
            if self.start_time and self.end_time and self.end_time <= self.start_time:
                errors['end_time'] = 'The end time must be after the start time.'
        elif self.start_time or self.end_time:
            errors['start_time'] = 'Days off cannot have working hours.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.employee} - {self.date.isoformat()}'


class MobilePushDevice(TimeStampedModel):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mobile_push_devices',
    )
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_seen_at', '-created_at']

    def __str__(self):
        return f'{self.employee} - {self.platform or "mobile"}'


class EmployeeNotification(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employee_notifications',
    )
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=180)
    body = models.TextField()
    destination_url = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_employee_notifications',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'read_at', 'created_at']),
        ]

    @property
    def is_read(self):
        return self.read_at is not None


class PushDelivery(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        INVALID = 'invalid', 'Invalid token'

    notification = models.ForeignKey(
        EmployeeNotification,
        on_delete=models.CASCADE,
        related_name='push_deliveries',
    )
    device = models.ForeignKey(
        MobilePushDevice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='push_deliveries',
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    expo_ticket_id = models.CharField(max_length=180, blank=True)
    failure_detail = models.TextField(blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['notification', 'device'],
                name='unique_notification_push_device',
            ),
        ]


def _as_local_datetime(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value, CALENDAR_TIME_ZONE)
    return timezone.localtime(value, CALENDAR_TIME_ZONE)


def _local_day_bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min), CALENDAR_TIME_ZONE)
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), CALENDAR_TIME_ZONE)
    return start, end


def schedule_event_local_dates(event):
    'Return every local calendar date touched by a schedule event.'
    if not event.start_at or not event.end_at or event.end_at <= event.start_at:
        return []
    local_start = _as_local_datetime(event.start_at)
    local_end = _as_local_datetime(event.end_at)
    days = []
    current_day = local_start.date()
    while current_day <= local_end.date():
        day_start, day_end = _local_day_bounds(current_day)
        if max(local_start, day_start) < min(local_end, day_end):
            days.append(current_day)
        current_day += timedelta(days=1)
    return days


def _event_conflicts_with_override(event, override):
    event_start = _as_local_datetime(event.start_at)
    event_end = _as_local_datetime(event.end_at)
    day_start, day_end = _local_day_bounds(override.date)
    overlap_start = max(event_start, day_start)
    overlap_end = min(event_end, day_end)
    if overlap_start >= overlap_end:
        return False
    if override.status == CalendarDayOverride.Status.CLOSED:
        return True
    if override.status != CalendarDayOverride.Status.SHORT:
        return False

    allowed_start = timezone.make_aware(
        datetime.combine(override.date, override.short_start),
        CALENDAR_TIME_ZONE,
    )
    allowed_end = timezone.make_aware(
        datetime.combine(override.date, override.short_end),
        CALENDAR_TIME_ZONE,
    )
    return event_start < allowed_start or event_end > allowed_end


def _calendar_events_conflicting_with_override(override):
    day_start, day_end = _local_day_bounds(override.date)
    events = ScheduleEvent.objects.filter(
        start_at__lt=day_end,
        end_at__gt=day_start,
    ).order_by('start_at')
    return [event for event in events if _event_conflicts_with_override(event, override)]


def _calendar_overrides_conflicting_with_event(event):
    dates = schedule_event_local_dates(event)
    if not dates:
        return []
    overrides = CalendarDayOverride.objects.filter(date__in=dates).order_by('date')
    return [override for override in overrides if _event_conflicts_with_override(event, override)]


def effective_employee_schedule(employee, day):
    """Return the effective Pacific-time shift for an employee and local date."""
    employee_override = EmployeeScheduleOverride.objects.filter(
        employee=employee,
        date=day,
    ).first()
    weekly_schedule = None
    if employee_override is None:
        weekly_schedule = EmployeeWeeklySchedule.objects.filter(
            employee=employee,
            weekday=day.weekday(),
        ).first()

    company_override = CalendarDayOverride.objects.filter(date=day).first()
    source = employee_override or weekly_schedule
    if employee_override is not None:
        source_status = employee_override.status
        source_start = employee_override.start_time
        source_end = employee_override.end_time
        source_label = 'Date override'
        reason = employee_override.reason
    elif weekly_schedule is not None and weekly_schedule.is_working:
        source_status = EmployeeScheduleOverride.Status.WORKING
        source_start = weekly_schedule.start_time
        source_end = weekly_schedule.end_time
        source_label = 'Weekly schedule'
        reason = ''
    else:
        source_status = EmployeeScheduleOverride.Status.OFF
        source_start = None
        source_end = None
        source_label = 'Not scheduled'
        reason = ''

    if company_override is not None and company_override.status == CalendarDayOverride.Status.CLOSED:
        return {
            'date': day,
            'status': EmployeeScheduleOverride.Status.OFF,
            'is_working': False,
            'start_time': None,
            'end_time': None,
            'source': source_label,
            'reason': company_override.reason or 'Company closed',
            'employee_override': employee_override,
            'weekly_schedule': weekly_schedule,
            'company_override': company_override,
            'is_company_closed': True,
            'is_company_short': False,
        }

    if source_status != EmployeeScheduleOverride.Status.WORKING or not source_start or not source_end:
        return {
            'date': day,
            'status': EmployeeScheduleOverride.Status.OFF,
            'is_working': False,
            'start_time': None,
            'end_time': None,
            'source': source_label,
            'reason': reason,
            'employee_override': employee_override,
            'weekly_schedule': weekly_schedule,
            'company_override': company_override,
            'is_company_closed': False,
            'is_company_short': bool(
                company_override and company_override.status == CalendarDayOverride.Status.SHORT
            ),
        }

    effective_start = source_start
    effective_end = source_end
    is_short = bool(
        company_override and company_override.status == CalendarDayOverride.Status.SHORT
    )
    if is_short:
        effective_start = max(effective_start, company_override.short_start)
        effective_end = min(effective_end, company_override.short_end)
        if effective_start >= effective_end:
            return {
                'date': day,
                'status': EmployeeScheduleOverride.Status.OFF,
                'is_working': False,
                'start_time': None,
                'end_time': None,
                'source': source_label,
                'reason': company_override.reason or reason or 'No hours available',
                'employee_override': employee_override,
                'weekly_schedule': weekly_schedule,
                'company_override': company_override,
                'is_company_closed': False,
                'is_company_short': True,
            }

    return {
        'date': day,
        'status': EmployeeScheduleOverride.Status.WORKING,
        'is_working': True,
        'start_time': effective_start,
        'end_time': effective_end,
        'source': source_label,
        'reason': reason or (company_override.reason if is_short else ''),
        'employee_override': employee_override,
        'weekly_schedule': weekly_schedule,
        'company_override': company_override,
        'is_company_closed': False,
        'is_company_short': is_short,
    }


class TimeEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    task = models.ForeignKey(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    adjusted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="adjusted_time_entries",
    )
    adjusted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-clock_in"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(clock_out__isnull=True),
                name="one_open_time_entry_per_employee",
            ),
        ]

    def clean(self):
        if self.clock_out and self.clock_out <= self.clock_in:
            raise ValidationError("Clock-out must be after clock-in.")
        if self.task_id and self.task.project_id and (
            not self.project_id or self.task.project_id != self.project_id
        ):
            raise ValidationError("The selected task must belong to the selected project.")


class ProjectDocument(models.Model):
    class Visibility(models.TextChoices):
        CLIENT = "client", "Client-visible"
        INTERNAL = "internal", "Internal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=80, default="Project document")
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="projects/documents/%Y/%m/", validators=[validate_uploaded_document])
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.INTERNAL)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AdminSecurityProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_security_profile",
    )
    pin_enabled = models.BooleanField(default=False)
    pin_hash = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Admin security for {self.user.get_username()}"


class AdminRecoveryToken(models.Model):
    class Purpose(models.TextChoices):
        SECURITY_RESET = "security_reset", "Security reset"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_recovery_tokens",
    )
    purpose = models.CharField(max_length=30, choices=Purpose.choices, default=Purpose.SECURITY_RESET)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "purpose", "expires_at"]),
        ]

    @property
    def is_usable(self):
        return self.used_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"{self.get_purpose_display()} for {self.user.get_username()}"
