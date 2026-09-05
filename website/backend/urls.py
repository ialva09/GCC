"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import include, path

from operations.admin import grand_coast_admin_site
from operations import views

urlpatterns = [
    path('gccad/', grand_coast_admin_site.urls),
    path('api/', include('operations.api_urls')),
    path('manifest.webmanifest', views.pwa_manifest, name='pwa-manifest'),
    path('service-worker.js', views.pwa_service_worker, name='pwa-service-worker'),
    path('offline/', views.pwa_offline, name='pwa-offline'),
    path('', include('operations.urls')),
]
