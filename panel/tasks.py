from celery import shared_task
from django.utils import timezone


@shared_task(ignore_result=True)
def send_doc_request_sms_task(doc_request_id, order_id, customer_mobile, doc_title, link):
    from core.services.notifications.events import ADDITIONAL_DOCUMENT_REQUESTED
    from core.services.notifications.sms import SmsNotificationService
    from core.services.notifications.utils import display_name
    from documents.models import AdditionalDocumentRequest

    doc_request = (
        AdditionalDocumentRequest.objects.select_related("order__customer").filter(pk=doc_request_id).first()
    )
    customer_name = display_name(doc_request.order.customer) if doc_request else "مشتری"

    result = SmsNotificationService().notify(ADDITIONAL_DOCUMENT_REQUESTED, customer_mobile, {
        "customer_name": customer_name,
        "order_id": order_id,
        "doc_title": doc_title,
        "link": link,
    })

    if result is not None:
        AdditionalDocumentRequest.objects.filter(pk=doc_request_id).update(sms_sent_at=timezone.now())
