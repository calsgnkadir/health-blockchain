# Veri Koruma Etki Değerlendirmesi (DPIA)
# VIP Health Vault — v5.0.0

## 1. Sistem Özeti
VIP Health Vault, devlet adamları, bakanlar ve kritik personelin tıbbi verilerini yüksek güvenlikli izole bir kasada tutmak üzere tasarlanmıştır.

## 2. Risk Analizi ve Azaltıcı Önlemler

| Risk | Tehdit Derecesi | Uygulanan Kriptografik / İdari Önlem |
|:---|:---|:---|
| Kamusal Blokzincirde Metadata Sızıntısı | Yüksek | Public Sepolia ve SIWE cüzdan entegrasyonu tamamen kaldırıldı. Yerel Dahili Merkle Hash-Chain kullanılıyor. |
| İç Tehdit (Kötü Niyetli Admin) | Kritik | Dual-Control M-of-N Approval Engine eklendi. Admin tek başına kayıt çözemez; Güvenlik Görevlisi çift onayı zorunludur. |
| Halka Açık Ağdan İnternet Saldırısı | Yüksek | `IPAllowlistMiddleware` ile ağ seviyesinde izolasyon sağlandı. Sadece VPN/İntranet IP'leri kabul edilir. |
| Vasi (Guardian) Hesabının Ele Geçirilmesi | Kritik | Sosyal kurtarma (Guardians) tamamen kaldırıldı. Şifresiz giriş için Donanım FIDO2 / Passkey mecburi tutuldu. |
