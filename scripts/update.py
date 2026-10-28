"""Tüm verileri çeker, çapraz kontrol eder, doğrulanmış veriyi data/ altına kaydeder ve siteyi üretir.

Kullanım: python scripts/update.py
"""
import json
import logging
import sys
from datetime import datetime, timezone

import pandas as pd

import sources as src
from config import (STORE, INSTRUMENTS, GROUPS, TOT_REPT, OI_TEXT_COL, SPEC_GROUP, MACRO_SERIES,
                    TOL_FX, TOL_OTHER, MACRO_TOL)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("update")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_store(path, index_col="date"):
    if path.exists():
        df = pd.read_csv(path, index_col=index_col, parse_dates=True)
        return df
    return None


def write_store(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index_label="date", float_format="%.6g")


# =====================================================================
# COT
# =====================================================================

def cot_fields(report):
    f = []
    for _, lf, sf, _, _ in GROUPS[report].values():
        f += [lf, sf]
    f += list(TOT_REPT[report][:2])
    return f


def to_store_frame(api_df, report):
    out = pd.DataFrame(index=api_df.index)
    out["oi"] = api_df["open_interest_all"]
    for g, (_, lf, sf, _, _) in GROUPS[report].items():
        out[f"{g}_long"] = api_df[lf]
        out[f"{g}_short"] = api_df[sf]
    return out


def check_cot(key, inst, api_df, text_rows, stored):
    """API ve metin dosyasını karşılaştırır. Doğrulanan son tarihi ve kontrol listesini döndürür."""
    report = inst["report"]
    checks = []
    latest = api_df.index[-1]
    row = api_df.iloc[-1]
    stored_last = stored.index[-1] if stored is not None and len(stored) else None

    def add(name, ok, detail, level="red"):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "level": "ok" if ok else level})

    add("Rapor tarihi salı günü", latest.weekday() == 1, latest.strftime("%Y-%m-%d"), "yellow")
    if stored_last is not None:
        add("Tarih önceki kayıttan eski değil", latest >= stored_last,
            f"API: {latest:%Y-%m-%d}, kayıtlı: {stored_last:%Y-%m-%d}")

    lc, sc, ltc, stc = TOT_REPT[report]
    oi = row["open_interest_all"]
    ok_l = abs(row[lc] + row[GROUPS[report]["nonrept"][1]] - oi) <= 1
    ok_s = abs(row[sc] + row[GROUPS[report]["nonrept"][2]] - oi) <= 1
    add("Pozisyon toplamı = Open Interest", ok_l and ok_s,
        f"OI {oi:,.0f}; long toplamı {row[lc] + row[GROUPS[report]['nonrept'][1]]:,.0f}; "
        f"short toplamı {row[sc] + row[GROUPS[report]['nonrept'][2]]:,.0f}")

    # İkinci kanal: CFTC metin dosyası
    text_ok = None
    if text_rows is None:
        add("CFTC metin dosyası ile karşılaştırma", False, "Metin dosyası indirilemedi", "yellow")
    elif inst["code"] not in text_rows:
        add("CFTC metin dosyası ile karşılaştırma", False, "Sözleşme metin dosyasında bulunamadı", "yellow")
    else:
        tdate, vals = text_rows[inst["code"]]
        if tdate != latest:
            text_ok = False
            add("API ve metin dosyası aynı haftayı gösteriyor", False,
                f"API: {latest:%Y-%m-%d}, metin dosyası: {tdate:%Y-%m-%d} (biri henüz güncellenmemiş)", "yellow")
        else:
            diffs = []
            pairs = [("Open Interest", oi, vals[OI_TEXT_COL])]
            for g, (gname, lf, sf, li, si) in GROUPS[report].items():
                pairs += [(f"{gname} long", row[lf], vals[li]), (f"{gname} short", row[sf], vals[si])]
            for label, a, b in pairs:
                try:
                    b = float(b)
                except ValueError:
                    b = float("nan")
                if not (abs(a - b) <= 0.5):
                    diffs.append(f"{label}: API {a:,.0f} / metin {b:,.0f}")
            text_ok = not diffs
            add("API ve metin dosyası rakamları birebir aynı", text_ok,
                "Tüm alanlar eşleşti (" + str(len(pairs)) + " alan)" if text_ok else "; ".join(diffs))

    # Anormal sıçrama kontrolü (sadece uyarı)
    spec = SPEC_GROUP[report]
    net = api_df[GROUPS[report][spec][1]] - api_df[GROUPS[report][spec][2]]
    chg = net.diff().abs()
    hist = chg.iloc[-157:-1]
    if len(hist) > 20 and hist.max() > 0:
        ratio = chg.iloc[-1] / hist.max()
        add("Haftalık değişim olağan aralıkta", ratio <= 3,
            f"Son değişim, son 3 yılın en büyük değişiminin {ratio:.1f} katı", "yellow")

    hard_fail = any(c["level"] == "red" for c in checks)
    if text_ok and not hard_fail:
        status, validated = "ok", latest
    else:
        status = "hold"
        if stored_last is not None:
            validated = min(stored_last, latest)
        else:
            validated = api_df.index[-2]
    return status, validated, checks


def update_cot(validation):
    texts = {}
    for report in ("tff", "disagg"):
        try:
            texts[report] = src.cftc_text(report)
        except Exception as e:
            log.warning("CFTC metin dosyası %s: %s", report, e)
            texts[report] = None

    for key, inst in INSTRUMENTS.items():
        report = inst["report"]
        path = STORE / "cot" / f"{key}.csv"
        stored = read_store(path)
        entry = {"report": report, "contract": inst["contract"]}
        try:
            api_df = src.cftc_api(report, inst["code"], cot_fields(report))
            status, validated, checks = check_cot(key, inst, api_df, texts[report], stored)
            frame = to_store_frame(api_df, report)
            frame = frame[frame.index <= validated]
            if stored is not None and status == "hold":
                frame = frame.combine_first(stored)
                frame = frame[frame.index <= validated]
            write_store(frame, path)
            entry.update(status=status, api_date=f"{api_df.index[-1]:%Y-%m-%d}",
                         validated_through=f"{validated:%Y-%m-%d}", checks=checks)
            log.info("COT %s: %s (doğrulanan son tarih %s)", key, status, validated.date())
        except Exception as e:
            log.error("COT %s: %s", key, e)
            entry.update(status="hold", error=str(e)[:300],
                         validated_through=f"{stored.index[-1]:%Y-%m-%d}" if stored is not None else None,
                         checks=[{"name": "CFTC API", "ok": False, "detail": str(e)[:300], "level": "red"}])
        validation["cot"][key] = entry


# =====================================================================
# Fiyatlar: çok kaynaklı konsensüs
# =====================================================================

def consensus(series_by_src, tol, priority):
    """Her gün için kaynakları karşılaştırır. En az iki kaynak tolerans içinde uyuşursa öncelikli kaynağın değeri alınır."""
    df = pd.DataFrame(series_by_src).sort_index()
    prices, status = {}, {}
    cols = [c for c in priority if c in df.columns]
    for dt, row in df.iterrows():
        vals = {c: row[c] for c in cols if pd.notna(row[c])}
        if not vals:
            continue
        if len(vals) == 1:
            c, v = next(iter(vals.items()))
            prices[dt], status[dt] = v, "single"
            continue
        best = None
        for c in cols:
            if c not in vals:
                continue
            agree = [d for d in vals if abs(vals[d] / vals[c] - 1) <= tol]
            if len(agree) >= 2 and (best is None or len(agree) > len(best[1])):
                best = (c, agree)
        if best:
            prices[dt], status[dt] = vals[best[0]], "ok"
        else:
            status[dt] = "conflict"
    return pd.Series(prices, dtype=float).sort_index(), pd.Series(status).sort_index()


def latest_status(st):
    """Son gün tek kaynaktaysa ama önceki günler doğrulandıysa bu bir yayın gecikmesidir, uyuşmazlık değil."""
    last = st.iloc[-1]
    if last == "single" and (st.iloc[-4:-1] == "ok").any():
        return "ok", "Son gün diğer kaynak(lar)da henüz yayınlanmadı; önceki günler doğrulandı"
    return last, None


def update_prices(validation):
    for key, inst in INSTRUMENTS.items():
        tol = TOL_FX if inst["kind"] == "fx" else TOL_OTHER
        path = STORE / "prices" / f"{key}.csv"
        got, src_info = {}, {}
        for sname, sym in inst["prices"].items():
            try:
                s = src.PRICE_FETCHERS[sname](sym)
                got[sname] = s
                src_info[sname] = {"ok": True, "symbol": sym, "last_date": f"{s.index[-1]:%Y-%m-%d}",
                                   "last": round(float(s.iloc[-1]), 6), "rows": int(len(s))}
            except Exception as e:
                log.warning("Fiyat %s/%s: %s", key, sname, e)
                src_info[sname] = {"ok": False, "symbol": sym, "error": str(e)[:200]}

        entry = {"sources": src_info, "tolerance": tol}
        stored = read_store(path)
        if got:
            priority = list(inst["prices"].keys())
            price, st = consensus(got, tol, priority)
            out = pd.DataFrame({"close": price, "status": st}).dropna(subset=["close"])
            # Spot kaynak yoksa (ör. Stooq erişilemezse) hangi kaynağın kullanıldığını belirt
            spot_sources = [s for s in ("yahoo", "stooq", "fred") if s in got]
            entry["basis"] = "spot" if spot_sources else "vadeli proxy"
            write_store(out, path)
            last30 = st.iloc[-30:].value_counts().to_dict()
            entry["last30"] = {k: int(last30.get(k, 0)) for k in ("ok", "single", "conflict")}
            ld = st.index[-1]
            entry["latest"] = {
                "date": f"{ld:%Y-%m-%d}", "status": st.iloc[-1],
                "values": {k: round(float(v.loc[ld]), 6) for k, v in got.items() if ld in v.index},
                "used": round(float(price.iloc[-1]), 6) if len(price) else None,
            }
            ok_count = sum(1 for v in src_info.values() if v["ok"])
            last, note = latest_status(st)
            if note:
                entry["note"] = note
            if last == "conflict":
                entry["status"] = "red"
            elif last == "single" or ok_count < len(src_info):
                entry["status"] = "yellow"
            else:
                entry["status"] = "ok"
        else:
            entry["status"] = "red"
            entry["error"] = "Hiçbir fiyat kaynağına ulaşılamadı; kayıtlı veri kullanılıyor" if stored is not None \
                else "Hiçbir fiyat kaynağına ulaşılamadı"

        # Canlı spot kontrolü (altın / gümüş)
        if "live" in inst:
            live = {}
            for lname, sym in inst["live"].items():
                try:
                    live[lname] = round(src.LIVE_FETCHERS[lname](sym), 4)
                except Exception as e:
                    live[lname] = None
                    log.warning("Canlı %s/%s: %s", key, lname, e)
            vals = [v for v in live.values() if v]
            agree = len(vals) == 2 and abs(vals[0] / vals[1] - 1) <= tol
            entry["live"] = {"time": now_iso(), "values": live, "agree": agree}
        validation["prices"][key] = entry
        log.info("Fiyat %s: %s", key, entry.get("status"))


# =====================================================================
# Makro
# =====================================================================

def update_macro(validation):
    for key, meta in MACRO_SERIES.items():
        path = STORE / "macro" / f"{key}.csv"
        got, info = {}, {}
        for sname, sid in meta["sources"].items():
            try:
                s = src.MACRO_FETCHERS[sname](sid)
                got[sname] = s
                info[sname] = {"ok": True, "id": sid, "last_date": f"{s.index[-1]:%Y-%m-%d}", "last": float(s.iloc[-1])}
            except Exception as e:
                log.warning("Makro %s/%s: %s", key, sname, e)
                info[sname] = {"ok": False, "id": sid, "error": str(e)[:200]}
        entry = {"name": meta["name"], "sources": info}
        if got:
            if len(got) >= 2:
                s, st = consensus(got, MACRO_TOL, list(meta["sources"].keys()))
                last30 = st.iloc[-30:].value_counts().to_dict()
                entry["last30"] = {k: int(last30.get(k, 0)) for k in ("ok", "single", "conflict")}
                last, note = latest_status(st)
                if note:
                    entry["detail"] = note
                entry["status"] = "ok" if last == "ok" else ("red" if last == "conflict" else "yellow")
            else:
                s = next(iter(got.values()))
                entry["status"] = "single"
            # mantık kontrolü: son değer son 5 yılın aralığının çok dışında mı?
            recent = s.iloc[-1300:]
            rng = recent.max() - recent.min()
            if rng > 0 and (s.iloc[-1] > recent.max() + rng or s.iloc[-1] < recent.min() - rng):
                entry["status"] = "red"
                entry["detail"] = "Son değer olağan aralığın çok dışında"
            write_store(s.rename("value").to_frame(), path)
            entry["last_date"] = f"{s.index[-1]:%Y-%m-%d}"
        else:
            entry["status"] = "red"
            entry["detail"] = "Kaynağa ulaşılamadı; kayıtlı veri kullanılıyor"
        validation["macro"][key] = entry

    # AAII
    try:
        a = src.aaii()
        write_store(a, STORE / "macro" / "aaii.csv")
        validation["macro"]["aaii"] = {"name": "AAII Yatırımcı Sentiment", "status": "single",
                                       "last_date": f"{a.index[-1]:%Y-%m-%d}",
                                       "sources": {"aaii": {"ok": True}}}
    except Exception as e:
        log.warning("AAII: %s", e)
        validation["macro"]["aaii"] = {"name": "AAII Yatırımcı Sentiment", "status": "red",
                                       "detail": str(e)[:200], "sources": {"aaii": {"ok": False}}}


def main():
    validation = {"generated": now_iso(), "cot": {}, "prices": {}, "macro": {}}
    update_cot(validation)
    update_prices(validation)
    update_macro(validation)
    (STORE / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=1))

    import compute
    compute.build(validation)
    log.info("Tamamlandı.")


if __name__ == "__main__":
    sys.exit(main())
