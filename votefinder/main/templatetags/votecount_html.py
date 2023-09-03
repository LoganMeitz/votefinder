from django import template

register = template.Library()

@register.inclusion_tag("votecount.html")
def votecount_html(vc):
    return vc.game_state

