import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cargo1.settings')

app = Celery('cargo1')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
# core.services.notifications.tasks تو در توی اپ core است، نه core/tasks.py؛
# autodiscover_tasks() پیش‌فرض فقط <app>/tasks.py را برای هر اپ نصب‌شده
# می‌بیند، پس مسیر تودرتو باید جداگانه معرفی شود تا یک worker واقعی هم آن
# را بشناسد (نه فقط این پردازش که با import مستقیم در views ثبتش می‌کند).
app.autodiscover_tasks(['core.services.notifications'])
