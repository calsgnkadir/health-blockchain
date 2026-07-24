# Rıza Yönetimi (Consent) — Akış Dokümantasyonu
# VIP Health Vault v3.1

> Bu belge, VIP Health Vault platformundaki tüm veri erişim onayı (consent) akışlarını,  
> API endpoint'lerini ve KVKK/GDPR uyum gerekliliklerini açıklar.

---

## 1. Normal Consent Akışı (Standart Doktor Erişimi)

`
Hasta (vip_patient)           Sistem                    Doktor (doctor)
     |                           |                           |
     |-- POST /consent --------> |                           |
     |   { doctor: "dr.smith",   |                           |
     |     record_type: "all",   |                           |
     |     duration_days: 30 }   |                           |
     |                           |-- Consent kaydedilir      |
     |                           |-- Audit log yazılır       |
     |<-- { success: true } -----|                           |
     |                           |                           |
     |                           |<--- GET /records/VIP-001 -|
     |                           |-- Consent doğrulanır      |
     |                           |-- Kayıtlar döndürülür --->|
     |                           |                           |
`

### API Endpointleri

| Endpoint | Method | Açıklama | Yetki |
|----------|--------|----------|-------|
| /api/v1/consent/{patient_id} | GET | Aktif onayları listele | vip_patient, doctor |
| /api/v1/consent | POST | Doktora onay ver | vip_patient |
| /api/v1/consent/{pid}/{doc}/{type} | DELETE | Onayı iptal et | vip_patient |

### Consent Türleri (record_type)

| Değer | Kapsam |
|-------|--------|
| ll | Tüm kayıt tipleri |
| ital_signs | Yalnızca vital bulgular |
| lab_result | Yalnızca laboratuvar sonuçları |
| prescription | Yalnızca reçeteler |
| diagnosis | Yalnızca tanılar |
| imaging | Yalnızca görüntüleme dosyaları |

---

## 2. Break-Glass Acil Erişim Akışı

`
Doktor (doctor)                Sistem                    Audit Trail
     |                           |                           |
     |-- POST /consent/{id}/     |                           |
     |       break-glass ------> |                           |
     |   { reason: "Hayati       |                           |
     |     tehlike — acil" }     |                           |
     |                           |-- Gerekçe sanitize edilir |
     |                           |-- 15 dk erişim açılır     |
     |                           |-- Blockchain'e log yazılır|-->|
     |<-- { success: true } -----|                           |   |
     |                           |                           |   |
     |--- GET /records/VIP-001   |                           |   |
     |    (Consent bypass) ------>|                          |   |
     |                           |-- 15 dk doldu mu? ------->|   |
     |                           |-- Erişim kapatılır       |   |
     |                           |-- Hasta bildirim alır     |   |
                                                                 |
                              [DEĞIŞTIRILEMEZ AUDIT LOG: --------+
                               - Doktor kullanıcı adı
                               - Zaman damgası
                               - Gerekçe
                               - Erişilen kayıt tipleri ]
`

**KVKK/GDPR Dayanak:** KVKK 6(3) — hayati tehlike; GDPR 9(2)(c) — sağlık hizmetinin gerektirdiği

---

## 3. QR/NFC Acil Erişim Akışı

`
Hasta (VIP-001)           QR Sistemi              Ambulans/Acil Servis
     |                       |                           |
     |-- GET /emergency/qr/  |                           |
     |   token/VIP-001 ----> |                           |
     |                       |-- HMAC-SHA256 token üretilir
     |                       |   (72 saat geçerli)       |
     |<-- QR kodu (PNG) -----|                           |
     |   [QR'i cüzdanında    |                           |
     |    veya cihazında     |                           |
     |    saklar]            |                           |
     |                       |                           |
     |   [Acil Durum!]       |                           |
     |                       |<-- POST /emergency/activate|
     |                       |    { token: "eyJ..." }    |
     |                       |-- Token HMAC doğrulanır   |
     |                       |-- 15 dk oturum açılır     |
     |                       |-- Yalnızca READ-ONLY      |
     |                       |-- Audit log yazılır ------>|
     |                       |-- { emergency_token: ... }|-->|
     |                       |                           |   |
     |-- GET /revoke/session--|                           |   |
     |   (isteğe bağlı) ---> |                           |   |
     |                       |-- Oturum iptal edilir     |   |
`

---

## 4. Dead-Man's Switch (Miras) Rıza Akışı

`
Hasta (VIP-001)           Sistem                    Varis (dr.smith)
     |                       |                          |
     |-- POST /deadman/config |                          |
     |   { inactivity: 90,   |                          |
     |     beneficiaries:    |                          |
     |     [{username: dr.smith,|                        |
     |       access: all}] } |                          |
     |                       |-- Yapılandırma kaydedilir|
     |<-- { success: true }  |                          |
     |                       |                          |
     |   [Her girişte]       |                          |
     |-- POST /deadman/ping ->|                          |
     |                       |-- Heartbeat sıfırlanır   |
     |                       |                          |
     |   [90 gün geçti]      |                          |
     |                       |-- Status: triggered      |
     |                       |-- Audit log yazılır      |
     |                       |                          |
     |                       |<-- GET /deadman/          |
     |                       |    beneficiary-access/   |
     |                       |    VIP-001 ------------>|
     |                       |-- Status=triggered mı?   |
     |                       |-- Evet → Kayıtlar açılır->|
`

**Önemli:** Hasta önceden açık rıza vermiştir (KVKK 5(1) / GDPR 6(1)(a)).  
Miras kilidi bu rızanın otomatik yürütme mekanizmasıdır.

---

## 5. ZKP Sıfır Bilgi Akışı

`
Hasta (VIP-001)           ZKP Sistemi              Doktor / Kurum
     |                       |                          |
     |-- POST /zkp/commitment |                          |
     |   { claim_type:       |                          |
     |     "has_allergy",    |                          |
     |     claim_label:      |                          |
     |     "Penisilin" }---->|                          |
     |                       |-- v = SHA256("has_allergy:Penisilin")
     |                       |-- r = random() (gizli)   |
     |                       |-- C = g^v * h^r (mod p)  |
     |                       |-- Proof üretilir          |
     |<-- { commitment, proof,|                          |
     |      secret.r } ------|                          |
     |                       |                          |
     |   [Kanıtı paylaşır]   |                          |
     |--- { proof_json } ---------------------------->  |
     |                       |                          |
     |                       |<-- POST /zkp/verify ------|
     |                       |    { commitment_hex,     |
     |                       |      R_hex, s_int, ...}  |
     |                       |-- h^s == R*(C/g^v)^e ?   |
     |                       |-- TRUE ✅                |
     |                       |-- { verified: true,      |
     |                       |    raw_data_exposed: false}|
     |                       |------------------------>  |
     |                       |    [Doktor yalnızca       |
     |                       |     "✓ Penisilin alerjisi |
     |                       |     VAR" sonucunu alır.   |
     |                       |     Ham veri GÖRÜLMEZ]   |
`

---

## 6. Rıza Yönetimi İlkeleri (KVKK/GDPR Özeti)

| İlke | Uygulama |
|------|----------|
| **Özgür** | Hasta zorunlu tutulmadan onay verir; onsuz hizmet kesilmez |
| **Belirli** | Her kayıt türü için ayrı onay (vital_signs, lab_result vb.) |
| **Bilgilendirilmiş** | Hangi doktorun, hangi veriye, ne kadar erişeceği açıkça belirtilir |
| **Açık** | Üstü kapalı onay yok; aktif eylem (POST /consent) gerekir |
| **Geri alınabilir** | DELETE /consent her an çalışır, anlık iptal |
| **Kanıtlanabilir** | Tüm onay/iptal olayları blockchain audit log'da |
