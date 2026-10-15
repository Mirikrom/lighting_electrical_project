from django.db import migrations, models
import django.db.models.deletion


def backfill_sale_item_snapshots(apps, schema_editor):
    SaleItem = apps.get_model('store', 'SaleItem')
    items = SaleItem.objects.select_related('variant__product').prefetch_related('variant__attribute_values__attribute')
    for item in items:
        variant = item.variant
        if variant is None or item.name_snapshot:
            continue
        product = variant.product
        item.name_snapshot = ((product.name if product else '') or '')[:300]
        params = []
        for av in variant.attribute_values.all():
            if getattr(av.attribute, 'name', '') == 'parametr':
                params.append(av.value)
        item.params_snapshot = ', '.join(params)[:300]
        item.unit_snapshot = ((getattr(product, 'unit', None) or 'dona'))[:10]
        item.sku_snapshot = (variant.sku or '')[:100]
        item.cost_price_snapshot = variant.cost_price
        item.save(update_fields=[
            'name_snapshot', 'params_snapshot', 'unit_snapshot', 'sku_snapshot', 'cost_price_snapshot',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0025_process_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleitem',
            name='name_snapshot',
            field=models.CharField(blank=True, default='', max_length=300, verbose_name='Mahsulot nomi (sotuv payti)'),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='params_snapshot',
            field=models.CharField(blank=True, default='', max_length=300, verbose_name='Parametrlar (sotuv payti)'),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='unit_snapshot',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name="O'lchov (sotuv payti)"),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='sku_snapshot',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='SKU (sotuv payti)'),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='cost_price_snapshot',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Tannarx (sotuv payti)'),
        ),
        migrations.RunPython(backfill_sale_item_snapshots, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='saleitem',
            name='variant',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='store.productvariant', verbose_name='Mahsulot varianti'),
        ),
        migrations.AlterField(
            model_name='saleitem',
            name='product_old',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='old_sale_items', to='store.product', verbose_name='Mahsulot (eski)'),
        ),
    ]
