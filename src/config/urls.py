from django.urls import path

from musical_genres_rag.Api import api
from musical_genres_rag.Home import home

# The JSON endpoints an orchestrator drives, mounted at the root so a path is the operation it runs.
# The documentation, and the engines it offers to pick from, are served at /docs.
#
# The root itself is the one page a person rather than an orchestrator arrives at, and is listed
# first because the mount below claims every path it is asked for, empty one included.
urlpatterns = [
    path('', home),
    path('', api.urls),
]
