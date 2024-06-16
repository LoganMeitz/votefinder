from django import template

register = template.Library()

@register.simple_tag
def pretty_votecount(to_execute, votes_received):
    return "⚪" * (to_execute - votes_received) + "🟢" * votes_received