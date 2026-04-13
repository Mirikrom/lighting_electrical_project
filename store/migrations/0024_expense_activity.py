import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0023_expense_amount_uzs_only'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpenseActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create', 'Yaratildi'), ('edit', 'Tahrirlandi'), ('delete', "O'chirildi")], max_length=10, verbose_name='Harakat')),
                ('expense_id', models.PositiveIntegerField(verbose_name='Rasxod #')),
                ('title_snapshot', models.CharField(max_length=200, verbose_name='Sarlavha (yozuv vaqti)')),
                ('amount_uzs_snapshot', models.DecimalField(decimal_places=0, max_digits=18, verbose_name="Summa (so'm, yozuv vaqti)")),
                ('expense_date_snapshot', models.DateField(blank=True, null=True, verbose_name='Rasxod sanasi')),
                ('category_name_snapshot', models.CharField(blank=True, max_length=120, verbose_name='Kategoriya')),
                ('detail_text', models.TextField(blank=True, verbose_name="Batafsil / o'zgarishlar")),
                ('performed_at', models.DateTimeField(auto_now_add=True, verbose_name='Vaqt')),
                ('market', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expense_activities', to='store.market', verbose_name='Market')),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='expense_activities_done', to=settings.AUTH_USER_MODEL, verbose_name='Kim qildi')),
            ],
            options={
                'verbose_name': 'Rasxod harakati',
                'verbose_name_plural': 'Rasxod harakatlari',
                'ordering': ['-performed_at'],
            },
        ),
    ]
