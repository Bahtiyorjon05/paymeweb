# Generated by Django 5.1.6 on 2025-02-23 10:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_transaction_received_amount_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='two_factor_code',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
