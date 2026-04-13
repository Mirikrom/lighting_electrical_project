import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_expense_activity_to_process_log(apps, schema_editor):
    ExpenseActivity = apps.get_model('store', 'ExpenseActivity')
    ProcessLog = apps.get_model('store', 'ProcessLog')
    for row in ExpenseActivity.objects.all():
        parts = []
        if row.category_name_snapshot:
            parts.append(f"Kategoriya: {row.category_name_snapshot}")
        if row.expense_date_snapshot:
            parts.append(f"Rasxod sanasi: {row.expense_date_snapshot}")
        parts.append(f"Summa: {row.amount_uzs_snapshot} so'm")
        if row.detail_text:
            parts.append(row.detail_text)
        ProcessLog.objects.create(
            market_id=row.market_id,
            entity_type='expense',
            action=row.action,
            entity_id=row.expense_id,
            title_snapshot=(row.title_snapshot or '')[:300],
            detail_text='\n'.join(parts),
            performed_by_id=row.performed_by_id,
            performed_at=row.performed_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0024_expense_activity'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcessLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entity_type', models.CharField(choices=[('expense', 'Rasxod'), ('sale', 'Sotuv'), ('product', 'Mahsulot / variant'), ('customer', 'Mijoz'), ('debt_payment', "Qarz to'lovi"), ('exchange_rate', 'Valyuta kursi')], max_length=24, verbose_name="Ob'ekt")),
                ('action', models.CharField(choices=[('create', 'Yaratildi'), ('edit', 'Tahrirlandi'), ('delete', "O'chirildi"), ('return', 'Qaytarilgan'), ('append', "Qo'shildi (sotuvga)"), ('pay', "To'lov"), ('cancel_pay', "To'lov bekor")], max_length=16, verbose_name='Harakat')),
                ('entity_id', models.PositiveIntegerField(verbose_name='ID #')),
                ('title_snapshot', models.CharField(max_length=300, verbose_name='Qisqa mazmun')),
                ('detail_text', models.TextField(blank=True, verbose_name='Batafsil')),
                ('performed_at', models.DateTimeField(auto_now_add=True, verbose_name='Vaqt')),
                ('market', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='process_logs', to='store.market', verbose_name='Market')),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='process_logs_done', to=settings.AUTH_USER_MODEL, verbose_name='Kim qildi')),
            ],
            options={
                'verbose_name': 'Jarayon yozuvi',
                'verbose_name_plural': 'Jarayonlar tarixi',
                'ordering': ['-performed_at'],
            },
        ),
        migrations.RunPython(copy_expense_activity_to_process_log, migrations.RunPython.noop),
        migrations.DeleteModel(name='ExpenseActivity'),
    ]
