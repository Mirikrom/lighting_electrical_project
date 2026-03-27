"""
Eski 0021+0022+0023 ni bitta migratsiyada birlashtirildi.

1) Eski SQLite bazalarda yetishmayotgan ustunlarni qo'shadi
2) created_at -> paid_at (ustun)
3) Django state: created_at -> paid_at + ordering (-paid_at)

Faqat 0020 dan keyin bitta migratsiya — serverga qo'yish osonroq.
"""
from django.db import migrations


def debtpayment_fix_forward(apps, schema_editor):
    connection = schema_editor.connection
    table = 'store_debtpayment'
    with connection.cursor() as cursor:
        existing = {c.name for c in connection.introspection.get_table_description(cursor, table)}

        if 'amount_original' not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN amount_original decimal")
            cursor.execute(f"UPDATE {table} SET amount_original = amount_usd WHERE amount_original IS NULL")

        if 'currency' not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN currency varchar(3) DEFAULT 'USD'")
            cursor.execute(f"UPDATE {table} SET currency = 'USD' WHERE currency IS NULL")

        if 'rate_used' not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN rate_used decimal")
            cursor.execute(f"UPDATE {table} SET rate_used = 12500 WHERE rate_used IS NULL")

        if 'is_cancelled' not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN is_cancelled bool DEFAULT 0")

        if 'cancelled_at' not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN cancelled_at datetime")

        if 'cancelled_by_id' not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN cancelled_by_id bigint")

        cols = {c.name for c in connection.introspection.get_table_description(cursor, table)}
        if 'paid_at' not in cols:
            if 'created_at' in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN paid_at datetime")
                cursor.execute(f"UPDATE {table} SET paid_at = created_at WHERE paid_at IS NULL")
                try:
                    cursor.execute(f"ALTER TABLE {table} DROP COLUMN created_at")
                except Exception:
                    pass
            else:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN paid_at datetime")
                cursor.execute(f"UPDATE {table} SET paid_at = CURRENT_TIMESTAMP WHERE paid_at IS NULL")


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0020_debtpayment'),
    ]

    operations = [
        migrations.RunPython(debtpayment_fix_forward, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField(
                    model_name='debtpayment',
                    old_name='created_at',
                    new_name='paid_at',
                ),
                migrations.AlterModelOptions(
                    name='debtpayment',
                    options={
                        'ordering': ['-paid_at'],
                        'verbose_name': "Qarz to'lovi",
                        'verbose_name_plural': "Qarz to'lovlari",
                    },
                ),
            ],
        ),
    ]
