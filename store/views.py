from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Count, Prefetch
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.urls import reverse_lazy
from .models import Product, Category, Sale, SaleItem, Customer, ProductVariant, Attribute, AttributeValue, Market, UserProfile, ExchangeRate
from .forms import RegisterForm
from decimal import Decimal, InvalidOperation
from django.utils import timezone
import json
import logging
import uuid

logger = logging.getLogger('store')

DEFAULT_USD_RATE = Decimal('12500')


def _render_product_created_for_sale(request, variant):
    """Sotish sahifasidan modal orqali mahsulot qo'shilganda: redirect o'rniga postMessage uchun sahifa."""
    name = getattr(variant.product, 'name', '') or str(variant)
    price = str(variant.price)
    unit = getattr(variant.product, 'unit', None) or 'dona'
    stock = 999999 if getattr(variant, 'unlimited_stock', False) else getattr(variant, 'stock_quantity', 0)
    return render(request, 'store/product_created_for_sale.html', {
        'variant_id': variant.id,
        'variant_name': name,
        'price': price,
        'unit': unit,
        'stock': stock,
    })


def get_current_usd_rate(market):
    """Joriy kunlik dollar kursi (1 USD = X so'm). Avval market bo'yicha, keyin global, keyin default."""
    today = timezone.localdate()
    # Avval shu market uchun bugun yoki eng so'nggi kurs
    if market:
        r = ExchangeRate.objects.filter(market=market).filter(date__lte=today).order_by('-date').first()
        if r:
            return r.rate
    # Global kurs (market=None)
    r = ExchangeRate.objects.filter(market__isnull=True).filter(date__lte=today).order_by('-date').first()
    if r:
        return r.rate
    return DEFAULT_USD_RATE


def get_request_market(request):
    """Foydalanuvchi biriktirilgan market (kirish talab qilinadi)."""
    if not request.user.is_authenticated:
        return None
    if not hasattr(request.user, 'profile'):
        return None
    return getattr(request.user.profile, 'market', None)


def user_is_manager(user) -> bool:
    """Foydalanuvchi menejer (yoki superuser/staff) ekanini tekshiradi."""
    if not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and getattr(profile, 'is_manager', False))


def require_market(view_func):
    """Kirish va market borligini tekshiradi; market bo'lmasa no_market sahifasiga yo'naltiradi."""
    @login_required
    def wrapper(request, *args, **kwargs):
        market = get_request_market(request)
        if market is None:
            return redirect('store:no_market')
        return view_func(request, *args, **kwargs)
    return wrapper


def login_view(request):
    """Login sahifasi — Django LoginView"""
    if request.user.is_authenticated:
        market = get_request_market(request)
        if market:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return redirect('store:no_market')
    return LoginView.as_view(
        template_name='store/login.html',
        redirect_authenticated_user=True,
    )(request)


def register_view(request):
    """Ro'yxatdan o'tish: login, parol, ixtiyoriy market nomi. Yangi user is_active=False — admin tasdiqlashi kerak."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Admin paneldan active qilguncha tizimga kira olmaydi
            user.save()
            market_name = (form.cleaned_data.get('market_name') or '').strip()
            market = None
            if market_name:
                market = Market.objects.create(name=market_name)
            profile = user.profile  # signal tomonidan yaratilgan
            if market:
                profile.market = market
                # Yangi market yaratgan foydalanuvchini avtomatik ravishda manager qilamiz
                profile.role = profile.ROLE_MANAGER
            profile.save()
            # Log in qilmaymiz — admin tasdiqlagach login qiladi
            messages.success(
                request,
                'Ro\'yxatdan o\'tdingiz. Admin hisobingizni tasdiqlagandan so\'ng tizimga kiring.'
            )
            return redirect('store:login')
        else:
            messages.error(request, 'Formani to\'g\'ri to\'ldiring.')
    else:
        form = RegisterForm()
    return render(request, 'store/register.html', {'form': form})


def logout_view(request):
    """Chiqish"""
    auth_logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


def no_market_view(request):
    """Market biriktirilmagan — admin kutish"""
    if not request.user.is_authenticated:
        return redirect('store:login')
    market = get_request_market(request)
    if market is not None:
        return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, 'store/no_market.html')


@require_market
def product_list(request):
    """Mahsulotlar ro'yxati — mahsulot bo'yicha guruhlash, har birida ranglar va qoldiq"""
    market = get_request_market(request)
    variants = ProductVariant.objects.filter(
        is_active=True, product__is_active=True,
        product__category__market=market
    ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute')
    categories = Category.objects.filter(market=market)
    
    category_id = request.GET.get('category')
    if category_id:
        variants = variants.filter(product__category_id=category_id)
    search_query = request.GET.get('search')
    if search_query:
        variants = variants.filter(
            Q(product__name__icontains=search_query) | Q(sku__icontains=search_query)
        )
    usd_rate = get_current_usd_rate(market)
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        try:
            min_uzs = Decimal(min_price)
            variants = variants.filter(price__gte=min_uzs / usd_rate)
        except (ValueError, TypeError):
            pass
    if max_price:
        try:
            max_uzs = Decimal(max_price)
            variants = variants.filter(price__lte=max_uzs / usd_rate)
        except (ValueError, TypeError):
            pass
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
    list_products = list(products_with_variants.values())

    # 100 tadan oshsa pagination
    paginator = Paginator(list_products, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    query_dict = request.GET.copy()
    if 'page' in query_dict:
        query_dict.pop('page')
    query_string = query_dict.urlencode()

    context = {
        'products_with_variants': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'categories': categories,
        'selected_category': int(category_id) if category_id else None,
        'search_query': search_query or '',
        'usd_rate': usd_rate,
    }
    return render(request, 'store/product_list.html', context)


@require_market
def product_detail(request, pk):
    """Mahsulot tafsilotlari — bitta variant bo'yicha kiriladi, barcha variantlar (rang, narx, qoldiq) ko'rsatiladi"""
    market = get_request_market(request)
    try:
        variant = ProductVariant.objects.get(pk=pk, is_active=True, product__is_active=True, product__category__market=market)
        product = variant.product
        all_variants = product.variants.filter(is_active=True).select_related('product').prefetch_related('attribute_values__attribute').order_by('pk')
        profit = variant.price - variant.cost_price
        profit_percent = 0
        if variant.cost_price > 0:
            profit_percent = (profit / variant.cost_price) * 100
        usd_rate = get_current_usd_rate(market)
        context = {
            'variant': variant,
            'product': product,
            'all_variants': all_variants,
            'profit': profit,
            'profit_percent': profit_percent,
            'usd_rate': usd_rate,
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
            usd_rate = get_current_usd_rate(market)
            context = {
                'variant': variant,
                'product': product,
                'all_variants': all_variants,
                'profit': profit,
                'profit_percent': profit_percent,
                'usd_rate': usd_rate,
            }
        else:
            usd_rate = get_current_usd_rate(market)
            context = {
                'variant': None,
                'product': product,
                'all_variants': [],
                'profit': 0,
                'profit_percent': 0,
                'usd_rate': usd_rate,
            }
        logger.info(f"Product detail viewed: {product}")
        return render(request, 'store/product_detail.html', context)


@require_market
@require_http_methods(["POST"])
def upload_product_image(request, pk):
    """Mahsulotga rasm yuklash (Product.image). Faqat shu market mahsuloti uchun."""
    market = get_request_market(request)
    product = get_object_or_404(Product, pk=pk, is_active=True, category__market=market)

    image = request.FILES.get('image')
    if not image:
        return JsonResponse({'success': False, 'error': 'Rasm topilmadi.'}, status=400)

    content_type = getattr(image, 'content_type', '') or ''
    if not content_type.startswith('image/'):
        return JsonResponse({'success': False, 'error': 'Faqat rasm fayl yuklash mumkin.'}, status=400)

    product.image = image
    product.save(update_fields=['image'])
    return JsonResponse({'success': True, 'image_url': product.image.url})


@require_market
def delete_product(request, pk):
    """Mahsulotni o'chirish"""
    market = get_request_market(request)
    if request.method != 'POST':
        return redirect('store:product_list_old')
    
    # Try to get ProductVariant first (shu market)
    try:
        variant = ProductVariant.objects.get(pk=pk, product__category__market=market)
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


def _create_product_form_data(post):
    """Validatsiya xatosi bo'lganda formani to'ldirish uchun POST dan ma'lumot."""
    return {
        'name': post.get('name', ''),
        'category': post.get('category', ''),
        'new_category': post.get('new_category', ''),
        'color': post.get('color', ''),
        'new_color': post.get('new_color', ''),
        'unit': post.get('unit', 'dona'),
        'sku': post.get('sku', ''),
        'price': post.get('price', ''),
        'price_currency': post.get('price_currency', 'USD'),
        'cost_price': post.get('cost_price', ''),
        'cost_currency': post.get('cost_currency', 'USD'),
        'stock_quantity': post.get('stock_quantity', ''),
        'unlimited_stock': post.get('unlimited_stock') == 'on',
        'quantity_received': post.get('quantity_received', ''),
        'existing_product_id': post.get('existing_product_id', ''),
        'edit_variant_id': post.get('edit_variant_id', ''),
        'description': post.get('description', ''),
        'parametr': post.getlist('parametr'),
    }


@require_market
@xframe_options_sameorigin
def create_product(request):
    """Yangi mahsulot qo'shish (yoki mavjud mahsulotni o'zgartirish / yangi variant qo'shish). iframe da (sotish sahifasidan) ochilishi uchun SAMEORIGIN."""
    market = get_request_market(request)
    categories = Category.objects.filter(market=market)
    # Get unique colors from existing variants (all categories)
    color_attr = Attribute.objects.filter(name='color').first()
    if color_attr:
        colors = AttributeValue.objects.filter(attribute=color_attr).values_list('value', flat=True).distinct().order_by('value')
    else:
        colors = []
    return_sale_param = request.GET.get('return_sale') or request.POST.get('return_sale')
    
    initial_product = None
    if request.method == 'GET':
        product_id = request.GET.get('product_id')
        variant_id = request.GET.get('variant_id')
        if product_id:
            try:
                p = Product.objects.get(pk=int(product_id), is_active=True, category__market=market)
                initial_product = {'id': p.id, 'name': p.name, 'category_id': p.category_id, 'unit': getattr(p, 'unit', 'dona'), 'description': (p.description or '')}
                if variant_id:
                    v = ProductVariant.objects.filter(
                        pk=int(variant_id), product=p, is_active=True
                    ).prefetch_related('attribute_values__attribute').first()
                    if v:
                        color = ''
                        parametrlar = []
                        for av in v.attribute_values.all():
                            if av.attribute.name == 'color':
                                color = av.value
                            elif av.attribute.name == 'parametr':
                                parametrlar.append(av.value)
                        usd_rate = get_current_usd_rate(market)
                        # Narx bazada USD da — forma $ da ko'rsatamiz
                        initial_product['variant'] = {
                            'id': v.id,
                            'color': color,
                            'parametrlar': parametrlar,
                            'price': float(v.price),
                            'cost_price': float(v.cost_price or 0),
                            'price_usd': round(float(v.price), 2),
                            'cost_price_usd': round(float(v.cost_price or 0), 2),
                            'stock_quantity': max(0, int(v.stock_quantity)),
                            'unlimited_stock': getattr(v, 'unlimited_stock', False),
                            'unit': getattr(v.product, 'unit', 'dona'),
                        }
            except (Product.DoesNotExist, ValueError):
                pass
    
    if request.method == 'POST':
        try:
            edit_variant_id = request.POST.get('edit_variant_id', '').strip()
            if edit_variant_id:
                # Variantni va Productni yangilash (nom, kategoriya, birlik, tavsif, rang, narx, miqdor, cheklanmagan, rasm)
                try:
                    vid = int(edit_variant_id)
                    variant = ProductVariant.objects.select_related('product').get(
                        pk=vid, is_active=True, product__category__market=market
                    )
                    product = variant.product
                    usd_rate = get_current_usd_rate(market)
                    # Product (umumiy) maydonlari — barcha variantlar uchun bir xil
                    name = request.POST.get('name', '').strip()
                    category_id = request.POST.get('category')
                    new_category_name = request.POST.get('new_category', '').strip()
                    unit = request.POST.get('unit', 'dona')
                    description = request.POST.get('description', '')
                    if name:
                        product.name = name
                    if unit in ('dona', 'metr'):
                        product.unit = unit
                    if description is not None:
                        product.description = description or ''
                    if new_category_name:
                        category, _ = Category.objects.get_or_create(
                            market=market, name=new_category_name, defaults={'description': ''}
                        )
                        product.category = category
                    elif category_id:
                        try:
                            product.category = Category.objects.get(pk=category_id, market=market)
                        except Category.DoesNotExist:
                            pass
                    product.save(update_fields=['name', 'category', 'unit', 'description'])
                    # Variant maydonlari
                    price = request.POST.get('price')
                    price_currency = request.POST.get('price_currency', 'USD')
                    cost_price = request.POST.get('cost_price', 0)
                    cost_currency = request.POST.get('cost_currency', 'USD')
                    stock_quantity = request.POST.get('stock_quantity', '').strip()
                    unlimited_stock_edit = (request.POST.get('unlimited_stock') == 'on')
                    if not unlimited_stock_edit and (not stock_quantity or int(stock_quantity or 0) < 1):
                        messages.error(request, 'Iltimos sonini kiriting yoki «Cheklanmagan» ni belgilang!')
                        return render(request, 'store/create_product.html', {
                            'categories': categories, 'colors': colors, 'return_sale': return_sale_param,
                            'form_data': _create_product_form_data(request.POST), 'form_post_stock_error': True
                        })
                    color = request.POST.get('color', '').strip()
                    new_color = request.POST.get('new_color', '').strip()
                    final_color = (new_color or color or '').strip()
                    # Rangni yangilash
                    if final_color:
                        color_attr, _ = Attribute.objects.get_or_create(
                            name='color',
                            defaults={'display_name': 'Rang'}
                        )
                        color_value, _ = AttributeValue.objects.get_or_create(
                            attribute=color_attr,
                            value=final_color.upper()
                        )
                        # Eski rang(lar)ni olib tashlash
                        old_color_values = list(
                            variant.attribute_values.filter(attribute=color_attr)
                        )
                        for ov in old_color_values:
                            variant.attribute_values.remove(ov)
                        variant.attribute_values.add(color_value)
                    # Parametrlar yangilash
                    parametr_list = [x.strip() for x in request.POST.getlist('parametr') if x and x.strip()]
                    parametr_attr, _ = Attribute.objects.get_or_create(
                        name='parametr',
                        defaults={'display_name': 'Parametr'}
                    )
                    old_param = list(variant.attribute_values.filter(attribute=parametr_attr))
                    for op in old_param:
                        variant.attribute_values.remove(op)
                    for pval in parametr_list[:5]:
                        p_av, _ = AttributeValue.objects.get_or_create(
                            attribute=parametr_attr,
                            value=pval.upper()
                        )
                        variant.attribute_values.add(p_av)
                    # Narx, tannarx, miqdor — bazada USD
                    if price and str(price).strip():
                        p_val = Decimal(str(price))
                        if price_currency == 'UZS':
                            p_val = p_val / Decimal(usd_rate)
                        variant.price = p_val
                    if cost_price is not None and str(cost_price).strip() != '':
                        c_val = Decimal(str(cost_price))
                        if cost_currency == 'UZS':
                            c_val = c_val / Decimal(usd_rate)
                        variant.cost_price = c_val
                    variant.unlimited_stock = unlimited_stock_edit
                    if unlimited_stock_edit:
                        # Cheklanmagan: miqdor hisobga olinmaydi
                        pass
                    elif stock_quantity is not None and str(stock_quantity).strip() != '':
                        variant.stock_quantity = max(0, int(float(stock_quantity)))
                    image = request.FILES.get('image')
                    if image:
                        variant.image = image
                    update_fields = ['price', 'cost_price', 'stock_quantity', 'unlimited_stock']
                    if image:
                        update_fields.append('image')
                    variant.save(update_fields=update_fields)
                    messages.success(request, f'Variant yangilandi: {variant.product.name}')
                    if request.GET.get('return_sale') or request.POST.get('return_sale'):
                        return _render_product_created_for_sale(request, variant)
                    return redirect('store:product_detail', pk=variant.pk)
                except (ProductVariant.DoesNotExist, ValueError) as e:
                    logger.warning(f"Edit variant failed: {e}")
                    messages.error(request, 'Variant topilmadi.')
            
            name = request.POST.get('name')
            category_id = request.POST.get('category')
            new_category_name = request.POST.get('new_category', '').strip()
            color = request.POST.get('color', '').strip()
            new_color = request.POST.get('new_color', '').strip()
            cost_price_raw = request.POST.get('cost_price', '').strip()
            cost_currency = request.POST.get('cost_currency', 'USD')
            price = request.POST.get('price')
            price_currency = request.POST.get('price_currency', 'USD')
            raw_stock = (request.POST.get('stock_quantity', '') or '').strip()
            stock_quantity = raw_stock or 0
            unlimited_stock = (request.POST.get('unlimited_stock') == 'on')  # faqat checkbox belgilanganda cheklanmagan
            quantity_received = request.POST.get('quantity_received', 0)  # For existing products
            description = request.POST.get('description', '')
            sku = request.POST.get('sku', '')
            image = request.FILES.get('image')
            
            # Validation
            if not name:
                messages.error(request, 'Mahsulot nomi kiritilishi shart!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            
            # Check if product with same name already exists
            existing_product_id = request.POST.get('existing_product_id', '').strip()
            logger.info(f"Creating product - name: {name}, existing_product_id: '{existing_product_id}'")
            
            if existing_product_id and existing_product_id != '' and existing_product_id != '0':
                # Existing product selected - create new variant with new color
                # existing_product_id can be Product.id (from old API) or ProductVariant.id (from search_products_autocomplete)
                try:
                    pid = int(existing_product_id)
                    try:
                        existing_product = Product.objects.get(pk=pid, category__market=market)
                    except Product.DoesNotExist:
                        variant = ProductVariant.objects.get(pk=pid, product__category__market=market)
                        existing_product = variant.product
                    
                    # Rang ixtiyoriy
                    final_color = (new_color or color or '').strip()
                    color_value = None
                    if final_color:
                        color_attr, _ = Attribute.objects.get_or_create(
                            name='color',
                            defaults={'display_name': 'Rang'}
                        )
                        color_value, _ = AttributeValue.objects.get_or_create(
                            attribute=color_attr,
                            value=final_color.upper()
                        )
                    
                    # Rang berilgan bo'lsa, shu rangdagi variant bormi tekshiramiz
                    existing_variant = None
                    if color_value:
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
                            return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
                        existing_variant.stock_quantity = max(0, existing_variant.stock_quantity) + new_quantity
                        existing_variant.save()
                        logger.info(f"Variant stock updated: {existing_variant}, Added: {new_quantity}, New total: {existing_variant.stock_quantity}")
                        messages.success(request, f'Mahsulot soni yangilandi: {existing_variant} (+{new_quantity} dona, Jami: {existing_variant.stock_quantity} dona)')
                        if request.GET.get('return_sale') or request.POST.get('return_sale'):
                            return _render_product_created_for_sale(request, existing_variant)
                        return redirect('store:product_detail', pk=existing_variant.pk)
                    else:
                        # Yangi variant — narx bazada USD da saqlanadi
                        usd_rate = get_current_usd_rate(market)
                        first_variant = existing_product.variants.filter(is_active=True).first()
                        if price and str(price).strip() and float(str(price)) > 0:
                            if price_currency == 'USD':
                                price_usd = Decimal(str(price))
                            else:
                                price_usd = Decimal(str(price)) / Decimal(usd_rate)
                        elif first_variant:
                            price_usd = first_variant.price
                        else:
                            messages.error(request, 'Sotish narxi kiritilishi shart!')
                            return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
                        # Yangi variant: miqdor yoki Cheklanmagan majburiy (0 bo'lmasin)
                        if not unlimited_stock and (not stock_quantity or int(stock_quantity) < 1):
                            messages.error(request, 'Iltimos sonini kiriting yoki «Cheklanmagan» ni belgilang!')
                            return render(request, 'store/create_product.html', {
                                'categories': categories, 'colors': colors, 'return_sale': return_sale_param,
                                'form_data': _create_product_form_data(request.POST), 'form_post_stock_error': True
                            })
                        # Tannarx (ixtiyoriy) — formadan yoki birinchi variantdan
                        cost_price_usd = first_variant.cost_price if first_variant else Decimal('0')
                        cost_price_raw = request.POST.get('cost_price', '').strip()
                        cost_currency = request.POST.get('cost_currency', 'USD')
                        if cost_price_raw:
                            try:
                                if cost_currency == 'USD':
                                    cost_price_usd = Decimal(str(cost_price_raw))
                                else:
                                    cost_price_usd = Decimal(str(cost_price_raw)) / Decimal(usd_rate)
                                if cost_price_usd < 0:
                                    cost_price_usd = Decimal('0')
                            except (ValueError, TypeError, InvalidOperation):
                                pass
                        
                        # Create new variant — kod model save() da avtomatik: nom 3 harf + raqam (raz-001, led-002)
                        new_variant = ProductVariant(
                            product=existing_product,
                            cost_price=cost_price_usd,
                            price=price_usd,
                            stock_quantity=max(0, int(stock_quantity) if stock_quantity else int(quantity_received) if quantity_received else 0),
                            unlimited_stock=unlimited_stock,
                            image=image
                        )
                        new_variant.save()
                        if color_value:
                            new_variant.attribute_values.add(color_value)
                        # Parametrlar (1tali, dumaloq, kotta va h.k.)
                        parametr_list = [x.strip() for x in request.POST.getlist('parametr') if x and x.strip()]
                        if parametr_list:
                            parametr_attr, _ = Attribute.objects.get_or_create(
                                name='parametr',
                                defaults={'display_name': 'Parametr'}
                            )
                            for pval in parametr_list[:5]:
                                p_av, _ = AttributeValue.objects.get_or_create(
                                    attribute=parametr_attr,
                                    value=pval.upper()
                                )
                                new_variant.attribute_values.add(p_av)
                        
                        logger.info(f"New variant created: {new_variant} (SKU: {new_variant.sku})")
                        msg_suffix = f' ({final_color.upper()})' if final_color else ''
                        messages.success(request, f'Yangi variant muvaffaqiyatli qo\'shildi: {existing_product.name}{msg_suffix}')
                        if request.GET.get('return_sale') or request.POST.get('return_sale'):
                            return _render_product_created_for_sale(request, new_variant)
                        return redirect('store:product_detail', pk=new_variant.pk)
                        
                except (Product.DoesNotExist, ProductVariant.DoesNotExist, ValueError) as e:
                    logger.error(f"Error with existing product: {str(e)}")
                    messages.error(request, 'Mahsulot topilmadi!')
                    return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            
            # Validate price before conversion
            if not price or price == '0' or price == '':
                messages.error(request, 'Sotish narxi kiritilishi shart!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            
            # Note: We allow products with the same name (e.g., "Led 20W oq" and "Led 20W sariq")
            # Each product will have a unique SKU based on ID
            
            # Handle category - create new if provided
            category = None
            if new_category_name:
                # Create new category (market bilan)
                category, created = Category.objects.get_or_create(
                    market=market,
                    name=new_category_name,
                    defaults={'description': ''}
                )
                logger.info(f"New category created: {category.name}")
            elif category_id:
                try:
                    category = Category.objects.get(pk=category_id, market=market)
                except Category.DoesNotExist:
                    messages.error(request, 'Noto\'g\'ri kategoriya!')
                    return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            else:
                messages.error(request, 'Kategoriya tanlanishi yoki yangi kategoriya nomi kiritilishi shart!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            
            # Narx bazada USD da saqlanadi — formadan USD yoki so'm ni USD ga o'tkazamiz
            usd_rate = get_current_usd_rate(market)
            try:
                cost_price = Decimal('0')
                cost_price_raw = request.POST.get('cost_price', '').strip()
                cost_currency = request.POST.get('cost_currency', 'USD')
                if cost_price_raw:
                    if cost_currency == 'USD':
                        cost_price = Decimal(str(cost_price_raw))
                    else:
                        cost_price = Decimal(str(cost_price_raw)) / Decimal(usd_rate)
                    if cost_price < 0:
                        cost_price = Decimal('0')

                if price_currency == 'USD':
                    price = Decimal(str(price))
                else:
                    price = Decimal(str(price)) / Decimal(usd_rate)
                
                if price < Decimal('0.01'):
                    messages.error(request, 'Sotish narxi 0.01 dan katta bo\'lishi kerak!')
                    return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            except (ValueError, TypeError, Exception) as e:
                logger.error(f"Error converting price: {str(e)}")
                messages.error(request, f'Narx noto\'g\'ri formatda kiritilgan!')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            
            # Handle color va parametrlar - Attribute/AttributeValue
            final_color = (new_color or color or '').strip()
            attribute_values = []
            if final_color:
                color_attr, _ = Attribute.objects.get_or_create(
                    name='color',
                    defaults={'display_name': 'Rang'}
                )
                color_value, _ = AttributeValue.objects.get_or_create(
                    attribute=color_attr,
                    value=final_color.upper()
                )
                attribute_values.append(color_value)
            # Parametrlar (5 tagacha: 1tali, dumaloq, kotta va h.k.)
            parametr_list = [x.strip() for x in request.POST.getlist('parametr') if x and x.strip()]
            if parametr_list:
                parametr_attr, _ = Attribute.objects.get_or_create(
                    name='parametr',
                    defaults={'display_name': 'Parametr'}
                )
                for pval in parametr_list[:5]:
                    p_av, _ = AttributeValue.objects.get_or_create(
                        attribute=parametr_attr,
                        value=pval.upper()
                    )
                    attribute_values.append(p_av)
            
            unit = request.POST.get('unit', 'dona')
            if unit not in ('dona', 'metr'):
                unit = 'dona'
            # Yangi mahsulot: miqdor yoki Cheklanmagan majburiy (0 bo'lmasin)
            if not unlimited_stock and (not stock_quantity or int(stock_quantity) < 1):
                messages.error(request, 'Iltimos sonini kiriting yoki «Cheklanmagan» ni belgilang!')
                return render(request, 'store/create_product.html', {
                    'categories': categories, 'colors': colors, 'return_sale': return_sale_param,
                    'form_data': _create_product_form_data(request.POST), 'form_post_stock_error': True
                })
            # Create Product (asosiy mahsulot)
            product = Product(
                name=name,
                category=category,
                unit=unit,
                description=description
            )
            
            if image:
                product.image = image
            
            try:
                product.save()
                logger.info(f"Product created: {product.name} (ID: {product.id})")
                
                # Create ProductVariant — kod model save() da avtomatik (nom 3 harf + raqam)
                variant = ProductVariant(
                    product=product,
                    sku=None,
                    cost_price=cost_price,
                    price=price,
                    stock_quantity=max(0, int(stock_quantity) if stock_quantity else 0),
                    unlimited_stock=unlimited_stock,
                    image=image  # Variant uchun ham rasm
                )
                
                variant.save()
                
                # Add attribute values to variant (after save)
                if attribute_values:
                    variant.attribute_values.set(attribute_values)
                
                logger.info(f"ProductVariant created successfully: {variant} (SKU: {variant.sku}, ID: {variant.id})")
                messages.success(request, f'Mahsulot muvaffaqiyatli qo\'shildi: {product.name}')
                if request.GET.get('return_sale') or request.POST.get('return_sale'):
                    return _render_product_created_for_sale(request, variant)
                return redirect('store:product_detail', pk=variant.pk)
            except Exception as save_error:
                logger.error(f"Error saving product: {str(save_error)}")
                messages.error(request, f'Mahsulotni saqlashda xatolik: {str(save_error)}')
                return render(request, 'store/create_product.html', {'categories': categories, 'colors': colors, 'return_sale': return_sale_param})
            
        except Exception as e:
            logger.error(f"Error creating product: {str(e)}")
            messages.error(request, f'Xatolik: {str(e)}')
    
    context = {'categories': categories, 'colors': colors}
    if initial_product is not None:
        context['initial_product'] = initial_product
    context['return_sale'] = return_sale_param
    return render(request, 'store/create_product.html', context)


@require_market
@csrf_exempt
def create_category_ajax(request):
    """AJAX orqali kategoriya qo'shish"""
    market = get_request_market(request)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            category_name = data.get('name', '').strip()
            
            if not category_name:
                return JsonResponse({'error': 'Kategoriya nomi kiritilishi shart!'}, status=400)
            
            category, created = Category.objects.get_or_create(
                market=market,
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


@require_market
@csrf_exempt
def create_sale(request):
    """Yangi sotuv yaratish"""
    market = get_request_market(request)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            customer_name = data.get('customer_name', '')
            customer_phone = data.get('customer_phone', '')
            payment_method = data.get('payment_method', 'cash')
            payment_cash_usd = data.get('payment_cash_usd')
            payment_card_usd = data.get('payment_card_usd')
            items = data.get('items', [])
            
            if not items:
                return JsonResponse({'error': 'Savat bo\'sh'}, status=400)
            
            # Bir vaqtda mobil va kompyuter bir xil mahsulotni sotganda konflikt bo'lmasligi uchun
            # tranzaksiyada variantlarni qulflaymiz (select_for_update) — faqat shu market mahsulotlari
            with transaction.atomic():
                variant_ids = [int(item_data['product_id']) for item_data in items]
                variants_dict = {
                    v.id: v for v in ProductVariant.objects.select_for_update().filter(
                        pk__in=variant_ids,
                        product__category__market=market
                    )
                }
                if len(variants_dict) != len(variant_ids):
                    return JsonResponse({'error': 'Mahsulot topilmadi'}, status=400)
                
                # Zaxirani tekshirish (qulflangan zaxira bo'yicha)
                for item_data in items:
                    vid = int(item_data['product_id'])
                    quantity = int(item_data['quantity'])
                    variant = variants_dict[vid]
                    if not getattr(variant, 'unlimited_stock', False) and variant.stock_quantity < quantity:
                        return JsonResponse({
                            'error': f'{variant} uchun yetarli mahsulot yo\'q (omborda: {variant.stock_quantity} dona)'
                        }, status=400)
                
                # Mijoz (shu market uchun)
                customer = None
                if customer_name:
                    if customer_phone:
                        customer, created = Customer.objects.get_or_create(
                            market=market,
                            phone=customer_phone,
                            defaults={'name': customer_name}
                        )
                        if not created and customer.name != customer_name:
                            customer.name = customer_name
                            customer.save()
                    else:
                        customer, created = Customer.objects.get_or_create(
                            market=market,
                            name=customer_name,
                            defaults={'phone': ''}
                        )
                
                usd_rate = data.get('usd_rate')
                sale_kwargs = dict(
                    market=market,
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
                
                total = Decimal('0')
                for item_data in items:
                    variant = variants_dict[int(item_data['product_id'])]
                    quantity = int(item_data['quantity'])
                    unit_price = Decimal(str(item_data['price']))
                    
                    SaleItem.objects.create(
                        sale=sale,
                        variant=variant,
                        quantity=quantity,
                        unit_price=unit_price
                    )
                    if not getattr(variant, 'unlimited_stock', False):
                        variant.stock_quantity = max(0, variant.stock_quantity - quantity)
                        variant.save(update_fields=['stock_quantity'])
                    total += unit_price * quantity
                
                # Chegirma foizini hisobga olish (agar bo'lsa)
                original_total = total
                discount_percent_raw = data.get('discount_percent')
                dp = Decimal('0')
                if discount_percent_raw is not None and discount_percent_raw != '':
                    try:
                        dp = Decimal(str(discount_percent_raw))
                    except (ValueError, TypeError, InvalidOperation):
                        dp = Decimal('0')
                if dp > 0:
                    if dp >= Decimal('100'):
                        dp = Decimal('99.99')
                    factor = (Decimal('100') - dp) / Decimal('100')
                    total = (total * factor).quantize(Decimal('0.01'))
                    sale.discount_percent = dp
                    sale.original_total_amount = original_total
                else:
                    sale.discount_percent = Decimal('0')
                    sale.original_total_amount = original_total
                
                sale.total_amount = total
                # To'lov bo'linmasi (USD) — mixed bo'lsa kiritiladi, aks holda avtomatik
                cash_amt = Decimal('0')
                card_amt = Decimal('0')
                if payment_method == 'mixed':
                    try:
                        cash_amt = Decimal(str(payment_cash_usd or '0'))
                        card_amt = Decimal(str(payment_card_usd or '0'))
                    except (ValueError, TypeError):
                        cash_amt = Decimal('0')
                        card_amt = Decimal('0')
                    # agar noto'g'ri bo'lsa: hammasini karta deb olamiz
                    if cash_amt < 0 or card_amt < 0 or (cash_amt + card_amt) == 0:
                        cash_amt = Decimal('0')
                        card_amt = total
                    # yig'indi jami summadan oshib ketsa yoki kam bo'lsa: cardni jami bo'yicha to'g'rilaymiz
                    if cash_amt > total:
                        cash_amt = total
                        card_amt = Decimal('0')
                    if cash_amt + card_amt != total:
                        card_amt = max(Decimal('0'), total - cash_amt)
                elif payment_method == 'cash':
                    cash_amt = total
                    card_amt = Decimal('0')
                elif payment_method == 'card':
                    cash_amt = Decimal('0')
                    card_amt = total

                sale.payment_cash_amount = cash_amt
                sale.payment_card_amount = card_amt
                sale.save(update_fields=['total_amount', 'original_total_amount', 'discount_percent', 'payment_cash_amount', 'payment_card_amount'])
            
            logger.info(f"Sale created: {sale.id}, Total: ${total} USD")
            return JsonResponse({'success': True, 'sale_id': sale.id})
            
        except Exception as e:
            logger.error(f"Error creating sale: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)
    
    categories = Category.objects.filter(market=market)
    
    # Top 8 eng ko'p sotilgan variantlar (1-o'rinda eng ko'p sotilgan)
    # Tez tanlov uchun faqat mavjud (stokda bor yoki cheklanmagan) variantlar
    from django.db.models import Q
    top_sold_variants = ProductVariant.objects.filter(
        is_active=True,
        product__is_active=True,
        product__category__market=market
    ).filter(
        Q(unlimited_stock=True) | Q(stock_quantity__gt=0)
    ).annotate(
        total_sold=Sum('saleitem__quantity')
    ).filter(
        total_sold__gt=0
    ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute').order_by('-total_sold')[:8]
    
    if not top_sold_variants.exists():
        top_sold_variants = ProductVariant.objects.filter(
            is_active=True,
            product__is_active=True,
            product__category__market=market
        ).filter(
            Q(unlimited_stock=True) | Q(stock_quantity__gt=0)
        ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute').order_by('-created_at')[:8]
    
    current_usd_rate = get_current_usd_rate(market)
    # JSON da narx USD da — $ o'zgarmasligi uchun, so'm faqat kurs bo'yicha hisoblanadi
    top_products_json = []
    for v in top_sold_variants:
        color = ''
        for av in v.attribute_values.all():
            if av.attribute.name == 'color':
                color = av.value
                break
        top_products_json.append({
            'id': v.id,
            'product_id': v.product.id,
            'name': v.product.name,
            'variant_name': str(v),
            'color': color,
            'sku': v.sku,
            'price': str(v.price),
            'stock': v.stock_quantity,
            'unlimited_stock': v.unlimited_stock,
            'unit': v.product.unit,
        })

    # Mavjud sotuvga mahsulot qo'shish rejimi (append_to_sale=? query parametri)
    append_sale_id = request.GET.get('append_to_sale')
    valid_append_sale_id = None
    if append_sale_id:
        try:
            candidate_id = int(append_sale_id)
            if Sale.objects.filter(pk=candidate_id, market=market).exists():
                valid_append_sale_id = candidate_id
        except (TypeError, ValueError):
            valid_append_sale_id = None

    # Mavjud sotuvni tahrirlash rejimi (edit_sale=? query parametri)
    edit_sale_id = request.GET.get('edit_sale')
    valid_edit_sale_id = None
    edit_sale_items = []
    if edit_sale_id:
        try:
            candidate_id = int(edit_sale_id)
            sale_for_edit = Sale.objects.filter(pk=candidate_id, market=market).prefetch_related(
                Prefetch('items', queryset=SaleItem.objects.select_related('variant__product'))
            ).first()
            if sale_for_edit:
                valid_edit_sale_id = sale_for_edit.id
                for item in sale_for_edit.items.all():
                    product = item.variant.product if item.variant else getattr(item, 'product_old', None)
                    unit = getattr(product, 'unit', 'dona') if product else 'dona'
                    name = str(item.variant) if item.variant else (getattr(product, 'name', '') or '')
                    stock = item.variant.stock_quantity if item.variant else 0
                    edit_sale_items.append({
                        'product_id': item.variant_id,
                        'name': name,
                        'price': float(item.unit_price),
                        'quantity': item.quantity,
                        'stock': stock,
                        'unit': unit,
                    })
        except (TypeError, ValueError):
            valid_edit_sale_id = None
            edit_sale_items = []

    return render(request, 'store/create_sale.html', {
        'top_products': top_sold_variants,
        'top_products_json': json.dumps(top_products_json),
        'categories': categories,
        'current_usd_rate': current_usd_rate,
        'append_sale_id': valid_append_sale_id,
        'edit_sale_id': valid_edit_sale_id,
        'edit_sale_items_json': json.dumps(edit_sale_items),
    })


@require_market
def credit_list(request):
    """Qarzdorlar ro'yxati"""
    market = get_request_market(request)
    credits = Sale.objects.filter(market=market, payment_method='credit').select_related('customer', 'created_by')
    
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
    current_usd_rate = get_current_usd_rate(market)

    # 100 tadan oshsa pagination
    credits = credits.order_by('-sale_date')
    paginator = Paginator(credits, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    query_dict = request.GET.copy()
    if 'page' in query_dict:
        query_dict.pop('page')
    query_string = query_dict.urlencode()

    # Get all customers for filter (shu market)
    customers = Customer.objects.filter(market=market, sale__payment_method='credit').distinct()

    return render(request, 'store/credit_list.html', {
        'credits': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'total_credits_count': paginator.count,
        'customer_debts': customer_debts,
        'total_debt': total_debt,
        'current_usd_rate': current_usd_rate,
        'customers': customers
    })


@require_market
def exchange_rate_view(request):
    """Kunlik dollar kursini kiritish/o'zgartirish. Kurs mahsulot narxlari va sotuvda ishlatiladi."""
    market = get_request_market(request)
    today = timezone.localdate()
    current_rate = get_current_usd_rate(market)
    # Bugungi kurs (shu market uchun) mavjudmi
    today_record = ExchangeRate.objects.filter(market=market).filter(date=today).first() if market else None
    if not market:
        today_record = ExchangeRate.objects.filter(market__isnull=True).filter(date=today).first()

    if request.method == 'POST':
        rate_str = request.POST.get('rate', '').strip()
        if not rate_str:
            messages.error(request, 'Kurs qiymatini kiriting.')
            return redirect('store:exchange_rate')
        try:
            rate_val = Decimal(rate_str.replace(',', '.'))
            if rate_val <= 0:
                messages.error(request, 'Kurs musbat son bo\'lishi kerak.')
                return redirect('store:exchange_rate')
        except (ValueError, TypeError):
            messages.error(request, 'Noto\'g\'ri format.')
            return redirect('store:exchange_rate')
        obj, created = ExchangeRate.objects.update_or_create(
            market=market,
            date=today,
            defaults={'rate': rate_val}
        )
        next_url = request.GET.get('next', '').strip()
        if next_url and next_url.startswith('/') and not next_url.startswith('//'):
            return redirect(next_url)
        if created:
            messages.success(request, f'Kurs saqlandi: 1 USD = {rate_val} so\'m')
        else:
            messages.success(request, f'Kurs yangilandi: 1 USD = {rate_val} so\'m')
        return redirect('store:exchange_rate')

    return render(request, 'store/exchange_rate.html', {
        'current_rate': current_rate,
        'today_record': today_record,
        'today': today,
    })


@require_market
def sale_list(request):
    """Sotuvlar ro'yxati"""
    market = get_request_market(request)
    sales = Sale.objects.filter(market=market).select_related('customer', 'created_by')
    
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

    # Faqat yakunlangan sotuvlar bo'yicha jami (bazada USD)
    from django.db.models import Sum as _Sum
    total_sales = sales.filter(status='completed').aggregate(_Sum('total_amount'))['total_amount__sum'] or 0
    current_usd_rate = get_current_usd_rate(market)

    # 100 tadan oshsa pagination
    sales = sales.order_by('-sale_date')
    paginator = Paginator(sales, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    query_dict = request.GET.copy()
    if 'page' in query_dict:
        query_dict.pop('page')
    query_string = query_dict.urlencode()

    context = {
        'sales': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'total_sales': total_sales,
        'total_sales_count': paginator.count,
        'current_usd_rate': current_usd_rate,
    }
    return render(request, 'store/sale_list.html', context)


@require_market
def sale_detail(request, pk):
    """Sotuv tafsilotlari va chek"""
    market = get_request_market(request)
    sale = get_object_or_404(Sale, pk=pk, market=market)
    current_usd_rate = get_current_usd_rate(market)
    return render(request, 'store/sale_detail.html', {'sale': sale, 'current_usd_rate': current_usd_rate})


@require_market
@require_http_methods(["POST"])
def cancel_sale(request, pk):
    """Sotuvni orqaga qaytarish (barcha mahsulotlarni omborga qaytarish, holatini 'Qaytarilgan' qilish)"""
    market = get_request_market(request)
    with transaction.atomic():
        sale = get_object_or_404(Sale.objects.select_for_update(), pk=pk, market=market)
        if sale.status == 'returned':
            messages.info(request, "Bu sotuv allaqachon qaytarilgan.")
            return redirect('store:sale_detail', pk=pk)
        if sale.status != 'completed':
            messages.error(request, "Faqat yakunlangan sotuvni qaytarish mumkin.")
            return redirect('store:sale_detail', pk=pk)

        # Omborga qaytarish
            for item in sale.items.select_related('variant'):
                if item.variant:
                    variant = item.variant
                    if not getattr(variant, 'unlimited_stock', False):
                        variant.stock_quantity = max(0, variant.stock_quantity + item.quantity)
                        variant.save(update_fields=['stock_quantity'])

        sale.status = 'returned'
        sale.save(update_fields=['status'])
        messages.success(request, "Sotuv orqaga qaytarildi va mahsulotlar omborga qaytarildi.")
    return redirect('store:sale_detail', pk=pk)


@require_market
@require_http_methods(["POST"])
def delete_sale(request, pk):
    """Sotuvni o'chirish. Agar hali qaytarilmagan bo'lsa, mahsulotlar omborga qaytariladi, so'ng sotuv o'chiriladi."""
    market = get_request_market(request)
    with transaction.atomic():
        sale = get_object_or_404(Sale.objects.select_for_update(), pk=pk, market=market)

        # Agar hali qaytarilmagan bo'lsa, omborga qaytaramiz
        if sale.status == 'completed':
            for item in sale.items.select_related('variant'):
                if item.variant:
                    variant = item.variant
                    if not getattr(variant, 'unlimited_stock', False):
                        variant.stock_quantity = max(0, variant.stock_quantity + item.quantity)
                        variant.save(update_fields=['stock_quantity'])

        sale_id = sale.id
        sale.delete()
        messages.success(request, f"Sotuv #{sale_id} to'liq o'chirildi.")
    return redirect('store:sale_list')


@require_market
@require_http_methods(["POST"])
def append_sale(request, pk):
    """Mavjud sotuvga yangi mahsulotlar qo'shish (inventar zaxirasini kamaytirib, jami summani oshirish)."""
    market = get_request_market(request)
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        if not items:
            return JsonResponse({'error': "Mahsulotlar ro'yxati bo'sh."}, status=400)

        with transaction.atomic():
            sale = get_object_or_404(Sale.objects.select_for_update(), pk=pk, market=market)
            if sale.status != 'completed':
                return JsonResponse({'error': "Faqat yakunlangan sotuvga mahsulot qo'shish mumkin."}, status=400)

            variant_ids = [int(item_data['product_id']) for item_data in items]
            variants_dict = {
                v.id: v for v in ProductVariant.objects.select_for_update().filter(
                    pk__in=variant_ids,
                    product__category__market=market
                )
            }
            if len(variants_dict) != len(variant_ids):
                return JsonResponse({'error': 'Mahsulot topilmadi'}, status=400)

            # Zaxirani tekshirish
            for item_data in items:
                vid = int(item_data['product_id'])
                quantity = int(item_data['quantity'])
                variant = variants_dict[vid]
                if not getattr(variant, 'unlimited_stock', False) and variant.stock_quantity < quantity:
                    return JsonResponse({
                        'error': f'{variant} uchun yetarli mahsulot yo\'q (omborda: {variant.stock_quantity} dona)'
                    }, status=400)

            total_added = Decimal('0')
            for item_data in items:
                variant = variants_dict[int(item_data['product_id'])]
                quantity = int(item_data['quantity'])
                unit_price = Decimal(str(item_data['price']))

                SaleItem.objects.create(
                    sale=sale,
                    variant=variant,
                    quantity=quantity,
                    unit_price=unit_price
                )
                if not getattr(variant, 'unlimited_stock', False):
                    variant.stock_quantity = max(0, variant.stock_quantity - quantity)
                    variant.save(update_fields=['stock_quantity'])
                total_added += unit_price * quantity

            sale.total_amount += total_added
            sale.save(update_fields=['total_amount'])

        logger.info(f"Sale appended: {sale.id}, Added total: ${total_added} USD")
        return JsonResponse({'success': True, 'sale_id': sale.id})
    except Exception as e:
        logger.error(f"Error appending sale: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


@require_market
@require_http_methods(["POST"])
def edit_sale(request, pk):
    """Mavjud sotuvni to'liq tahrirlash: eski mahsulotlarni korzinkadan olib, yangisini yozadi."""
    market = get_request_market(request)
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        payment_method = data.get('payment_method')
        payment_cash_usd = data.get('payment_cash_usd')
        payment_card_usd = data.get('payment_card_usd')
        if not items:
            return JsonResponse({'error': "Mahsulotlar ro'yxati bo'sh."}, status=400)

        with transaction.atomic():
            sale = get_object_or_404(Sale.objects.select_for_update(), pk=pk, market=market)
            if sale.status != 'completed':
                return JsonResponse({'error': "Faqat yakunlangan sotuvni tahrirlash mumkin."}, status=400)

            # Eski mahsulotlarni omborga qaytaramiz
            for item in sale.items.select_related('variant'):
                if item.variant:
                    variant = item.variant
                    if not getattr(variant, 'unlimited_stock', False):
                        variant.stock_quantity = max(0, variant.stock_quantity + item.quantity)
                        variant.save(update_fields=['stock_quantity'])

            # Eski itemlarni o'chiramiz
            sale.items.all().delete()

            variant_ids = [int(item_data['product_id']) for item_data in items]
            variants_dict = {
                v.id: v for v in ProductVariant.objects.select_for_update().filter(
                    pk__in=variant_ids,
                    product__category__market=market
                )
            }
            if len(variants_dict) != len(variant_ids):
                return JsonResponse({'error': 'Mahsulot topilmadi'}, status=400)

            # Zaxirani tekshirish
            for item_data in items:
                vid = int(item_data['product_id'])
                quantity = int(item_data['quantity'])
                variant = variants_dict[vid]
                if not getattr(variant, 'unlimited_stock', False) and variant.stock_quantity < quantity:
                    return JsonResponse({
                        'error': f'{variant} uchun yetarli mahsulot yo\'q (omborda: {variant.stock_quantity} dona)'
                    }, status=400)

            total = Decimal('0')
            for item_data in items:
                variant = variants_dict[int(item_data['product_id'])]
                quantity = int(item_data['quantity'])
                unit_price = Decimal(str(item_data['price']))

                SaleItem.objects.create(
                    sale=sale,
                    variant=variant,
                    quantity=quantity,
                    unit_price=unit_price
                )
                if not getattr(variant, 'unlimited_stock', False):
                    variant.stock_quantity = max(0, variant.stock_quantity - quantity)
                    variant.save(update_fields=['stock_quantity'])
                total += unit_price * quantity

            original_total = total
            discount_percent_raw = data.get('discount_percent')
            dp = Decimal('0')
            if discount_percent_raw is not None and discount_percent_raw != '':
                try:
                    dp = Decimal(str(discount_percent_raw))
                except (ValueError, TypeError, InvalidOperation):
                    dp = Decimal('0')
            if dp > 0:
                if dp >= Decimal('100'):
                    dp = Decimal('99.99')
                factor = (Decimal('100') - dp) / Decimal('100')
                total = (total * factor).quantize(Decimal('0.01'))
                sale.discount_percent = dp
                sale.original_total_amount = original_total
            else:
                sale.discount_percent = Decimal('0')
                sale.original_total_amount = original_total

            sale.total_amount = total
            if payment_method:
                sale.payment_method = payment_method

            # To'lov bo'linmasi (USD)
            cash_amt = Decimal('0')
            card_amt = Decimal('0')
            if sale.payment_method == 'mixed':
                try:
                    cash_amt = Decimal(str(payment_cash_usd or '0'))
                    card_amt = Decimal(str(payment_card_usd or '0'))
                except (ValueError, TypeError):
                    cash_amt = Decimal('0')
                    card_amt = Decimal('0')
                if cash_amt < 0 or card_amt < 0 or (cash_amt + card_amt) == 0:
                    cash_amt = Decimal('0')
                    card_amt = total
                if cash_amt > total:
                    cash_amt = total
                    card_amt = Decimal('0')
                if cash_amt + card_amt != total:
                    card_amt = max(Decimal('0'), total - cash_amt)
            elif sale.payment_method == 'cash':
                cash_amt = total
                card_amt = Decimal('0')
            elif sale.payment_method == 'card':
                cash_amt = Decimal('0')
                card_amt = total

            sale.payment_cash_amount = cash_amt
            sale.payment_card_amount = card_amt
            sale.save(update_fields=['total_amount', 'original_total_amount', 'discount_percent', 'payment_method', 'payment_cash_amount', 'payment_card_amount'])

        logger.info(f"Sale edited: {sale.id}, New total: ${total} USD")
        return JsonResponse({'success': True, 'sale_id': sale.id})
    except Exception as e:
        logger.error(f"Error editing sale: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


@require_market
def print_receipt(request, pk):
    """Chek chiqarish"""
    market = get_request_market(request)
    sale = get_object_or_404(
        Sale.objects.prefetch_related(
            Prefetch('items', queryset=SaleItem.objects.select_related('variant').prefetch_related('variant__attribute_values__attribute'))
        ),
        pk=pk, market=market
    )
    logger.info(f"Receipt printed for sale: {sale.id}")
    receipt_rate = float(sale.usd_rate) if sale.usd_rate else float(get_current_usd_rate(market))
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
        item_usd = float(item.subtotal)
        product = item.variant.product if item.variant else getattr(item, 'product_old', None)
        unit = getattr(product, 'unit', 'dona') if product else 'dona'
        qty_suffix = " M" if unit == 'metr' else "x"
        lines.append(f"{item.product.name}  {item.quantity}{qty_suffix}  ${item_usd:.2f}")
        if item.variant:
            params = [av.value for av in item.variant.attribute_values.all() if getattr(av.attribute, 'name', '') == 'parametr']
            if params:
                lines.append("  " + ", ".join(params))
    total_usd = float(sale.total_amount)
    total_usd_formatted = f"{total_usd:,.2f}"
    total_soom = total_usd * receipt_rate
    total_soom_formatted = f"{total_soom:,.0f}"

    original_total_usd = float(sale.original_total_amount or sale.total_amount)
    original_total_usd_formatted = f"{original_total_usd:,.2f}"
    original_total_soom = original_total_usd * receipt_rate
    original_total_soom_formatted = f"{original_total_soom:,.0f}"
    discount_percent_display = ""
    discount_usd = 0.0
    discount_soom = 0.0
    original_total_applied = False
    if sale.discount_percent and float(sale.discount_percent) > 0 and original_total_usd > 0:
        original_total_applied = True
        discount_percent_display = f"{float(sale.discount_percent):.2f}"
        discount_usd = original_total_usd - total_usd
        if discount_usd < 0:
            discount_usd = 0.0
        discount_soom = discount_usd * receipt_rate
    discount_usd_formatted = f"{discount_usd:,.2f}"
    discount_soom_formatted = f"{discount_soom:,.0f}"

    lines.append('')
    if original_total_applied:
        lines.append(f"JAMI: ${original_total_usd_formatted}  {original_total_soom_formatted} so'm")
        lines.append(f"Chegirma: {discount_percent_display}%  -${discount_usd_formatted}  -{discount_soom_formatted} so'm")
        lines.append(f"Yakuniy: ${total_usd_formatted}  {total_soom_formatted} so'm")
    else:
        lines.append(f"JAMI: ${total_usd_formatted}  {total_soom_formatted} so'm")
    receipt_text = '\n'.join(lines)
    html = render_to_string('store/receipt.html', {
        'sale': sale,
        'receipt_rate': receipt_rate,
        'receipt_rate_formatted': receipt_rate_formatted,
        'receipt_text': receipt_text,
        'total_usd_formatted': total_usd_formatted,
        'total_soom_formatted': total_soom_formatted,
        'original_total_applied': original_total_applied,
        'original_total_usd_formatted': original_total_usd_formatted,
        'original_total_soom_formatted': original_total_soom_formatted,
        'discount_usd_formatted': discount_usd_formatted,
        'discount_soom_formatted': discount_soom_formatted,
        'discount_percent_display': discount_percent_display,
    })
    response = HttpResponse(html)
    response['Content-Type'] = 'text/html; charset=utf-8'
    return response


@require_market
def get_products_json(request):
    """AJAX uchun mahsulotlar JSON"""
    market = get_request_market(request)
    category_id = request.GET.get('category_id')
    search = request.GET.get('search', '')
    
    variants = ProductVariant.objects.filter(
        is_active=True,
        product__is_active=True,
        product__category__market=market
    ).filter(
        Q(unlimited_stock=True) | Q(stock_quantity__gt=0)
    ).select_related('product', 'product__category')
    
    if category_id:
        variants = variants.filter(product__category_id=category_id)
    
    if search:
        variants = variants.filter(
            Q(product__name__icontains=search) | Q(sku__icontains=search)
        )
    
    rate = get_current_usd_rate(market)
    data = [{
        'id': v.id,
        'name': v.product.name,
        'variant_name': str(v),
        'price': str(v.price * rate),  # so'm da (kassa savatida)
        'stock': 999999 if getattr(v, 'unlimited_stock', False) else v.stock_quantity,
        'unlimited_stock': v.unlimited_stock,
        'sku': v.sku,
        'unit': v.product.unit,
        'image': v.image.url if v.image else (v.product.image.url if v.product.image else ''),
    } for v in variants[:50]]
    
    return JsonResponse({'products': data})


@require_market
def search_products_autocomplete(request):
    """Autocomplete uchun mahsulotlarni qidirish - variantlar bo'yicha.
    include_out_of_stock=1 bo'lsa (mahsulot qo'shish sahifasi) qolmagan variantlar ham qaytadi."""
    market = get_request_market(request)
    query = request.GET.get('q', '').strip()
    include_out_of_stock = request.GET.get('include_out_of_stock') == '1'
    
    if len(query) < 2:
        return JsonResponse({'products': []})
    
    variants = ProductVariant.objects.filter(
        is_active=True,
        product__is_active=True,
        product__category__market=market
    ).filter(
        Q(product__name__icontains=query) | Q(sku__icontains=query)
    ).select_related('product', 'product__category').prefetch_related('attribute_values__attribute')
    if not include_out_of_stock:
        variants = variants.filter(stock_quantity__gt=0, unlimited_stock=False)
    variants = variants[:20]
    
    rate = get_current_usd_rate(market)
    data = []
    for v in variants:
        color = ''
        for av in v.attribute_values.all():
            if av.attribute.name == 'color':
                color = av.value
                break
        # Narx bazada USD — API so'm da qaytaramiz (ko'rsatish va forma uchun)
        data.append({
            'id': v.id,
            'product_id': v.product.id,
            'name': v.product.name,
            'variant_name': str(v),
            'sku': v.sku,
            'price': str(v.price * rate),
            'cost_price': str((v.cost_price or 0) * rate),
            'category': v.product.category.name if v.product.category else '',
            'category_id': v.product.category.id if v.product.category else None,
            'color': color,
            'description': v.product.description or '',
            'stock': v.stock_quantity,
            'unlimited_stock': v.unlimited_stock,
            'unit': v.product.unit,
        })
    
    # Sort by name to show similar products together
    data.sort(key=lambda x: x['name'])
    
    return JsonResponse({'products': data})


@require_market
@csrf_exempt
def get_colors_by_category(request):
    """Kategoriya bo'yicha ranglarni qaytarish"""
    market = get_request_market(request)
    category_id = request.GET.get('category_id')
    
    if not category_id:
        return JsonResponse({'colors': []})
    
    try:
        category = Category.objects.get(pk=category_id, market=market)
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


@require_market
def get_variant_price(request, variant_id):
    """Variantning joriy narxini bazadan qaytaradi (hamma joyda bir xil narx — bitta manba)."""
    market = get_request_market(request)
    try:
        variant = ProductVariant.objects.get(
            pk=variant_id, is_active=True, product__category__market=market
        )
        return JsonResponse({'price_usd': float(variant.price)})
    except ProductVariant.DoesNotExist:
        return JsonResponse({'error': 'Variant topilmadi'}, status=404)


@require_market
@csrf_exempt
def update_variant_price(request, variant_id):
    """Kassada korzinkadagi mahsulot narxini o'zgartirish — variant narxi bazada ham yangilanadi (hamma joyda)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=405)
    market = get_request_market(request)
    try:
        variant = ProductVariant.objects.get(
            pk=variant_id, is_active=True, product__category__market=market
        )
    except ProductVariant.DoesNotExist:
        return JsonResponse({'error': 'Variant topilmadi'}, status=404)
    try:
        data = json.loads(request.body) if request.body else {}
        price_usd = data.get('price_usd')
        if price_usd is not None:
            price_usd = Decimal(str(price_usd))
            if price_usd < Decimal('0'):
                return JsonResponse({'error': 'Narx manfiy bo\'lmasin'}, status=400)
            variant.price = price_usd.quantize(Decimal('0.01'))
        else:
            price_soom = data.get('price_soom')
            if price_soom is None:
                return JsonResponse({'error': 'price_usd yoki price_soom kerak'}, status=400)
            price_soom = Decimal(str(price_soom))
            if price_soom < 0:
                return JsonResponse({'error': 'Narx manfiy bo\'lmasin'}, status=400)
            rate = get_current_usd_rate(market)
            variant.price = (price_soom / rate).quantize(Decimal('0.01'))
        variant.save(update_fields=['price'])
        return JsonResponse({'success': True, 'price_usd': float(variant.price)})
    except (ValueError, TypeError) as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_market
def get_product_variants_json(request, product_id):
    """Mahsulotning barcha variantlari (rang, narx so'mda, qoldiq) — create_product da mavjud variantlarni ko'rsatish uchun"""
    market = get_request_market(request)
    try:
        product = Product.objects.get(pk=product_id, is_active=True, category__market=market)
    except Product.DoesNotExist:
        return JsonResponse({'variants': [], 'product_name': ''})
    rate = get_current_usd_rate(market)
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
            'price': str(v.price * rate),  # so'm da
            'price_usd': str(v.price),  # USD da
            'stock': v.stock_quantity,
            'unlimited_stock': v.unlimited_stock,
            'sku': v.sku,
        })
    unit_display = product.get_unit_display()
    return JsonResponse({
        'variants': data,
        'product_name': product.name,
        'unit': product.unit,
        'unit_display': unit_display,
    })


@require_market
@csrf_exempt
def search_customers_autocomplete(request):
    """Autocomplete uchun mijozlarni qidirish"""
    market = get_request_market(request)
    query = request.GET.get('q', '').strip()
    
    if len(query) < 1:
        return JsonResponse({'customers': []})
    
    customers = Customer.objects.filter(
        Q(name__icontains=query) | Q(phone__icontains=query),
        market=market
    ).order_by('name')[:10]  # Limit to 10 for autocomplete
    
    data = [{
        'id': c.id,
        'name': c.name,
        'phone': c.phone or '',
    } for c in customers]
    
    return JsonResponse({'customers': data})


@require_market
def statistics(request):
    """Statistika: sotuvlar va qarzlar summasi (sana oralig'i bo'yicha yoki hammasi)."""
    if not user_is_manager(request.user):
        messages.error(request, "Statistika faqat menejerlar uchun.")
        return redirect('store:product_list')

    market = get_request_market(request)
    current_usd_rate = get_current_usd_rate(market)

    date_from = (request.GET.get('date_from') or '').strip()
    date_to = (request.GET.get('date_to') or '').strip()

    sales_qs = Sale.objects.filter(market=market, status='completed')
    # Sanalar oralig'i bo'yicha filtrlash (ixtiyoriy)
    has_filter = bool(date_from or date_to)
    if has_filter:
        if date_from:
            sales_qs = sales_qs.filter(sale_date__date__gte=date_from)
        if date_to:
            sales_qs = sales_qs.filter(sale_date__date__lte=date_to)

    # Summalar (USD va so'm) — so'mni har sotuvning usd_rate bo'yicha hisoblaymiz
    total_sales_usd = Decimal('0')
    total_sales_uzs = Decimal('0')
    for s in sales_qs.only('total_amount', 'usd_rate'):
        rate = s.usd_rate if s.usd_rate else current_usd_rate
        usd = (s.total_amount or Decimal('0'))
        total_sales_usd += usd
        total_sales_uzs += usd * rate

    credits_qs = Sale.objects.filter(market=market, status='completed', payment_method='credit')
    if has_filter:
        if date_from:
            credits_qs = credits_qs.filter(sale_date__date__gte=date_from)
        if date_to:
            credits_qs = credits_qs.filter(sale_date__date__lte=date_to)

    total_credit_usd = Decimal('0')
    total_credit_uzs = Decimal('0')
    if has_filter:
        for s in credits_qs.only('total_amount', 'usd_rate'):
            rate = s.usd_rate if s.usd_rate else current_usd_rate
            usd = (s.total_amount or Decimal('0'))
            total_credit_usd += usd
            total_credit_uzs += usd * rate

    # Sof foyda — faqat tannarx kiritilgan tovarlar bo'yicha (tannarxi yo'q tovarlar hisobga olinmaydi)
    total_profit_usd = Decimal('0')
    total_profit_uzs = Decimal('0')
    if has_filter:
        sale_ids = list(sales_qs.values_list('id', flat=True))
        items = SaleItem.objects.filter(sale_id__in=sale_ids).select_related('variant')
        for item in items:
            if item.variant and item.variant.cost_price and item.variant.cost_price > 0:
                cost = item.variant.cost_price * item.quantity
                total_profit_usd += (item.subtotal or Decimal('0')) - cost
        total_profit_uzs = total_profit_usd * current_usd_rate

    context = {
        'date_from': date_from,
        'date_to': date_to,
        'total_sales_usd': total_sales_usd,
        'total_sales_uzs': total_sales_uzs,
        'total_credit_usd': total_credit_usd,
        'total_credit_uzs': total_credit_uzs,
        'total_profit_usd': total_profit_usd,
        'total_profit_uzs': total_profit_uzs,
        'current_usd_rate': current_usd_rate,
    }
    return render(request, 'store/statistics.html', context)


# @login_required
def hide(request):
    """Hide page"""
    return render(request, 'store/hide.html')