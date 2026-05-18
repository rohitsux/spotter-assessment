"""URL routes for the trips app — mounted under /api/ by spotter_api/urls.py."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import TripViewSet, geocode_autocomplete

router = DefaultRouter()
router.register(r"trips", TripViewSet, basename="trip")

urlpatterns = [
    *router.urls,
    path("geocode/", geocode_autocomplete, name="geocode-autocomplete"),
]
