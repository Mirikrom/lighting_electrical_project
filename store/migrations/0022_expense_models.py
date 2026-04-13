# Generated manually for ExpenseCategory and Expense

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0021_debtpayment_fix_schema_and_state'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpenseCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Kategoriya nomi')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='Tartib')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('market', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expense_categories', to='store.market', verbose_name='Market')),
            ],
            options={
                'verbose_name': 'Rasxod kategoriyasi',
                'verbose_name_plural': 'Rasxod kategoriyalari',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Sarlavha')),
                ('notes', models.TextField(blank=True, verbose_name='Izoh')),
                ('amount_usd', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Summa (USD)')),
                ('usd_rate', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Kurs (1 USD = so'm) — yozuv vaqtidagi")),
                ('expense_date', models.DateField(verbose_name='Rasxod sanasi')),
                ('payment_method', models.CharField(choices=[('cash', 'Naqd'), ('card', 'Karta'), ('transfer', "O'tkazma"), ('other', 'Boshqa')], default='cash', max_length=20, verbose_name="To'lov turi")),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='expenses', to='store.expensecategory', verbose_name='Kategoriya')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_expenses', to=settings.AUTH_USER_MODEL, verbose_name='Kiritgan')),
                ('market', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expenses', to='store.market', verbose_name='Market')),
            ],
            options={
                'verbose_name': 'Rasxod',
                'verbose_name_plural': 'Rasxodlar',
                'ordering': ['-expense_date', '-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='expensecategory',
            constraint=models.UniqueConstraint(fields=('market', 'name'), name='unique_expense_category_per_market'),
        ),
    ]
