from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_appconfig'),
    ]

    operations = [
        migrations.CreateModel(
            name='FAQ',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(max_length=100, verbose_name='カテゴリ')),
                ('question', models.TextField(verbose_name='質問')),
                ('answer', models.TextField(verbose_name='回答')),
                ('row_number', models.IntegerField(verbose_name='スプシ行番号')),
            ],
            options={
                'verbose_name': 'FAQ',
                'verbose_name_plural': 'FAQ',
                'ordering': ['row_number'],
            },
        ),
    ]
