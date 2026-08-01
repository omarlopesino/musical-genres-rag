from django.conf import settings
from django.shortcuts import render

"""The page served at the root: what this project runs, and where each of those answers.

The same table README.md opens with, served instead of read in the repository, so whoever was handed
the address of this application finds the rest of it from there without a checkout of the sources.

The ui and this very app are named by the settings the API already hands out in its own answers,
since those are the addresses a caller reaches them at. The others are published by compose.yml on
whatever host runs it, which this application has no setting for and no way of asking.
"""

TEMPLATE = 'musical_genres_rag/home.html'

"""Where this application documents itself.

Relative, unlike the addresses below: whoever is reading this page has already reached the app, so
the host it answered on is the one the documentation is opened at, whatever a setting says.
"""
DOCS_PATH = '/docs'

"""Only what a browser opens is listed. The database and the cache are named in README.md too, but
an address something else connects to is nothing to click on, and this page is only ever clicked."""
def service(name, purpose, url):
    return {'name': name, 'purpose': purpose, 'url': url}

SERVICES = [
    service(
        'ui',
        'Streamlit: the chat, and the conversations, feedback and evaluation pages',
        settings.UI_BASE_URL,
    ),
    service(
        'app',
        'Django: the JSON API the pipeline is driven by',
        settings.API_BASE_URL + DOCS_PATH,
    ),
    service('grafana', 'The dashboard over live traffic, admin / admin', 'http://localhost:3000'),
    service('airflow', 'The orchestrator running the dags in dags/, with no login', 'http://localhost:8080'),
]

def home(request):
    return render(request, TEMPLATE, {'services': SERVICES, 'docs': DOCS_PATH})
