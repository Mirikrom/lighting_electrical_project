from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import logging

logger = logging.getLogger('store')


class Category(models.Model):
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
    """Asosiy mahsulot - variantlar uchun asos"""
    name = models.CharField(max_length=200, verbose_name="Mahsulot nomi")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products', verbose_name="Kategoriya")
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
    sku = models.CharField(max_length=100, unique=True, verbose_name="SKU")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="Kirib kelish narxi", default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="Sotish narxi")
    stock_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Ombordagi miqdor")
    image = models.ImageField(upload_to='products/variants/', blank=True, null=True, verbose_name="Variant rasm")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="Faol")

    class Meta:
        verbose_name = "Mahsulot varianti"
        verbose_name_plural = "Mahsulot variantlari"
        ordering = ['product', '-created_at']

    def __str__(self):
        variant_name = ", ".join([f"{av.attribute.name}: {av.value}" for av in self.attribute_values.all()])
        if variant_name:
            return f"{self.product.name} ({variant_name})"
        return f"{self.product.name}"

    def get_display_name(self):
        """Variant nomini ko'rinadigan formatda qaytaradi"""
        variant_parts = [f"{av.attribute.display_name}: {av.value}" for av in self.attribute_values.all().select_related('attribute')]
        if variant_parts:
            return ", ".join(variant_parts)
        return "Asosiy variant"

    def save(self, *args, **kwargs):
        # Check if this is an update (pk exists) to avoid recursion
        is_update = self.pk is not None
        
        # Auto-generate SKU if not provided
        if not self.sku:
            category_prefix = self.product.category.name[:3].upper() if self.product and self.product.category else "PRD"
            
            # Get attribute values - only if pk exists (after first save)
            variant_suffix = ""
            if is_update:
                try:
                    # Use refresh_from_db to avoid recursion
                    self.refresh_from_db(fields=['id'])
                    attr_values = list(self.attribute_values.all()[:3])
                    if attr_values:
                        variant_suffix = "-" + "-".join([av.value[:2].upper() for av in attr_values])
                except:
                    pass  # If attribute_values not accessible yet, skip
            
            if self.id:
                next_num = self.id
            else:
                next_num = ProductVariant.objects.count() + 1
            
            self.sku = f"{category_prefix}-{next_num:04d}{variant_suffix}"
        
        # Save first to get ID
        super().save(*args, **kwargs)
        
        # Update SKU with attribute values after save if needed (only if not already updated)
        if is_update and self.sku and not any(char.islower() for char in self.sku.split('-')[-1] if self.sku.count('-') > 1):
            # Check if SKU needs update with attribute values
            try:
                attr_values = list(self.attribute_values.all()[:3])
                if attr_values:
                    category_prefix = self.product.category.name[:3].upper() if self.product and self.product.category else "PRD"
                    variant_suffix = "-" + "-".join([av.value[:2].upper() for av in attr_values])
                    new_sku = f"{category_prefix}-{self.id:04d}{variant_suffix}"
                    if new_sku != self.sku:
                        # Update only SKU field using update() to avoid recursion
                        ProductVariant.objects.filter(pk=self.pk).update(sku=new_sku)
                        self.sku = new_sku  # Update instance attribute
            except Exception as e:
                logger.error(f"Error updating SKU with attribute values: {str(e)}")
        
        logger.info(f"ProductVariant saved: {self} (SKU: {self.sku})")


class Customer(models.Model):
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
    PAYMENT_METHODS = [
        ('cash', 'Naqd pul'),
        ('card', 'Karta'),
        ('transfer', 'O\'tkazma'),
        ('credit', 'Qarzga'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Mijoz")
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name="Sotish sanasi")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Jami summa")
    usd_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Dollar kursi (so'm)")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash', verbose_name="To'lov usuli")
    notes = models.TextField(blank=True, verbose_name="Izohlar")
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, verbose_name="Yaratgan")

    class Meta:
        verbose_name = "Sotuv"
        verbose_name_plural = "Sotuvlar"
        ordering = ['-sale_date']

    def __str__(self):
        return f"Sotuv #{self.id} - {self.total_amount} so'm"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        logger.info(f"Sale created: {self.id}, Total: {self.total_amount} so'm")


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items', verbose_name="Sotuv")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Mahsulot varianti")
    # Backward compatibility - eski Product uchun
    product_old = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Mahsulot (eski)", related_name='old_sale_items')
    quantity = models.IntegerField(validators=[MinValueValidator(1)], verbose_name="Miqdor")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Birlik narxi")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Jami")

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
        # Update sale total
        self.sale.total_amount = sum(item.subtotal for item in self.sale.items.all())
        self.sale.save()
        # Update variant stock
        if self.variant:
            self.variant.stock_quantity -= self.quantity
            self.variant.save()
            logger.info(f"SaleItem added: {self.variant} x {self.quantity}")
        elif self.product_old:
            # Backward compatibility
            self.product_old.stock_quantity -= self.quantity
            self.product_old.save()
            logger.info(f"SaleItem added (old): {self.product_old.name} x {self.quantity}")
