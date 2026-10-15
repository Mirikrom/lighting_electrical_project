import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from store.models import (
    Category,
    Customer,
    DebtPayment,
    Market,
    Product,
    ProductVariant,
    Sale,
    SaleItem,
    UserProfile,
)
from store.views import credit_sale_principal


class CreditSaleDebtTests(TestCase):
    def setUp(self):
        self.market = Market.objects.create(name='Test market')
        self.user = User.objects.create_user('seller', password='pass')
        profile = self.user.profile
        profile.market = self.market
        profile.role = UserProfile.ROLE_SELLER
        profile.save(update_fields=['market', 'role'])
        category = Category.objects.create(market=self.market, name='Cat')
        product = Product.objects.create(name='Lampa', category=category)
        self.v1 = ProductVariant.objects.create(
            product=product, price=Decimal('300.00'), cost_price=Decimal('100.00'), stock_quantity=10,
        )
        self.v2 = ProductVariant.objects.create(
            product=product, price=Decimal('200.00'), cost_price=Decimal('50.00'), stock_quantity=10,
        )
        self.customer = Customer.objects.create(market=self.market, name='Ali', phone='901112233')
        self.sale = Sale.objects.create(
            market=self.market,
            customer=self.customer,
            payment_method='credit',
            total_amount=Decimal('500.00'),
            original_total_amount=Decimal('500.00'),
            status='completed',
            created_by=self.user,
        )
        SaleItem.objects.create(sale=self.sale, variant=self.v1, quantity=1, unit_price=Decimal('300.00'))
        SaleItem.objects.create(sale=self.sale, variant=self.v2, quantity=1, unit_price=Decimal('200.00'))
        self.client.force_login(self.user)

    def test_edit_reduces_credit_debt(self):
        response = self.client.post(
            reverse('store:edit_sale', args=[self.sale.id]),
            data=json.dumps({
                'items': [{'product_id': self.v1.id, 'quantity': 1, 'price': '300'}],
                'payment_method': 'credit',
                'customer_name': 'Ali',
                'customer_phone': '901112233',
                'discount_percent': 0,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_method, 'credit')
        self.assertEqual(self.sale.total_amount, Decimal('300.00'))

        page = self.client.get(reverse('store:credit_list'))
        self.assertEqual(len(page.context['customer_debts']), 1)
        self.assertEqual(page.context['customer_debts'][0]['total_debt'], Decimal('300.00'))
        self.assertEqual(page.context['credits'][0].debt_principal, Decimal('300.00'))

    def test_full_return_removes_customer_from_debtors(self):
        response = self.client.post(
            reverse('store:edit_sale', args=[self.sale.id]),
            data=json.dumps({
                'items': [],
                'payment_method': 'credit',
                'customer_name': 'Ali',
                'customer_phone': '901112233',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.total_amount, Decimal('0'))
        self.assertEqual(self.sale.items.count(), 0)

        page = self.client.get(reverse('store:credit_list'))
        self.assertEqual(page.context['customer_debts'], [])
        self.assertEqual(list(page.context['credits']), [])

    def test_stale_total_follows_remaining_goods(self):
        SaleItem.objects.filter(sale=self.sale, variant=self.v2).delete()
        self.sale.total_amount = Decimal('500.00')
        self.sale.save(update_fields=['total_amount'])
        self.sale = Sale.objects.prefetch_related('items').get(pk=self.sale.pk)
        self.assertEqual(credit_sale_principal(self.sale), Decimal('300.00'))

        page = self.client.get(reverse('store:credit_list'))
        self.assertEqual(page.context['customer_debts'][0]['total_debt'], Decimal('300.00'))

    def test_return_on_paid_check_reduces_other_debt(self):
        other = Sale.objects.create(
            market=self.market,
            customer=self.customer,
            payment_method='credit',
            total_amount=Decimal('50.00'),
            original_total_amount=Decimal('50.00'),
            status='completed',
            created_by=self.user,
        )
        other.total_amount = Decimal('400.00')
        other.original_total_amount = Decimal('400.00')
        other.save(update_fields=['total_amount', 'original_total_amount'])
        SaleItem.objects.create(sale=other, variant=self.v2, quantity=1, unit_price=Decimal('400.00'))
        DebtPayment.objects.create(
            sale=self.sale,
            amount_usd=Decimal('500.00'),
            amount_original=Decimal('500.00'),
            currency='USD',
            rate_used=Decimal('12500'),
        )
        response = self.client.post(
            reverse('store:edit_sale', args=[self.sale.id]),
            data=json.dumps({
                'items': [{'product_id': self.v1.id, 'quantity': 1, 'price': '300'}],
                'payment_method': 'cash',
                'customer_name': 'Ali',
                'customer_phone': '901112233',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_method, 'credit')
        self.assertEqual(self.sale.total_amount, Decimal('300.00'))

        page = self.client.get(reverse('store:credit_list'))
        # 300 lik chekka 500 to'langan. 200 ortiqcha ikkinchi 400 lik chekka o'tadi → qarz 200.
        self.assertEqual(len(page.context['customer_debts']), 1)
        self.assertEqual(page.context['customer_debts'][0]['total_debt'], Decimal('200.00'))

    def test_returned_sale_is_not_a_debt(self):
        self.sale.status = 'returned'
        self.sale.save(update_fields=['status'])
        page = self.client.get(reverse('store:credit_list'))
        self.assertEqual(page.context['customer_debts'], [])

    def test_statistics_debt_drops_when_goods_are_returned(self):
        profile = self.user.profile
        profile.role = UserProfile.ROLE_MANAGER
        profile.save(update_fields=['role'])
        other = Sale.objects.create(
            market=self.market,
            customer=self.customer,
            payment_method='credit',
            total_amount=Decimal('400.00'),
            original_total_amount=Decimal('400.00'),
            status='completed',
            created_by=self.user,
        )
        SaleItem.objects.create(sale=other, variant=self.v2, quantity=1, unit_price=Decimal('400.00'))
        DebtPayment.objects.create(
            sale=self.sale,
            amount_usd=Decimal('500.00'),
            amount_original=Decimal('500.00'),
            currency='USD',
            rate_used=Decimal('12500'),
        )
        today = timezone.localdate().isoformat()
        url = reverse('store:statistics') + f'?date_from={today}&date_to={today}'

        before = self.client.get(url)
        self.assertEqual(before.context['total_credit_usd'], Decimal('400.00'))

        response = self.client.post(
            reverse('store:edit_sale', args=[self.sale.id]),
            data=json.dumps({
                'items': [{'product_id': self.v1.id, 'quantity': 1, 'price': '300'}],
                'payment_method': 'cash',
                'customer_name': 'Ali',
                'customer_phone': '901112233',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        after = self.client.get(url)
        # 300 lik chekka 500 to'langan. 200 ortiqcha 400 lik chekka o'tadi → statistika 200.
        self.assertEqual(after.context['total_credit_usd'], Decimal('200.00'))

    def test_cancel_sale_restores_stock_and_leaves_statistics(self):
        profile = self.user.profile
        profile.role = UserProfile.ROLE_MANAGER
        profile.save(update_fields=['role'])
        self.v1.stock_quantity = 8
        self.v1.save(update_fields=['stock_quantity'])
        self.v2.stock_quantity = 9
        self.v2.save(update_fields=['stock_quantity'])
        today = timezone.localdate().isoformat()
        url = reverse('store:statistics') + f'?date_from={today}&date_to={today}'

        before = self.client.get(url)
        self.assertEqual(before.context['total_sales_usd'], Decimal('500.00'))
        self.assertEqual(before.context['total_profit_usd'], Decimal('350.00'))

        response = self.client.post(reverse('store:cancel_sale', args=[self.sale.id]))
        self.assertEqual(response.status_code, 302)
        self.sale.refresh_from_db()
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertEqual(self.sale.status, 'returned')
        self.assertEqual(self.v1.stock_quantity, 9)
        self.assertEqual(self.v2.stock_quantity, 10)

        after = self.client.get(url)
        self.assertEqual(after.context['total_sales_usd'], Decimal('0'))
        self.assertEqual(after.context['total_profit_usd'], Decimal('0'))
        self.assertEqual(after.context['total_credit_usd'], Decimal('0'))

        self.client.post(reverse('store:cancel_sale', args=[self.sale.id]))
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertEqual(self.v1.stock_quantity, 9)
        self.assertEqual(self.v2.stock_quantity, 10)

    def test_deleting_catalog_product_keeps_sold_line(self):
        item = self.sale.items.get(variant=self.v1)
        self.assertEqual(item.name_snapshot, 'LAMPA')
        self.assertEqual(item.line_name(), 'LAMPA')
        self.v1.delete()
        item.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertIsNone(item.variant_id)
        self.assertEqual(item.name_snapshot, 'LAMPA')
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.unit_price, Decimal('300.00'))
        self.assertEqual(self.sale.items.count(), 2)
        self.assertEqual(self.sale.total_amount, Decimal('500.00'))
