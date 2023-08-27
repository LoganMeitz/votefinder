from django import template

register = template.Library()

@register.inclusion_tag("votecount.html")
def votecount_html(vc):
    print(vc.game_state)
    return vc.game_state

