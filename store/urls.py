from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('no-market/', views.no_market_view, name='no_market'),
    path('', views.create_sale, name='product_list'),  # Home page -> New Sale
    path('products/', views.product_list, name='product_list_old'),
    path('products/create/', views.create_product, name='create_product'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/upload-image/', views.upload_product_image, name='upload_product_image'),
    path('products/<int:pk>/delete/', views.delete_product, name='delete_product'),
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/create/', views.create_sale, name='create_sale'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:pk>/cancel/', views.cancel_sale, name='cancel_sale'),
    path('sales/<int:pk>/delete/', views.delete_sale, name='delete_sale'),
    path('sales/<int:pk>/append/', views.append_sale, name='append_sale'),
    path('sales/<int:pk>/edit/', views.edit_sale, name='edit_sale'),
    path('credits/', views.credit_list, name='credit_list'),
    path('credits/customer/<int:customer_id>/', views.credit_customer_detail, name='credit_customer_detail'),
    path('statistics/', views.statistics, name='statistics'),
    path('exchange-rate/', views.exchange_rate_view, name='exchange_rate'),
    path('sales/<int:pk>/receipt/', views.print_receipt, name='print_receipt'),
    path('api/products/', views.get_products_json, name='products_json'),
    path('api/categories/create/', views.create_category_ajax, name='create_category_ajax'),
    path('api/products/search/', views.search_products_autocomplete, name='search_products_autocomplete'),
    path('api/products/<int:product_id>/variants/', views.get_product_variants_json, name='product_variants_json'),
    path('api/products/variant/<int:variant_id>/price/', views.get_variant_price, name='get_variant_price'),
    path('api/products/variant/<int:variant_id>/update-price/', views.update_variant_price, name='update_variant_price'),
    path('api/customers/search/', views.search_customers_autocomplete, name='search_customers_autocomplete'),
    path('api/colors/by-category/', views.get_colors_by_category, name='get_colors_by_category'),
    path('hide/', views.hide, name='hide'),
]

