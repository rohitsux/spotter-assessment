"""URL routes for the trips app — mounted under /api/ by spotter_api/urls.py."""

from rest_framework.routers import DefaultRouter

from .views import TripViewSet

router = DefaultRouter()
router.register(r"trips", TripViewSet, basename="trip")

urlpatterns = router.urls
