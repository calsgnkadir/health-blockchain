# VIP Health Vault (VIP Sağlık Kasası) · Backend & Frontend v3.0

VIP Health Vault, VIP hastaların tıbbi verilerini ultra-güvenli, değiştirilemez ve kriptografik olarak denetlenebilir bir blokzinciri altyapısında saklayan, Clean Architecture prensiplerine göre tasarlanmış kurumsal bir web platformudur.

---

## 🏗️ Mimari Yapı (Clean Architecture)

Proje, bağımlılıkların içe doğru akmasını sağlayan ve iş mantığını dış arayüzlerden (veritabanı, sunucu, ön yüz) ayıran 4 katmanlı temiz mimari yapısına sahiptir:

1. **Core (Domain & Ports)**: 
   - `entities.py`: `User`, `Block` ve `HealthRecord` gibi temel iş nesnelerini barındırır.
   - `ports/`: Veritabanı ve kriptografi işlemlerini soyutlayan arayüz kontratlarını içerir (`repositories.py`, `unit_of_work.py`).
2. **Core Services (Use Cases)**: 
   - Kimlik doğrulama (`AuthService`), kayıt yönetimi (`RecordService`), denetim zinciri (`AuditService`) ve erişim doğrulama (`ConsentValidator`) iş mantıkları burada yürütülür.
3. **Infrastructure**:
   - `lmdb_repositories.py`: Veritabanı arayüzlerini LMDB motoruyla eşleştirir.
   - `crypto_strategies.py`: AES-GCM-256 kriptografik şifreleme stratejisini uygular.
4. **Presentation & API (FastAPI / Uvicorn)**:
   - `backend/main.py`: REST API endpoint'leri, JWT token yetkilendirme, rate-limiting koruması, CSRF doğrulaması ve SPA statik dosya sunucusunu yönetir.
   - **CQRS Pattern**: Tüm veri okuma işlemleri `QueryHandler`, veri yazma işlemleri ise `CommandHandler` üzerinden geçirilerek ayrıştırılmıştır.

---

## 🔒 Güvenlik Sıkılaştırmaları

- **JWT RSA Token Yetkilendirme**: Token imzalamada asimetrik RSA (RS256) kullanılır. Özel anahtar (`.jwt_private.pem`), makineye özgü donanım parmak izi (`get_device_id()`) veya `VHV_JWT_PASSPHRASE` ile `BestAvailableEncryption` yöntemi kullanılarak şifreli saklanır.
- **CSRF Koruması**: Güvenli olmayan tüm API isteklerinde (`POST`, `PUT`, `DELETE`) cookie-header eşleşmeli CSRF doğrulama sistemi aktiftir.
- **Hassas Veri Şifreleme**: Hasta tarafından "Confidential" olarak işaretlenen bloklar, hasta şifresinden türetilen anahtarla AES-GCM kullanılarak şifrelenir ve blokzincirine öyle yazılır. Şifre asla sunucu tarafında saklanmaz.
- **Rate-Limiting & Proxy Güvenliği**: Kötü niyetli brute-force saldırılarını önlemek için rate limiter entegre edilmiştir. `TRUST_PROXIES=true` ayarlanmadığı sürece reverse proxy başlıklarına (`X-Forwarded-For`) güvenilmez, doğrudan istemci soket IP'si baz alınır.
- **Rıza Yönetimi (Consent Management)**: Hekimler, hastanın açık rızası (`all` veya ilgili kayıt kategorisi) olmadığı sürece hastanın kayıtlarını listeyemez ve göremez.
- **Acil Durum Geçidi (Break Glass)**: Acil klinik durumlarda hekimler gerekçe belirterek 15 dakikalık geçici bypass yetkisi alabilir. Bu işlem anında denetim zincirine (`Audit Log`) ve cihaz kimliğiyle birlikte kaydedilir.

---

## 💻 Ön Yüz Modüler ES6 Yapısı

Monolitik devasa frontend dosyası yerine ön yüz mantığı modüler ES6 sınıflarına ayrılmıştır:
- `app.js`: Giriş noktası ve global pencere olay yönlendiricisi (`window` bindings).
- `modules/auth.js`: Oturum açma, kapatma ve TOTP 2FA yönetimi.
- `modules/dashboard.js`: Navigasyon ve yaşamsal bulgular klinik özet paneli.
- `modules/records.js`: Tıbbi kayıt listeleme, şifre çözme, dosya yükleme ve off-chain indirme.
- `modules/consent.js`: Rıza verme/iptal etme ve Break Glass yönetimi.
- `modules/appointments.js`: Randevu oluşturma ve iptal etme.
- `modules/triage.js`: Yapay zeka semptom analiz chatbot arayüzü.
- `modules/blockchain.js`: Blok zinciri görsel bütünlük timeline arayüzü.

---

## 🚀 Kurulum ve Çalıştırma

### 1. Bağımlılıkların Yüklenmesi
```powershell
pip install -r requirements.txt
```

### 2. Ortam Değişkenlerinin Ayarlanması (Opsiyonel)
```powershell
# Windows PowerShell
$env:ENVIRONMENT="development"   # Geliştirme modunda varsayılan hesapları otomatik oluşturur
$env:VHV_DEMO_MODE="true"        # Giriş ekranında demo hesap bilgilerini gösterir
$env:TRUST_PROXIES="false"       # Reverse proxy arkasında çalışmıyorsa false olmalıdır
```

### 3. Uygulamanın Başlatılması
```powershell
python backend/main.py
# veya
uvicorn backend.main:app --reload --port 8000
```
Tarayıcınızdan `http://localhost:8000` adresine giderek platforma erişebilirsiniz.

---

## 🧪 Otomatik Testler

Platformun mimari, kriptografik ve güvenlik gereksinimlerini doğrulamak için yazılmış otomatik testleri çalıştırmak için:
```powershell
python -m unittest test_architecture_upgrades.py
```
