from django.urls import path

from musical_genres_rag.Api import api

# The JSON endpoints an orchestrator drives, mounted at the root so a path is the operation it runs.
# The documentation, and the engines it offers to pick from, are served at /docs.
urlpatterns = [
    path('', api.urls),
]
