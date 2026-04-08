from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_faq'),
    ]

    operations = [
        migrations.AddField(
            model_name='faq',
            name='embedding',
            field=models.TextField(blank=True, default='', verbose_name='埋め込みベクトル'),
        ),
    ]
