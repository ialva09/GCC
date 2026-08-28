from django.urls import path

from . import views


app_name = "demo"

urlpatterns = [
    path("", views.public_page, {"page": "home"}, name="home"),
    path("services/", views.public_page, {"page": "services"}, name="services"),
    path("projects/", views.public_page, {"page": "projects"}, name="projects"),
    path("process/", views.public_page, {"page": "process"}, name="process"),
    path("contact/", views.public_page, {"page": "contact"}, name="contact"),
    path("demo/admin/", views.admin_preview, name="admin-overview"),
    path("demo/admin/<slug:section>/", views.admin_preview, name="admin-section"),
    path("demo/portal/", views.portal_preview, name="portal"),
]
