from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from decimal import Decimal
import logging
import re

logger = logging.getLogger('store')


class Market(models.Model):
    """Do'kon / magazin — har bir market o'z mahsulotlari va sotuvlari bilan"""
    name = models.CharField(max_length=200, verbose_name="Market nomi")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Market"
        verbose_name_plural = "Marketlar"
        ordering = ['name']

    def __str__(self):
        return self.name


class ExchangeRate(models.Model):
    """Kunlik dollar kursi (1 USD = rate so'm) — mahsulot narxlari va sotuvda ishlatiladi"""
    market = models.ForeignKey(Market, on_delete=models.CASCADE, null=True, blank=True, related_name='exchange_rates', verbose_name="Market")
    rate = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name="1 USD (so'm)")
    date = models.DateField(verbose_name="Sana")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Valyuta kursi"
        verbose_name_plural = "Valyuta kurslari"
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['market', 'date'], name='unique_market_date_rate'),
        ]

    def __str__(self):
        return f"1 USD = {self.rate} so'm ({self.date})"


class UserProfile(models.Model):
    """Foydalanuvchi biriktirilgan market va roli"""
    ROLE_MANAGER = 'manager'
    ROLE_SELLER = 'seller'
    ROLE_CHOICES = [
        (ROLE_MANAGER, "Menejer"),
        (ROLE_SELLER, "Sotuvchi"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile', verbose_name="Foydalanuvchi")
    market = models.ForeignKey(Market, on_delete=models.SET_NULL, null=True, blank=True, related_name='users', verbose_name="Market")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_SELLER, verbose_name="Rol")

    class Meta:
        verbose_name = "Foydalanuvchi profili"
        verbose_name_plural = "Foydalanuvchi profillari"

    def __str__(self):
        return f"{self.user.username} — {self.market.name if self.market else 'market tanlanmagan'}"

    @property
    def is_manager(self) -> bool:
        return self.role == self.ROLE_MANAGER


class Category(models.Model):
    market = models.ForeignKey(Market, on_delete=models.CASCADE, null=True, blank=True, related_name='categories', verbose_name="Market")
    name = models.CharField(max_length=100, verbose_name="Kategoriya nomi")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    UNIT_CHOICES = [
        ('dona', 'Dona'),
        ('metr', 'Metr'),
    ]
    """Asosiy mahsulot - variantlar uchun asos"""
    name = models.CharField(max_length=200, verbose_name="Mahsulot nomi")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products', verbose_name="Kategoriya")
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='dona', verbose_name="O'lchov birligi")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name="Asosiy rasm")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="Faol")

    class Meta:
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Convert name to uppercase
        if self.name:
            self.name = self.name.upper()
        super().save(*args, **kwargs)

    def get_default_variant(self):
        """Default variantni qaytaradi (birinchi variant yoki None)"""
        return self.variants.filter(is_active=True).first()


class Attribute(models.Model):
    """Mahsulot atributlari (masalan: Rang, Kuchlanish, O'lcham)"""
    name = models.CharField(max_length=100, unique=True, verbose_name="Atribut nomi")
    display_name = models.CharField(max_length=100, blank=True, verbose_name="Ko'rinadigan nom")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Atribut"
        verbose_name_plural = "Atributlar"
        ordering = ['name']

    def __str__(self):
        return self.display_name or self.name

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.name
        super().save(*args, **kwargs)


class AttributeValue(models.Model):
    """Atribut qiymatlari (masalan: Oq, Qora, 20W, 30W)"""
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='values', verbose_name="Atribut")
    value = models.CharField(max_length=100, verbose_name="Qiymat")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Atribut qiymati"
        verbose_name_plural = "Atribut qiymatlari"
        ordering = ['attribute', 'value']
        unique_together = ['attribute', 'value']

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"

    def save(self, *args, **kwargs):
        # Convert value to uppercase if it's a color attribute
        if self.attribute.name.lower() == 'color' and self.value:
            self.value = self.value.upper()
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    """Mahsulot variantlari - Product + AttributeValue kombinatsiyasi"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants', verbose_name="Mahsulot")
    attribute_values = models.ManyToManyField(AttributeValue, related_name='variants', verbose_name="Atribut qiymatlari")
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name="SKU")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))], verbose_name="Kirib kelish narxi", default=Decimal('0.00'))
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="Sotish narxi")
    stock_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Ombordagi miqdor")
    unlimited_stock = models.BooleanField(default=False, verbose_name="Cheklanmagan zaxira")
    image = models.ImageField(upload_to='products/variants/', blank=True, null=True, verbose_name="Variant rasm")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="Faol")

    class Meta:
        verbose_name = "Mahsulot varianti"
        verbose_name_plural = "Mahsulot variantlari"
        ordering = ['product', '-created_at']

    def __str__(self):
        variant_name = ", ".join([av.value for av in self.attribute_values.all()])
        if variant_name:
            return f"{self.product.name} ({variant_name})"
        return f"{self.product.name}"

    def get_display_name(self):
        """Variant nomini ko'rinadigan formatda qaytaradi"""
        variant_parts = [f"{av.attribute.display_name}: {av.value}" for av in self.attribute_values.all().select_related('attribute')]
        if variant_parts:
            return ", ".join(variant_parts)
        return "Asosiy variant"

    @classmethod
    def generate_sku_for_product(cls, product_name):
        """Kod: nomining boshidagi 3 ta harf + ketma-ket raqam (raz-001, led-002), unikal."""
        if not product_name or not str(product_name).strip():
            prefix = 'prd'
        else:
            letters = ''.join(c for c in str(product_name) if c.isalpha())[:3].lower()
            prefix = (letters + 'xxx')[:3] if letters else 'prd'
        existing = cls.objects.values_list('sku', flat=True)
        max_num = 0
        for sku in existing:
            if sku and re.match(r'^[a-z]{3}-\d{3}$', sku):
                try:
                    num = int(sku.split('-')[1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    pass
        next_num = max_num + 1
        return f"{prefix}-{next_num:03d}"

    def save(self, *args, **kwargs):
        # Ombordagi miqdor hech qachon manfiy bo'lmasin
        if self.stock_quantity is not None and self.stock_quantity < 0:
            self.stock_quantity = 0
        # Kod bo'sh bo'lsa: nom boshidagi 3 harf + ketma-ket raqam (raz-001, led-002)
        if not self.sku and self.product_id:
            self.sku = self.generate_sku_for_product(self.product.name)
        super().save(*args, **kwargs)
        logger.info(f"ProductVariant saved: {self} (SKU: {self.sku})")


class Customer(models.Model):
    market = models.ForeignKey(Market, on_delete=models.CASCADE, null=True, blank=True, related_name='customers', verbose_name="Market")
    name = models.CharField(max_length=100, verbose_name="Mijoz ismi")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    address = models.TextField(blank=True, verbose_name="Manzil")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mijoz"
        verbose_name_plural = "Mijozlar"
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Sale(models.Model):
    STATUS_CHOICES = [
        ('completed', "Yakunlangan"),
        ('returned', "Qaytarilgan"),
    ]
    PAYMENT_METHODS = [
        ('cash', 'Naqd pul'),
        ('card', 'Karta'),
        ('transfer', 'O\'tkazma'),
        ('mixed', 'Aralash (Naqd + Karta)'),
        ('credit', 'Qarzga'),
    ]

    market = models.ForeignKey(Market, on_delete=models.CASCADE, null=True, blank=True, related_name='sales', verbose_name="Market")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Mijoz")
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name="Sotish sanasi")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Jami summa (USD)")
    original_total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Chegirmasiz jami (USD)")
    usd_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Dollar kursi (so'm)")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash', verbose_name="To'lov usuli")
    payment_cash_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Naqd (USD)")
    payment_card_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Karta (USD)")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Chegirma (%)")
    notes = models.TextField(blank=True, verbose_name="Izohlar")
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, verbose_name="Yaratgan")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed', verbose_name="Holati")

    class Meta:
        verbose_name = "Sotuv"
        verbose_name_plural = "Sotuvlar"
        ordering = ['-sale_date']

    def __str__(self):
        return f"Sotuv #{self.id} - ${self.total_amount}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        logger.info(f"Sale created: {self.id}, Total: ${self.total_amount}")


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items', verbose_name="Sotuv")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Mahsulot varianti")
    # Backward compatibility - eski Product uchun
    product_old = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Mahsulot (eski)", related_name='old_sale_items')
    quantity = models.IntegerField(validators=[MinValueValidator(1)], verbose_name="Miqdor")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Birlik narxi (USD)")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Jami (USD)")

    class Meta:
        verbose_name = "Sotuv elementi"
        verbose_name_plural = "Sotuv elementlari"

    def __str__(self):
        return f"{self.variant} x {self.quantity}"

    @property
    def product(self):
        """Backward compatibility - Product'ni qaytaradi"""
        if self.variant:
            return self.variant.product
        return self.product_old

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)
