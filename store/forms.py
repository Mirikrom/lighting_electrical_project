from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    """Ro'yxatdan o'tish: login, parol, ixtiyoriy market nomi"""
    username = forms.CharField(
        label="Login",
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Login (username)'})
    )
    password1 = forms.CharField(
        label="Parol",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Parol'})
    )
    password2 = forms.CharField(
        label="Parolni takrorlang",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Parolni takrorlang'})
    )
    market_name = forms.CharField(
        label="Market nomi (ixtiyoriy)",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Bo'sh qoldirsangiz, admin keyin market biriktiradi"})
    )

    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')
