from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from .models import Product, Category, Sale, SaleItem, Customer, ProductVariant, Attribute, AttributeValue
from decimal import Decimal
import json
import logging
import uuid

logger = logging.getLogger('store')


def product_list(request):
    """Mahsulotlar ro'yxati — mahsulot bo'yicha guruhlash, har birida ranglar va qoldiq"""
    variants = ProductVariant.objects.filter(
        is_active=True, product__is_active=True
    ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute')
    categories = Category.objects.all()
    
    category_id = request.GET.get('category')
    if category_id:
        variants = variants.filter(product__category_id=category_id)
    search_query = request.GET.get('search')
    if search_query:
        variants = variants.filter(
            Q(product__name__icontains=search_query) | Q(sku__icontains=search_query)
        )
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        variants = variants.filter(price__gte=min_price)
    if max_price:
        variants = variants.filter(price__lte=max_price)
    in_stock = request.GET.get('in_stock')
    if in_stock == 'true':
        variants = variants.filter(stock_quantity__gt=0)
    
    # Guruhlash: product bo'yicha bitta qator, variantlar (rang, qoldiq) ostida
    from collections import OrderedDict
    products_with_variants = OrderedDict()
    for v in variants:
        pid = v.product_id
        if pid not in products_with_variants:
            products_with_variants[pid] = {'product': v.product, 'variants': []}
        products_with_variants[pid]['variants'].append(v)
    
    context = {
        'products_with_variants': list(products_with_variants.values()),
        'categories': categories,
        'selected_category': int(category_id) if category_id else None,
        'search_query': search_query or '',
    }
    return render(request, 'store/product_list.html', context)


def product_detail(request, pk):
    """Mahsulot tafsilotlari — bitta variant bo'yicha kiriladi, barcha variantlar (rang, narx, qoldiq) ko'rsatiladi"""
    try:
        variant = ProductVariant.objects.get(pk=pk, is_active=True, product__is_active=True)
        product = variant.product
        all_variants = product.variants.filter(is_active=True).select_related('product').prefetch_related('attribute_values__attribute').order_by('pk')
        profit = variant.price - variant.cost_price
        profit_percent = 0
        if variant.cost_price > 0:
            profit_percent = (profit / variant.cost_price) * 100
        context = {
            'variant': variant,
            'product': product,
            'all_variants': all_variants,
            'profit': profit,
            'profit_percent': profit_percent,
        }
        logger.info(f"Product detail viewed: {variant}")
        return render(request, 'store/product_detail.html', context)
    except ProductVariant.DoesNotExist:
        product = get_object_or_404(Product, pk=pk, is_active=True)
        variant = product.variants.filter(is_active=True).first()
        all_variants = product.variants.filter(is_active=True).prefetch_related('attribute_values__attribute').order_by('pk')
        if variant:
            profit = variant.price - variant.cost_price
            profit_percent = (profit / variant.cost_price) * 100 if variant.cost_price > 0 else 0
            context = {
                'variant': variant,
                'product': product,
                'all_variants': all_variants,
                'profit': profit,
                'profit_percent': profit_percent,
            }
        else:
            context = {
                'variant': None,
                'product': product,
                'all_variants': [],
                'profit': 0,
                'profit_percent': 0,
            }
        logger.info(f"Product detail viewed: {product}")
        return render(request, 'store/product_detail.html', context)


def delete_product(request, pk):
    """Mahsulotni o'chirish"""
    if request.method != 'POST':
        return redirect('store:product_list_old')
    
    # Try to get ProductVariant first
    try:
        variant = ProductVariant.objects.get(pk=pk)
        product_name = variant.product.name
        
        try:
            variant.delete()
            logger.info(f"ProductVariant deleted: {product_name}")
            messages.success(request, f'Mahsulot muvaffaqiyatli o\'chirildi: {product_name}')
            
            # Check where the request came from
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            
            referer = request.META.get('HTTP_REFERER', '')
            if referer:
                return redirect(referer)
            return redirect('store:product_list_old')
        except Exception as e:
            logger.error(f"Error deleting variant: {str(e)}")
            messages.error(request, f'Mahsulotni o\'chirishda xatolik: {str(e)}')
            referer = request.META.get('HTTP_REFERER', '')
            if referer:
                return redirect(referer)
            return redirect('store:product_list_old')
    except ProductVariant.DoesNotExist:
        # Fallback to Product (old structure)
        try:
            product = Product.objects.get(pk=pk)
            product_name = product.name
            
            try:
                product.delete()
                logger.info(f"Product deleted: {product_name}")
                messages.success(request, f'Mahsulot muvaffaqiyatli o\'chirildi: {product_name}')
                
                # Check where the request came from
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                
                # Check HTTP_REFERER to see where user came from
                referer = request.META.get('HTTP_REFERER', '')
                if referer:
                    return redirect(referer)
                return redirect('store:product_list_old')
            except Exception as e:
                logger.error(f"Error deleting product: {str(e)}")
                messages.error(request, f'Xatolik: {str(e)}')
                referer = request.META.get('HTTP_REFERER', '')
                if referer:
                    return redirect(referer)
                return redirect('store:product_list_old')
        except Product.DoesNotExist:
            messages.error(request, 'Mahsulot topilmadi!')
            return redirect('store:product_list_old')


def create_product(request):
    """Yangi mahsulot qo'shish"""
    categories = Category.objects.all()
    # Get unique colors from existing variants (all categories)
    color_attr = Attribute.objects.filter(name='color').first()
    if color_attr:
        colors = AttributeValue.objects.filter(attribute=color_attr).values_list('value', flat=True).distinct().order_by('value')
    else:
        colors = []
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            category_id = request.POST.get('category')
            new_category_name = request.POST.get('new_category', '').strip()
            color = request.POST.get('color', '').strip()
            new_color = request.POST.get('new_color', '').strip()
            cost_price = request.POST.get('cost_price', 0)
            cost_currency = request.POST.get('cost_currency', 'USD')
            price = request.POST.get('price')
            price_currency = request.POST.get('price_currency', 'USD')
            stock_quantity = request.POST.get('stock_quantity', 0)
            quantity_received = request.POST.get('quantity_received', 0)  # For existing products
            description = request.POST.get('description', '')
            sku = request.POST.get('sku', '')
            image = request.FILES.get('image')
            
            # Validation
            if not name:
                messages.error(request, 'Mahsulot nomi kiritilishi shart!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            
            # Check if product with same name already exists
            existing_product_id = request.POST.get('existing_product_id', '').strip()
            logger.info(f"Creating product - name: {name}, existing_product_id: '{existing_product_id}'")
            
            if existing_product_id and existing_product_id != '' and existing_product_id != '0':
                # Existing product selected - create new variant with new color
                # existing_product_id can be Product.id (from old API) or ProductVariant.id (from search_products_autocomplete)
                try:
                    pid = int(existing_product_id)
                    try:
                        existing_product = Product.objects.get(pk=pid)
                    except Product.DoesNotExist:
                        variant = ProductVariant.objects.get(pk=pid)
                        existing_product = variant.product
                    
                    # Get color
                    final_color = new_color if new_color else color
                    if not final_color:
                        messages.error(request, 'Rang tanlanishi yoki yangi rang nomi kiritilishi shart!')
                        return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
                    
                    # Get or create color attribute and value
                    color_attr, _ = Attribute.objects.get_or_create(
                        name='color',
                        defaults={'display_name': 'Rang'}
                    )
                    color_value, _ = AttributeValue.objects.get_or_create(
                        attribute=color_attr,
                        value=final_color.upper()
                    )
                    
                    # Check if variant with this color already exists
                    existing_variant = ProductVariant.objects.filter(
                        product=existing_product,
                        attribute_values=color_value,
                        is_active=True
                    ).first()
                    
                    if existing_variant:
                        # Variant already exists - update stock
                        new_quantity = int(quantity_received) if quantity_received else int(stock_quantity) if stock_quantity else 0
                        if new_quantity <= 0:
                            messages.error(request, 'Qancha kelgan sonini kiriting!')
                            return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
                        existing_variant.stock_quantity += new_quantity
                        existing_variant.save()
                        logger.info(f"Variant stock updated: {existing_variant}, Added: {new_quantity}, New total: {existing_variant.stock_quantity}")
                        messages.success(request, f'Mahsulot soni yangilandi: {existing_variant} (+{new_quantity} dona, Jami: {existing_variant.stock_quantity} dona)')
                        return redirect('store:product_detail', pk=existing_variant.pk)
                    else:
                        # Create new variant with new color — narxni formadan yoki birinchi variantdan olamiz
                        usd_rate = getattr(settings, 'USD_TO_UZS_RATE', 12500)
                        first_variant = existing_product.variants.filter(is_active=True).first()
                        if price and str(price).strip() and float(str(price)) > 0:
                            default_price = Decimal(str(price)) * Decimal(usd_rate) if price_currency == 'USD' else Decimal(str(price))
                        elif first_variant:
                            default_price = first_variant.price
                        else:
                            messages.error(request, 'Sotish narxi kiritilishi shart!')
                            return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
                        if cost_price and str(cost_price).strip() and float(str(cost_price)) >= 0:
                            default_cost_price = Decimal(str(cost_price)) * Decimal(usd_rate) if cost_currency == 'USD' else Decimal(str(cost_price))
                        elif first_variant:
                            default_cost_price = first_variant.cost_price
                        else:
                            default_cost_price = Decimal('0')
                        
                        # Create new variant — SKU unique bo'lishi kerak (UNIQUE constraint)
                        cat_prefix = (existing_product.category.name[:3].upper() if existing_product.category else "PRD")
                        unique_sku = f"{cat_prefix}-{existing_product.id}-{final_color.upper()[:2]}-{uuid.uuid4().hex[:6]}"
                        new_variant = ProductVariant(
                            product=existing_product,
                            sku=unique_sku,
                            cost_price=default_cost_price,
                            price=default_price,
                            stock_quantity=int(stock_quantity) if stock_quantity else int(quantity_received) if quantity_received else 0,
                            image=image
                        )
                        new_variant.save()
                        new_variant.attribute_values.add(color_value)
                        
                        logger.info(f"New variant created: {new_variant} (SKU: {new_variant.sku})")
                        messages.success(request, f'Yangi variant muvaffaqiyatli qo\'shildi: {existing_product.name} ({final_color.upper()})')
                        return redirect('store:product_detail', pk=new_variant.pk)
                        
                except (Product.DoesNotExist, ProductVariant.DoesNotExist, ValueError) as e:
                    logger.error(f"Error with existing product: {str(e)}")
                    messages.error(request, 'Mahsulot topilmadi!')
                    return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            
            # Validate price before conversion
            if not price or price == '0' or price == '':
                messages.error(request, 'Sotish narxi kiritilishi shart!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            
            # Note: We allow products with the same name (e.g., "Led 20W oq" and "Led 20W sariq")
            # Each product will have a unique SKU based on ID
            
            # Handle category - create new if provided
            category = None
            if new_category_name:
                # Create new category
                category, created = Category.objects.get_or_create(
                    name=new_category_name,
                    defaults={'description': ''}
                )
                logger.info(f"New category created: {category.name}")
            elif category_id:
                try:
                    category = Category.objects.get(pk=category_id)
                except Category.DoesNotExist:
                    messages.error(request, 'Noto\'g\'ri kategoriya!')
                    return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            else:
                messages.error(request, 'Kategoriya tanlanishi yoki yangi kategoriya nomi kiritilishi shart!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            
            # Convert to UZS if USD (only for new products)
            usd_rate = getattr(settings, 'USD_TO_UZS_RATE', 12500)
            try:
                if cost_price and cost_price != '0' and cost_price != '':
                    if cost_currency == 'USD':
                        cost_price = Decimal(str(cost_price)) * Decimal(usd_rate)
                    else:
                        cost_price = Decimal(str(cost_price))
                else:
                    cost_price = Decimal('0')
                
                # Price is already validated above, so convert it
                if price_currency == 'USD':
                    price = Decimal(str(price)) * Decimal(usd_rate)
                else:
                    price = Decimal(str(price))
                
                # Validate price is greater than 0.01 (model requirement)
                if price < Decimal('0.01'):
                    messages.error(request, 'Sotish narxi 0.01 dan katta bo\'lishi kerak!')
                    return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            except (ValueError, TypeError, Exception) as e:
                logger.error(f"Error converting price: {str(e)}")
                messages.error(request, f'Narx noto\'g\'ri formatda kiritilgan!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            
            # Handle color - create Attribute and AttributeValue if needed
            final_color = new_color if new_color else color
            attribute_values = []
            
            if final_color:
                # Get or create color attribute
                color_attr, _ = Attribute.objects.get_or_create(
                    name='color',
                    defaults={'display_name': 'Rang'}
                )
                # Get or create color value
                color_value, _ = AttributeValue.objects.get_or_create(
                    attribute=color_attr,
                    value=final_color
                )
                attribute_values.append(color_value)
            
            # Create Product (asosiy mahsulot)
            product = Product(
                name=name,
                category=category,
                description=description
            )
            
            if image:
                product.image = image
            
            try:
                product.save()
                logger.info(f"Product created: {product.name} (ID: {product.id})")
                
                # Create ProductVariant (narx, ombor, SKU bilan)
                variant = ProductVariant(
                    product=product,
                    sku=sku if sku else None,
                    cost_price=cost_price,
                    price=price,
                    stock_quantity=int(stock_quantity) if stock_quantity else 0,
                    image=image  # Variant uchun ham rasm
                )
                
                variant.save()
                
                # Add attribute values to variant (after save)
                if attribute_values:
                    variant.attribute_values.set(attribute_values)
                    # Update SKU with attribute values after setting them
                    if variant.pk:
                        try:
                            attr_values = list(variant.attribute_values.all()[:3])
                            if attr_values:
                                category_prefix = variant.product.category.name[:3].upper() if variant.product and variant.product.category else "PRD"
                                variant_suffix = "-" + "-".join([av.value[:2].upper() for av in attr_values])
                                new_sku = f"{category_prefix}-{variant.id:04d}{variant_suffix}"
                                if new_sku != variant.sku:
                                    variant.sku = new_sku
                                    variant.save(update_fields=['sku'])
                        except Exception as e:
                            logger.error(f"Error updating SKU after setting attribute values: {str(e)}")
                
                logger.info(f"ProductVariant created successfully: {variant} (SKU: {variant.sku}, ID: {variant.id})")
                messages.success(request, f'Mahsulot muvaffaqiyatli qo\'shildi: {product.name}')
                return redirect('store:product_detail', pk=variant.pk)
            except Exception as save_error:
                logger.error(f"Error saving product: {str(save_error)}")
                messages.error(request, f'Mahsulotni saqlashda xatolik: {str(save_error)}')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors})
            
        except Exception as e:
            logger.error(f"Error creating product: {str(e)}")
            messages.error(request, f'Xatolik: {str(e)}')
    
    return render(request, 'store/create_product.html', {'categories': categories})


@csrf_exempt
def create_category_ajax(request):
    """AJAX orqali kategoriya qo'shish"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            category_name = data.get('name', '').strip()
            
            if not category_name:
                return JsonResponse({'error': 'Kategoriya nomi kiritilishi shart!'}, status=400)
            
            category, created = Category.objects.get_or_create(
                name=category_name,
                defaults={'description': data.get('description', '')}
            )
            
            if created:
                logger.info(f"Category created via AJAX: {category.name}")
                return JsonResponse({
                    'success': True,
                    'category': {
                        'id': category.id,
                        'name': category.name
                    }
                })
            else:
                return JsonResponse({
                    'success': True,
                    'category': {
                        'id': category.id,
                        'name': category.name
                    },
                    'message': 'Bu kategoriya allaqachon mavjud'
                })
                
        except Exception as e:
            logger.error(f"Error creating category: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid method'}, status=405)


@csrf_exempt
def create_sale(request):
    """Yangi sotuv yaratish"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            customer_name = data.get('customer_name', '')
            customer_phone = data.get('customer_phone', '')
            payment_method = data.get('payment_method', 'cash')
            items = data.get('items', [])
            
            # Create or get customer
            customer = None
            if customer_name:
                # If phone is provided, search by phone first, otherwise by name
                if customer_phone:
                    customer, created = Customer.objects.get_or_create(
                        phone=customer_phone,
                        defaults={'name': customer_name}
                    )
                    # Update name if customer exists but name is different
                    if not created and customer.name != customer_name:
                        customer.name = customer_name
                        customer.save()
                else:
                    # If no phone, search by name
                    customer, created = Customer.objects.get_or_create(
                        name=customer_name,
                        defaults={'phone': ''}
                    )
            
            usd_rate = data.get('usd_rate')
            sale_kwargs = dict(
                customer=customer,
                payment_method=payment_method,
                created_by=request.user if request.user.is_authenticated else None
            )
            if usd_rate is not None and usd_rate != '':
                try:
                    sale_kwargs['usd_rate'] = Decimal(str(usd_rate))
                except (ValueError, TypeError):
                    pass
            sale = Sale.objects.create(**sale_kwargs)
            
            # Add items
            total = Decimal('0')
            for item_data in items:
                variant = ProductVariant.objects.get(pk=item_data['product_id'])
                quantity = int(item_data['quantity'])
                unit_price = Decimal(str(item_data['price']))
                
                if variant.stock_quantity < quantity:
                    sale.delete()
                    return JsonResponse({'error': f'{variant} uchun yetarli mahsulot yo\'q'}, status=400)
                
                SaleItem.objects.create(
                    sale=sale,
                    variant=variant,
                    quantity=quantity,
                    unit_price=unit_price
                )
                
                # Update variant stock
                variant.stock_quantity -= quantity
                variant.save()
                
                total += unit_price * quantity
            
            sale.total_amount = total
            sale.save()
            
            logger.info(f"Sale created: {sale.id}, Total: {total} so'm")
            return JsonResponse({'success': True, 'sale_id': sale.id})
            
        except Exception as e:
            logger.error(f"Error creating sale: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)
    
    categories = Category.objects.all()
    
    # Get top 5 most sold variants
    top_sold_variants = ProductVariant.objects.filter(
        is_active=True,
        product__is_active=True,
        stock_quantity__gt=0
    ).annotate(
        total_sold=Sum('saleitem__quantity')
    ).filter(
        total_sold__gt=0
    ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute').order_by('-total_sold')[:5]
    
    # If no sales yet, get last 5 added variants
    if not top_sold_variants.exists():
        top_sold_variants = ProductVariant.objects.filter(
            is_active=True,
            product__is_active=True,
            stock_quantity__gt=0
        ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute').order_by('-created_at')[:5]
    
    # Prepare top products for autocomplete (variants as JSON)
    top_products_json = []
    for v in top_sold_variants:
        color = ''
        for av in v.attribute_values.all():
            if av.attribute.name == 'color':
                color = av.value
                break
        top_products_json.append({
            'id': v.id,  # Variant ID
            'product_id': v.product.id,
            'name': v.product.name,
            'variant_name': str(v),
            'color': color,
            'sku': v.sku,
            'price': str(v.price),
            'stock': v.stock_quantity,
        })
    
    return render(request, 'store/create_sale.html', {
        'top_products': top_sold_variants,
        'top_products_json': json.dumps(top_products_json),
        'categories': categories
    })


def credit_list(request):
    """Qarzdorlar ro'yxati"""
    credits = Sale.objects.filter(payment_method='credit').select_related('customer', 'created_by')
    
    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        credits = credits.filter(sale_date__date__gte=date_from)
    if date_to:
        credits = credits.filter(sale_date__date__lte=date_to)
    
    # Filter by customer
    customer_id = request.GET.get('customer')
    if customer_id:
        credits = credits.filter(customer_id=customer_id)
    
    # Calculate total debt per customer
    from django.db.models import Sum
    customer_debts = credits.values('customer__id', 'customer__name', 'customer__phone').annotate(
        total_debt=Sum('total_amount')
    ).order_by('-total_debt')
    
    total_debt = credits.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Get all customers for filter
    customers = Customer.objects.filter(sale__payment_method='credit').distinct()
    
    return render(request, 'store/credit_list.html', {
        'credits': credits,
        'customer_debts': customer_debts,
        'total_debt': total_debt,
        'customers': customers
    })


def sale_list(request):
    """Sotuvlar ro'yxati"""
    sales = Sale.objects.all().select_related('customer', 'created_by')
    
    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        sales = sales.filter(sale_date__date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__date__lte=date_to)
    
    # Filter by payment method
    payment_method = request.GET.get('payment_method')
    if payment_method:
        sales = sales.filter(payment_method=payment_method)
    
    context = {
        'sales': sales,
        'total_sales': sum(sale.total_amount for sale in sales),
    }
    return render(request, 'store/sale_list.html', context)


def sale_detail(request, pk):
    """Sotuv tafsilotlari va chek"""
    sale = get_object_or_404(Sale, pk=pk)
    return render(request, 'store/sale_detail.html', {'sale': sale})


def print_receipt(request, pk):
    """Chek chiqarish"""
    sale = get_object_or_404(Sale, pk=pk)
    logger.info(f"Receipt printed for sale: {sale.id}")
    receipt_rate = float(sale.usd_rate) if sale.usd_rate else 12500
    receipt_rate_formatted = f"{receipt_rate:,.0f}"
    # Telegramga yuborish uchun matn (qurilma: PC/Mac/Android — shu qurilmadagi Telegram ochiladi)
    lines = [
        'Laziz_Electronics_Store',
        f"Chek #{sale.id}",
        sale.sale_date.strftime('%d.%m.%Y %H:%M'),
        f"Bugungi kurs: {receipt_rate_formatted} so'm",
        '',
    ]
    if sale.customer:
        lines.append(f"Mijoz: {sale.customer.name}")
        if sale.customer.phone:
            lines.append(f"Tel: {sale.customer.phone}")
        lines.append('')
    pay = dict(Sale.PAYMENT_METHODS).get(sale.payment_method, sale.payment_method)
    lines.append(f"To'lov: {pay}")
    lines.append('')
    for item in sale.items.all():
        usd = float(item.subtotal) / receipt_rate
        lines.append(f"{item.product.name}  {item.quantity}x  ${usd:.2f}")
    total_usd = float(sale.total_amount) / receipt_rate
    total_usd_formatted = f"{total_usd:,.2f}"
    total_soom_formatted = f"{float(sale.total_amount):,.0f}"
    lines.append('')
    lines.append(f"JAMI: ${total_usd_formatted}  {total_soom_formatted} so'm")
    receipt_text = '\n'.join(lines)
    html = render_to_string('store/receipt.html', {
        'sale': sale,
        'receipt_rate': receipt_rate,
        'receipt_rate_formatted': receipt_rate_formatted,
        'receipt_text': receipt_text,
        'total_usd_formatted': total_usd_formatted,
        'total_soom_formatted': total_soom_formatted,
    })
    response = HttpResponse(html)
    response['Content-Type'] = 'text/html; charset=utf-8'
    return response


def get_products_json(request):
    """AJAX uchun mahsulotlar JSON"""
    category_id = request.GET.get('category_id')
    search = request.GET.get('search', '')
    
    variants = ProductVariant.objects.filter(is_active=True, product__is_active=True, stock_quantity__gt=0).select_related('product', 'product__category')
    
    if category_id:
        variants = variants.filter(product__category_id=category_id)
    
    if search:
        variants = variants.filter(
            Q(product__name__icontains=search) | Q(sku__icontains=search)
        )
    
    data = [{
        'id': v.id,
        'name': v.product.name,
        'variant_name': str(v),
        'price': str(v.price),
        'stock': v.stock_quantity,
        'sku': v.sku,
        'image': v.image.url if v.image else (v.product.image.url if v.product.image else ''),
    } for v in variants[:50]]  # Limit to 50 for performance
    
    return JsonResponse({'products': data})


def search_products_autocomplete(request):
    """Autocomplete uchun mahsulotlarni qidirish - variantlar bo'yicha"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'products': []})
    
    # Search variants by product name or SKU
    variants = ProductVariant.objects.filter(
        is_active=True,
        product__is_active=True,
        stock_quantity__gt=0
    ).filter(
        Q(product__name__icontains=query) | Q(sku__icontains=query)
    ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute')[:20]  # Ko'proq variant — guruhlashdan keyin bir nechta mahsulot chiqadi
    
    data = []
    for v in variants:
        # Get color from attribute values
        color = ''
        for av in v.attribute_values.all():
            if av.attribute.name == 'color':
                color = av.value
                break
        
        data.append({
            'id': v.id,  # Variant ID
            'product_id': v.product.id,
            'name': v.product.name,
            'variant_name': str(v),
            'sku': v.sku,
            'price': str(v.price),
            'cost_price': str(v.cost_price) if v.cost_price else '0',
            'category': v.product.category.name if v.product.category else '',
            'category_id': v.product.category.id if v.product.category else None,
            'color': color,
            'description': v.product.description or '',
            'stock': v.stock_quantity,
        })
    
    # Sort by name to show similar products together
    data.sort(key=lambda x: x['name'])
    
    return JsonResponse({'products': data})


@csrf_exempt
def get_colors_by_category(request):
    """Kategoriya bo'yicha ranglarni qaytarish"""
    category_id = request.GET.get('category_id')
    
    if not category_id:
        return JsonResponse({'colors': []})
    
    try:
        category = Category.objects.get(pk=category_id)
        # Get colors from variants that belong to products in this category
        color_attr = Attribute.objects.filter(name='color').first()
        
        if color_attr:
            # Get all variants for products in this category that have color attribute
            variants = ProductVariant.objects.filter(
                product__category=category,
                is_active=True,
                product__is_active=True
            ).prefetch_related('attribute_values__attribute')
            
            # Extract unique color values
            colors = set()
            for variant in variants:
                for attr_value in variant.attribute_values.all():
                    if attr_value.attribute.name == 'color':
                        colors.add(attr_value.value)
            
            colors = sorted(list(colors))
        else:
            colors = []
        
        return JsonResponse({'colors': colors})
    except Category.DoesNotExist:
        return JsonResponse({'colors': []})


def get_product_variants_json(request, product_id):
    """Mahsulotning barcha variantlari (rang, narx, qoldiq) — create_product da mavjud variantlarni ko'rsatish uchun"""
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        return JsonResponse({'variants': [], 'product_name': ''})
    variants = product.variants.filter(is_active=True).select_related('product').prefetch_related('attribute_values__attribute')
    data = []
    for v in variants:
        color = ''
        for av in v.attribute_values.all():
            if av.attribute.name == 'color':
                color = av.value
                break
        data.append({
            'id': v.id,
            'color': color,
            'price': str(v.price),
            'stock': v.stock_quantity,
            'sku': v.sku,
        })
    return JsonResponse({'variants': data, 'product_name': product.name})


@csrf_exempt
def search_customers_autocomplete(request):
    """Autocomplete uchun mijozlarni qidirish"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 1:
        return JsonResponse({'customers': []})
    
    customers = Customer.objects.filter(
        Q(name__icontains=query) | Q(phone__icontains=query)
    ).order_by('name')[:10]  # Limit to 10 for autocomplete
    
    data = [{
        'id': c.id,
        'name': c.name,
        'phone': c.phone or '',
    } for c in customers]
    
    return JsonResponse({'customers': data})


# @login_required
def hide(request):
    """Hide page"""
    return render(request, 'store/hide.html')