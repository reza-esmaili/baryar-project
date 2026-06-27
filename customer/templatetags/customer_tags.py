from django import template
from orders.models import CustomerNotification
from support.models import Ticket

register = template.Library()


@register.simple_tag(takes_context=True)
def unread_notifications_count(context):
    request = context.get('request')
    if request and request.user.is_authenticated:
        return CustomerNotification.objects.filter(user=request.user, is_read=False).count()
    return 0


@register.simple_tag(takes_context=True)
def unread_support_count(context):
    request = context.get('request')
    if request and request.user.is_authenticated:
        return Ticket.objects.filter(user=request.user, unread_for_user=True).count()
    return 0
