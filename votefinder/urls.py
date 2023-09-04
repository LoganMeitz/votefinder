from django.urls import include, path
from django.contrib import admin
from votefinder.main import urls as main_urls
from votefinder.vfauth import urls as auth_urls
from debug_app import urls as debug_urls

from django.conf import settings

admin.autodiscover()

urlpatterns = [
    path('auth/', include(auth_urls)),
    path('admin/', admin.site.urls),
    path('', include(main_urls)),
]


if settings.VF_DEBUG:
    urlpatterns.append(path('debug/', include(debug_urls)))
