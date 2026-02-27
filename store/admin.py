from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Market, UserProfile, Category, Product, Attribute, AttributeValue, ProductVariant, Customer, Sale, SaleItem


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = "Profili (market)"
    verbose_name_plural = "Market biriktirish"
    fk_name = 'user'


class UserAdminWithProfile(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = BaseUserAdmin.list_display + ('get_market',)

    def get_market(self, obj):
        if hasattr(obj, 'profile') and obj.profile.market:
            return obj.profile.market.name
        return '—'
    get_market.short_description = 'Market'


admin.site.unregister(User)
admin.site.register(User, UserAdminWithProfile)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'market']
    list_filter = ['market']
    search_fields = ['user__username']
    raw_id_fields = ['user']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'market', 'description', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['market', 'created_at']


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ['attribute_values', 'sku', 'cost_price', 'price', 'stock_quantity', 'image', 'is_active']
    filter_horizontal = ['attribute_values']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'unit', 'is_active', 'created_at']
    list_filter = ['category', 'unit', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ProductVariantInline]
    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('name', 'category', 'unit', 'description', 'image', 'is_active')
        }),
        ('Vaqt', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_name', 'created_at']
    search_fields = ['name', 'display_name']
    list_filter = ['created_at']


@admin.register(AttributeValue)
class AttributeValueAdmin(admin.ModelAdmin):
    list_display = ['attribute', 'value', 'created_at']
    list_filter = ['attribute', 'created_at']
    search_fields = ['attribute__name', 'value']


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'get_variant_name', 'sku', 'cost_price', 'price', 'stock_quantity', 'is_active', 'created_at']
    list_filter = ['product__category', 'is_active', 'created_at']
    search_fields = ['product__name', 'sku']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['attribute_values']
    fieldsets = (
        ('Mahsulot', {
            'fields': ('product', 'attribute_values')
        }),
        ('Narx va miqdor', {
            'fields': ('sku', 'cost_price', 'price', 'stock_quantity', 'image', 'is_active')
        }),
        ('Vaqt', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_variant_name(self, obj):
        return obj.get_display_name()
    get_variant_name.short_description = 'Variant'


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1
    fields = ['variant', 'quantity', 'unit_price', 'subtotal']
    readonly_fields = ['subtotal']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['id', 'market', 'customer', 'sale_date', 'total_amount', 'payment_method', 'created_by']
    list_filter = ['market', 'sale_date', 'payment_method']
    search_fields = ['customer__name', 'customer__phone']
    readonly_fields = ['sale_date', 'total_amount']
    inlines = [SaleItemInline]
    fieldsets = (
        ('Mijoz ma\'lumotlari', {
            'fields': ('customer',)
        }),
        ('Sotuv ma\'lumotlari', {
            'fields': ('sale_date', 'total_amount', 'payment_method', 'notes', 'created_by')
        }),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'market', 'phone', 'address', 'created_at']
    search_fields = ['name', 'phone']
    list_filter = ['market', 'created_at']


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ['sale', 'variant', 'quantity', 'unit_price', 'subtotal']
    list_filter = ['sale__sale_date']
    search_fields = ['variant__product__name', 'variant__sku', 'sale__id']
