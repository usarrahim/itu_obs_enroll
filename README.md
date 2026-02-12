## İTÜ OBS Ders Kayıt Otomasyon Scripti

Bu repo, İTÜ OBS ders kayıt ekranına tam saatinde istek atmak için yazılmış,
minimal bir Python scripti içerir. Script:

- Playwright ile OBS'e tarayıcı üzerinden giriş yapar.
- JWT Bearer token alır.
- Belirlediğiniz hedef zamanda, girdiğiniz CRN listesi ile OBS ders kayıt API'sine istek gönderir.
- İsterseniz aynı oturumla ek istekler atmanıza izin verir.

Bu proje yalnızca **kişisel kullanım** içindir. Üniversitenin kullanım şartları, hız limitleri
ve akademik etik kuralları tamamen sizin sorumluluğunuzdadır.

---

## İçerik

- `itu_obs_enroll.py`: Ana script, kullanıcıdan bilgileri alır ve istekleri yapar.
- `obs_login.py`: Playwright kullanarak OBS'e login olup JWT token alan yardımcı modül.
- `requirements.txt`: Gerekli Python paketleri.

---

## Kurulum

1. Python 3.10+ kurulu olduğundan emin olun.
2. Depoyu klonlayın:

```bash
git clone <repo-url>
cd pub-ke-uti
```

3. Sanal ortam (isteğe bağlı ama tavsiye edilir):

```bash
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# veya
source .venv/bin/activate  # macOS / Linux
```

4. Bağımlılıkları yükleyin:

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Kullanım

Ana script:

```bash
python itu_obs_enroll.py
```

Script sizden sırayla şunları ister:

1. **OBS kullanıcı adın (e-posta)**  
2. **OBS şifren** (terminalde gizli girilir)  
3. **Hedef saat** (örneğin `14:00:00.500`)  
4. **ADD (ECRN) CRN listesi**  
   - Örnek: `12345, 23456, 34567`
   - Boş bırakırsanız ekleme yapılmaz.
5. **DROP (SCRN) CRN listesi**  
   - Örnek: `11111, 22222`
   - Boş bırakırsanız ders bırakma yapılmaz.

Ardından:

- Playwright ile OBS'e otomatik giriş yapılır.
- `obs_login.py` içindeki akış, `/ogrenci/auth/jwt` endpoint'inden JWT token almaya çalışır.
- Token alındıktan sonra script hedef saate kadar bekler ve tek seferlik kayıt isteği gönderir.
- Sonrasında terminalde `"1"` + Enter tuşlayarak aynı oturumla ek istekler atabilirsiniz.

---

## Güvenlik Notları

- Kullanıcı adı ve şifre **asla koda yazılmamalıdır**. Script bu bilgileri her çalıştırmada
  terminalden ister.
- Depoyu GitHub'a atarken `.env` dosyası kullanıyorsanız, `.gitignore` zaten `.env` satırını
  içerir; yine de hassas bilgileri commit etmediğinizden emin olun.
- OBS tarafındaki endpointler ve davranışlar zamanla değişebilir. Bu durumda özellikle
  `obs_login.py` içindeki login / JWT alma akışını güncellemeniz gerekebilir.

---

## Hukuki / Etik Sorumluluk

- Bu proje resmi bir İTÜ ürünü değildir.
- Kullanımınızdan doğan her türlü sorumluluk size aittir.
- Üniversitenin otomasyon sistemi için belirlediği kuralları, hız limitlerini ve kullanım
  koşullarını ihlal etmeyecek şekilde kullanmanız gerekir.

