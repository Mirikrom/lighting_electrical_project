# Rasxodlar: amount_usd + usd_rate -> amount_uzs (butun so'm)

import django.core.validators
from decimal import Decimal, ROUND_HALF_UP
from django.db import migrations, models


DEFAULT_RATE = Decimal('12500')


def forwards_migrate_amounts(apps, schema_editor):
    Expense = apps.get_model('store', 'Expense')
    for e in Expense.objects.iterator():
        rate = e.usd_rate or DEFAULT_RATE
        usd = e.amount_usd or Decimal('0')
        uzs = (usd * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        if uzs < 1:
            uzs = Decimal('1')
        e.amount_uzs = uzs
        e.save(update_fields=['amount_uzs'])


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0022_expense_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='amount_uzs',
            field=models.DecimalField(
                blank=True, decimal_places=0, max_digits=18, null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('1'))],
                verbose_name="Summa (so'm)",
            ),
        ),
        migrations.RunPython(forwards_migrate_amounts, migrations.RunPython.noop),
        migrations.RemoveField(model_name='expense', name='amount_usd'),
        migrations.RemoveField(model_name='expense', name='usd_rate'),
        migrations.AlterField(
            model_name='expense',
            name='amount_uzs',
            field=models.DecimalField(
                decimal_places=0, max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal('1'))],
                verbose_name="Summa (so'm)",
            ),
        ),
    ]
