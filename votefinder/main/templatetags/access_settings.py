from django import template
from django.conf import settings

register = template.Library()

@register.simple_tag
def access_settings(setting):
    return getattr(settings, setting, "")