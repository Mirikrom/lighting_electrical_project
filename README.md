# Lustra & Lempala - Elektr narsalar do'koni

Django asosida yaratilgan lustra, lempala va boshqa elektr narsalar uchun sotuv tizimi.

## Xususiyatlar

- ✅ Mahsulotlar boshqaruvi (kategoriyalar, narxlar, ombor)
- ✅ Sotuv tizimi
- ✅ Filtrlash va qidirish
- ✅ Chek chiqarish
- ✅ Logging tizimi
- ✅ Zamonaviy va chiroyli dizayn
- ✅ SQLite ma'lumotlar bazasi

## O'rnatish

1. Virtual environment yaratish:
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. Kerakli paketlarni o'rnatish:
```bash
pip install -r requirements.txt
```

3. Ma'lumotlar bazasini yaratish:
```bash
python manage.py makemigrations
python manage.py migrate
```

4. Superuser yaratish:
```bash
python manage.py createsuperuser
```

5. Serverni ishga tushirish:
```bash
python manage.py runserver
```

## Foydalanish

- Admin panel: http://127.0.0.1:8000/admin/
- Asosiy sahifa: http://127.0.0.1:8000/
- Mahsulotlar: http://127.0.0.1:8000/
- Sotuv yaratish: http://127.0.0.1:8000/sales/create/
- Sotuvlar ro'yxati: http://127.0.0.1:8000/sales/

## Struktura

- `store/` - Asosiy app
  - `models.py` - Ma'lumotlar bazasi modellari
  - `views.py` - View funksiyalari
  - `admin.py` - Admin panel sozlashlari
- `templates/store/` - HTML template'lar
- `media/` - Rasm va fayllar
- `logs/` - Log fayllari

## Keyingi optimallashtirishlar

- [ ] Statistika va hisobotlar
- [ ] Mijozlar boshqaruvi
- [ ] Kassa tizimi
- [ ] Export/Import funksiyalari
- [ ] Ko'p tillilik qo'llab-quvvatlash

