"""Root URL configuration for the Django API."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('decisions.urls')),
]
