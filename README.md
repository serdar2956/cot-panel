# COT Panel

EUR/USD, GBP/USD, XAU/USD, XAG/USD, Nasdaq-100 ve S&P 500 (ek olarak DXY) için COT, open interest, makro, volatilite, likidite ve sentiment paneli. Site GitHub Pages üzerinde çalışır, veriler GitHub Actions ile her hafta otomatik güncellenir.

## Sekmeler

| Sekme | İçerik |
|---|---|
| Özet | Tüm enstrümanlar tek tabloda: bileşik skor, COT endeksleri, Willco, OI, fiyat–OI durumu, adil değer sapması, uyarılar |
| Enstrümanlar | Grup pozisyonları, COT Index (26/52/156 hafta), net pozisyonlar, OI, Willco, bileşik skor ve bileşenleri, makro adil değer, aşırı uç istatistikleri |
| Makro | Faiz farkları, reel faiz, getiri eğrisi, kredi spread'i, NFCI, GDPNow, altın/gümüş, bakır/altın, NDX/SPX oranları |
| Volatilite | Volatilite rejimi, implied ve realized volatilite, VIX vade yapısı, MOVE |
| Likidite | Net likidite (Fed bilançosu − TGA − ters repo) ve endekslerle ilişkisi |
| Sentiment | Küçük spekülatör (COT non-reportable) endeksi, AAII anketi |
| İstatistik | Aşırı uç sonrası fiyat hareketi, sezonsallık, korelasyon matrisi ve bozulmalar |
| Veri Doğrulama | Her kaynağın durumu ve çapraz kontrol sonuçları |

## Veri kaynakları ve doğrulama

- **COT:** CFTC, Futures Only. Döviz, endeks ve DXY için TFF, altın ve gümüş için Disaggregated raporu. CFTC API'si ile CFTC haftalık metin dosyası birebir karşılaştırılır. Uyuşmazlık varsa yeni hafta yayımlanmaz, sonraki çalıştırmada tekrar denenir.
- **Fiyat (spot):** Yahoo Finance, Stooq, FRED. En az iki kaynak tolerans içinde uyuşmalı (döviz %0.3, diğerleri %1). Altın ve gümüş için Yahoo'da spot veri olmadığından Yahoo vadeli kontratı (GC=F, SI=F) proxy olarak kullanılır, son fiyat ayrıca Swissquote ve gold-api canlı spot ile kontrol edilir. DXY, resmi formülüyle kurlardan hesaplanarak kontrol edilir.
- **Makro:** FRED, ECB, CBOE (VIX, VIX3M, VXN ve GVZ, Yahoo ile çapraz kontrol), AAII.

## Güncelleme takvimi

`.github/workflows/update.yml` cuma akşamı üç kez (Türkiye saatiyle yaklaşık 23:45, 00:45, 02:30) ve pazartesi bir kez çalışır. **Actions** sekmesinden **Run workflow** ile elle de çalıştırılabilir.

## Kurulum

1. Bu klasörü GitHub'da **public** bir repo olarak yükle.
2. **Settings → Pages → Build and deployment**: Source = *Deploy from a branch*, Branch = `main`, klasör = `/docs`.
3. **Settings → Actions → General → Workflow permissions**: *Read and write permissions* seçili olmalı.
4. **Actions** sekmesinde iş akışını etkinleştir ve bir kez **Run workflow** ile çalıştır.

Site adresi: `https://<kullanıcı-adı>.github.io/<repo-adı>/`

## Yerelde çalıştırma

```bash
pip install -r requirements.txt
python scripts/update.py          # verileri çeker, doğrular ve docs/data/ altına yazar
cd docs && python -m http.server  # http://localhost:8000
```

Eğitim ve araştırma amaçlıdır, yatırım tavsiyesi değildir.
