from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_update_faq_system_prompt_footer"),
    ]

    operations = [
        migrations.AddField(
            model_name="faq",
            name="search_keywords",
            field=models.CharField(blank=True, default="", max_length=500, verbose_name="検索キーワード"),
        ),
    ]
