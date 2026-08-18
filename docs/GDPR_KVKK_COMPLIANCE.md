# KVKK & GDPR Uyumluluk Beyanı
# VIP Health Vault — Veri Koruma Çerçevesi v5.0.0

> **Belge Türü:** Kişisel Veri İşleme Envanteri ve Uyum Beyanı  
> **Kapsam:** VIP Health Vault platformunda işlenen kişisel ve özel nitelikli tıbbi veriler  
> **Güncelleme:** 2026-07-28  
> **Referans Mevzuat:** 6698 sayılı KVKK · GDPR (AB) 2016/679 · ISO/IEC 27701:2019 · ISO 27001

---

## 1. Veri Sorumlusu Bilgileri

| Alan | Bilgi |
|------|-------|
| **Ünvan** | VIP Health Vault İşletmecisi |
| **Teknik Mimarisi** | Isolated Single-Tenant Architecture, Clean Architecture, CQRS |
| **Veri İşleme Modeli** | Off-chain şifreli depolama + Local Signed Merkle Hash-Chain |

> ⚠️ **Kritik Mimari Notu:** Ham Kişisel Sağlık Verisi (PHI) **hiçbir zaman kamuya açık ağlara yazılmaz**;
> izole tek-kiracılı (single-tenant) dağıtımın dışına çıkmaz.
>
> 🚧 **Uygulama durumu:** Pseudonymization Engine (`anon_id` ayrıştırma) mevcuttur ancak
> henüz kayıt yazma yoluna bağlanmamıştır — bkz. aşağıdaki **Bölüm 4 · Yol Haritası**.

---

## 2. İşlenen Kişisel Veri Kategorileri

### 2.1 Sıradan Kişisel Veriler
- Kimlik (Ad, soyad, kullanıcı adı)
- Dijital Kimlik (FIDO2 Passkey credential ID, IP Allowlist)
- Güvenlik (Argon2id şifre hash, TOTP sırrı)

### 2.2 Özel Nitelikli Kişisel Veriler (Sağlık Verileri)
- Tıbbi Tanı (ICD-10, doktor notları)
- Vital Bulgular (Tansiyon, nabız, SpO2)
- Reçete, Laboratuvar, Alerji, Ameliyat kayıtları

---

## 3. Güvenlik ve Uyum Mekanizmaları

1. **Pseudonymization Engine (KVKK M.7 & GDPR Art. 32)** — 🚧 *iskele hazır, yazma yoluna bağlanmadı*:
   - Kriptografik `anon_id` üreten motor (`core/pseudonymization/`) ve uçları mevcuttur.
   - **Mevcut durum:** Kayıtlar zincire `patient_id`, `doctor_name` gibi kimlik alanlarını açık metin olarak yazar; ayrıştırma henüz `AddRecordCommand` yolunda uygulanmamaktadır. Planlanan çalışma için bkz. Bölüm 4.
2. **Çift Onaylı Yetki İlkesi (Dual-Control)**:
   - Sistem Yöneticisi (Admin) dahi VIP hastanın ham şifreli verisini tek başına çözemez. Güvenlik Görevlisi (`security_officer`) co-signature (çift onay) şarttır.
3. **Zaman Sınırlı Rıza ve Otomatik Süre Dolumu**:
   - Doktor rızaları saat ve gün bazlı tanımlanır. Süresi dolduğu anda erişim otomatik kapanır ve `CONSENT_EXPIRED` logu atılır.
4. **Network Level Isolation (Ağ İzolasyonu)**:
   - `IPAllowlistMiddleware` ile varsayılan olarak kamuya kapalıdır; sadece kurum VPN ve yetkili IP bloklarına açık tutulur.

---

## 4. Yol Haritası (Planlanan Uyum Çalışmaları)

Bu bölüm, beyanın kod tabanının **önünde** iddia içermemesi için, henüz
uygulanmamış uyum mekanizmalarını dürüstçe listeler. Her madde bağımsız olarak
teslim edilebilecek şekilde sıralanmıştır.

| Durum | Mekanizma | Karşılık |
| :---: | :--- | :--- |
| 🔜 sırada | **Diskte şifreleme** — her klinik yük, KMS'ten türeyen anahtarla AES-256 ile diskte şifrelenir (yetkili oturum için sunucu çözer) | GDPR Art. 32 / KVKK M.12 |
| 🔜 sırada | **Erişim izinin zincire yazılması** — `RECORD_DECRYPTED` / `RECORDS_VIEWED` olayları blok olarak eklenir ve hastaya gösterilir | ISO 27001 A.12.4 |
| 📋 planlandı | **Pseudonymization'ın yazma yoluna bağlanması** — kimlik alanları `anon_id` ile ayrıştırılarak zincire yazılır | KVKK M.7 / GDPR Art. 32 |
| 📋 planlandı | **Anahtar imhası ile silme (erasure)** — append-only zincirde "unutulma hakkı", kayda özel şifreleme anahtarının imhasıyla sağlanır | GDPR Art. 17 / KVKK M.7 |
| 📋 planlandı | **Merkle kökünün dış çıpalanması** — RFC 3161 zaman damgası veya imzalı günlük kök ile operatör-değiştiremez bütünlük kanıtı | ISO 27001 A.12.4 |

> Bu tablo, güvenlik denetiminde "beyan edilen ≠ uygulanan" boşluğunu ortadan
> kaldırmak için tutulur. Bir madde uygulandığında Bölüm 3'e taşınır.
