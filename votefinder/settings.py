# Django configuration, as well as many settings used by votefinder itself.
# This file reads environment variables from the operating system as well as a local dotenv (.env) file.
# If you are setting up your local development environment for the first time, you shouldn't have to edit
# this file. See the installation instructions on how to set up your own dotenv file for local development.
#
# Do NOT put any secrets in this file! It is part of the repository. It should only contain static site
# configuration required by Django and sensible defaults for other settings. Any secrets should be in
# the dotenv file, or else in the operating system's environment.

from django.core.exceptions import ImproperlyConfigured

# env_helpers is a helper module for accessing the environment.
from .env_helpers import env_bool, env_string, env_integer, env_string_list

# --------------------------------------------------------------------------------
# Various Django settings.
VF_DEBUG = env_bool('VF_DEBUG', default=False)
VF_SECRET_KEY = env_string('VF_SECRET_KEY', default='Votefinder Default Secret Key')
VF_TIME_ZONE = env_string('VF_TIME_ZONE', default='America/New_York')  # Default is the TZ of the SA forum account.

# This becomes Django's "allowed domains" setting.
VF_DOMAINS = env_string_list('VF_DOMAINS', separator=' ', default=['127.0.0.1', 'localhost'])

# This is what Votefinder considers the domain it's running on and may be used when generating links to Votefinder and such.
# Default primary domain to the first domain listed, but you can override it if you really want.
if len(VF_DOMAINS) > 0:
    VF_PRIMARY_DOMAIN = VF_DOMAINS[0]
VF_PRIMARY_DOMAIN = env_string('VF_PRIMARY_DOMAIN', VF_PRIMARY_DOMAIN)

# Logging settings
VF_LOG_LEVEL = env_string('VF_LOG_LEVEL')
VF_LOG_FILE_PATH = env_string('VF_LOG_FILE_PATH')

# Database settings
VF_DATABASE_DRIVER = env_string('VF_DATABASE_DRIVER', 'mysql')

# Used when database driver is sqlite
VF_SQLITE_FILENAME = env_string('VF_SQLITE_FILENAME')

# Used when database driver is mysql
VF_MYSQL_NAME = env_string('VF_MYSQL_NAME')
VF_MYSQL_USER = env_string('VF_MYSQL_USER')
VF_MYSQL_PASS = env_string('VF_MYSQL_PASS')
VF_MYSQL_HOST = env_string('VF_MYSQL_HOST')
VF_MYSQL_PORT = env_integer('VF_MYSQL_PORT', default=3306)

# Email server settings
VF_EMAIL_HOST = env_string('VF_EMAIL_HOST')
VF_EMAIL_PORT = env_integer('VF_EMAIL_PORT', default=25)
VF_EMAIL_USER = env_string('VF_EMAIL_USER')
VF_EMAIL_PASS = env_string('VF_EMAIL_PASS')
VF_EMAIL_USE_TLS = env_bool('VF_EMAIL_USE_TLS', default=True)

# Email sent by Votefinder comes from this address
VF_FROM_EMAIL = env_string('VF_FROM_EMAIL', default='reset@votefinder.org')

# Administrator contact information
VF_ADMIN_NAME = env_string('VF_ADMIN_NAME', default='Administrator')
VF_ADMIN_EMAIL = env_string('VF_ADMIN_EMAIL', default='admin@votefinder.org')

# SomethingAwful forum and discord integration
VF_SA_USER = env_string('VF_SA_USER')
VF_SA_PASS = env_string('VF_SA_PASS')
VF_SA_DISCORD_WEBHOOK = env_string('VF_SA_DISCORD_WEBHOOK')
VF_SA_DISCORD_CHANNEL = env_string('VF_SA_DISCORD_CHANNEL')

# Bread n' Roses forum integration
VF_BNR_API_KEY = env_string('VF_BNR_API_KEY')

# Fonts used in vote image generation
VF_REGULAR_FONT_PATH = 'votefinder/main/static/votefinder/MyriadPro-Regular.otf'
VF_BOLD_FONT_PATH = 'votefinder/main/static/votefinder/MyriadPro-Bold.otf'

# --------------------------------------------------------------------------------
# From here on, it's settings interpreted directly by Django. Many of them are set from settings read from the environment above,
# but some of them are unlikely to need to change based on environment and are not read.
SITE_ID = 1

FIXTURE_DIRS = ['votefinder/fixtures/']

WEB_ROOT = 'votefinder/'
STATIC_ROOT = env_string('VF_STATIC_ROOT', default="votefinder/static/")
STATIC_URL = 'static/'
STATICFILES_DIRS = env_string_list('VF_STATICFILES_DIRS', separator=' ', default=[])
MEDIA_ROOT = ''

LOGIN_URL = '/auth/login'
LOGIN_REDIRECT_URL = '/'
MEDIA_URL = 'http://media.votefinder.org/media/'
ADMIN_MEDIA_PREFIX = 'http://media.votefinder.org/admin/'

LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_L10N = True

DEBUG = VF_DEBUG
ALLOWED_HOSTS = VF_DOMAINS
SECRET_KEY = VF_SECRET_KEY
TIME_ZONE = VF_TIME_ZONE

ADMINS = (
    [(VF_ADMIN_NAME, VF_ADMIN_EMAIL)]
)
MANAGERS = ADMINS

EMAIL_HOST = VF_EMAIL_HOST
EMAIL_PORT = VF_EMAIL_PORT
EMAIL_HOST_USER = VF_EMAIL_USER
EMAIL_HOST_PASSWORD = VF_EMAIL_PASS
EMAIL_USE_TLS = VF_EMAIL_USE_TLS
DEFAULT_FROM_EMAIL = VF_FROM_EMAIL

DATABASES = {}

if VF_DATABASE_DRIVER == 'mysql':
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': VF_MYSQL_NAME,
        'USER': VF_MYSQL_USER,
        'PASSWORD': VF_MYSQL_PASS,
        'HOST': VF_MYSQL_HOST,
        'PORT': VF_MYSQL_PORT,
        'OPTIONS': {'charset': 'utf8mb4'},
    }
elif VF_DATABASE_DRIVER == 'sqlite':
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': VF_SQLITE_FILENAME
    }
else:
    raise ImproperlyConfigured('VF_DATABASE_DRIVER must be set to one of: mysql, sqlite')

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            'votefinder/main/templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # Insert your TEMPLATE_CONTEXT_PROCESSORS here or use this
                # list if you haven't customized them:
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.request',
            ],
        },
    },
]

if VF_LOG_FILE_PATH is not None and VF_LOG_LEVEL is not None:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'file': {
                'level': VF_LOG_LEVEL,
                'class': 'logging.FileHandler',
                'filename': VF_LOG_FILE_PATH,
                'formatter': 'simple'
            },
        },
        'loggers': {
            '': {
                'handlers': ['file'],
                'level': VF_LOG_LEVEL,
                'propagate': True,
            },
        },
        'formatters': {
            'simple': {
                'format': '{name} {levelname} {asctime} {message}',
                'style': '{',
            },
        }
    }

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
    'django.contrib.auth.hashers.SHA1PasswordHasher',
    'django.contrib.auth.hashers.UnsaltedSHA1PasswordHasher',
]

MIDDLEWARE = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = 'votefinder.urls'

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.admin',
    'django.contrib.staticfiles',
    'votefinder.main',
    'votefinder.vfauth',
)

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'