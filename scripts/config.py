"""Enstrüman, grup ve veri kaynağı tanımları."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data"           # doğrulanmış ham veri (repo'da saklanır)
SITE_DATA = ROOT / "docs" / "data"  # sitenin okuduğu JSON dosyaları

USER_AGENT = "cot-panel/1.0 (personal research dashboard; github.com)"
HISTORY_START = "2006-01-01"

# Uyarı eşikleri
INDEX_HIGH = 80
INDEX_LOW = 20
LOOKBACKS = [26, 52, 156]

# Fiyat toleransları (göreli fark)
TOL_FX = 0.003
TOL_OTHER = 0.01

# --- CFTC ---
CFTC_API = "https://publicreporting.cftc.gov/resource/{ds}.json"
CFTC_DATASETS = {"tff": "gpe5-46if", "disagg": "72hh-3qpy"}  # Futures Only
CFTC_TEXT = {
    "tff": "https://www.cftc.gov/dea/newcot/FinFutWk.txt",
    "disagg": "https://www.cftc.gov/dea/newcot/f_disagg.txt",
}

# Gruplar: anahtar -> (Türkçe ad, API long alanı, API short alanı, metin dosyası long/short sütunu)
GROUPS = {
    "tff": {
        "dealer": ("Dealer / Aracı", "dealer_positions_long_all", "dealer_positions_short_all", 8, 9),
        "asset_mgr": ("Asset Manager", "asset_mgr_positions_long", "asset_mgr_positions_short", 11, 12),
        "lev_funds": ("Leveraged Funds", "lev_money_positions_long", "lev_money_positions_short", 14, 15),
        "other": ("Diğer Raporlanan", "other_rept_positions_long", "other_rept_positions_short", 17, 18),
        "nonrept": ("Küçük Spekülatör", "nonrept_positions_long_all", "nonrept_positions_short_all", 22, 23),
    },
    "disagg": {
        "prod_merc": ("Üretici / Tüccar", "prod_merc_positions_long", "prod_merc_positions_short", 8, 9),
        "swap": ("Swap Dealer", "swap_positions_long_all", "swap__positions_short_all", 10, 11),
        "managed_money": ("Managed Money", "m_money_positions_long_all", "m_money_positions_short_all", 13, 14),
        "other": ("Diğer Raporlanan", "other_rept_positions_long", "other_rept_positions_short", 16, 17),
        "nonrept": ("Küçük Spekülatör", "nonrept_positions_long_all", "nonrept_positions_short_all", 21, 22),
    },
}
# Toplam raporlanan pozisyon alanları (OI tutarlılık kontrolü için)
TOT_REPT = {
    "tff": ("tot_rept_positions_long_all", "tot_rept_positions_short", 20, 21),
    "disagg": ("tot_rept_positions_long_all", "tot_rept_positions_short", 19, 20),
}
OI_TEXT_COL = 7

# Her rapor türünde ana spekülatif grup ve "yavaş para" / ticari grup
SPEC_GROUP = {"tff": "lev_funds", "disagg": "managed_money"}
SLOW_GROUP = {"tff": "asset_mgr", "disagg": "prod_merc"}

INSTRUMENTS = {
    "eurusd": {
        "name": "EUR/USD", "report": "tff", "code": "099741", "contract": "Euro FX (CME)",
        "kind": "fx", "decimals": 5,
        "prices": {"yahoo": "EURUSD=X", "stooq": "eurusd", "fred": "DEXUSEU"},
    },
    "gbpusd": {
        "name": "GBP/USD", "report": "tff", "code": "096742", "contract": "British Pound (CME)",
        "kind": "fx", "decimals": 5,
        "prices": {"yahoo": "GBPUSD=X", "stooq": "gbpusd", "fred": "DEXUSUK"},
    },
    "xauusd": {
        "name": "XAU/USD", "report": "disagg", "code": "088691", "contract": "Gold (COMEX)",
        "kind": "metal", "decimals": 2,
        # Yahoo'da spot altın yok: Stooq spot, Yahoo GC=F vadeli proxy olarak kullanılır
        "prices": {"stooq": "xauusd", "yahoo_futures": "GC=F"},
        "live": {"swissquote": "XAU/USD", "goldapi": "XAU"},
    },
    "xagusd": {
        "name": "XAG/USD", "report": "disagg", "code": "084691", "contract": "Silver (COMEX)",
        "kind": "metal", "decimals": 3,
        "prices": {"stooq": "xagusd", "yahoo_futures": "SI=F"},
        "live": {"swissquote": "XAG/USD", "goldapi": "XAG"},
    },
    "nasdaq": {
        "name": "Nasdaq-100", "report": "tff", "code": "209742", "contract": "E-mini Nasdaq-100 (CME)",
        "kind": "index", "decimals": 1,
        "prices": {"yahoo": "^NDX", "stooq": "^ndx", "fred": "NASDAQ100"},
    },
    "sp500": {
        "name": "S&P 500", "report": "tff", "code": "13874A", "contract": "E-mini S&P 500 (CME)",
        "kind": "index", "decimals": 1,
        "prices": {"yahoo": "^GSPC", "stooq": "^spx", "fred": "SP500"},
    },
    "dxy": {
        "name": "DXY (Dolar Endeksi)", "report": "tff", "code": "098662", "contract": "USD Index (ICE)",
        "kind": "fx", "decimals": 3,
        # İkinci kaynak: DXY'nin resmi formülüyle Yahoo kurlarından hesaplanır
        "prices": {"yahoo": "DX-Y.NYB", "computed_dxy": "formula"},
    },
}
MAIN_INSTRUMENTS = ["eurusd", "gbpusd", "xauusd", "xagusd", "nasdaq", "sp500"]

# DXY formülü: 50.14348112 × EURUSD^-0.576 × USDJPY^0.136 × GBPUSD^-0.119 × USDCAD^0.091 × USDSEK^0.042 × USDCHF^0.036
DXY_WEIGHTS = {"EURUSD=X": -0.576, "JPY=X": 0.136, "GBPUSD=X": -0.119, "CAD=X": 0.091, "SEK=X": 0.042, "CHF=X": 0.036}
DXY_CONST = 50.14348112

# --- Makro seriler ---
# kaynak: fred | ecb | cboe | yahoo ; birden fazla kaynak verilirse çapraz kontrol yapılır
MACRO_SERIES = {
    "us2y": {"name": "ABD 2Y Getiri", "unit": "%", "sources": {"fred": "DGS2"}},
    "us10y": {"name": "ABD 10Y Getiri", "unit": "%", "sources": {"fred": "DGS10"}},
    "eu2y": {"name": "Euro Bölgesi AAA 2Y Getiri", "unit": "%",
             "sources": {"ecb": "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"}},
    "uk10y_m": {"name": "İngiltere 10Y Getiri (aylık)", "unit": "%", "sources": {"fred": "IRLTLT01GBM156N"}},
    "us10y_m": {"name": "ABD 10Y Getiri (aylık)", "unit": "%", "sources": {"fred": "IRLTLT01USM156N"}},
    "real10y": {"name": "ABD 10Y Reel Getiri (TIPS)", "unit": "%", "sources": {"fred": "DFII10"}},
    "curve": {"name": "Getiri Eğrisi 10Y-2Y", "unit": "%", "sources": {"fred": "T10Y2Y"}},
    "walcl": {"name": "Fed Bilançosu", "unit": "mn $", "sources": {"fred": "WALCL"}},
    "tga": {"name": "Hazine Hesabı (TGA)", "unit": "mn $", "sources": {"fred": "WTREGEN"}},
    "rrp": {"name": "Ters Repo (RRP)", "unit": "mlr $", "sources": {"fred": "RRPONTSYD"}},
    "nfci": {"name": "Chicago Fed Finansal Koşullar (NFCI)", "unit": "", "sources": {"fred": "NFCI"}},
    "hy_spread": {"name": "Yüksek Getirili Tahvil Spread'i", "unit": "%", "sources": {"fred": "BAMLH0A0HYM2"}},
    "gdpnow": {"name": "Atlanta Fed GDPNow", "unit": "%", "sources": {"fred": "GDPNOW"}},
    "vix": {"name": "VIX", "unit": "", "sources": {"yahoo": "^VIX", "cboe": "VIX"}},
    "vix3m": {"name": "VIX 3 Ay", "unit": "", "sources": {"yahoo": "^VIX3M", "cboe": "VIX3M"}},
    "vxn": {"name": "VXN (Nasdaq Volatilite)", "unit": "", "sources": {"yahoo": "^VXN", "cboe": "VXN"}},
    "gvz": {"name": "GVZ (Altın Volatilite)", "unit": "", "sources": {"yahoo": "^GVZ", "cboe": "GVZ"}},
    "move": {"name": "MOVE (Tahvil Volatilite)", "unit": "", "sources": {"yahoo": "^MOVE"}},
    "copper": {"name": "Bakır Vadeli", "unit": "$", "sources": {"yahoo": "HG=F"}},
}
MACRO_TOL = 0.01

# Doğrulama ekranında gösterilen kaynak açıklamaları
SOURCE_NOTES = {
    "yahoo": "Yahoo Finance — günlük kapanış",
    "yahoo_futures": "Yahoo Finance — vadeli kontrat (spot için proxy)",
    "stooq": "Stooq — spot günlük kapanış",
    "fred": "FRED (St. Louis Fed) — FX için New York öğle kuru, kapanıştan birkaç saat farklı olabilir",
    "computed_dxy": "Resmi DXY formülüyle Yahoo kurlarından hesaplanan değer",
    "ecb": "Avrupa Merkez Bankası veri portalı",
    "cboe": "CBOE resmi endeks geçmişi",
    "swissquote": "Swissquote canlı spot fiyat",
    "goldapi": "gold-api.com canlı spot fiyat",
    "aaii": "AAII haftalık yatırımcı anketi",
}
