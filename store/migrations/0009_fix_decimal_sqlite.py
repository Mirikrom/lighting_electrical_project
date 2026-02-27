# Fix SQLite Decimal read error (decimal.InvalidOperation on quantize)
# Python 3.14/Django: bazada 0 (int) yoki ba'zi float lar o'qiganda InvalidOperation bo'ladi.
# Barcha variantlarning cost_price va price ni aniq 2 xonali REAL qilib yozamiz.

from django.db import migrations, connection


def fix_decimal_values(apps, schema_editor):
    """ProductVariant jadvalidagi cost_price va price ni to'g'ri formatga keltirish"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, cost_price, price FROM store_productvariant")
        for row in cursor.fetchall():
            vid, cp, pr = row
            try:
                cp_val = round(float(cp), 2) if cp is not None else 0.0
                pr_val = round(float(pr), 2) if pr is not None else 0.01
            except (TypeError, ValueError):
                cp_val, pr_val = 0.0, 0.01
            if pr_val < 0.01:
                pr_val = 0.01
            cursor.execute(
                "UPDATE store_productvariant SET cost_price = %s, price = %s WHERE id = %s",
                [cp_val, pr_val, vid]
            )


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0008_add_product_unit'),
    ]

    operations = [
        migrations.RunPython(fix_decimal_values, migrations.RunPython.noop),
    ]
