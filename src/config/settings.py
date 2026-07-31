import os
from pathlib import Path

from dotenv import load_dotenv

# BASE_DIR is the repository root: settings.py lives at <root>/src/config/.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Django does not read .env on its own, unlike the entry points it replaces.
load_dotenv(BASE_DIR / '.env')

"""Reads a required environment variable, naming it when it is missing"""
def required(variable):
    value = os.getenv(variable)
    if value is None:
        raise Exception('The environment variable "' + variable + '" is required to run the application.')

    return value

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-only-not-for-production')
DEBUG = os.getenv('DJANGO_DEBUG', 'true').lower() == 'true'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Where a finished evaluation is read, which the API hands back as the link to the run it stored.
# The app serving that page is the "ui" service, reached by whoever called the API rather than by us.
UI_BASE_URL = os.getenv('UI_BASE_URL', 'http://localhost:8501')

# This very application, as whoever calls it reaches it: a generated file is handed back as a URL
# on it, and the caller downloading that file is somewhere else, so the address cannot be our own.
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

# Where the weights the vector engines embed with are read from. Downloaded by "make downloadModel"
# rather than committed, and relative to the repository, which is what the containers mount.
MODELS_DIRECTORY = Path(os.getenv('MODELS_DIRECTORY', BASE_DIR / 'models'))

# The web layer is a JSON API and nothing else: no admin, auth, sessions or contenttypes, since
# ninja serves it without templates, cookies or a CSRF token to carry.
INSTALLED_APPS = [
    'musical_genres_rag',
]

MIDDLEWARE = []

# The only page this project serves is the API documentation, which ninja renders through a template
# of its own, so the backend is configured with nowhere of ours to look for one.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': False,
    },
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': required('POSTGRES_HOST'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'NAME': required('POSTGRES_DATABASE'),
        'USER': required('POSTGRES_USER'),
        'PASSWORD': required('POSTGRES_PASSWORD'),
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://{host}:{port}/{database}'.format(
            host = required('REDIS_HOST'),
            port = os.getenv('REDIS_PORT', '6379'),
            database = os.getenv('REDIS_DATABASE', '0'),
        ),
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
