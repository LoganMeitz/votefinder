from django import template
from django.utils.safestring import mark_safe
from django.utils.safestring import SafeString

register = template.Library()

@register.simple_tag
def votecount_html(vc):
    result = mark_safe(vc.get_html())
    print(result)
    print(isinstance(result, SafeString))
    return result