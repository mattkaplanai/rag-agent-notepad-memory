"""URL configuration for the decisions API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'decisions', views.RefundDecisionViewSet)

urlpatterns = [
    path('health/', views.health_check, name='health-check'),
    path('analyze/', views.analyze_case, name='analyze-case'),
    path('', include(router.urls)),
]
