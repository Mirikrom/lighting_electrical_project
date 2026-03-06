# Sale va SaleItem summalari endi USD da saqlanadi.
# Mavjud ma'lumotlarni so'm dan USD ga o'tkazamiz: qiymat / usd_rate

from decimal import Decimal
from django.db import migrations

DEFAULT_RATE = Decimal('12500')


def soom_to_usd(apps, schema_editor):
    Sale = apps.get_model('store', 'Sale')
    SaleItem = apps.get_model('store', 'SaleItem')
    for sale in Sale.objects.all():
        rate = sale.usd_rate if sale.usd_rate and sale.usd_rate > 0 else DEFAULT_RATE
        # Sale total hozir so'm da — USD ga
        if sale.total_amount is not None and sale.total_amount != 0:
            sale.total_amount = (sale.total_amount / rate).quantize(Decimal('0.01'))
            sale.save(update_fields=['total_amount'])
        for item in sale.items.all():
            if item.unit_price is not None and item.unit_price != 0:
                item.unit_price = (item.unit_price / rate).quantize(Decimal('0.01'))
            if item.subtotal is not None and item.subtotal != 0:
                item.subtotal = (item.subtotal / rate).quantize(Decimal('0.01'))
            item.save(update_fields=['unit_price', 'subtotal'])


def usd_to_soom(apps, schema_editor):
    Sale = apps.get_model('store', 'Sale')
    SaleItem = apps.get_model('store', 'SaleItem')
    for sale in Sale.objects.all():
        rate = sale.usd_rate if sale.usd_rate and sale.usd_rate > 0 else DEFAULT_RATE
        if sale.total_amount is not None and sale.total_amount != 0:
            sale.total_amount = (sale.total_amount * rate).quantize(Decimal('0.01'))
            sale.save(update_fields=['total_amount'])
        for item in sale.items.all():
            if item.unit_price is not None and item.unit_price != 0:
                item.unit_price = (item.unit_price * rate).quantize(Decimal('0.01'))
            if item.subtotal is not None and item.subtotal != 0:
                item.subtotal = (item.subtotal * rate).quantize(Decimal('0.01'))
            item.save(update_fields=['unit_price', 'subtotal'])


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0014_sale_status'),
    ]

    operations = [
        migrations.RunPython(soom_to_usd, usd_to_soom),
    ]
