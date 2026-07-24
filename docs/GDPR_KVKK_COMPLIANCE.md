# KVKK & GDPR Uyumluluk Beyanı
# VIP Health Vault — Veri Koruma Çerçevesi v1.0

> **Belge Türü:** Kişisel Veri İşleme Envanteri ve Uyumluluk Beyanı  
> **Kapsam:** VIP Health Vault platformunda işlenen tüm kişisel ve özel nitelikli kişisel veriler  
> **Güncelleme:** 2026-07-24  
> **Referans Mevzuat:** 6698 sayılı KVKK · GDPR (AB) 2016/679 · HIPAA (ABD) · ISO/IEC 27701:2019

---

## 1. Veri Sorumlusu Bilgileri

| Alan | Bilgi |
|------|-------|
| **Ünvan** | VIP Health Vault İşletmecisi |
| **Platform** | health-blockchain (GitHub: calsgnkadir/health-blockchain) |
| **Teknik Mimarisi** | Clean Architecture, CQRS, Blockchain Notarization |
| **Veri İşleme Modeli** | Off-chain şifreli depolama + On-chain Merkle Root notarizasyonu |

> ⚠️ **Kritik Mimari Notu:** Ham Kişisel Sağlık Verisi (PHI) **hiçbir zaman blockchain'e yazılmaz**.  
> Yalnızca kriptografik hash (Merkle root) zincire kaydedilir — GDPR 4(1) ve KVKK 3(d) uyumu sağlanır.

---

## 2. İşlenen Kişisel Veri Kategorileri

### 2.1 Sıradan Kişisel Veriler

| Veri Kategorisi | Veri Örnekleri | İşleme Amacı | Hukuki Dayanak |
|----------------|----------------|--------------|----------------|
| Kimlik | Ad, soyad, kullanıcı adı | Hesap yönetimi | KVKK 5(2)(c) / GDPR 6(1)(b) |
| İletişim | E-posta (opsiyonel) | Bildirim | KVKK 5(1) / GDPR 6(1)(a) |
| Dijital Kimlik | Cüzdan adresi (Ethereum), device fingerprint | Kimlik doğrulama | KVKK 5(2)(f) / GDPR 6(1)(f) |
| Güvenlik | Argon2id şifre hash, TOTP sırrı | Güvenlik | KVKK 5(2)(f) / GDPR 6(1)(b) |

### 2.2 Özel Nitelikli Kişisel Veriler (Sağlık Verileri)

| Veri Kategorisi | Veri Örnekleri | Saklama Konumu | Şifreleme |
|----------------|----------------|----------------|-----------|
| Tıbbi Tanı | ICD-10 kodları, hastalık açıklamaları | Off-chain (LMDB/IPFS) | AES-256-GCM |
| Reçete | İlaç adı, doz, süre | Off-chain | AES-256-GCM |
| Laboratuvar | Kan tahlili, test sonuçları | Off-chain | AES-256-GCM |
| Görüntüleme | DICOM dosyaları (MRI, röntgen) | IPFS (şifreli) | AES-256-GCM |
| Ameliyat | Operasyon tipi, tarih | Off-chain | AES-256-GCM |
| Alerji | Alerjen madde adları | Off-chain | AES-256-GCM |
| Vital Bulgular | Tansiyon, nabız, SpO2 | Off-chain | AES-256-GCM |
| **ZKP Commitment** | Pedersen commitment değerleri | SQLite (commitment_hex) | Matematiksel gizlilik |

> **KVKK 6. Madde / GDPR 9. Madde:** Sağlık verileri özel nitelikli kişisel veri kategorisindedir.  
> Platform, bu verileri yalnızca **açık rıza (explicit consent)** veya **sağlık hizmeti amacıyla** işler.

---

## 3. Veri İşleme Envanteri (RoPA)

### 3.1 Hasta Kaydı ve Kimlik Doğrulama

| Alan | Detay |
|------|-------|
| **Faaliyet** | Kullanıcı hesabı oluşturma, kimlik doğrulama |
| **Veri Sahibi Kategorisi** | VIP Hasta (vip_patient rolü) |
| **İşlenen Veriler** | Kullanıcı adı, şifre hash (Argon2id), 2FA sırrı, cüzdan adresi |
| **Amaç** | Yetkisiz erişimi engellemek |
| **Hukuki Dayanak** | KVKK 5(2)(c) — sözleşme, GDPR 6(1)(b) |
| **Saklama Süresi** | Hesap aktif olduğu sürece + 10 yıl (zorunlu tutma) |
| **Güvenlik Önlemi** | Argon2id (m=65536, t=3, p=2), TOTP, WebAuthn FIDO2, rate limiting |
| **Üçüncü Taraf** | Yok |

### 3.2 Tıbbi Kayıt İşleme

| Alan | Detay |
|------|-------|
| **Faaliyet** | Sağlık kayıtlarının oluşturulması, görüntülenmesi, güncellenmesi |
| **Veri Sahibi Kategorisi** | VIP Hasta |
| **İşlenen Veriler** | Tüm sağlık verileri (tanı, reçete, lab, görüntüleme vb.) |
| **Amaç** | Sağlık hizmetinin sağlanması, tıbbi geçmişin korunması |
| **Hukuki Dayanak** | KVKK 6(3) — sağlık hizmeti; GDPR 9(2)(h) |
| **Saklama Süresi** | Minimum 20 yıl (Türkiye Hasta Hakları Yönetmeliği) |
| **Güvenlik Önlemi** | AES-256-GCM çift katman şifreleme, LMDB/IPFS off-chain depolama |
| **Blockchain Kaydı** | Yalnızca SHA-256 Merkle root — PHI içermez |
| **Üçüncü Taraf** | IPFS (şifreli — içerik görülemez) |

### 3.3 Doktor Erişim Onayı (Consent)

| Alan | Detay |
|------|-------|
| **Faaliyet** | Hasta → Doktor erişim izni verme/iptal etme |
| **İşlenen Veriler** | Hasta ID, doktor kullanıcı adı, kayıt türü, süre |
| **Amaç** | Veri sahibinin erişim kontrolünü yönetmesi |
| **Hukuki Dayanak** | KVKK 5(1) / GDPR 6(1)(a) — açık rıza |
| **Denetim Kaydı** | Her onay/iptal işlemi blockchain'e zaman damgalı kaydedilir |
| **Geri Alınabilirlik** | Hasta istediği zaman DELETE /api/v1/consent/{id} ile iptal edebilir |

### 3.4 Break-Glass Acil Erişim

| Alan | Detay |
|------|-------|
| **Faaliyet** | Doktor, acil durumlarda hasta onayı olmadan kayıtlara erişir |
| **İşlenen Veriler** | Erişilen kayıt tipleri, doktor kimliği, gerekçe, zaman |
| **Hukuki Dayanak** | KVKK 6(3) — hayati tehlike; GDPR 9(2)(c) |
| **Süre Sınırı** | 15 dakika (otomatik sona erme) |
| **Denetim** | Tüm break-glass olayları değiştirilemez audit log'a yazılır |
| **Bildirim** | Hasta, erişim sonrası sistemde bildirim alır |

### 3.5 QR/NFC Acil Erişim Oturumu

| Alan | Detay |
|------|-------|
| **Faaliyet** | Ambulans/acil servis personeli QR ile erişim alır |
| **İşlenen Veriler** | HMAC-SHA256 token, oturum ID, aktivasyon zamanı, IP |
| **Süre Sınırı** | 72 saat token geçerliliği, 15 dakika oturum |
| **Kapsam** | Yalnızca READ-ONLY, acil sağlık verileri |
| **İptal** | Hasta veya doktor /api/v1/emergency/revoke/{id} ile anlık iptal edebilir |

### 3.6 Dead-Man's Switch (Miras Kilidi)

| Alan | Detay |
|------|-------|
| **Faaliyet** | İnaktivite süresinde varis erişiminin tetiklenmesi |
| **İşlenen Veriler** | Varis kullanıcı adları, ilişki bilgisi, inaktivite eşiği, heartbeat zamanı |
| **Hukuki Dayanak** | KVKK 5(2)(c) — hasta önceden açık rıza vermiştir |
| **Tetiklenme Koşulu** | Yapılandırılmış inaktivite süresi (30-365 gün) dolması |
| **Güvenlik** | Varis erişimi yalnızca 	riggered durumunda ve belirlenen kapsam dahilinde |

### 3.7 ZKP Seçici İfşa (Sıfır Bilgi Kanıtı)

| Alan | Detay |
|------|-------|
| **Faaliyet** | Hasta, sağlık özelliğini açıklamadan kanıtlar |
| **İşlenen Veriler** | Pedersen commitment_hex, kanıt metadata (R_hex, s_int, challenge_hex) |
| **Ham Veri** | **İşlenmez, depolanmaz, iletilmez** — matematiksel gizlilik güvencesi |
| **Doğrulayıcı** | Doktor/kurum kanıtı token olmadan doğrulayabilir |
| **GDPR Uyumu** | Data minimization ilkesinin en güçlü uygulaması (GDPR 5(1)(c)) |

---

## 4. Veri Sahibi Hakları (KVKK 11. Madde / GDPR 15-22. Maddeler)

| Hak | API Endpoint / Mekanizma | Yanıt Süresi |
|----|-------------------------|-------------|
| **Bilgi alma (KVKK 11/a)** | GET /api/v1/records/{patient_id} | Anlık |
| **Erişim (GDPR Art. 15)** | Hasta paneli → tüm kayıtları görüntüle | Anlık |
| **Düzeltme (KVKK 11/b)** | Yeni kayıt bloğu eklenebilir (blockchain değişmez) | Anlık |
| **Silme / Unutulma (GDPR Art. 17)** | Manuel veri sorumlusu işlemi (**) | 30 gün |
| **İşlemeyi kısıtlama** | DELETE /api/v1/consent/... (doktor erişimini kal) | Anlık |
| **Veri taşınabilirliği (GDPR Art. 20)** | GET /api/v1/records/{id} → JSON/FHIR R4 formatı | Anlık |
| **İtiraz (KVKK 11/e)** | Consent iptali ve audit log talebi | 30 gün |

> (**) **Silme Hakkı ve Blockchain Gerilimi:** Blockchain'e yazılan Merkle root'lar değiştirilemez niteliktedir.  
> Ancak ham sağlık verisi off-chain sistemlerde tutulduğundan, fiziksel veri silinebilir.  
> Blockchain'de kalan hash artık herhangi bir kişisel veriye teknik olarak erişim sağlayamaz.  
> Bu yaklaşım EDPB (Avrupa Veri Koruma Kurulu) "Blockchain ve GDPR" rehberiyle uyumludur.

---

## 5. Güvenlik Önlemleri (Teknik ve İdari Tedbirler)

### 5.1 Teknik Önlemler

| Önlem | Uygulama |
|-------|----------|
| Şifreleme (at-rest) | AES-256-GCM + Argon2id key derivation |
| Şifreleme (in-transit) | TLS 1.3 (Render.com / production) |
| Kimlik Doğrulama | RS256 JWT + TOTP 2FA + WebAuthn FIDO2 + SIWE |
| Yetkilendirme | Role-based (vip_patient, doctor, admin) + Consent |
| Denetim Kaydı | Her kayıt erişimi blockchain audit log'a yazılır |
| CSRF Koruması | SameSite strict cookie + X-CSRF-Token header |
| XSS Koruması | Sunucu tarafı sanitizasyon (bleach) + CSP header |
| Rate Limiting | IP bazlı istek sınırlama middleware |
| Bütünlük | SHA-256 Merkle tree + on-chain notarization |
| Sıfır Bilgi | Pedersen Commitment + Schnorr NIZK (ZKP modülü) |

### 5.2 İdari Önlemler

- Geliştirici erişimi git blame ile izlenir
- Tüm değişiklikler commit geçmişinde değiştirilemez biçimde kayıtlıdır
- .env.example şablonu, gerçek sırlar .env.example'a asla yazılmaz
- SECURITY.md'de güvenlik açığı bildirme süreci tanımlıdır

---

## 6. Veri Transferi (Yurt İçi / Yurt Dışı)

| Sistem | Konum | Aktarılan Veri | Güvence |
|--------|-------|----------------|---------|
| Render.com | ABD (AWS bölgesi) | Uygulama kodu, şifreli veriler | SCCs / EU-U.S. DPF |
| IPFS (Simülasyon) | Yerel | Şifreli dosya blobu | Şifre çözme anahtarı aktarılmaz |
| Polygon/Sepolia | Küresel | Yalnızca Merkle root hash | PHI içermiyor |
| GitHub | ABD | Kaynak kodu (sırlar hariç) | Public repo — sır yok |

---

## 7. Saklama ve İmha Politikası

| Veri Türü | Saklama Süresi | İmha Yöntemi |
|-----------|----------------|--------------|
| Sağlık kayıtları | 20 yıl (Türkiye) / hastanın ömrü + 10 yıl | Kriptografik silme (anahtar imhası) |
| Kimlik bilgileri | Hesap kapatma + 10 yıl | Güvenli silme |
| Audit log | 10 yıl | Arşiv → imha |
| Consent kayıtları | İptal tarihi + 5 yıl | Güvenli silme |
| ZKP commitment | Hasta talebi ile | Kayıt silme (DELETE zkp_commitments) |
| Session token | JWT exp (1 saat) / QR token (72 saat) | Otomatik sona erme |

---

## 8. Kişisel Veri İhlali Prosedürü

**KVKK 12/5 ve GDPR 33. Madde gereği:**

1. **İhlal Tespiti** → Sistem audit log alarm mekanizması
2. **İlk 24 saat** → İç değerlendirme, etki analizi
3. **72 saat içinde** → KVKK Kurulu'na bildirim (GDPR: DPA'ya bildirim)
4. **Veri sahiplerine bildirim** → "Yüksek risk" ihlallerinde zorunlu
5. **Hafifletici faktörler** → AES-256 şifreleme aktifse ve anahtar ele geçirilmediyse risk minimal kabul edilir

**İletişim:** SECURITY.md dosyasındaki prosedür uygulanır.

---

## 9. Referanslar

- [Kişisel Verilerin Korunması Kanunu No. 6698](https://www.kvkk.gov.tr/Icerik/4208/6698-SAYILI-KANUN)
- [GDPR — Regulation (EU) 2016/679](https://gdpr-info.eu/)
- [EDPB — Blockchain ve GDPR Rehberi](https://edpb.europa.eu/our-work-tools/our-documents/guidelines/)
- [HIPAA Privacy Rule](https://www.hhs.gov/hipaa/for-professionals/privacy/index.html)
- [ISO/IEC 27701:2019 — Privacy Information Management](https://www.iso.org/standard/71670.html)
- [docs/adr/0001-offchain-storage-onchain-anchoring.md](./adr/0001-offchain-storage-onchain-anchoring.md)
