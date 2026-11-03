from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='StripeEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stripe_event_id', models.CharField(max_length=255, unique=True)),
                ('event_type', models.CharField(max_length=100)),
                ('processed_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddIndex(
            model_name='analyticsmetric',
            index=models.Index(fields=['tenant', '-timestamp'], name='core_analyt_tenant__230a4e_idx'),
        ),
        migrations.AddConstraint(
            model_name='analyticsmetric',
            constraint=models.UniqueConstraint(fields=('tenant', 'metric_name', 'timestamp'), name='unique_tenant_metric_timestamp'),
        ),
    ]
