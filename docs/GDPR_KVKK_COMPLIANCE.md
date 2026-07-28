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

> ⚠️ **Kritik Mimari Notu:** Ham Kişisel Sağlık Verisi (PHI) **hiçbir zaman kamuya açık ağlara yazılmaz**.  
> Yalnızca yerel kriptografik hash (Merkle root) zincire kaydedilir ve kimlikler Pseudonymization Engine (`anon_id`) ile ayrıştırılır.

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

1. **Pseudonymization Engine (KVKK M.7 & GDPR Art. 32)**:
   - Kişisel kimlik verileri ile tıbbi kayıtlar kriptografik `anon_id` ile birbirinden ayrıştırılmıştır.
2. **Çift Onaylı Yetki İlkesi (Dual-Control)**:
   - Sistem Yöneticisi (Admin) dahi VIP hastanın ham şifreli verisini tek başına çözemez. Güvenlik Görevlisi (`security_officer`) co-signature (çift onay) şarttır.
3. **Zaman Sınırlı Rıza ve Otomatik Süre Dolumu**:
   - Doktor rızaları saat ve gün bazlı tanımlanır. Süresi dolduğu anda erişim otomatik kapanır ve `CONSENT_EXPIRED` logu atılır.
4. **Network Level Isolation (Ağ İzolasyonu)**:
   - `IPAllowlistMiddleware` ile varsayılan olarak kamuya kapalıdır; sadece kurum VPN ve yetkili IP bloklarına açık tutulur.
