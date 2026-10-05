from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('overtimeapp', '0002_auditevent_exportbatch_emaillog_attempts_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='emaillog',
            name='html_body',
            field=models.TextField(blank=True, default=''),
        ),
    ]
