from django import template

register = template.Library()


@register.filter
def getattr_val(obj, attr):
    """دسترسی پویا به attribute یک شیء در تمپلیت."""
    return getattr(obj, attr, False)
