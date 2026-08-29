# Grand Coast Construction Operations Platform

This README is my walkthrough for the Grand Coast Construction website and internal operations platform. I wrote it in the order that I would set up, run, use, and test the application myself.

The project is a Django application for:

- Grand Coast Construction's public marketing website
- The private staff Operations workspace
- The employee Team workspace
- The secure client portal
- The lower-level Django administration interface, styled with Unfold

The visual system stays consistent everywhere: Grand Coast navy, blue, white, and gold; the supplied Grand Coast logo; Montserrat for interface text; and Merriweather for major headings.

## What I have built

I converted the original frontend prototype into a database-backed Django application. The browser is no longer the source of truth for leads, estimates, projects, tasks, users, documents, messages, or media.

The application now includes:

- Secure Django session authentication
- Owner, Manager, Office, and Field employee roles
- Employee profiles and one-time employee invitation links
- Client records and one-time client portal invitations
- Lead capture from the public contact form
- Lead assignment, statuses, priorities, notes, and tasks
- Lead-to-client conversion
- Server-calculated estimates with editable line items
- Client estimate review and acceptance
- Project creation from accepted estimates
- Project assignments, milestones, updates, documents, and media
- Unified internal tasks
- Internal schedule events and employee calendars
- Employee clock-in, clock-out, and time entries
- Two-way client and staff messaging
- Protected client-only documents and media
- Public project detail pages and gallery readiness
- Content Studio for public website content
- Optional Google Review link
- Unfold for the native /admin/ interface
- Operations search from the Unfold admin home

I intentionally did not add Stripe, payment processing, payment webhooks, card collection, email delivery, external calendar synchronization, payroll functionality, or geolocation tracking.

## Project layout

I keep the Django project inside the website directory:

~~~text
GCC/
├── README.md
└── website/
    ├── manage.py
    ├── backend/
    │   ├── settings.py
    │   ├── urls.py
    │   ├── asgi.py
    │   └── wsgi.py
    ├── operations/
    │   ├── models.py
    │   ├── forms.py
    │   ├── views.py
    │   ├── urls.py
    │   ├── services.py
    │   ├── search.py
    │   ├── admin.py
    │   ├── migrations/
    │   ├── management/commands/seed_operations.py
    │   ├── templates/operations/
    │   └── static/operations/
    ├── templates/
    ├── db.sqlite3
    ├── media/
    └── venv/
~~~

The old demo app has been retired. Old /demo/... links only redirect to the current routes for bookmark compatibility; demo is not used in the visible navigation or page copy.

## 1. I prepare my local environment

I open PowerShell and move into the Django project:

~~~powershell
cd C:\dev\GCC\website
~~~

If I need to create the virtual environment from scratch, I run:

~~~powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
~~~

If PowerShell does not allow activation, I can use the virtual-environment Python executable directly for every command:

~~~powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

The main dependencies are:

- Django 6.1
- django-unfold 0.104.1
- django-storages with boto3 support for optional production object storage

For local development, the application uses SQLite and stores uploaded files under website/media/.

## 2. I apply the database migrations

I apply Django's migrations:

~~~powershell
.\venv\Scripts\python.exe manage.py migrate
~~~

The Operations migrations create and preserve the application data for:

- Clients and client invites
- Leads and staff assignment
- Estimates and estimate line items
- Projects and staff assignments
- Milestones and project updates
- Unified tasks
- Media assets and lead attachments
- Client messages
- Employee profiles and employee invites
- Schedule events
- Time entries
- Project documents
- Services, process steps, and site settings
- Activity history

The previous follow-up concept was migrated into the new Task model while preserving completion state. I do not delete or reset existing application data when I run migrations.

## 3. I create or confirm my owner account

I create a superuser if I do not already have one:

~~~powershell
.\venv\Scripts\python.exe manage.py createsuperuser
~~~

I use that account for:

- The separate Django/Unfold administration area at /admin/
- The full staff Operations workspace
- Local setup and data inspection

The seed command automatically places an existing superuser in the Owner group and creates an EmployeeProfile for staff accounts.

## 4. I seed the local presentation data

I run the idempotent seed command:

~~~powershell
.\venv\Scripts\python.exe manage.py seed_operations
~~~

I can safely run this more than once. It uses stable identifying fields and does not duplicate the seeded records.

The seed command creates or preserves sample:

- Services and process steps
- Clients and leads
- Estimates and line items
- Projects and milestones
- Project updates
- Media records using the existing branded sample artwork
- Tasks and activity entries
- Site content

For a local client-portal walkthrough, I can create the seeded Maya client login by passing a password explicitly:

~~~powershell
.\venv\Scripts\python.exe manage.py seed_operations --client-password "ChangeThisLocalOnly123!"
~~~

That password is only for my local presentation database. I do not put credentials in source control, and the command has no hardcoded default password.

The command also creates these groups idempotently:

- Owner
- Manager
- Office
- Field

I can verify the database state with:

~~~powershell
.\venv\Scripts\python.exe manage.py showmigrations
~~~

## 5. I start the website

I run the local server:

~~~powershell
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
~~~

I then open:

- Public website: http://127.0.0.1:8000/
- Staff Operations: http://127.0.0.1:8000/dashboard/
- Employee Team workspace: http://127.0.0.1:8000/team/
- Client portal: http://127.0.0.1:8000/portal/
- Unfold administration: http://127.0.0.1:8000/admin/
- Staff login: http://127.0.0.1:8000/accounts/login/

## 6. I understand the account permissions

All staff accounts use Django's existing User model, Group model, and session authentication.

### Owner

I use the Owner role for the business owner or full administrator. An Owner can use the full Operations workspace, manage team access, manage operational records, and use the native Django/Unfold user and group administration.

### Manager

A Manager can run the operational workflow, including team invitations, leads, clients, estimates, projects, tasks, schedules, documents, messages, updates, and media.

### Office

An Office user can work with clients, leads, follow-up tasks, estimates, documents, messages, and project information. Office users do not receive employee role administration.

### Field

A Field user receives the dedicated Team workspace. A Field user can see only assigned projects, assigned tasks, relevant client context, personal schedule entries, personal time entries, internal updates, and permitted media reporting. Field users cannot enter the staff dashboard, native Unfold admin, or another client's portal.

### Client

A client only sees the projects, estimates, milestones, client-visible updates, client-visible documents, permitted media, and messages connected to that client's own record.

I enforce these restrictions in both group permissions and view/queryset logic. I do not rely on hiding a link in the interface as a security boundary.

## 7. I walk through the public website

I start at / and check the public experience:

- The Grand Coast logo appears in the header and footer.
- The navy, blue, white, and gold palette is consistent.
- The home page includes the current headline, supporting copy, services, process, featured work, and contact call-to-action.
- The public navigation links to Services, Projects, Process, and Contact.
- The public layout works on desktop and mobile.

The public routes are:

- /
- /services/
- /projects/
- /process/
- /contact/

The public contact form uses normal Django form handling and CSRF protection. I can submit a test inquiry from /contact/, and it creates a real Lead record in the database.

## 8. I manage a new lead

I sign in as an Owner, Manager, or authorized Office user and open:

~~~text
/dashboard/leads/
~~~

I use the lead workspace to:

1. Search by name, service, location, or related client details.
2. Filter by lead status.
3. Select a lead to open its detail panel.
4. Assign the lead to a staff member.
5. Move the lead through New, Contacted, Qualified, Quoted, Won, or Lost.
6. Mark the lead as a priority.
7. Add or edit internal notes.
8. Add a task with a due date, priority, and assignee.
9. Review activity history.
10. Convert the lead into a Client when I am ready.

The lead conversion is explicit. A lead does not silently become a client just because it exists.

The intended business sequence is:

~~~text
Lead captured
    → Lead converted into Client
    → Estimate created
    → Estimate accepted by Client
    → Project created
    → Staff, tasks, milestones, documents, updates, and media assigned
~~~

Lead status changes, assignments, notes, priority changes, tasks, and conversion activity persist in the database.

## 9. I create client portal access

From the client workspace at:

~~~text
/dashboard/clients/
~~~

I can:

- Create or edit client records.
- See linked leads, estimates, and projects.
- Create a one-time client invite.
- Copy the invite link for the client.
- Revoke access.
- Review client messages and unread state.

The application does not send email yet. I copy the generated invite link and send it manually.

The client invite:

- Is stored as a hash rather than a raw token.
- Expires after seven days.
- Can only be used once.
- Lets the client create a username and password.

The client completes the invite at:

~~~text
/accounts/invite/<token>/
~~~

After logging in, the client is redirected to /portal/.

## 10. I create and manage an estimate

I open:

~~~text
/dashboard/estimates/
~~~

I can create an estimate from a lead that already has a client association. I add line items with:

- Description
- Quantity
- Unit price
- Sort order

The estimate editor recalculates the subtotal and total in the browser for convenience, but the server recalculates the final Decimal total before saving. The browser is not trusted for business calculations.

I can:

- Save an estimate as Draft.
- Edit line items.
- Remove line items.
- Set an informational deposit amount.
- Send the estimate.
- Preview the customer-facing estimate.
- Decline or accept through the appropriate workflow.

The supported estimate statuses are:

- Draft
- Sent
- Accepted
- Declined

Once an estimate is accepted, it becomes read-only. If I need changes, I create a new estimate revision rather than silently changing the accepted record.

The deposit amount is informational only. No payment status, card collection, Stripe request, Checkout session, PaymentIntent, or webhook exists in this application.

## 11. I test client estimate acceptance

I sign in with the seeded client account or a client account created through an invite and open:

~~~text
/portal/
~~~

I confirm that the client can see only their own:

- Project information
- Estimate
- Deposit information
- Milestones
- Client-visible updates
- Client-visible documents
- Public/client media
- Project conversation

I click the estimate acceptance action. The application records:

- Accepted status
- Acceptance timestamp
- Accepting client user

The interface clearly explains that acceptance does not collect payment.

## 12. I convert an accepted estimate into a project

From the estimate workspace, I select the action to create a project from an accepted estimate.

The project form can include:

- Project title
- Client
- Lead
- Accepted estimate
- Assigned staff
- Location
- Project type
- Status
- Next step
- Summary
- Start date
- Target date
- Published state
- Cover image or fallback artwork

Lead-derived projects require the accepted-estimate workflow. I can still create standalone projects for work that did not originate from a lead.

I manage projects at:

~~~text
/dashboard/projects/
~~~

Inside a project I can:

- Change the project status.
- Assign employees.
- Toggle milestones complete or incomplete.
- Add project updates.
- Mark updates as client-visible or internal.
- Add documents.
- Add or edit media.
- Review activity history.
- Preview the client-facing project view.

## 13. I use unified tasks

I manage internal tasks at:

~~~text
/dashboard/tasks/
~~~

Tasks can be connected to:

- A lead
- A project
- A milestone

Each task supports:

- Title
- Description
- One assigned employee
- Watcher employees
- Status
- Priority
- Due date
- Completion timestamp
- Created/updated metadata

The task statuses are:

- Open
- In progress
- Blocked
- Complete

The priorities are:

- Normal
- High
- Urgent

I can filter tasks by employee, project, status, priority, due date, or search text. Task creation, reassignment, and completion add activity entries.

Employees work with their assigned tasks at:

~~~text
/team/tasks/
~~~

They can update permitted task fields and status, but they cannot see unrelated staff tasks.

## 14. I use the internal calendar

Managers and authorized Office users create and edit schedule events at:

~~~text
/dashboard/calendar/
~~~

A schedule event supports:

- Title
- Assigned employees
- Optional project
- Optional task
- Start time
- End time
- Location
- Notes

The calendar is internal and non-recurring. There is no Google Calendar or Outlook synchronization.

Employees view their own schedule at:

~~~text
/team/calendar/
~~~

The Team workspace provides a monthly calendar with a mobile-friendly list fallback.

## 15. I test employee clock-in and time tracking

I use the staff review page at:

~~~text
/dashboard/time/
~~~

Employees use:

~~~text
/team/time/
~~~

An employee can clock in and clock out. The application allows only one active time entry per employee.

A time entry can include:

- Employee
- Optional project
- Optional task
- Clock-in timestamp
- Clock-out timestamp
- Note
- Manager correction metadata

Managers and Owners can correct time entries. Employees can see their own recent entries.

Database timestamps remain timezone-aware. The application uses America/Los_Angeles and displays times in 12-hour format, such as 1:05 PM.

This is operational time tracking only. I do not treat it as payroll, wage, overtime, geolocation, or compliance software.

## 16. I use the employee Team workspace

I open:

~~~text
/team/
~~~

The Team workspace includes:

- Personal overview
- Assigned projects
- Assigned tasks
- Today's schedule
- Time tracking
- Internal project reporting
- Permitted media reporting
- Employee profile
- Password change

Employees can update their own profile information at:

~~~text
/team/profile/<user-id>/
~~~

I use the staff team-management area at:

~~~text
/dashboard/team/
~~~

From there, an Owner or Manager can:

- Invite an employee.
- Choose the employee's group.
- View employee profiles.
- Update job title, phone, and active status.
- Create a one-time password reset link.

The employee onboarding link expires after seven days. Password reset links expire after one day and can only be used once. Since email delivery is deferred, I copy these links manually.

## 17. I prepare project documents

I upload and manage project documents at:

~~~text
/dashboard/documents/
~~~

Documents support:

- Project association
- Title
- Category
- Description
- File
- Internal visibility
- Client-visible visibility
- Uploader and timestamps

The upload uses a multipart Django form with file type and size validation. Common PDF and office document formats are supported.

Client-visible documents are delivered through an authenticated Django view. A client cannot access an internal document by guessing its URL, and a client cannot access a document belonging to another client's project.

## 18. I prepare media and future galleries

I manage media from:

~~~text
/dashboard/media/
~~~

The system supports:

- Images and videos
- Captions
- Project association
- Public visibility
- Client-only visibility
- Internal visibility
- Protected authenticated delivery for non-public files

The current media is presentation artwork and seeded sample content. I have not added new real construction photography.

When I have real photos and videos, I can upload them through the existing staff interface. The system is already prepared for:

- Public project galleries
- Client-only project media
- Internal staff media
- Image lightbox previews
- Video display
- Empty gallery states when a project has no real photography yet

Field employees cannot publish internal reporting media publicly.

## 19. I view public project pages

Published projects have public detail pages at:

~~~text
/projects/<project-uuid>/
~~~

A public project page can show:

- Project title and location
- Project summary and story
- Current public status
- Cover image or branded fallback artwork
- Public media gallery
- An empty gallery state when there is no public photography yet
- Google Review call-to-action when configured

Only published projects and public media are exposed on the public website.

## 20. I use Content Studio

I edit public website content at:

~~~text
/dashboard/content/
~~~

Content Studio controls:

- Homepage headline
- Homepage supporting copy
- Service names and descriptions
- Featured project information
- Process steps
- Google Review URL

After saving, the public pages read from the database and show the updated content. I do not need to edit templates for normal content changes.

The Google Review field is a normal external URL. If it is blank, the public review call-to-action does not render. There is no Google API, Places API, synchronization, or stored Google credential.

## 21. I use the native Unfold administration

I open:

~~~text
/admin/
~~~

Unfold is the lower-level Django administration interface. It is separate from the branded Operations workspace at /dashboard/.

I use Unfold for:

- User and group administration
- Lower-level model inspection
- Permissions
- Database-backed record management
- History and change forms

The Unfold interface keeps the Grand Coast logo, navy/blue/white/gold palette, light theme, and Operations wording.

The Unfold admin search is extended to search Operations records, including:

- Clients
- Leads
- Employees
- Estimates
- Projects
- Tasks
- Schedule events
- Documents
- Messages
- Media
- Services
- Process steps
- Site settings
- Related milestones, updates, line items, and client details

When I select an Operations result, it opens the branded dashboard or Team workspace instead of sending me to an unrelated native edit page.

## 22. I understand local file storage and production storage

During development, I use:

~~~text
MEDIA_ROOT = website/media/
MEDIA_URL = /media/
~~~

Django serves local media while DEBUG is enabled.

The production storage backend can be enabled only when I explicitly configure the environment:

~~~powershell
$env:USE_SUPABASE_STORAGE = "true"
$env:SUPABASE_S3_ENDPOINT = "https://<project>.storage.supabase.co/storage/v1/s3"
$env:SUPABASE_S3_ACCESS_KEY = "<access-key>"
$env:SUPABASE_S3_SECRET_KEY = "<secret-key>"
$env:SUPABASE_STORAGE_BUCKET = "<bucket-name>"
$env:SUPABASE_S3_REGION = "us-east-1"
~~~

I keep these values out of source control. If USE_SUPABASE_STORAGE is not enabled, the application makes no Supabase storage request and uses local filesystem storage.

Before a real deployment, I also configure:

~~~powershell
$env:DJANGO_SECRET_KEY = "<long-random-production-secret>"
$env:DJANGO_DEBUG = "false"
$env:ALLOWED_HOSTS = "grandcoastconstruction.com,www.grandcoastconstruction.com"
~~~

I do not use the development secret key or DEBUG=true in production.

## 23. I run the automated checks

I run Django's system checks:

~~~powershell
.\venv\Scripts\python.exe manage.py check
~~~

I confirm that no model changes are waiting for a migration:

~~~powershell
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
~~~

I run the Operations test suite:

~~~powershell
.\venv\Scripts\python.exe manage.py test operations --verbosity 1
~~~

The current suite covers:

- Migration and seed behavior
- Idempotent Owner, Manager, Office, and Field groups
- Employee invitation creation, expiry, and one-time use
- Password setup and manager-issued reset links
- Staff, Field, client, and anonymous access restrictions
- Lead creation, assignment, status, priority, and client conversion
- Estimate creation, line-item Decimal totals, status transitions, and acceptance
- Accepted estimate to project conversion
- Task assignment, watcher access, status, priority, due dates, and activity
- Schedule event visibility
- Clock-in/out, duplicate active-entry prevention, corrections, and Pacific display
- Document upload validation and protected delivery
- Client-visible versus internal updates, documents, media, and messages
- Two-way client/staff messaging and unread behavior
- Public project pages and public-media filtering
- Google Review link visibility
- Public content updates
- Payment exclusion
- No business state stored in browser local storage

I expect the checks to finish with no system-check errors, no migration changes, and all Operations tests passing.

## 24. I manually test the main workflows

After starting the server, I test the application in this order.

### Public website

1. I open /.
2. I click Services, Projects, Process, and Contact.
3. I submit a test contact form.
4. I verify that a new lead appears in /dashboard/leads/.
5. I resize the browser to a mobile width and confirm there is no horizontal overflow.

### Owner workflow

1. I log in at /accounts/login/.
2. I open /dashboard/.
3. I confirm the fixed navigation and staff account area remain visible.
4. I open Leads, Clients, Tasks, Estimates, Projects, Calendar, Time, Documents, Media, and Content.
5. I assign a lead and change its status.
6. I convert the lead into a client.
7. I create an estimate and edit its line items.
8. I send the estimate.
9. I create or use a client invite.
10. I create a project after the estimate is accepted.
11. I assign an employee and toggle a milestone.
12. I add a project update and choose whether it is client-visible.
13. I upload an internal document and a client-visible document.
14. I add a task and schedule event.
15. I review messages and reply to a client.

### Employee workflow

1. I create an employee invitation from /dashboard/team/.
2. I copy the generated link.
3. I open the link in a private browser window.
4. I create the employee username and password.
5. I sign in and verify that the employee lands in /team/.
6. I confirm the employee sees only assigned projects, tasks, schedules, and time entries.
7. I update a task.
8. I add an internal project update.
9. I clock in and clock out.
10. I confirm that the employee cannot open /dashboard/, /admin/, or another employee's information.

### Client workflow

1. I create or use a client invite from /dashboard/clients/.
2. I copy the invite link.
3. I open it in a separate private browser window.
4. I create the client's login.
5. I verify that the client lands in /portal/.
6. I review the estimate and accept it.
7. I verify that no payment screen or payment request appears.
8. I check project status, milestones, client-visible updates, media, and documents.
9. I send a message to staff.
10. I verify that the client cannot view another client's project or internal records.

### Unfold workflow

1. I open /admin/.
2. I confirm the Grand Coast logo and colors.
3. I use the admin search for a known lead, project, estimate, or client.
4. I click the result.
5. I verify that it opens the relevant Operations dashboard or Team page.
6. I open the native user and group pages when I need low-level account administration.

## 25. I test the responsive design

I check at least one desktop size and one narrow mobile size. I verify:

- The navy sidebar remains usable.
- The staff account section stays visible in the Operations navigation.
- Tables and split panes do not create accidental page-wide horizontal scrolling.
- The mobile navigation can collapse and reopen.
- Forms remain readable and submit buttons remain reachable.
- The client portal remains usable as a future mobile webview.
- Public galleries and project fallback artwork scale correctly.
- The Unfold login, home, list, and form pages do not clip.

## 26. I check the security boundaries

I verify that:

- Anonymous visitors can view public pages but not staff or client workspaces.
- Clients cannot access /dashboard/, /team/, or /admin/.
- Field employees cannot access the Owner dashboard or another employee's records.
- Internal project updates, media, and documents are protected.
- Client-only files require authentication and project ownership.
- Invite links are hashed, expire, and cannot be reused.
- Forms use CSRF protection.
- Estimate totals are recalculated server-side.
- Accepted estimates cannot be edited in place.
- No business data is stored in localStorage.
- No Stripe, payment, webhook, or card request is made.
- No Supabase request is made unless I explicitly enable production storage settings.

## 27. I prepare for a future deployment

I keep the current GoDaddy website untouched while I review this Django application with the owner.

Before deployment, I would:

1. Set a strong production DJANGO_SECRET_KEY.
2. Turn DJANGO_DEBUG off.
3. Set the correct ALLOWED_HOSTS.
4. Configure the production database.
5. Decide whether to enable Supabase S3-compatible storage.
6. Configure HTTPS and secure cookie settings.
7. Run collectstatic.
8. Create real staff accounts and remove any local presentation accounts.
9. Upload real project photography and documents.
10. Confirm the owner approves the content, roles, workflows, and client-facing language.
11. Deploy the Django application separately from the existing GoDaddy site.
12. Keep payment processing deferred until the business requirements are discussed and approved.

For static assets in a deployment environment, I run:

~~~powershell
.\venv\Scripts\python.exe manage.py collectstatic --noinput
~~~

## Current platform boundary

This is now a real backend-powered construction-management foundation, but it is still intentionally focused on the agreed first phase:

- Local SQLite for development
- Local filesystem media by default
- Optional Supabase S3-compatible storage configuration
- Manual copying of invite and reset links
- Internal calendar only
- Informational estimate deposits
- No payment collection
- No email notifications
- No external calendar synchronization
- No real construction photography added yet
- No payroll or compliance timekeeping

That boundary lets me demonstrate the complete Grand Coast workflow now while keeping the application ready for the owner's decisions about production hosting, communications, photography, documents, payments, and future integrations.
