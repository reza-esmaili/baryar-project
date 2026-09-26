from .models import SupportAgent


def auto_assign_agent(ticket):

    agents = SupportAgent.objects.filter(
        departments=ticket.department
    )

    if agents.exists():
        ticket.assigned_agent = agents.order_by("?").first()
        ticket.save()


def notify_ticket_answered(ticket):
    """پیامک «پاسخ به تیکت» به صاحب تیکت (اگر رویداد در داشبورد فعال باشد)."""
    from core.services.notifications.events import TICKET_ANSWERED
    from core.services.notifications.tasks import notify_task
    from core.services.notifications.utils import display_name

    owner = ticket.user
    if not owner or not owner.mobile:
        return
    notify_task.delay(TICKET_ANSWERED, owner.mobile, {
        "user_name": display_name(owner),
        "ticket_id": ticket.pk,
        "subject": ticket.subject,
    })
