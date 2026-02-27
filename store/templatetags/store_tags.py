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


@register.filter
def multiply(value, arg):
    """value * arg. Narx (USD) * kurs = so'm."""
    if arg is None or value is None:
        return 0
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return 0


@register.filter
def intdot(value):
    """So'm uchun ming ajratuvchi nuqta: 14000 -> 14.000."""
    if value is None:
        return '0'
    try:
        n = int(round(float(value)))
        s = str(n)
        if n < 0:
            s = s[1:]
            sign = '-'
        else:
            sign = ''
        if len(s) <= 3:
            return sign + s
        result = []
        for i, c in enumerate(reversed(s)):
            if i > 0 and i % 3 == 0:
                result.append('.')
            result.append(c)
        return sign + ''.join(reversed(result))
    except (TypeError, ValueError):
        return '0'


@register.filter
def comma_to_dot(value):
    """Narxda vergulni nuqtaga almashtirish."""
    if value is None:
        return ''
    return str(value).replace(',', '.')


@register.filter
def variant_parametrlar(variant):
    """Variantning barcha parametr atributlarini vergul bilan qaytaradi (chek uchun)."""
    if not variant:
        return ''
    try:
        parts = [av.value for av in variant.attribute_values.all() if av.attribute.name == 'parametr']
        return ', '.join(parts) if parts else ''
    except Exception:
        return ''
