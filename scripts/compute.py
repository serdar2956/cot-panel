"""Doğrulanmış veriden sitenin kullandığı JSON dosyalarını üretir."""
import json
import logging
import math

import numpy as np
import pandas as pd

from config import (STORE, SITE_DATA, INSTRUMENTS, MAIN_INSTRUMENTS, GROUPS, SPEC_GROUP, SLOW_GROUP,
                    LOOKBACKS, INDEX_HIGH, INDEX_LOW, MACRO_SERIES, SOURCE_NOTES, TOL_FX, TOL_OTHER)

log = logging.getLogger("compute")
FWD = [1, 4, 12]


# ---------------------------------------------------------------- yardımcılar

def load(path, col=None):
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[col] if col else df


def macro(key):
    s = load(STORE / "macro" / f"{key}.csv", "value")
    return s.astype(float) if s is not None else None


def clean(v, nd=4):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if (math.isnan(v) or math.isinf(v)) else round(float(v), nd)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def col(s, nd=4):
    return [clean(x, nd) for x in s.tolist()]


def dates(idx):
    return [d.strftime("%Y-%m-%d") for d in idx]


def write(name, obj):
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def cot_index(x, n):
    lo = x.rolling(n, min_periods=n).min()
    hi = x.rolling(n, min_periods=n).max()
    return ((x - lo) / (hi - lo).replace(0, np.nan) * 100).clip(0, 100)


def asof(daily, idx):
    """Günlük seriyi verilen tarihlere 'o tarih veya öncesindeki son değer' olarak hizalar."""
    if daily is None or daily.empty:
        return pd.Series(np.nan, index=idx)
    d = daily.dropna().sort_index()
    pos = d.index.searchsorted(idx, side="right") - 1
    vals = np.where(pos >= 0, d.values[np.clip(pos, 0, None)], np.nan)
    return pd.Series(vals, index=idx, dtype=float)


def expanding_z(s, min_periods=52):
    m = s.expanding(min_periods).mean()
    sd = s.expanding(min_periods).std()
    return ((s - m) / sd.replace(0, np.nan)).clip(-2, 2) / 2


def spearman(a, b):
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 30:
        return np.nan
    ra = pd.Series(a[m]).rank().values
    rb = pd.Series(b[m]).rank().values
    c = np.corrcoef(ra, rb)[0, 1]
    return c


def label_score(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "Veri yok"
    if x >= 40:
        return "Güçlü yükseliş eğilimi"
    if x >= 15:
        return "Orta yükseliş eğilimi"
    if x > -15:
        return "Nötr"
    if x > -40:
        return "Orta düşüş eğilimi"
    return "Güçlü düşüş eğilimi"


def price_oi_state(dp, doi):
    if pd.isna(dp) or pd.isna(doi):
        return None
    if dp >= 0 and doi >= 0:
        return {"code": "up_up", "text": "Fiyat ↑ OI ↑ — Güçlü yükseliş (yeni alıcılar giriyor)", "bias": 1}
    if dp >= 0 and doi < 0:
        return {"code": "up_down", "text": "Fiyat ↑ OI ↓ — Zayıf yükseliş (short kapatma)", "bias": 0}
    if dp < 0 and doi >= 0:
        return {"code": "down_up", "text": "Fiyat ↓ OI ↑ — Güçlü düşüş (yeni satıcılar giriyor)", "bias": -1}
    return {"code": "down_down", "text": "Fiyat ↓ OI ↓ — Zayıf düşüş (long kapatma)", "bias": 0}


# ---------------------------------------------------------------- makro hazırlık

def macro_frame():
    m = {k: macro(k) for k in MACRO_SERIES}
    netliq = None
    if m["walcl"] is not None and m["tga"] is not None and m["rrp"] is not None:
        w = m["walcl"] / 1e6  # trilyon $
        tga = asof(m["tga"], w.index) / 1e6
        rrp = asof(m["rrp"], w.index) / 1e3
        netliq = (w - tga - rrp).dropna()
    m["netliq"] = netliq
    return m


def prices_daily():
    out = {}
    for key in INSTRUMENTS:
        df = load(STORE / "prices" / f"{key}.csv")
        if df is not None and not df.empty:
            out[key] = df["close"].astype(float)
    return out


# ---------------------------------------------------------------- enstrüman

def instrument_frame(key, inst, px):
    report = inst["report"]
    cot = load(STORE / "cot" / f"{key}.csv")
    if cot is None or cot.empty:
        return None
    W = pd.DataFrame(index=cot.index)
    W["oi"] = cot["oi"]
    W["oi_chg"] = W["oi"].diff()
    W["oi_idx52"] = cot_index(W["oi"], 52)
    W["price"] = asof(px, W.index) if px is not None else np.nan
    for g in GROUPS[report]:
        net = cot[f"{g}_long"] - cot[f"{g}_short"]
        W[f"{g}_long"] = cot[f"{g}_long"]
        W[f"{g}_short"] = cot[f"{g}_short"]
        W[f"{g}_net"] = net
        W[f"{g}_chg"] = net.diff()
        W[f"{g}_pct"] = net / W["oi"] * 100
        for n in LOOKBACKS:
            W[f"{g}_idx{n}"] = cot_index(net, n)
        # Willco: OI'ye göre normalize net pozisyonun 26 haftalık stokastiği
        W[f"{g}_willco"] = cot_index(W[f"{g}_pct"], 26)
    return W


def divergences(key, inst, W):
    out = []
    report = inst["report"]
    spec, slow = SPEC_GROUP[report], SLOW_GROUP[report]
    last = W.iloc[-1]
    names = {g: v[0] for g, v in GROUPS[report].items()}
    if report == "tff":
        a, l = last.get("asset_mgr_idx52"), last.get("lev_funds_idx52")
        if pd.notna(a) and pd.notna(l) and abs(a - l) >= 60:
            out.append({"type": "group", "text": f"Asset Manager (endeks {a:.0f}) ve Leveraged Funds (endeks {l:.0f}) ters uçlarda"})
        d_am = W["asset_mgr_net"].diff(4)
        d_lf = W["lev_funds_net"].diff(4)
        sa, sl = d_am.iloc[-160:].std(), d_lf.iloc[-160:].std()
        if pd.notna(sa) and pd.notna(sl) and np.sign(d_am.iloc[-1]) != np.sign(d_lf.iloc[-1]) \
                and abs(d_am.iloc[-1]) > sa and abs(d_lf.iloc[-1]) > sl:
            yon = lambda x: "artırdı" if x > 0 else "azalttı"
            out.append({"type": "group", "text": f"Son 4 haftada Asset Manager net pozisyonunu {yon(d_am.iloc[-1])}, "
                                                 f"Leveraged Funds {yon(d_lf.iloc[-1])} (zıt yönlü, güçlü hareket)"})
    # fiyat - pozisyon ayrışması
    p = W["price"]
    idx = W[f"{spec}_idx52"]
    if p.notna().sum() > 20 and pd.notna(idx.iloc[-1]) and pd.notna(idx.iloc[-5]):
        hi13, lo13 = p.iloc[-13:].max(), p.iloc[-13:].min()
        d_idx = idx.iloc[-1] - idx.iloc[-5]
        if p.iloc[-1] >= hi13 and d_idx <= -15:
            out.append({"type": "price", "text": f"Fiyat 13 haftanın zirvesinde ama {names[spec]} endeksi 4 haftada {d_idx:.0f} puan düştü (negatif ayrışma)"})
        if p.iloc[-1] <= lo13 and d_idx >= 15:
            out.append({"type": "price", "text": f"Fiyat 13 haftanın dibinde ama {names[spec]} endeksi 4 haftada +{d_idx:.0f} puan yükseldi (pozitif ayrışma)"})
    return out


def extreme_stats(W, group, name):
    """Endeks aşırı bölgeye ilk girdiğinde sonraki 1/4/12 haftalık fiyat değişimi."""
    p = W["price"]
    fwd = {k: (p.shift(-k) / p - 1) * 100 for k in FWD}
    idx = W[f"{group}_idx52"]
    res = {"group": group, "name": name, "zones": []}
    for zone, cond in (("high", idx >= INDEX_HIGH), ("low", idx <= INDEX_LOW)):
        entry = cond & ~cond.shift(1, fill_value=False)
        ev_dates = W.index[entry & p.notna()]
        row = {"zone": zone, "count": int(len(ev_dates)), "fwd": {}}
        for k in FWD:
            r = fwd[k].loc[ev_dates].dropna()
            row["fwd"][str(k)] = {
                "n": int(len(r)),
                "mean": clean(r.mean(), 2) if len(r) else None,
                "median": clean(r.median(), 2) if len(r) else None,
                "pos": clean((r > 0).mean() * 100, 0) if len(r) else None,
            }
        row["last_events"] = dates(ev_dates[-5:])
        res["zones"].append(row)
    res["baseline"] = {str(k): {"mean": clean(fwd[k].mean(), 2), "pos": clean((fwd[k].dropna() > 0).mean() * 100, 0)} for k in FWD}
    return res


# ---------------------------------------------------------------- bileşik skor

def composite(key, inst, W, px, M, prices):
    report = inst["report"]
    spec, slow = SPEC_GROUP[report], SLOW_GROUP[report]
    names = {g: v[0] for g, v in GROUPS[report].items()}
    idx = W.index
    p = W["price"]
    S = {}
    labels = {}

    def add(k, label, s):
        S[k] = s.reindex(idx).astype(float)
        labels[k] = label

    add("cot_spec", f"COT: {names[spec]} endeksi (52h)", (W[f"{spec}_idx52"] - 50) / 50)
    add("cot_slow", f"COT: {names[slow]} endeksi (52h)", (W[f"{slow}_idx52"] - 50) / 50)
    add("cot_small", "COT: Küçük spekülatör endeksi (52h)", (W["nonrept_idx52"] - 50) / 50)
    add("cot_flow", f"COT: {names[spec]} 4 haftalık akış", expanding_z(W[f"{spec}_net"].diff(4) / W["oi"]))
    add("oi_confirm", "Fiyat-OI teyidi (4h)", expanding_z((W["oi"].pct_change(4)) * np.sign(p.pct_change(4))))
    if px is not None and len(px) > 250:
        ma200 = px.rolling(200).mean()
        add("trend", "Trend: fiyat / 200 günlük ortalama", expanding_z(asof(px / ma200 - 1, idx)))
    add("momentum", "Momentum (12-1 ay)", expanding_z(p.shift(4) / p.shift(52) - 1))
    zp = (p - p.rolling(20).mean()) / p.rolling(20).std()
    add("meanrev", "Ortalamaya dönüş (20h z-skor)", (zp.clip(-2, 2) / 2))
    if px is not None:
        mret = px.resample("ME").last().pct_change().dropna()
        seas = pd.Series(np.nan, index=idx)
        for d in idx:
            past = mret[(mret.index.month == d.month) & (mret.index.year < d.year)]
            if len(past) >= 5:
                seas[d] = past.mean()
        add("season", "Sezonsallık (bu ayın tarihsel ortalaması)", expanding_z(seas))

    dxy = prices.get("dxy")
    def wk(s):
        return asof(s, idx) if s is not None else pd.Series(np.nan, index=idx)

    if key in ("eurusd", "dxy") and M["eu2y"] is not None and M["us2y"] is not None:
        spread = wk(M["eu2y"]) - wk(M["us2y"])
        add("rates", "Faiz farkı değişimi (EU2Y-US2Y, 4h)", expanding_z(spread.diff(4)))
    if key == "gbpusd" and M["uk10y_m"] is not None and M["us10y_m"] is not None:
        spread = wk(M["uk10y_m"]) - wk(M["us10y_m"])
        add("rates", "Faiz farkı değişimi (UK10Y-US10Y, 13h)", expanding_z(spread.diff(13)))
    if key in ("eurusd", "gbpusd", "xauusd", "xagusd") and dxy is not None:
        add("dxy", "Dolar endeksi 4 haftalık değişim", expanding_z(wk(dxy).pct_change(4)))
    if key in ("xauusd", "xagusd") and M["real10y"] is not None:
        add("real", "Reel faiz değişimi (10Y TIPS, 4h)", expanding_z(wk(M["real10y"]).diff(4)))
    if key == "xauusd" and M["gvz"] is not None:
        add("gvz", "Altın volatilitesi (GVZ) seviyesi", expanding_z(wk(M["gvz"])))
    if key == "xagusd" and "xauusd" in prices:
        add("gsr", "Altın/Gümüş oranı", expanding_z(wk(prices["xauusd"]) / p))
    if key in ("nasdaq", "sp500"):
        if M["netliq"] is not None:
            add("netliq", "Net likidite 13 haftalık değişim", expanding_z(wk(M["netliq"]).pct_change(13)))
        if M["hy_spread"] is not None:
            add("credit", "Kredi spread'i değişimi (4h)", expanding_z(wk(M["hy_spread"]).diff(4)))
        if M["vix"] is not None and M["vix3m"] is not None:
            add("vixts", "VIX vade yapısı (VIX/VIX3M)", expanding_z(wk(M["vix"]) / wk(M["vix3m"])))
        if M["nfci"] is not None:
            add("nfci", "Finansal koşullar (NFCI)", expanding_z(wk(M["nfci"])))
        a = load(STORE / "macro" / "aaii.csv")
        if a is not None:
            add("aaii", "AAII boğa-ayı farkı", expanding_z(asof(a["bullish"] - a["bearish"], idx)))

    df = pd.DataFrame(S)
    fwd4 = (p.shift(-4) / p - 1).values
    keys = list(df.columns)
    X = df.values
    n = len(df)
    weights = np.full((n, len(keys)), np.nan)
    for i in range(n):
        j = i - 4  # hedefi bilinen son satır
        if j < 104:
            continue
        for c in range(len(keys)):
            weights[i, c] = spearman(X[:j + 1, c], fwd4[:j + 1])
    Wt = np.nan_to_num(weights)
    Xs = np.nan_to_num(X)
    valid = ~np.isnan(X)
    num = (Wt * Xs).sum(1)
    den = (np.abs(Wt) * valid).sum(1)
    score = pd.Series(np.where(den > 0, num / np.where(den > 0, den, 1) * 100, np.nan), index=idx)
    score[np.isnan(weights).all(1)] = np.nan

    # örneklem dışı başarı
    f4 = pd.Series(fwd4, index=idx)
    m = score.notna() & f4.notna()
    perf = {"ic": clean(spearman(score[m].values, f4[m].values), 3), "n": int(m.sum())}
    up, dn = m & (score >= 25), m & (score <= -25)
    perf["hit_up"] = clean((f4[up] > 0).mean() * 100, 0) if up.sum() else None
    perf["n_up"] = int(up.sum())
    perf["hit_down"] = clean((f4[dn] < 0).mean() * 100, 0) if dn.sum() else None
    perf["n_down"] = int(dn.sum())
    perf["base_up"] = clean((f4[m] > 0).mean() * 100, 0) if m.sum() else None

    last_w = weights[-1]
    comps = []
    den_last = np.nansum(np.abs(last_w) * valid[-1])
    for c, k in enumerate(keys):
        s, w = X[-1, c], last_w[c]
        comps.append({
            "key": k, "label": labels[k], "signal": clean(s, 3), "weight": clean(w, 3),
            "contribution": clean(w * s / den_last * 100, 1) if den_last and not np.isnan(s) and not np.isnan(w) else None,
        })
    comps.sort(key=lambda r: -abs(r["contribution"] or 0))
    return score, comps, perf


# ---------------------------------------------------------------- adil değer

def fair_value(key, W, M, prices, window=104):
    idx = W.index
    def wk(s):
        return asof(s, idx) if s is not None else None
    facs = {}
    if key == "eurusd" and M["eu2y"] is not None:
        facs = {"EU2Y-US2Y": wk(M["eu2y"]) - wk(M["us2y"])}
    elif key == "gbpusd" and M["uk10y_m"] is not None:
        facs = {"UK10Y-US10Y": wk(M["uk10y_m"]) - wk(M["us10y_m"])}
    elif key in ("xauusd", "xagusd") and M["real10y"] is not None and "dxy" in prices:
        facs = {"Reel faiz": wk(M["real10y"]), "log DXY": np.log(wk(prices["dxy"]))}
    elif key in ("nasdaq", "sp500") and M["netliq"] is not None:
        facs = {"log Net likidite": np.log(wk(M["netliq"])), "Reel faiz": wk(M["real10y"])}
    elif key == "dxy" and M["eu2y"] is not None:
        facs = {"US2Y-EU2Y": wk(M["us2y"]) - wk(M["eu2y"]), "Reel faiz": wk(M["real10y"])}
    if not facs:
        return None
    y = np.log(W["price"])
    F = pd.DataFrame(facs)
    data = pd.concat([y.rename("y"), F], axis=1, sort=True).dropna()
    if len(data) < window + 10:
        return None
    fair = pd.Series(np.nan, index=data.index)
    z = pd.Series(np.nan, index=data.index)
    r2 = np.nan
    Xall = np.column_stack([np.ones(len(data)), data[list(facs)].values])
    yall = data["y"].values
    for i in range(window, len(data)):
        Xw, yw = Xall[i - window:i], yall[i - window:i]
        beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
        resid = yw - Xw @ beta
        pred = Xall[i] @ beta
        fair.iloc[i] = np.exp(pred)
        sd = resid.std()
        z.iloc[i] = (yall[i] - pred) / sd if sd > 0 else np.nan
        if i == len(data) - 1:
            ss = ((yw - yw.mean()) ** 2).sum()
            r2 = 1 - (resid ** 2).sum() / ss if ss > 0 else np.nan
    return {"factors": list(facs), "dates": dates(fair.index), "fair": col(fair, 5), "price": col(np.exp(data["y"]), 5),
            "z": col(z, 2), "r2": clean(r2, 2), "last_z": clean(z.iloc[-1], 2)}


# ---------------------------------------------------------------- ana akış

def build(validation=None):
    if validation is None:
        p = STORE / "validation.json"
        validation = json.loads(p.read_text()) if p.exists() else {"cot": {}, "prices": {}, "macro": {}}
    M = macro_frame()
    prices = prices_daily()
    summary = {"generated": validation.get("generated"), "instruments": [], "alerts": [],
               "thresholds": {"high": INDEX_HIGH, "low": INDEX_LOW}}
    stats_all = {}

    for key, inst in INSTRUMENTS.items():
        px = prices.get(key)
        W = instrument_frame(key, inst, px)
        if W is None:
            log.warning("%s için COT verisi yok", key)
            continue
        report = inst["report"]
        spec, slow = SPEC_GROUP[report], SLOW_GROUP[report]
        gnames = {g: v[0] for g, v in GROUPS[report].items()}
        last = W.iloc[-1]

        score, comps, perf = composite(key, inst, W, px, M, prices)
        dv = divergences(key, inst, W)
        st1 = price_oi_state(W["price"].diff().iloc[-1], W["oi_chg"].iloc[-1])
        st4 = price_oi_state(W["price"].diff(4).iloc[-1], W["oi"].diff(4).iloc[-1])
        fv = fair_value(key, W, M, prices)

        groups_out = []
        for g in GROUPS[report]:
            groups_out.append({
                "key": g, "name": gnames[g], "long": clean(last[f"{g}_long"], 0), "short": clean(last[f"{g}_short"], 0),
                "net": clean(last[f"{g}_net"], 0), "chg": clean(last[f"{g}_chg"], 0), "pct": clean(last[f"{g}_pct"], 1),
                **{f"idx{n}": clean(last[f"{g}_idx{n}"], 0) for n in LOOKBACKS},
                "willco": clean(last[f"{g}_willco"], 0),
                "role": "spec" if g == spec else ("slow" if g == slow else None),
            })

        stats = [extreme_stats(W, spec, gnames[spec]), extreme_stats(W, slow, gnames[slow]),
                 extreme_stats(W, "nonrept", gnames["nonrept"])]
        stats_all[key] = {"name": inst["name"], "stats": stats}

        series = {"dates": dates(W.index), "price": col(W["price"], inst["decimals"]),
                  "oi": col(W["oi"], 0), "oi_chg": col(W["oi_chg"], 0), "oi_idx52": col(W["oi_idx52"], 0),
                  "score": col(score, 1)}
        for g in GROUPS[report]:
            series[f"{g}_net"] = col(W[f"{g}_net"], 0)
            series[f"{g}_long"] = col(W[f"{g}_long"], 0)
            series[f"{g}_short"] = col(W[f"{g}_short"], 0)
            series[f"{g}_willco"] = col(W[f"{g}_willco"], 0)
            for n in LOOKBACKS:
                series[f"{g}_idx{n}"] = col(W[f"{g}_idx{n}"], 0)

        vcot = validation.get("cot", {}).get(key, {})
        vpx = validation.get("prices", {}).get(key, {})
        inst_out = {
            "key": key, "name": inst["name"], "contract": inst["contract"], "report": report,
            "report_name": "TFF (Traders in Financial Futures)" if report == "tff" else "Disaggregated",
            "date": f"{W.index[-1]:%Y-%m-%d}", "decimals": inst["decimals"],
            "price": clean(last["price"], inst["decimals"]), "price_basis": vpx.get("basis", "spot"),
            "groups": groups_out, "group_names": gnames, "spec": spec, "slow": slow,
            "oi": clean(last["oi"], 0), "oi_chg": clean(last["oi_chg"], 0), "oi_idx52": clean(last["oi_idx52"], 0),
            "price_oi_1w": st1, "price_oi_4w": st4, "divergences": dv,
            "score": clean(score.iloc[-1], 0), "score_label": label_score(clean(score.iloc[-1], 0)),
            "components": comps, "score_perf": perf, "fair_value": fv, "series": series,
            "validation": {"cot": vcot.get("status"), "price": vpx.get("status")},
        }
        write(f"inst_{key}.json", inst_out)

        summary["instruments"].append({
            "key": key, "name": inst["name"], "date": inst_out["date"], "price": inst_out["price"],
            "price_now": clean(px.iloc[-1], inst["decimals"]) if px is not None else None,
            "price_now_date": f"{px.index[-1]:%Y-%m-%d}" if px is not None else None,
            "price_basis": inst_out["price_basis"],
            "decimals": inst["decimals"], "main": key in MAIN_INSTRUMENTS,
            "spec_name": gnames[spec], "slow_name": gnames[slow],
            "spec_idx": clean(last[f"{spec}_idx52"], 0), "slow_idx": clean(last[f"{slow}_idx52"], 0),
            "small_idx": clean(last["nonrept_idx52"], 0), "oi_idx": clean(last["oi_idx52"], 0),
            "spec_willco": clean(last[f"{spec}_willco"], 0),
            "spec_chg": clean(last[f"{spec}_chg"], 0),
            "score": inst_out["score"], "score_label": inst_out["score_label"],
            "price_oi": st1, "fv_z": fv["last_z"] if fv else None,
            "validation": inst_out["validation"],
        })

        # Uyarılar
        for g in GROUPS[report]:
            if g not in (spec, slow, "nonrept"):
                continue
            v = last[f"{g}_idx52"]
            if pd.notna(v) and (v >= INDEX_HIGH or v <= INDEX_LOW):
                summary["alerts"].append({"inst": key, "name": inst["name"], "level": "extreme",
                                          "text": f"{gnames[g]} COT endeksi {v:.0f} — aşırı {'long' if v >= INDEX_HIGH else 'short'} bölgesi"})
        for d in dv:
            summary["alerts"].append({"inst": key, "name": inst["name"], "level": "divergence", "text": d["text"]})
        if inst_out["score"] is not None and abs(inst_out["score"]) >= 40:
            summary["alerts"].append({"inst": key, "name": inst["name"], "level": "score",
                                      "text": f"Bileşik skor {inst_out['score']:+.0f} — {inst_out['score_label']}"})
        if vcot.get("status") == "hold":
            summary["alerts"].append({"inst": key, "name": inst["name"], "level": "validation",
                                      "text": "Yeni COT verisi doğrulanamadı, bekletiliyor (son doğrulanan veri gösteriliyor)"})
        if vpx.get("status") == "red":
            summary["alerts"].append({"inst": key, "name": inst["name"], "level": "validation",
                                      "text": "Fiyat kaynakları uyuşmuyor"})

    build_macro(M, prices, summary)
    build_vol(M, prices, summary)
    build_liquidity(M, prices)
    build_sentiment(M, summary)
    build_stats(prices, stats_all, summary)
    write("summary.json", summary)
    validation["notes"] = SOURCE_NOTES
    validation["names"] = {k: v["name"] for k, v in INSTRUMENTS.items()}
    validation["tolerances"] = {"fx": TOL_FX, "other": TOL_OTHER}
    write("validation.json", validation)
    log.info("Site verisi üretildi: %s", SITE_DATA)


def weekly(s, start="2006-01-01"):
    if s is None:
        return None
    return s[s.index >= start].resample("W-FRI").last().dropna()


def pack(series_dict, start="2006-01-01", nd=4):
    df = pd.DataFrame({k: weekly(v, start) for k, v in series_dict.items() if v is not None})
    return {"dates": dates(df.index), **{k: col(df[k], nd) for k in df.columns}}


def build_macro(M, prices, summary):
    out = {}
    if M["us2y"] is not None and M["eu2y"] is not None:
        out["eur_rates"] = pack({"us2y": M["us2y"], "eu2y": M["eu2y"], "eurusd": prices.get("eurusd")})
    if M["uk10y_m"] is not None and M["us10y_m"] is not None:
        out["gbp_rates"] = pack({"uk10y": M["uk10y_m"], "us10y": M["us10y_m"], "gbpusd": prices.get("gbpusd")})
    out["gold_real"] = pack({"real10y": M["real10y"], "xauusd": prices.get("xauusd")})
    out["curve"] = pack({"curve": M["curve"], "us10y": M["us10y"], "us2y": M["us2y"]})
    out["gdpnow"] = pack({"gdpnow": M["gdpnow"]}, start="2014-01-01")
    out["credit"] = pack({"hy_spread": M["hy_spread"], "nfci": M["nfci"]})
    ratios = {}
    if "xauusd" in prices and "xagusd" in prices:
        ratios["gold_silver"] = prices["xauusd"] / prices["xagusd"]
    if M["copper"] is not None and "xauusd" in prices:
        ratios["copper_gold"] = M["copper"] / prices["xauusd"] * 1000
    if "nasdaq" in prices and "sp500" in prices:
        ratios["ndx_spx"] = prices["nasdaq"] / prices["sp500"]
    ratios["us10y"] = M["us10y"]
    out["ratios"] = pack({k: v.dropna() for k, v in ratios.items() if v is not None})
    # son değerler tablosu
    latest = []
    for k, meta in MACRO_SERIES.items():
        s = M.get(k)
        if s is None or s.empty:
            continue
        prev = s[s.index <= s.index[-1] - pd.Timedelta(days=28)]
        latest.append({"key": k, "name": meta["name"], "unit": meta["unit"], "date": f"{s.index[-1]:%Y-%m-%d}",
                       "value": clean(s.iloc[-1], 3), "chg4w": clean(s.iloc[-1] - prev.iloc[-1], 3) if len(prev) else None})
    if M["netliq"] is not None:
        s = M["netliq"]
        latest.append({"key": "netliq", "name": "Net Likidite (Fed − TGA − RRP)", "unit": "trn $",
                       "date": f"{s.index[-1]:%Y-%m-%d}", "value": clean(s.iloc[-1], 3),
                       "chg4w": clean(s.iloc[-1] - s.iloc[-5], 3) if len(s) > 5 else None})
    out["latest"] = latest
    write("macro.json", out)


def build_vol(M, prices, summary):
    out = {"pairs": [], "regimes": []}
    pairs = [("sp500", "vix", "S&P 500 — VIX"), ("nasdaq", "vxn", "Nasdaq-100 — VXN"), ("xauusd", "gvz", "Altın — GVZ")]
    for pk, ik, label in pairs:
        px, iv = prices.get(pk), M.get(ik)
        if px is None or iv is None:
            continue
        rv = np.log(px).diff().rolling(20).std() * np.sqrt(252) * 100
        df = pd.concat([iv.rename("iv"), rv.rename("rv")], axis=1, sort=True).dropna()
        df = df[df.index >= "2015-01-01"]
        spread = df["iv"] - df["rv"]
        out["pairs"].append({"key": ik, "label": label, "dates": dates(df.index), "iv": col(df["iv"], 2),
                             "rv": col(df["rv"], 2), "last_iv": clean(df["iv"].iloc[-1], 2),
                             "last_rv": clean(df["rv"].iloc[-1], 2), "last_spread": clean(spread.iloc[-1], 2),
                             "spread_pct": clean((spread.iloc[-756:] < spread.iloc[-1]).mean() * 100, 0)})
    if M["vix"] is not None and M["vix3m"] is not None:
        r = (M["vix"] / M["vix3m"]).dropna()
        r = r[r.index >= "2010-01-01"]
        out["term"] = {"dates": dates(r.index), "ratio": col(r, 3), "last": clean(r.iloc[-1], 3)}
        if r.iloc[-1] > 1:
            summary["alerts"].append({"inst": "sp500", "name": "VIX", "level": "vol",
                                      "text": f"VIX vade yapısı ters döndü (VIX/VIX3M = {r.iloc[-1]:.2f}) — panik bölgesi, tarihsel olarak dip sinyali"})
    if M["move"] is not None:
        out["move"] = pack({"move": M["move"]}, start="2010-01-01", nd=2)
    for key in INSTRUMENTS:
        px = prices.get(key)
        if px is None or len(px) < 800:
            continue
        rv = np.log(px).diff().rolling(20).std() * np.sqrt(252) * 100
        rv = rv.dropna()
        pct = (rv.iloc[-756:] < rv.iloc[-1]).mean() * 100
        regime = "Düşük" if pct < 25 else ("Yüksek" if pct > 75 else "Normal")
        out["regimes"].append({"key": key, "name": INSTRUMENTS[key]["name"], "rv": clean(rv.iloc[-1], 2),
                               "pct": clean(pct, 0), "regime": regime,
                               "hint": "Range / ortalamaya dönüş stratejileri" if regime == "Düşük"
                               else ("Trend / kırılım stratejileri, risk azalt" if regime == "Yüksek" else "Karışık")})
    write("vol.json", out)


def build_liquidity(M, prices):
    out = {}
    nl = M["netliq"]
    if nl is None:
        write("liquidity.json", out)
        return
    nl = nl[nl.index >= "2009-01-01"]
    sp = asof(prices.get("sp500"), nl.index) if "sp500" in prices else None
    nd = asof(prices.get("nasdaq"), nl.index) if "nasdaq" in prices else None
    comp = pd.DataFrame({"netliq": nl, "walcl": asof(M["walcl"], nl.index) / 1e6,
                         "tga": asof(M["tga"], nl.index) / 1e6, "rrp": asof(M["rrp"], nl.index) / 1e3,
                         "sp500": sp, "nasdaq": nd})
    out = {"dates": dates(comp.index), **{k: col(comp[k], 3 if k not in ("sp500", "nasdaq") else 1) for k in comp.columns}}
    c13 = comp.pct_change(13)
    recent = c13.iloc[-156:]
    out["corr13"] = {k: clean(recent["netliq"].corr(recent[k]), 2) for k in ("sp500", "nasdaq") if k in recent}
    out["chg13"] = clean(c13["netliq"].iloc[-1] * 100, 2)
    out["last"] = clean(nl.iloc[-1], 3)
    write("liquidity.json", out)


def build_sentiment(M, summary):
    out = {}
    a = load(STORE / "macro" / "aaii.csv")
    if a is not None:
        a = a[a.index >= "2006-01-01"]
        spread = (a["bullish"] - a["bearish"]) * 100
        z = (spread - spread.mean()) / spread.std()
        out["aaii"] = {"dates": dates(a.index), "bullish": col(a["bullish"] * 100, 1), "bearish": col(a["bearish"] * 100, 1),
                       "neutral": col(a["neutral"] * 100, 1), "spread": col(spread, 1), "spread8": col(spread.rolling(8).mean(), 1),
                       "last_spread": clean(spread.iloc[-1], 1), "last_z": clean(z.iloc[-1], 2), "date": f"{a.index[-1]:%Y-%m-%d}"}
        if abs(z.iloc[-1]) >= 1.5:
            summary["alerts"].append({"inst": "sp500", "name": "AAII", "level": "sentiment",
                                      "text": f"AAII boğa-ayı farkı aşırı {'iyimser' if z.iloc[-1] > 0 else 'kötümser'} (z={z.iloc[-1]:.1f}) — ters sinyal olarak değerlendirilir"})
    write("sentiment.json", out)


def build_stats(prices, stats_all, summary):
    out = {"extremes": stats_all, "seasonality": {}, "corr": {}}
    months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    for key in INSTRUMENTS:
        px = prices.get(key)
        if px is None:
            continue
        m = px.resample("ME").last().pct_change().dropna() * 100
        m = m[m.index >= "2006-01-01"]
        rows = []
        for i in range(1, 13):
            r = m[m.index.month == i]
            rows.append({"month": months[i - 1], "mean": clean(r.mean(), 2), "median": clean(r.median(), 2),
                         "pos": clean((r > 0).mean() * 100, 0), "n": int(len(r))})
        out["seasonality"][key] = {"name": INSTRUMENTS[key]["name"], "rows": rows,
                                   "years": f"{m.index[0].year}–{m.index[-1].year}"}
    # korelasyon matrisi
    rets = {}
    for key in INSTRUMENTS:
        if key in prices:
            rets[INSTRUMENTS[key]["name"].split(" ")[0]] = np.log(prices[key]).diff()
    for k, label in (("us10y", "ABD 10Y"), ("real10y", "Reel Faiz"), ("vix", "VIX")):
        s = macro(k)
        if s is not None:
            rets[label] = s.diff() if k != "vix" else np.log(s).diff()
    R = pd.DataFrame(rets)
    R = R[R.index >= R.index.max() - pd.Timedelta(days=500)].dropna(how="all")
    # farklı piyasa tatilleri yüzünden boşlukları at
    R = R.dropna()
    c60 = R.iloc[-60:].corr()
    c252 = R.iloc[-252:].corr()
    names = list(R.columns)
    out["corr"] = {"names": names, "c60": [[clean(c60.loc[a, b], 2) for b in names] for a in names],
                   "c252": [[clean(c252.loc[a, b], 2) for b in names] for a in names]}
    breaks = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = c60.loc[a, b], c252.loc[a, b]
            if pd.notna(x) and pd.notna(y) and np.sign(x) != np.sign(y) and abs(x - y) >= 0.5:
                breaks.append({"a": a, "b": b, "c60": clean(x, 2), "c252": clean(y, 2)})
    out["corr"]["breaks"] = breaks
    for br in breaks:
        summary["alerts"].append({"inst": None, "name": "Korelasyon", "level": "corr",
                                  "text": f"{br['a']} – {br['b']} korelasyonu bozuldu: 60 gün {br['c60']:+.2f}, 1 yıl {br['c252']:+.2f}"})
    write("stats.json", out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
