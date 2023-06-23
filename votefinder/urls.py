from django.conf import settings
from django.urls import include, path, re_path
from django.contrib import admin
from django.views import static
from votefinder.main import urls as main_urls
from votefinder.vfauth import urls as auth_urls

admin.autodiscover()

urlpatterns = [
    path('auth/', include(auth_urls)),
    path('admin/', admin.site.urls),
    path('', include(main_urls)),
]

