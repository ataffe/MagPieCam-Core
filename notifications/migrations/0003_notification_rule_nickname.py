from django.db import migrations, models


def backfill_rule_nickname(apps, schema_editor):
    """Existing notifications predate this column. Recover the nickname from
    the still-linked rule where possible; a notification whose rule was
    already deleted has no way to know what it used to be called.
    """
    Notification = apps.get_model('notifications', 'Notification')
    for notification in Notification.objects.select_related('rule').iterator():
        notification.rule_nickname = (
            notification.rule.rule_nickname if notification.rule_id else 'Deleted rule')
        notification.save(update_fields=['rule_nickname'])


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_alter_notification_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='rule_nickname',
            field=models.CharField(default=''),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_rule_nickname, migrations.RunPython.noop),
    ]
