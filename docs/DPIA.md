# Veri Koruma Etki Değerlendirmesi (DPIA)
# Mahrem — v6.0.0

## 1. Sistem Özeti
Mahrem, serbest çalışan psikologların danışan kayıtlarını (seans notları, ölçek
sonuçları, tedavi planları, ödevler) tutmak için tasarlanmıştır. Bu kayıtlar KVKK
m.6 kapsamında özel nitelikli sağlık verisidir. Danışan, uzmanının hangi kayıtları
ne kadar süre göreceğine kendisi karar verir.

Önceki sürüm (*VIP Health Vault*) aynı güvenlik çekirdeğini üst düzey kişilerin
tıbbi verileri için kullanıyordu; aşağıdaki ilk dört satır o dönemde alınan
kararlardır ve geçerliliğini korur.

## 2. Risk Analizi ve Azaltıcı Önlemler

| Risk | Tehdit Derecesi | Uygulanan Kriptografik / İdari Önlem |
|:---|:---|:---|
| Kamusal Blokzincirde Metadata Sızıntısı | Yüksek | Public Sepolia ve SIWE cüzdan entegrasyonu tamamen kaldırıldı. Yerel Dahili Merkle Hash-Chain kullanılıyor. |
| İç Tehdit (Kötü Niyetli Admin) | Kritik | Dual-Control M-of-N Approval Engine eklendi. Admin tek başına kayıt çözemez; Güvenlik Görevlisi çift onayı zorunludur. |
| Halka Açık Ağdan İnternet Saldırısı | Yüksek | `IPAllowlistMiddleware` ile ağ seviyesinde izolasyon sağlandı. Sadece VPN/İntranet IP'leri kabul edilir. |
| Vasi (Guardian) Hesabının Ele Geçirilmesi | Kritik | Sosyal kurtarma (Guardians) tamamen kaldırıldı. Donanım FIDO2 / Passkey desteklenir. |
| Uzmanın rıza dışı kayıt okuması | Kritik | Tek erişim politikası (ADR-0003): rızası olmayan uzman danışanın dosyasını hiç göremez, rıza kayıt türü bazındadır. Tek kayıt uç noktasındaki IDOR bu kapsamda kapatıldı. |
| Danışanın özel notlarının uzmana, uzmanın süreç notlarının danışana sızması | Yüksek | Kayıt düzeyinde erişim seviyeleri: "Client Only" uzmana, "Practitioner Only" danışana hiçbir uç noktada gösterilmez. |
| Davet kodunun ele geçirilmesi | Orta | Kod tek kullanımlık, 72 saat geçerli, yalnızca hash'i saklanır; bağlantıda URL parçasında (`#`) taşındığı için sunucu loglarına düşmez. Davet hiçbir erişim vermez. |
| Parola tahmini | Yüksek | Argon2id, IP başına dakikada 5 giriş denemesi (şifre, passkey ve davet kodu). |
