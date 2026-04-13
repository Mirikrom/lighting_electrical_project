from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    Market, UserProfile, Category, Product, Attribute, AttributeValue, ProductVariant,
    Customer, Sale, SaleItem, Expense, ExpenseCategory, ProcessLog,
)


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
    autocomplete_fields = ['market']


class UserAdminWithProfile(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'get_market')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    list_editable = ['is_active']  # Ro'yxatdan tasdiqlash: Active belgisini qo'yish

    def get_market(self, obj):
        if hasattr(obj, 'profile') and obj.profile.market:
            return obj.profile.market.name
        return '—'
    get_market.short_description = 'Market'


admin.site.unregister(User)
admin.site.register(User, UserAdminWithProfile)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'market', 'role']
    list_filter = ['market', 'role']
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
    list_display = ['product', 'get_variant_name', 'sku', 'cost_price', 'price', 'stock_quantity', 'unlimited_stock', 'is_active', 'created_at']
    list_filter = ['product__category', 'unlimited_stock', 'is_active', 'created_at']
    search_fields = ['product__name', 'sku']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['attribute_values']
    fieldsets = (
        ('Mahsulot', {
            'fields': ('product', 'attribute_values')
        }),
        ('Narx va miqdor', {
            'fields': ('sku', 'cost_price', 'price', 'stock_quantity', 'unlimited_stock', 'image', 'is_active')
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
    list_display = ['id', 'market', 'customer', 'sale_date', 'total_amount', 'payment_method', 'payment_cash_amount', 'payment_card_amount', 'created_by']
    list_filter = ['market', 'sale_date', 'payment_method']
    search_fields = ['customer__name', 'customer__phone']
    readonly_fields = ['sale_date', 'total_amount']
    inlines = [SaleItemInline]
    fieldsets = (
        ('Mijoz ma\'lumotlari', {
            'fields': ('customer',)
        }),
        ('Sotuv ma\'lumotlari', {
            'fields': ('sale_date', 'total_amount', 'payment_method', 'payment_cash_amount', 'payment_card_amount', 'notes', 'created_by')
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


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'market', 'sort_order', 'created_at']
    list_filter = ['market']
    search_fields = ['name']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'market', 'category', 'amount_uzs', 'expense_date', 'payment_method', 'created_by', 'created_at']
    list_filter = ['market', 'expense_date', 'payment_method', 'category']
    search_fields = ['title', 'notes']
    readonly_fields = ['created_at']
    date_hierarchy = 'expense_date'


@admin.register(ProcessLog)
class ProcessLogAdmin(admin.ModelAdmin):
    list_display = ['performed_at', 'entity_type', 'action', 'entity_id', 'title_snapshot', 'performed_by', 'market']
    list_filter = ['entity_type', 'action', 'market', 'performed_at']
    search_fields = ['title_snapshot', 'detail_text', 'performed_by__username']
    readonly_fields = [
        'market', 'entity_type', 'action', 'entity_id', 'title_snapshot', 'detail_text',
        'performed_by', 'performed_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
