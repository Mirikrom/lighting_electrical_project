from django import template

register = template.Library()


@register.filter
def divide(value, arg):
    """value / arg. Avoid division by zero."""
    if arg is None or arg == 0:
        return 0
    try:
        return float(value) / float(arg)
    except (TypeError, ValueError):
        return 0
