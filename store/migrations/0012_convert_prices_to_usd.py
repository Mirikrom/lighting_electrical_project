# Migration: ProductVariant narxlari endi USD da saqlanadi.
# Eski qiymatlar so'mda edi — 12500 ga bo'lib USD ga o'tkazamiz.

from decimal import Decimal
from django.db import migrations


def convert_to_usd(apps, schema_editor):
    ProductVariant = apps.get_model('store', 'ProductVariant')
    rate = Decimal('12500')
    for v in ProductVariant.objects.all():
        if v.price and v.price > 0:
            v.price = (v.price / rate).quantize(Decimal('0.01'))
        if v.cost_price and v.cost_price > 0:
            v.cost_price = (v.cost_price / rate).quantize(Decimal('0.01'))
        v.save(update_fields=['price', 'cost_price'])


def convert_to_uzs(apps, schema_editor):
    ProductVariant = apps.get_model('store', 'ProductVariant')
    rate = Decimal('12500')
    for v in ProductVariant.objects.all():
        if v.price and v.price > 0:
            v.price = (v.price * rate).quantize(Decimal('0.01'))
        if v.cost_price and v.cost_price > 0:
            v.cost_price = (v.cost_price * rate).quantize(Decimal('0.01'))
        v.save(update_fields=['price', 'cost_price'])


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0011_add_exchange_rate'),
    ]

    operations = [
        migrations.RunPython(convert_to_usd, convert_to_uzs),
    ]
