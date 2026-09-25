from django.core.management.base import BaseCommand

from land_freight.services import expire_stale_requests


class Command(BaseCommand):
    help = "درخواست‌های حمل زمینی بازی را که مهلت پذیرششان گذشته، منقضی می‌کند (برای cron یا Celery beat)."

    def handle(self, *args, **options):
        count = expire_stale_requests()
        self.stdout.write(self.style.SUCCESS(f"{count} request(s) expired."))
