# 4 Ajanlı Sabah Finans Brifingi

Her iş günü 07:30'da başlayan, 08:15'te abonelere e-posta gönderen otomasyon.

```
07:30 ─ Ajan 1 Data Collector ─► briefing.json ─┬─► Ajan 2 HTML ─► briefing.html ─┐
                                                └─► Ajan 3 Video (paralel) ───────┤ (VIDEO_DEADLINE'a kadar)
08:15 ─────────────────────────────────────────────────────── Ajan 4 Dispatcher ◄─┘
                                       └─► Görsel Ajan → terminal/public/data/terminal.json (AURA TERMINAL)
```

## Kurulum

```bash
make install        # .venv + bağımlılıklar + .env şablonu
```

`.env` içindeki anahtarları doldurun (bkz. `.env.example`). Python 3.10+ önerilir (3.9 ile de test edildi).

## Bulutta çalıştırma (GitHub Actions — önerilen)

Mac kapalı olsa da çalışır. [.github/workflows/sabah-brifingi.yml](.github/workflows/sabah-brifingi.yml):

| Zaman (TSİ) | İş |
|---|---|
| Hafta içi 07:15 | Bülten + ses/video hazırlanır, ses GitHub Pages'e yayımlanır, **08:15**'te e-posta gönderilir (resmi tatillerde atlanır) |
| Her gün 18:30, 23:50 | KAP bildirim kopyası (önbellekte saklanır) |
| Elle "Run workflow" | `hemen-gonder`: beklemeden çalıştır ve gönder · `deneme`: e-posta göndermeden ve ses yayımlamadan çalıştır (kayıt kontrolü) |

Kurulum: GitHub CLI ile giriş yapıp (`gh auth login`) `make cloud-setup`. Betik depoyu oluşturur, anahtarları
`.env`'den GitHub Secrets'a aktarır (ekrana yazmadan), ilk test çalışmasını başlatır ve GitHub Pages'i açar.
Depo herkese açıktır (ücretsiz Pages için); `.env` ve `output/` yüklenmez. Sesler tahmin edilemeyen adlarla
yayımlanır ve 14 gün sonra silinir; ancak depo açık olduğundan `gh-pages` dalında görünürler (içerik kamuya açık
haber özetidir). Basın taraması Google Haberler'e erişemezse Bing Haberler'e geçer. Bulut kurulduysa Mac'teki zamanlayıcıyı kaldırın (`make schedule-uninstall`).

## Kişisel kurulum (Mac + Gmail)

1. Google hesabında 2 adımlı doğrulamayı açın, [uygulama şifresi](https://myaccount.google.com/apppasswords) oluşturun.
2. `make email-setup` — Gmail adresi ve uygulama şifresi sorulur (şifre görünmez), Gmail girişi doğrulanır,
   `.env` güncellenir. Gönderen ve alıcı sizin adresinizdir.
3. `make send-test` — gerçek veriyle hemen çalışır ve bülteni adresinize gönderir.
4. `make schedule-install` — Mac'te arka plan servisi (launchd): hafta içi 07:30 başlar, 08:15'te gönderir,
   KAP kopyasını 18:30 ve 23:50'de alır. Çalışma sırasında Mac'in boşta uyuması engellenir (`caffeinate`).
5. `sudo pmset repeat wakeorpoweron MTWRF 07:25:00` — Mac'in hafta içi 07:25'te uyanması.

Mac kapalıysa, kapağı kapalı ve pilde ise veya oturum kapalıysa bülten gönderilmez. Kayıtlar: `logs/scheduler.log`.
Kaldırmak için: `make schedule-uninstall` ve `sudo pmset repeat cancel`.

## Test

```bash
make test           # 11 test, dış servis çağrısı yok
make mock           # sahte veriyle uçtan uca çalıştırma → output/<tarih>/
```

`make mock` = `python main.py --mock --no-wait`. Mock mod **hiçbir zaman e-posta göndermez**
(`--send` verilmedikçe); bunun yerine `briefing.eml` ve `briefing_sent.html` yazar.

## Çalıştırma

| Komut | Açıklama |
|---|---|
| `python main.py --schedule` | Hafta içi 07:30 zamanlayıcısı (TR resmi tatillerini atlar) |
| `python main.py --now` | Şimdi çalıştır, 08:15'i bekleyip gönder |
| `python main.py --now --no-wait --dry-run` | Gerçek veri, beklemeden, gönderim yerine .eml |
| `python -m agents.<ajan> ...` | Her ajan tek başına çalıştırılabilir (`--help`) |

Prod için `--schedule` modunu bir servis olarak (launchd/systemd/Docker) ayakta tutun.

## Yapay zekâ (küratörlük ve konuşma metni)

[agents/llm.py](agents/llm.py) ortak katmanı; `.env` içinde `LLM_PROVIDER` ile seçilir:

| Değer | Kullanılan | Not |
|---|---|---|
| `gemini` (varsayılan) | `GEMINI_TEXT_MODEL` (`gemini-3.8-flash`), `GEMINI_API_KEY` | Ses için girilen anahtarı kullanır |
| `anthropic` | `ANTHROPIC_MODEL` (`claude-opus-5-5`), `ANTHROPIC_API_KEY` | |
| `none` | Kural tabanlı yedek | Anahtar gerekmez |

Yapay zekâ çıktısı her çalışmada kaynaklara karşı denetlenir: kaynak haberlerde olmayan linkler silinir,
kaynakta veya piyasa verisinde geçmeyen rakamlar `briefing.json` → `unverified_figures` alanına ve çalışma
kaydına yazılır. Yapay zekâ hata verirse bülten kural tabanlı yedekle yine çıkar. Testler gerçek API çağırmaz.

## Hata toleransı

- **Ajan 1/2 kritik**: yeniden denenir; Claude erişilemezse kural tabanlı küratörlüğe düşer.
- **Ajan 3 kritik değil**: ayrı thread'de çalışır; `VIDEO_DEADLINE` (vars. 08:10) itibarıyla hazır
  değilse veya hata verirse bülten videosuz gider. Teleprompter scripti her durumda kaydedilir.
- **Ajan 4**: Resend'de kişi başı gönderim + 429/5xx için geri çekilmeli yeniden deneme.
- Her çalışmanın özeti `output/<tarih>/run_report.json` dosyasına yazılır.

## Veri kaynakları — dikkat edilmesi gerekenler

- **Bloomberg / Reuters** içeriği lisanslıdır; kurumunuzun lisanslı feed URL'lerini `.env`'e girin.
- **KAP**: Resmi RSS/API yoktur; kap.org.tr'nin kendi sayfaları için kullandığı bildirim listesi servisi okunur
  ([agents/kap_source.py](agents/kap_source.py)). Servis yalnızca o günün bildirimlerini verdiğinden zamanlayıcı her
  gece `KAP_SNAPSHOT_TIME` (23:50) kopyası alır; sabah çalışması bu kopyayla canlı listeyi birleştirir.
  Komisyon/fon/repo gibi rutin bildirimler elenir, kalanlar konu ve içerik ağırlığına göre puanlanır;
  `kap_watchlist.txt` içindeki şirketler öne çıkarılır. Servis değişir veya yanıt vermezse bülten KAP'sız çıkar.
  Tek başına deneme: `python -m agents.kap_source` (gece kopyası: `--snapshot`).
- **Banka haberleri** (Garanti BBVA, Akbank, Yapı Kredi, QNB): bankaların kendi sitelerindeki basın bültenleri
  ([agents/bank_news.py](agents/bank_news.py)) → bültende ayrı **Bankacılık Gündemi** bölümü. Genel bir çıkarıcı
  sayfadaki tarihli haber kartlarını bulur (bankaya özel kod yok). Yalnızca finansal önemi olanlar (tahvil/eurobond,
  sendikasyon, seküritizasyon, fonlama, sonuçlar, kredi notu) alınır; etkinlik/ödül/sponsorluk haberleri elenir.
  Sayfalarda saat olmadığından pencere "önceki iş gününden bugüne"dir; yeni haber yoksa bölüm görünmez.
  Bir sitenin yapısı değişirse çalışma kaydında "haber kartı bulunamadı" uyarısı çıkar.
  Tek başına deneme: `python -m agents.bank_news --all`. Bankaların KAP bildirimleri `kap_watchlist.txt` ile öne çıkarılır.
  Bültendeki **4 Büyük Banka** bölümü her gün görünür: her bankanın sitesindeki son önemli duyurusu + son 3 günde
  **basında** (Google Haberler araması; yalnızca güvenilir yayınlar, banka adı başlıkta, finansal önem filtresi,
  promosyon/ödül/kampanya haberleri ayrı tutulur) ve **KAP'ta** (rutin bildirimler hariç) çıkan en fazla 3 finansal
  haber; ayrıca "Promosyon, ödül ve sponsorluk" alt başlığında konu başına en yeni 1 haber (en fazla 2),
  bankanın kendi sitesindeki son 3 günlük kurumsal duyurular dahil.
  `BANK_MENTIONS_ENABLED=false` ile basın/KAP kısmı kapatılabilir.
- **Piyasa verileri** yfinance (Yahoo) üzerinden alınır; USD/TRY için TCMB `today.xml` yedektir.
  Kurumsal kullanımda lisanslı bir veri sağlayıcısıyla değiştirilmesi önerilir.
- **Ekonomik takvim**: `output/<tarih>/calendar.json` veya `fixtures/economic_calendar.json` dosyasından okunur
  (format: `fixtures/mock_briefing.json` içindeki `economic_calendar`). Lisanslı takvim API'nizi
  `data_agent.load_calendar_hint` içine bağlayabilirsiniz.

## Ses/video

- **Gemini (varsayılan, `VIDEO_PROVIDER=gemini`)**: Google AI Studio anahtarıyla Türkçe TTS
  (`gemini-3.8-flash-lite-tts`). Gemini'de sayısal hız parametresi yok; ses doğal spiker temposunda
  üretilir, ffmpeg `atempo` ile tam `VOICE_SPEED` (1.25x) hızına getirilir ve piyasa kartlarından oluşan
  1280x720 bir görselle MP4'e dönüştürülür (`video_card.png`, `briefing_video.mp4`). Birleştirme başarısız
  olursa yalnızca ses (WAV) gönderilir. ffmpeg, `imageio-ffmpeg` paketiyle birlikte gelir; ayrıca kurulum gerekmez.
  Tek başına deneme: `python -m agents.video_agent output/<tarih>/briefing.json --provider gemini`
- **ElevenLabs**: API `speed` üst sınırı 1.2'dir; 1.25x'e ulaşmak için ses 1.2 ile üretilip
  ffmpeg `atempo` ile tamamlanır.
- **HeyGen / D-ID**: konuşan avatar videosu; kuyruğa alınır ve deadline'a kadar durum sorgulanır.
- E-postada video (MP4) ve 1.25x ses (MP3) ek olarak gelir; bültendeki **Sesli Brifing** bölümünde yalnızca süre ve
  **▶ Dinle** bağlantısı bulunur. Bağlantı bu Mac'teki yerel medya sunucusunu açar (`http://localhost:8765`,
  yalnızca bu bilgisayardan erişilir, yalnızca ses/video dosyalarını sunar). Sunucu zamanlayıcı servisiyle birlikte
  çalışır; servis kurulu değilse `make media-server`. Telefonda bağlantı açılmaz, ek kullanılır.

## Görsel Ajan — AURA TERMINAL

React 19 + TypeScript + Vite + Tailwind v4 ile yazılmış kurumsal sabah masası arayüzü ([terminal/](terminal/)).
Boru hattı her çalıştığında [agents/terminal_export.py](agents/terminal_export.py) `terminal/public/data/terminal.json`
dosyasını ve web için sıkıştırılmış sesi üretir; arayüz bu dosyayı okur.

```bash
make terminal         # geliştirme sunucusu → http://localhost:5173
make terminal-build   # statik derleme → terminal/dist (herhangi bir dahili web sunucusunda servis edilebilir)
```

Node.js `~/.local/node` altındadır (resmi LTS, yönetici şifresi gerektirmez).

**Gerçek veri:** gösterge şeridi (BIST 100/30, USD/TRY, EUR/TRY, EUR/USD, DXY, Brent, Altın, ABD 10Y),
BIST 100 klasik pivot seviyeleri (önceki seans Y/D/K), sektör nabzı (endeks veya öncü hisse sepeti), toplanan
tüm haberlerden oluşan piyasa akışı (kategori, etki, hisse etiketi), Gemini sesi + spiker metni.

**Örnek veri (arayüzde açıkça işaretli):** analist masası hedef fiyatları (lisanslı araştırma akışı gerekir;
gerçek kurum adı kullanılmaz), TR 2Y tahvil ("—"), boş gelen takvim. Şeritteki saniye altı fiyat hareketleri
**simülasyondur** (önceki kapanışa göre ortalamaya döner, şeritte "simülasyon" yazar, durdurulabilir);
dışa aktarılan not ve haber çekmecesi her zaman gerçek kapanış verisini kullanır.
