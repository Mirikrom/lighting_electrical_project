from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('', views.create_sale, name='product_list'),  # Home page -> New Sale
    path('products/', views.product_list, name='product_list_old'),
    path('products/create/', views.create_product, name='create_product'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/delete/', views.delete_product, name='delete_product'),
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/create/', views.create_sale, name='create_sale'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('credits/', views.credit_list, name='credit_list'),
    path('sales/<int:pk>/receipt/', views.print_receipt, name='print_receipt'),
    path('api/products/', views.get_products_json, name='products_json'),
    path('api/categories/create/', views.create_category_ajax, name='create_category_ajax'),
    path('api/products/search/', views.search_products_autocomplete, name='search_products_autocomplete'),
    path('api/products/<int:product_id>/variants/', views.get_product_variants_json, name='product_variants_json'),
    path('api/customers/search/', views.search_customers_autocomplete, name='search_customers_autocomplete'),
    path('api/colors/by-category/', views.get_colors_by_category, name='get_colors_by_category'),
    path('hide/', views.hide, name='hide'),
]

