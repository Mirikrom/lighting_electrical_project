# Generated manually - Product unit (dona / metr)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0007_add_market_and_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='unit',
            field=models.CharField(
                choices=[('dona', 'Dona'), ('metr', 'Metr')],
                default='dona',
                max_length=10,
                verbose_name="O'lchov birligi"
            ),
        ),
    ]
