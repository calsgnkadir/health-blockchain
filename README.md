# 🛡️ VIP Health Vault (VIP Sağlık Kasası) · Kurumsal Blokzinciri Sağlık Defteri (v3.1)

[![CI Pipeline](https://github.com/your-username/health-blockchain/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/health-blockchain/actions)
[![Test Coverage](https://img.shields.io/badge/Coverage-98%25-brightgreen.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![LMDB](https://img.shields.io/badge/LMDB-Lightning%20DB-orange.svg)](https://symas.com/lmdb/)
[![Security](https://img.shields.io/badge/Security-AES--GCM--256-red.svg)](https://en.wikipedia.org/wiki/Galois/Counter_Mode)

**VIP Health Vault**, yüksek öncelikli ve kritik öneme sahip kişilerin (VIP hastalar) tıbbi verilerini, değiştirilemez ve kriptografik olarak denetlenebilir bir blokzinciri altyapısında saklayan, **Temiz Mimari (Clean Architecture)** ve **CQRS** prensiplerine göre tasarlanmış, üst düzey güvenlik odaklı, yeni nesil bir e-sağlık ve rıza yönetim platformudur.

Sistem; sıfır güven (Zero-Trust) güvenliği, donanım parmak izine bağlı RSA JWT yetkilendirme, çift katmanlı şifreleme (AES-GCM-256 + İstemci Tarafı Uçtan Uca Şifreleme), akıllı FHIR/Giyilebilir cihaz entegrasyonları, yapay zeka semptom analiz asistanı ve son derece premium bir **Glassmorphic Cyberpunk** arayüz tasarımı sunmaktadır.

---

## 🏗️ Mimari Tasarım (Clean Architecture & CQRS)

Platform, bağımlılıkların yalnızca içe doğru akmasını sağlayan ve iş mantığını (Business Logic) dış arayüzlerden (veritabanı, sunucu, ön yüz kütüphaneleri vb.) tamamen izole eden **4 Katmanlı Temiz Mimari** mimarisine göre yapılandırılmıştır:

```mermaid
graph TD
    %% Katman Renklendirmeleri ve Yapısı
    subgraph Sunum / API Katmanı [Presentation & API Layer]
        main[backend/main.py]
        routers[backend/routers/*]
        middleware[backend/middleware/*]
        main --> routers
        main --> middleware
    end

    subgraph Uygulama Servisleri / Senaryolar [Core Services & Use Cases]
        service_auth[AuthService]
        service_record[RecordService]
        service_audit[AuditService]
        validator[ConsentValidator]
    end

    subgraph Öz Alan ve Portlar [Core Domain & Ports]
        entities[entities.py: User, Block, HealthRecord]
        ports[ports/interfaces: Repositories, UnitOfWork]
    end

    subgraph Altyapı Katmanı [Infrastructure Layer]
        lmdb_repo[LMDB Repositories]
        crypto_strat[Crypto Strategies: AES-GCM-256]
    end

    %% İlişkiler ve Bağımlılık Yönleri
    routers --> service_auth & service_record & service_audit
    service_record --> validator
    service_auth & service_record & service_audit --> entities
    service_auth & service_record & service_audit --> ports
    ports --> lmdb_repo
    ports --> crypto_strat
    lmdb_repo --> database[(LMDB Engine)]

    style Sunum / API Katmanı fill:#1a1c23,stroke:#7928ca,stroke-width:2px,color:#fff
    style Uygulama Servisleri / Senaryolar fill:#111318,stroke:#00e5ff,stroke-width:2px,color:#fff
    style Öz Alan ve Portlar fill:#0f1015,stroke:#ff007f,stroke-width:2px,color:#fff
    style Altyapı Katmanı fill:#0a0b0e,stroke:#00e676,stroke-width:2px,color:#fff
```

### 🧱 Katmanların Detaylı Rolleri

1.  **Core Domain (Çekirdek Alan)**:
    *   [entities.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/core/domain/entities.py): Sistemdeki temel iş nesnelerini (`User`, `Block`, `HealthRecord`, `AuditLog`, `ConsentRules`) barındırır. Hiçbir dış kütüphaneye veya çerçeveye bağımlılığı yoktur.
    *   [ports/](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/core/ports/): Dış dünyayla iletişim kontratlarını (interface) tanımlar. Veri erişim soyutlaması için `Repository` ve `UnitOfWork` arayüzlerini içerir.
2.  **Core Services (Uygulama Servisleri)**:
    *   [auth_service.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/core/services/auth_service.py): Kullanıcı oluşturma, TOTP 2FA doğrulama ve kimlik doğrulama süreçleri.
    *   [record_service.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/core/services/record_service.py): Blokzincirine yeni kayıt ekleme, blok doğrulama, zincir bütünlüğünü denetleme.
    *   [audit_service.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/core/services/audit_service.py): Güvenlikle ilgili kritik olayları (giriş denemeleri, break-glass kullanımı) kaydeder.
    *   [consent_validator.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/core/services/consent_validator.py): Hekimlerin hasta kayıtlarına erişim yetkisini anlık olarak doğrular.
3.  **Infrastructure (Altyapı)**:
    *   [lmdb_repositories.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/infrastructure/repositories/lmdb_repositories.py): Hızlı, bellek eşlemeli (memory-mapped) LMDB veritabanı işlemlerini gerçekleştirir.
    *   [crypto_strategies.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/infrastructure/cryptography/crypto_strategies.py): Veri şifreleme ve bütünlük kontrolü için endüstri standardı **AES-256-GCM** motorunu barındırır.
4.  **Presentation & API (Sunum ve FastAPI Giriş Noktası)**:
    *   [main.py](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/backend/main.py): FastAPI uygulamasını ayağa kaldırır, middleware entegrasyonlarını yönetir ve statik SPA arayüzünü sunar.
    *   [routers/](file:///c:/Users/user/OneDrive/Desktop/health-blockchain-main/health-blockchain-main/backend/routers/): API uç noktalarını (`/auth`, `/records`, `/consent`, `/admin`) modüler şekilde ayırarak sunar.

---

## 🔒 Güvenlik Sıkılaştırmaları ve Zero-Trust İlkeleri

VIP seviyesindeki hassas tıbbi bilgilerin gizliliği ve değiştirilemezliği için platformda üst düzey siber güvenlik standartları uygulanmaktadır:

*   **Donanım Parmak İzi Destekli RSA Token İmzalama**: Kullanıcı oturum yönetiminde kullanılan asimetrik RSA key-pair (RS256) anahtarları sunucuda düz metin olarak barındırılmaz. Sunucunun çalıştığı fiziksel makineye özgü donanım bileşenlerinden üretilen parmak izi (`get_device_id()`) ile AES-CBC modunda şifrelenmiş olarak diskte saklanır (`.jwt_private.pem`).
*   **Çift Katmanlı Şifreleme Mimarisi**:
    *   *Sunucu Tarafı*: Blok verileri ve tıbbi kayıt içerikleri sisteme kaydedilmeden önce rastgele üretilen veri anahtarları ile AES-GCM-256 standardında şifrelenir.
    *   *İstemci Tarafı (Client-Side Encryption)*: Hasta, kaydını "Confidential" (Gizli) olarak belirlediğinde, dosya/veri daha tarayıcıdan çıkmadan hastanın kendi belirlediği bir parola ile AES-GCM kullanılarak şifrelenir. Sunucu veya veritabanı yöneticileri dahil, bu parolaya sahip olmayan hiç kimse verinin içeriğini asla okuyamaz.
*   **Cookie-Header Eşleşmeli CSRF Koruması**: `POST`, `PUT`, `DELETE` gibi veri değiştiren isteklerde, tarayıcı çerezi (cookie) ve istek başlığında (`X-CSRF-Token`) eş zamanlı doğrulama yapan sıkı bir CSRF önleyici middleware mevcuttur.
*   **Sıkı Rate Limiter ve Proxy Güvenliği**: Brute-force ve DDoS benzeri istekleri engellemek için endpoint bazlı IP rate-limiting uygulanır. `TRUST_PROXIES=true` tanımlanmadığı sürece reverse proxy başlıklarına güvenilmez, istemci doğrudan soket seviyesinden tanımlanır.
*   **XSS Temizleme ve Girdi Doğrulama**: Kullanıcı tarafından girilen tüm string alanlar (Örn: Hekim adı, hastane) sunucuya ulaştığı an `html.escape` filtrelerinden geçirilerek saklanır.

---

## 👥 Roller ve Erişim Kontrol Matrisi

Sistem, RBAC (Role-Based Access Control) ve Dinamik Rıza Kurallarını harmanlayarak çalışır:

| Rol | Dashboard Erişimi | Kayıt Ekleme | Kayıt Okuma Yetkisi | Sistem Günlüğü (Audit) | Rıza Tanımlama |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **VIP Patient** (Hasta) | Kendi Sağlık Durumu | Hayır (Salt Okuma) | Sadece Kendine Ait | Hayır | Kendi Rıza Ayarlarını Yönetir |
| **Doctor** (Hekim) | Sınırlı Klinik Özet | Evet | Sadece Yetkilendirilen Kayıtlar | Hayır | break-glass tetikleyebilir |
| **Admin** (Yönetici) | Sistem ve Zincir Durumu | Hayır | Hayır (Tıbbi veri kapalı) | Evet (Tam Erişim) | Hayır |

> [!IMPORTANT]
> **Rıza Mekanizması (Consent Engine)**: Bir hekimin, hastanın tıbbi kayıtlarına erişebilmesi için hastanın rıza yönetim ekranından o hekime veya ilgili tıbbi kategoriye (Cardiology, Oncology vb.) izin vermiş olması gerekir. Rıza yoksa API isteği `403 Forbidden` ile reddedilir.
>
> **Acil Durum Modu (Break Glass Protocol)**: Kritik ve hayati durumlarda hekimler, rızası olmayan bir hastanın verisine erişmek için gerekçe sunarak "Break Glass" modunu aktif edebilir. Bu mod hekime **15 dakikalık geçici erişim hakkı** tanımlar. Bu süre boyunca yapılan her okuma ve erişim, hekimin cihaz parmak izi ve kullanıcı kimliğiyle birlikte silinemez denetim günlüğüne (`Audit Logs`) kaydedilir.

---

## 🎨 Premium Görsel Tasarım ve Arayüz Sistemi (Glassmorphism Cyberpunk)

Uygulamanın ön yüz tasarımı sıradan şablonlardan arındırılmış, etkileyici ve modern bir **SaaS Grid / Cyberpunk** temasına sahiptir:

*   **Premium Glassmorphism**: `backdrop-filter: blur(16px)` ve `border: 1px solid rgba(255, 255, 255, 0.06)` kullanılarak zengin derinlik hissi veren şeffaf kart tasarımları oluşturulmuştur.
*   **Dinamik Kategori Neon Işımaları (Cyber Glow)**:
    Kullanıcının gezindiği menü kategorisine göre tüm ön yüzün birincil rengi, gölgeleri, buton neon parlamaları ve form çerçeveleri dinamik olarak değişir:
    *   🟡 **Main Panel (Genel Görünüm)**: Amber Altın (`#FFB300`)
    *   🔵 **Health Ledger (Blokzinciri Defteri)**: Turkuaz Mavi (`#00E5FF`)
    *   🔴 **Access & Security (Güvenlik / Rıza)**: Menekşe Pembe (`#FF007F`)
    *   🟢 **Smart Integrations (Entegrasyonlar & AI)**: Zümrüt Yeşili (`#00E676`)
*   **Gelişmiş Kaydırma Altyapısı**: Sidebar menüsündeki tüm seçenekler ve alt menüler ekran çözünürlüğünden bağımsız olarak dikeyde taşma yapmadan bağımsız bir kaydırma alanına (`overflow-y: auto`) sahiptir.
*   **İngilizce Dil Bütünlüğü**: Arayüzdeki tüm metinler, uyarı pencereleri ve özel dosya yükleme alanları global standartlara uygun olarak **%100 İngilizce** hazırlanmıştır.

---

## 📂 Dizin ve Dosya Yapısı

```text
health-blockchain-main/
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI Konfigürasyonu
├── backend/
│   ├── main.py                     # API Giriş Noktası & SPA Sunucusu
│   ├── dependencies.py             # FastAPI Bağımlılık Enjeksiyonları (DI)
│   ├── routers/                    # API Modülleri
│   │   ├── admin.py
│   │   ├── auth.py
│   │   ├── consent.py
│   │   ├── records.py
│   │   └── misc.py
│   ├── middleware/                 # CSRF ve Güvenlik Filtreleri
│   └── static/                     # Ön Yüz (Frontend) Kaynakları
│       ├── index.html
│       ├── css/
│       │   └── style.css           # Premium Glassmorphism CSS Sistem
│       └── js/
│           ├── app.js              # SPA Uygulama Yöneticisi
│           └── modules/            # ES6 Modüler JS Sınıfları
├── core/
│   ├── domain/
│   │   └── entities.py             # Domain Modelleri (User, Block, Record)
│   ├── ports/                      # Soyut Arayüzler (Portlar)
│   └── services/                   # İş Mantığı Servisleri
├── database/
│   ├── connection.py               # LMDBConnectionManager (Thread-Safe)
│   └── storage.py                  # LMDB Depolama Arayüzü & Seeding
├── infrastructure/
│   ├── cryptography/
│   │   └── crypto_strategies.py    # AES-GCM-256 Şifreleme Sınıfı
│   └── repositories/
│       ├── lmdb_repositories.py    # LMDB Tabanlı Kalıcı Saklama Alanı
│       └── lmdb_unit_of_work.py    # ACID İşlemleri için Unit of Work deseni
├── tests/
│   ├── test_auth.py                # Kimlik Doğrulama Birim Testleri
│   └── test_records.py             # Sağlık Kayıtları Birim Testleri
├── Dockerfile                      # Container Konfigürasyonu
├── docker-compose.yml              # Çoklu Container Orkestrasyonu
├── test_architecture_upgrades.py   # Mimari ve Kripto Birim Testleri (Eski)
└── test_e2e_api.py                 # Uçtan Uca Entegrasyon Testleri
```

---

## 🚀 Kurulum ve Çalıştırma

### 🐋 Docker ile Hızlı Kurulum (Tek Komutla - Önerilen)

Uygulamayı herhangi bir yerel bağımlılık (Python, LMDB vb.) kurmak zorunda kalmadan Docker ve Docker Compose yardımıyla tek bir komutla ayağa kaldırabilirsiniz:

```bash
# Container'ı derleyin ve arka planda çalıştırın
docker compose up --build -d
```

Uygulama otomatik olarak **`http://localhost:8000`** portunda çalışmaya başlayacaktır. Hasta kayıtları host makinenizdeki `backend/projects/` dizininde kalıcı olarak saklanır (volume persistence).

---

### 🐍 Standart Kurulum (Lokal Python Ortamı)

#### 🛠️ Sistem Gereksinimleri
*   Python 3.10 veya üzeri sürüm
*   Windows / Linux / macOS İşletim Sistemi

#### 1. Bağımlılıkları Kurun
Proje dizininde terminali açarak gerekli kütüphaneleri yükleyin:
```powershell
pip install -r requirements.txt
```

#### 2. Ortam Değişkenlerini Tanımlayın
Geliştirme aşamasında demo modunu aktifleştirmek ve test hesaplarını otomatik oluşturmak için ortam değişkenlerini tanımlayabilirsiniz:
```powershell
# Windows PowerShell
$env:ENVIRONMENT="development"
$env:VHV_DEMO_MODE="true"
$env:TRUST_PROXIES="false"
```

#### 3. Uygulamayı Başlatın
Uygulamayı direkt Python scripti olarak veya `uvicorn` ile başlatabilirsiniz:
```powershell
# Direkt çalıştırma (Önerilen)
python backend/main.py

# Veya uvicorn hot-reload ile
uvicorn backend.main:app --reload --port 8000
```
Çalıştırdıktan sonra tarayıcınızdan **`http://localhost:8000`** adresine giderek uygulamaya erişebilirsiniz.

---

## 👥 Demo Giriş Bilgileri

Geliştirme modunda (`VHV_DEMO_MODE="true"`), giriş ekranında otomatik olarak seçebileceğiniz üç farklı rol için hazır demo hesaplar oluşturulur:

1.  **Yönetici (Admin)**
    *   **Username**: `admin`
    *   **Password**: `AdminPassword123!`
    *   **2FA TOTP**: `JBSWY3DPEHPK3PXP` (2FA Kodu girerken arayüzdeki demo butonundan otomatik kod üretebilirsiniz)
2.  **Hekim (Doctor)**
    *   **Username**: `dr_house`
    *   **Password**: `DoctorPassword123!`
    *   **2FA TOTP**: `JBSWY3DPEHPK3PXP`
3.  **Hasta (VIP Patient)**
    *   **Username**: `john_doe`
    *   **Password**: `PatientPassword123!`
    *   **2FA TOTP**: `JBSWY3DPEHPK3PXP`

---

## 🧪 Otomatik Doğrulama ve Test Adımları

Platformda bulunan iş mantıklarının, blok zinciri bütünlüğünün ve kriptografik algoritmaların doğruluğunu doğrulamak için tasarlanmış geniş kapsamlı test senaryolarını çalıştırabilirsiniz:

```powershell
# 1. Birim Testleri (Unit Tests)
python -m unittest discover tests -v

# 2. Uçtan Uca API Entegrasyon Testleri (End-to-End API Tests)
python test_e2e_api.py
```
Testler çalıştığında blok şifreleme zinciri, yetkilendirmeler, break-glass kiralama süreleri ve rıza politikaları tamamen doğrulanır.
