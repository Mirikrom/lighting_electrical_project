from django.apps import AppConfig


def ensure_user_profile(sender, instance, created, **kwargs):
    """Yangi User yaratilganda UserProfile yaratish (market=None)"""
    if created and not hasattr(instance, 'profile'):
        from .models import UserProfile
        UserProfile.objects.get_or_create(user=instance, defaults={'market': None})


def _patch_sqlite_decimal_converter():
    """Python 3.14 + SQLite: Decimal o'qiganda InvalidOperation bo'lmasligi uchun konverterni xavfsiz qilish"""
    from decimal import Decimal, InvalidOperation
    from django.db.backends import sqlite3

    base_get_decimal = sqlite3.operations.DatabaseOperations.get_decimalfield_converter

    def safe_get_decimalfield_converter(self, expression):
        orig_converter = base_get_decimal(self, expression)
        decimal_places = getattr(expression.output_field, 'decimal_places', 2)

        def safe_converter(value, expression, connection):
            try:
                return orig_converter(value, expression, connection)
            except InvalidOperation:
                if value is None:
                    return None
                try:
                    d = Decimal(str(value))
                    quantize = Decimal(10) ** -decimal_places
                    return d.quantize(quantize)
                except Exception:
                    return Decimal('0').quantize(Decimal(10) ** -decimal_places)

        return safe_converter

    sqlite3.operations.DatabaseOperations.get_decimalfield_converter = safe_get_decimalfield_converter


class StoreConfig(AppConfig):
    name = 'store'

    def ready(self):
        from django.contrib.auth.models import User
        from django.db.models.signals import post_save
        post_save.connect(ensure_user_profile, sender=User)
        _patch_sqlite_decimal_converter()
