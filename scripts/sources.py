"""Veri kaynaklarından çekme fonksiyonları. Her fonksiyon tarih indeksli pd.Series döndürür ya da hata fırlatır."""
import io
import time
import logging

import pandas as pd
import requests

from config import USER_AGENT, HISTORY_START, CFTC_API, CFTC_DATASETS, CFTC_TEXT, DXY_WEIGHTS, DXY_CONST

log = logging.getLogger("sources")


def http_get(url, params=None, timeout=60, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)[:200]
        if i < tries - 1:
            time.sleep(2 ** (i + 1))
    raise RuntimeError(f"{url} -> {last}")


def _clean(s, positive=True):
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if positive:
        s = s[s > 0]
    if s.empty:
        raise RuntimeError("boş seri")
    return s


# ---------------- CFTC ----------------

def cftc_api(report, code, fields):
    """CFTC Socrata API'den Futures Only geçmişi."""
    url = CFTC_API.format(ds=CFTC_DATASETS[report])
    params = {
        "cftc_contract_market_code": code,
        "$where": f"report_date_as_yyyy_mm_dd >= '{HISTORY_START}T00:00:00'",
        "$select": ",".join(["report_date_as_yyyy_mm_dd", "open_interest_all"] + fields),
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": 5000,
    }
    rows = http_get(url, params=params, timeout=120).json()
    if not rows:
        raise RuntimeError(f"CFTC API boş: {code}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df.pop("report_date_as_yyyy_mm_dd")).dt.normalize()
    for c in df.columns:
        if c != "date":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.drop_duplicates("date", keep="last").set_index("date").sort_index()


def cftc_text(report):
    """CFTC'nin haftalık metin dosyası: {sözleşme kodu: (tarih, satır listesi)}"""
    text = http_get(CFTC_TEXT[report], timeout=60).text
    if not text.lstrip().startswith('"'):
        raise RuntimeError("CFTC metin dosyası beklenen formatta değil")
    out = {}
    for row in pd.read_csv(io.StringIO(text), header=None, dtype=str).itertuples(index=False):
        code = str(row[3]).strip()
        out[code] = (pd.Timestamp(str(row[2]).strip()), [str(x).strip() for x in row])
    return out


# ---------------- Fiyatlar ----------------

_yahoo_cache = {}


def yahoo(symbol):
    if symbol in _yahoo_cache:
        return _yahoo_cache[symbol]
    import yfinance as yf
    last = None
    for i in range(3):
        try:
            h = yf.Ticker(symbol).history(start="2000-01-01", interval="1d", auto_adjust=False)
            if h is not None and not h.empty:
                if symbol.endswith("=X"):
                    # Yahoo döviz barlarında "Close" bayat kalıyor (gün açılışına yakın). Günün gerçek kapanışı
                    # bir sonraki barın açılışıdır; son (devam eden) bar için anlık fiyat kullanılır.
                    close = h["Open"].shift(-1)
                    close.iloc[-1] = h["Close"].iloc[-1]
                    s = _clean(close)
                else:
                    s = _clean(h["Close"])
                _yahoo_cache[symbol] = s
                time.sleep(1)
                return s
            last = "boş yanıt"
        except Exception as e:  # yfinance çok çeşitli hata fırlatabiliyor
            last = str(e)[:200]
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"Yahoo {symbol}: {last}")


_stooq_down = None


def stooq(symbol):
    """Stooq bağlantı düzeyinde erişilemiyorsa aynı çalıştırmada tekrar denenmez."""
    global _stooq_down
    if _stooq_down:
        raise RuntimeError(f"Stooq erişilemiyor: {_stooq_down}")
    try:
        r = http_get("https://stooq.com/q/d/l/", params={"s": symbol, "i": "d"}, timeout=30, tries=2)
    except RuntimeError as e:
        if "Connection" in str(e) or "timed out" in str(e):
            _stooq_down = str(e)[:150]
        raise
    if not r.text.startswith("Date"):
        raise RuntimeError(f"Stooq {symbol}: CSV yerine farklı yanıt geldi")
    df = pd.read_csv(io.StringIO(r.text))
    return _clean(df.set_index("Date")["Close"])


def fred(series_id, allow_negative=False):
    r = http_get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id}, timeout=90)
    df = pd.read_csv(io.StringIO(r.text))
    s = df.set_index(df.columns[0])[df.columns[1]]
    return _clean(s, positive=not allow_negative)


def ecb(key, allow_negative=True):
    flow, rest = key.split("/", 1)
    r = http_get(f"https://data-api.ecb.europa.eu/service/data/{flow}/{rest}",
                 params={"format": "csvdata", "startPeriod": HISTORY_START}, timeout=90)
    df = pd.read_csv(io.StringIO(r.text))
    return _clean(df.set_index("TIME_PERIOD")["OBS_VALUE"], positive=not allow_negative)


def cboe(index):
    r = http_get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{index}_History.csv", timeout=60)
    df = pd.read_csv(io.StringIO(r.text))
    col = "CLOSE" if "CLOSE" in df.columns else df.columns[-1]
    s = df.set_index(pd.to_datetime(df["DATE"], format="%m/%d/%Y"))[col]
    return _clean(s)


def computed_dxy(_):
    parts = {sym: yahoo(sym) for sym in DXY_WEIGHTS}
    df = pd.DataFrame(parts).dropna()
    if df.empty:
        raise RuntimeError("DXY hesaplanamadı")
    val = DXY_CONST
    for sym, w in DXY_WEIGHTS.items():
        val = val * df[sym] ** w
    return val


def aaii():
    r = http_get("https://www.aaii.com/files/surveys/sentiment.xls", timeout=90)
    df = pd.read_excel(io.BytesIO(r.content), sheet_name="SENTIMENT", header=None)
    dates = pd.to_datetime(df[0], errors="coerce", format="mixed")
    df = df[dates.notna()].copy()
    df.index = dates[dates.notna()].dt.normalize()
    out = pd.DataFrame({
        "bullish": pd.to_numeric(df[1], errors="coerce"),
        "neutral": pd.to_numeric(df[2], errors="coerce"),
        "bearish": pd.to_numeric(df[3], errors="coerce"),
    }).dropna()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    if out.empty:
        raise RuntimeError("AAII boş")
    return out


# ---------------- Canlı spot (son fiyat kontrolü) ----------------

def live_swissquote(pair):
    j = http_get(f"https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{pair}", timeout=30).json()
    p = j[0]["spreadProfilePrices"][0]
    return (p["bid"] + p["ask"]) / 2


def live_goldapi(sym):
    return float(http_get(f"https://api.gold-api.com/price/{sym}", timeout=30).json()["price"])


PRICE_FETCHERS = {
    "yahoo": yahoo,
    "yahoo_futures": yahoo,
    "stooq": stooq,
    "fred": fred,
    "computed_dxy": computed_dxy,
}
MACRO_FETCHERS = {
    "fred": lambda sid: fred(sid, allow_negative=True),
    "ecb": ecb,
    "cboe": cboe,
    "yahoo": yahoo,
}
LIVE_FETCHERS = {"swissquote": live_swissquote, "goldapi": live_goldapi}
