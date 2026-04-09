from django.db import migrations


NEW_FOOTER = (
    "--- FAQ データ終了 ---\n\n"
    "【回答ルール】\n"
    "- 上記FAQに記載のある情報のみを根拠に回答してください。\n"
    "- FAQに該当する情報がない場合は「その情報は持ち合わせていません」と明示し、推測や一般知識で補完しないでください。\n"
    "- URLや具体的な数値・固有名詞はFAQに明記されているもののみ使用してください。\n"
    "- 回答は簡潔かつ丁寧にしてください。"
)


def update_footer(apps, schema_editor):
    AppConfig = apps.get_model("api", "AppConfig")
    AppConfig.objects.filter(key="faq_system_prompt_footer").update(value=NEW_FOOTER)


def revert_footer(apps, schema_editor):
    AppConfig = apps.get_model("api", "AppConfig")
    old_footer = "--- FAQ データ終了 ---\n\n回答は簡潔かつ丁寧にしてください。"
    AppConfig.objects.filter(key="faq_system_prompt_footer").update(value=old_footer)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0011_faq_embedding"),
    ]

    operations = [
        migrations.RunPython(update_footer, revert_footer),
    ]
