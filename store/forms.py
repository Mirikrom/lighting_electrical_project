import re
from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Expense, ExpenseCategory


class RegisterForm(UserCreationForm):
    """Ro'yxatdan o'tish: login, parol, ixtiyoriy market nomi"""
    username = forms.CharField(
        label="Login",
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    password1 = forms.CharField(
        label="Parol",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label="Parolni takrorlang",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    market_name = forms.CharField(
        label="Market nomi (ixtiyoriy)",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')


class ExpenseForm(forms.ModelForm):
    """Rasxod qo'shish/tahrirlash — ixtiyoriy yangi kategoriya nomi bilan."""

    new_category_name = forms.CharField(
        label="Yangi kategoriya (ixtiyoriy)",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = Expense
        fields = ['title', 'notes', 'amount_uzs', 'expense_date', 'payment_method', 'category']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'amount_uzs': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric'}),
            'expense_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, market=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ExpenseCategory.objects.none()
        self.fields['category'].required = False
        self.fields['category'].empty_label = "— Kategoriyasiz —"
        if market:
            self.fields['category'].queryset = ExpenseCategory.objects.filter(market=market).order_by('sort_order', 'name')

    def clean_amount_uzs(self):
        raw = self.cleaned_data.get('amount_uzs')
        if raw is None:
            raise forms.ValidationError("Summani kiriting.")
        if isinstance(raw, Decimal):
            d = int(raw)
        else:
            digits = re.sub(r'\D', '', str(raw))
            if not digits:
                raise forms.ValidationError("Summani raqam bilan kiriting.")
            d = int(digits)
        if d < 1:
            raise forms.ValidationError("Summa kamida 1 so'm bo'lishi kerak.")
        return Decimal(d)
