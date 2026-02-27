# Lenta mahsulotlarini metrda ko'rsatish uchun unit='metr' qilish

from django.db import migrations


def set_lenta_products_metr(apps, schema_editor):
    Product = apps.get_model('store', 'Product')
    Product.objects.filter(name__icontains='lenta').update(unit='metr')


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0009_fix_decimal_sqlite'),
    ]

    operations = [
        migrations.RunPython(set_lenta_products_metr, migrations.RunPython.noop),
    ]
