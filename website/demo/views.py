from django.shortcuts import render


PUBLIC_PAGES = {"home", "services", "projects", "process", "contact"}
ADMIN_SECTIONS = {"overview", "leads", "estimates", "projects", "media", "content"}


def public_page(request, page="home"):
    if page not in PUBLIC_PAGES:
        page = "home"
    return render(request, "demo/public.html", {"page": page})


def admin_preview(request, section="overview"):
    if section not in ADMIN_SECTIONS:
        section = "overview"
    return render(request, "demo/admin.html", {"active_section": section})


def portal_preview(request):
    return render(request, "demo/portal.html")
