# Generated manually for Market and UserProfile

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_default_market_and_assign(apps, schema_editor):
    """Mavjud ma'lumotlar uchun default market yaratish va biriktirish"""
    Market = apps.get_model('store', 'Market')
    UserProfile = apps.get_model('store', 'UserProfile')
    Category = apps.get_model('store', 'Category')
    Customer = apps.get_model('store', 'Customer')
    Sale = apps.get_model('store', 'Sale')
    User = apps.get_model(settings.AUTH_USER_MODEL)

    default_market, _ = Market.objects.get_or_create(
        name='Birinchi market',
        defaults={}
    )

    for cat in Category.objects.filter(market__isnull=True):
        cat.market = default_market
        cat.save(update_fields=['market_id'])
    for cust in Customer.objects.filter(market__isnull=True):
        cust.market = default_market
        cust.save(update_fields=['market_id'])
    for sale in Sale.objects.filter(market__isnull=True):
        sale.market = default_market
        sale.save(update_fields=['market_id'])

    for user in User.objects.all():
        UserProfile.objects.get_or_create(user=user, defaults={'market': default_market})


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0006_add_customer_telegram_username'),
    ]

    operations = [
        migrations.CreateModel(
            name='Market',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Market nomi')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Market',
                'verbose_name_plural': 'Marketlar',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('market', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users', to='store.market', verbose_name='Market')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL, verbose_name='Foydalanuvchi')),
            ],
            options={
                'verbose_name': 'Foydalanuvchi profili',
                'verbose_name_plural': 'Foydalanuvchi profillari',
            },
        ),
        migrations.AddField(
            model_name='category',
            name='market',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='store.market', verbose_name='Market'),
        ),
        migrations.AddField(
            model_name='customer',
            name='market',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='store.market', verbose_name='Market'),
        ),
        migrations.AddField(
            model_name='sale',
            name='market',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sales', to='store.market', verbose_name='Market'),
        ),
        migrations.RunPython(create_default_market_and_assign, migrations.RunPython.noop),
    ]
