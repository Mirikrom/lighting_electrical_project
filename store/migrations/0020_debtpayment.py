from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0019_sale_discount_percent_sale_original_total_amount'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DebtPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_usd', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name="To'lov (USD)")),
                ('amount_original', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Kiritilgan summa')),
                ('currency', models.CharField(choices=[('USD', 'USD'), ('UZS', "So'm")], default='USD', max_length=3, verbose_name='Valyuta')),
                ('rate_used', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Ishlatilgan kurs')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='Izoh')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name="To'lov sanasi")),
                ('is_cancelled', models.BooleanField(default=False, verbose_name='Bekor qilingan')),
                ('cancelled_at', models.DateTimeField(blank=True, null=True, verbose_name='Bekor qilingan sana')),
                ('cancelled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cancelled_debt_payments', to=settings.AUTH_USER_MODEL, verbose_name='Bekor qilgan')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_debt_payments', to=settings.AUTH_USER_MODEL, verbose_name='Qabul qilgan')),
                ('sale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='debt_payments', to='store.sale', verbose_name='Qarz sotuvi')),
            ],
            options={
                'verbose_name': "Qarz to'lovi",
                'verbose_name_plural': "Qarz to'lovlari",
                'ordering': ['-created_at'],
            },
        ),
    ]
