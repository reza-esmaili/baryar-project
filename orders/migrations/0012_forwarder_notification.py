from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('forwarders', '__first__'),
        ('orders', '0011_add_order_message_and_customer_notification'),
    ]

    operations = [
        migrations.CreateModel(
            name='ForwarderNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notif_type', models.CharField(choices=[('message', 'پیام جدید از مشتری'), ('doc_upload', 'آپلود مدرک توسط مشتری')], max_length=20, verbose_name='نوع اعلان')),
                ('title', models.CharField(max_length=255, verbose_name='عنوان')),
                ('subtitle', models.CharField(blank=True, max_length=255, verbose_name='زیرعنوان')),
                ('url', models.CharField(blank=True, max_length=500, verbose_name='لینک')),
                ('is_read', models.BooleanField(default=False, verbose_name='خوانده شده')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')),
                ('forwarder_company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forwarder_notifications', to='forwarders.forwardercompany', verbose_name='شرکت فورواردر')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='forwarder_notifications', to='orders.cargorequest', verbose_name='سفارش مرتبط')),
            ],
            options={
                'verbose_name': 'اعلان فورواردر',
                'verbose_name_plural': 'اعلان‌های فورواردر',
                'ordering': ['-created_at'],
            },
        ),
    ]
