import django.contrib.postgres.fields
from django.db import migrations, models


def bundle_rules_into_notifications(apps, schema_editor):
    """Fold each notification's single rule into the new multi-rule columns.

    Pre-existing notifications were one-per-rule, so each becomes a bundle of
    exactly one rule. A notification whose rule was already deleted keeps its
    denormalized nickname and ends up with an empty m2m.
    """
    Notification = apps.get_model('notifications', 'Notification')
    for notification in Notification.objects.iterator():
        notification.rule_nicknames = [notification.rule_nickname]
        notification.save(update_fields=['rule_nicknames'])
        if notification.rule_id:
            notification.rules.add(notification.rule_id)


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0001_initial'),
        ('notifications', '0006_notification_video_clip_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='rules',
            field=models.ManyToManyField(blank=True, related_name='notifications', to='rules.rule'),
        ),
        migrations.AddField(
            model_name='notification',
            name='rule_nicknames',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=240), default=list, size=None),
        ),
        migrations.RunPython(bundle_rules_into_notifications, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='notification',
            name='rule',
        ),
        migrations.RemoveField(
            model_name='notification',
            name='rule_nickname',
        ),
    ]
