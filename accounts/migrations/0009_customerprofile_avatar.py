from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_alter_customerprofile_national_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerprofile',
            name='avatar',
            field=models.ImageField(blank=True, null=True, upload_to='customer_avatars/', verbose_name='تصویر پروفایل'),
        ),
    ]
