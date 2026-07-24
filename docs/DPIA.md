# Veri Koruma Etki Değerlendirmesi (DPIA)
# VIP Health Vault — Data Protection Impact Assessment v1.0

> **Dayanak:** GDPR Madde 35 / KVKK "Veri Sorumluları Sicili" Yönetmeliği  
> **Tarih:** 2026-07-24  
> **Değerlendirilen Sistem:** VIP Health Vault — Blockchain Tabanlı VIP Sağlık Kayıt Sistemi  
> **Risk Seviyesi (Başlangıç):** YÜKSEKKkk (Özel nitelikli kişisel veri — sağlık)  
> **Risk Seviyesi (Azaltma Sonrası):** ORTA-DÜŞÜK

---

## 1. Sistem ve İşleme Faaliyeti Açıklaması

VIP Health Vault; yüksek profilli bireyler (ünlüler, üst düzey yöneticiler, politikacılar) için
tasarlanmış, blockchain tabanlı ultra-güvenli sağlık kayıt yönetim sistemidir.

**İşleme Faaliyetleri:**
- Kişisel sağlık verilerinin (PHI) şifreli depolanması
- Doktor erişim izni yönetimi (consent)
- Blockchain üzerinde bütünlük notarizasyonu
- Acil durum erişim yönetimi (QR/NFC, Break-Glass)
- Miras/varis sağlık veri aktarımı (Dead-Man's Switch)
- Sıfır bilgi kanıtı ile seçici veri ifşası (ZKP)

---

## 2. DPIA Zorunluluğunun Değerlendirilmesi

GDPR Madde 35'e göre DPIA aşağıdaki durumlarda zorunludur:

| Kriter | VIP Health Vault Değerlendirmesi | Sonuç |
|--------|----------------------------------|-------|
| Özel nitelikli veri işleme (sağlık) | ✅ Evet | Zorunlu |
| Büyük ölçekte işleme | ✅ VIP nüfus segmenti | Zorunlu |
| Sistematik profilleme | ❌ Hayır | Opsiyonel |
| Yeni teknoloji (blockchain) | ✅ Evet | Zorunlu |
| Yüksek riskli gruplar | ✅ Evet (VIP = yüksek hedef) | Zorunlu |

**Sonuç: DPIA ZORUNLUDUR ✅**

---

## 3. Risk Envanteri ve Azaltma Matrisi

### Risk 1: Yetkisiz Tıbbi Veri Erişimi

| Kriter | Değer |
|--------|-------|
| **Tanım** | Kötü niyetli aktör veya yetkisiz kullanıcı tıbbi kayıtlara erişir |
| **Olasılık (Azaltma Öncesi)** | Yüksek (VIP = yüksek değerli hedef) |
| **Etki** | Çok Yüksek (şantaj, itibar zararı, fiziksel tehlike) |
| **Risk Skoru (Öncesi)** | 🔴 **YÜKSEKKkk (5×5 = 25)** |
| **Azaltma Önlemleri** | Argon2id şifre hash; AES-256-GCM veri şifreleme; RS256 JWT + TOTP 2FA + WebAuthn; Role-based erişim kontrol; Consent zorunluluğu; Rate limiting; Audit trail |
| **Kalan Risk** | 🟡 **ORTA (2×3 = 6)** |

### Risk 2: Blockchain'de Kişisel Veri Kalıcılığı (GDPR Art. 17 Uyumsuzluğu)

| Kriter | Değer |
|--------|-------|
| **Tanım** | PHI blockchain'e yazılırsa silinemez → "unutulma hakkı" ihlali |
| **Olasılık (Öncesi)** | Yüksek (tasarım hatası riski) |
| **Etki** | Çok Yüksek (GDPR ihlali, para cezası) |
| **Risk Skoru (Öncesi)** | 🔴 **YÜKSEKKkk (5×5 = 25)** |
| **Azaltma Önlemleri** | **Mimari Karar:** Ham PHI ASLA blockchain'e yazılmaz. Yalnızca SHA-256 Merkle root kaydedilir. PHI off-chain sistemlerde silinebilir. Blockchain'deki hash tek başına PHI değildir. |
| **Kalan Risk** | 🟢 **DÜŞÜK (1×2 = 2)** |
| **Referans** | [docs/adr/0001](./adr/0001-offchain-storage-onchain-anchoring.md) |

### Risk 3: Yetkisiz Acil Erişim (Break-Glass Kötüye Kullanımı)

| Kriter | Değer |
|--------|-------|
| **Tanım** | Doktor, gerekli olmayan durumlarda break-glass yetkisini kötüye kullanır |
| **Olasılık** | Orta |
| **Etki** | Yüksek |
| **Risk Skoru (Öncesi)** | 🔴 **YÜKSEKKkk (3×4 = 12)** |
| **Azaltma Önlemleri** | 15 dakika otomatik sona erme; gerekçe zorunluluğu; tüm break-glass olayları değiştirilemez audit log'a kaydedilir; hasta bildirim sistemi |
| **Kalan Risk** | 🟡 **ORTA (2×2 = 4)** |

### Risk 4: QR Token Ele Geçirilmesi

| Kriter | Değer |
|--------|-------|
| **Tanım** | Ambulans QR kodu yetkisiz kişilerce kopyalanıp kullanılır |
| **Olasılık** | Düşük |
| **Etki** | Orta |
| **Risk Skoru (Öncesi)** | 🟡 **ORTA (2×3 = 6)** |
| **Azaltma Önlemleri** | HMAC-SHA256 imzalı token; 72 saat geçerlilik; 15 dakika oturum süresi; anlık iptal endpoint'i; oturum bazlı audit log |
| **Kalan Risk** | 🟢 **DÜŞÜK (1×2 = 2)** |

### Risk 5: Dead-Man's Switch Yanlış Tetiklenmesi

| Kriter | Değer |
|--------|-------|
| **Tanım** | Sistem yanlışlıkla tetiklenir ve varis yetkisiz erişim alır |
| **Olasılık** | Düşük |
| **Etki** | Yüksek |
| **Risk Skoru (Öncesi)** | 🟡 **ORTA (2×4 = 8)** |
| **Azaltma Önlemleri** | Yapılandırılabilir eşik (30-365 gün); heartbeat ping mekanizması; dondurma (paused) modu; varis erişimi yalnızca belirli kapsam dahilinde; tüm olaylar audit log'a kaydedilir |
| **Kalan Risk** | 🟢 **DÜŞÜK (1×2 = 2)** |

### Risk 6: ZKP Kanıt Sahteciliği

| Kriter | Değer |
|--------|-------|
| **Tanım** | Kötü niyetli aktör sahte bir ZKP kanıtıyla sağlık özelliğini yanıltıcı biçimde kanıtlar |
| **Olasılık** | Çok Düşük |
| **Etki** | Orta |
| **Risk Skoru (Öncesi)** | 🟡 **DÜŞÜK-ORTA (1×3 = 3)** |
| **Azaltma Önlemleri** | Pedersen commitment binding özelliği; Schnorr soundness (kanıt sahteciliği kriptografik olarak imkansız 2048-bit safe prime grubunda); Fiat-Shamir challenge bağımlılığı |
| **Kalan Risk** | 🟢 **ÇOK DÜŞÜK (1×1 = 1)** |

### Risk 7: Veri Sızıntısı (Insider Threat)

| Kriter | Değer |
|--------|-------|
| **Tanım** | İçerideki yetkili kullanıcı (admin/doktor) veriyi sızdırır |
| **Olasılık** | Orta |
| **Etki** | Çok Yüksek |
| **Risk Skoru (Öncesi)** | 🔴 **YÜKSEKKkk (3×5 = 15)** |
| **Azaltma Önlemleri** | Şifre çözme yalnızca hasta şifresi ile mümkün; doktor yalnızca consent verilen kayıt tiplerini görebilir; audit log; role-based erişim; break-glass gerekçe zorunluluğu |
| **Kalan Risk** | 🟡 **ORTA (2×3 = 6)** |

---

## 4. Genel Risk Değerlendirme Özeti

| Risk | Öncesi | Sonrası |
|------|--------|---------|
| Yetkisiz veri erişimi | 🔴 25 | 🟡 6 |
| Blockchain'de PHI kalıcılığı | 🔴 25 | 🟢 2 |
| Break-glass kötüye kullanımı | 🔴 12 | 🟡 4 |
| QR token ele geçirilmesi | 🟡 6 | 🟢 2 |
| Dead-Man yanlış tetiklenme | 🟡 8 | 🟢 2 |
| ZKP sahteciliği | 🟡 3 | 🟢 1 |
| İçeriden sızıntı | 🔴 15 | 🟡 6 |
| **GENEL** | **🔴 YÜKSEKKkk** | **🟡 ORTA-DÜŞÜK** |

---

## 5. Privacy by Design İlkelerinin Uygulanması (GDPR Art. 25)

| İlke | Uygulama |
|------|----------|
| **Veri minimizasyonu** | ZKP ile sıfır bilgi; blockchain'e yalnızca hash |
| **Amaç sınırlılığı** | Her endpoint belirli amaçla kısıtlı; consent scope |
| **Depolama sınırlılığı** | Session token otomatik sona erme; QR 72 saat |
| **Bütünlük ve gizlilik** | AES-256-GCM + Merkle root notarization |
| **Hesap verebilirlik** | Tüm erişimler audit log'da; değiştirilemez blockchain kaydı |
| **Tasarımdan gizlilik** | Off-chain PHI, on-chain hash — mimari seviyede korunan |
| **Varsayılan gizlilik** | Yeni doktor eklenmeden önce consent yoktur; varsayılan = erişim yok |

---

## 6. Danışma ve Onay

| Rol | Eylem | Durum |
|-----|-------|-------|
| Teknik Güvenlik İncelemesi | SECURITY.md + audit trail doğrulama | ✅ Tamamlandı |
| Mimari Güvenlik İncelemesi | ADR-0001 off-chain kararı | ✅ Tamamlandı |
| Kriptografi İncelemesi | AES-256-GCM + Argon2id + Schnorr ZKP | ✅ Tamamlandı |
| DPO / Hukuk Danışması | Gerçek üretim öncesi gerekli | ⏳ Beklemede |
| KVKK VERBİS Kaydı | Üretim ortamında zorunlu | ⏳ Beklemede |

---

## 7. DPIA Revizyon Takvimi

- **İlk DPIA:** 2026-07-24
- **Bir Sonraki İnceleme:** 2027-01-24 (6 ayda bir zorunlu)
- **Tetikleyici Revizyonlar:** Yeni özellik eklendiğinde, veri sızıntısı sonrasında, mevzuat değişikliğinde
