import time
import math
import requests
import numpy as np
import pandas as pd
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://fapi.binance.com"
INTERVALS = ["15m", "1h", "4h"]
TIMEOUT = 12
MAX_WORKERS = 8

WATCHLIST = {
    # Main coins
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    # Top alts
    "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","TRXUSDT","LTCUSDT","BCHUSDT",
    "NEARUSDT","SUIUSDT","APTUSDT","ARBUSDT","OPUSDT","ATOMUSDT","UNIUSDT",
    "AAVEUSDT","INJUSDT","HBARUSDT","FILUSDT","ETCUSDT","TONUSDT",
    # Meme coins
    "DOGEUSDT","1000SHIBUSDT","1000PEPEUSDT","WIFUSDT","1000BONKUSDT",
    "1000FLOKIUSDT","TRUMPUSDT","PENGUUSDT","FARTCOINUSDT","POPCATUSDT",
    "BOMEUSDT","NEIROUSDT","1000NEIROUSDT","PNUTUSDT","MOODENGUSDT","GOATUSDT",
    "TURBOUSDT","MEWUSDT","1000SATSUSDT","ACTUSDT","BRETTUSDT",
}

st.set_page_config(page_title="Crypto Futures Signal Scanner", page_icon="📡", layout="wide")

st.title("📡 Crypto Futures Signal Scanner")
st.caption("Binance USDⓈ-M Perpetual • Public market data only • Signals are research alerts, not guarantees")

with st.sidebar:
    st.header("Scanner settings")
    min_score = st.slider("Minimum signal score", 80, 100, 80, 1)
    risk_pct = st.slider("Account risk per trade (%)", 0.25, 2.0, 1.0, 0.25)
    capital = st.number_input("Available capital (USDT)", min_value=1.0, value=41.0, step=1.0)
    leverage = st.selectbox("Reference leverage", [3, 5, 10, 15, 20], index=2)
    scan_all = st.checkbox("Scan every active USDT perpetual (slow)", value=False)
    st.caption("Default: scans only main coins, top alts and top meme coins (about 45 coins).")
    st.caption("Timeframes: 15m entry, 1h confirmation, 4h trend. Uses completed candles only.")
    run_scan = st.button("🔎 SCAN MARKET", type="primary", use_container_width=True)

def get_json(path, params=None, attempts=3):
    for attempt in range(attempts):
        try:
            r = requests.get(BASE + path, params=params, timeout=TIMEOUT)
            if r.status_code in (418, 429):
                time.sleep(2 + attempt * 3)
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == attempts - 1:
                return None
            time.sleep(0.7 * (attempt + 1))
    return None

def get_universe():
    info = get_json("/fapi/v1/exchangeInfo")
    tickers = get_json("/fapi/v1/ticker/24hr")
    if not info or not tickers:
        raise RuntimeError("Could not load Binance Futures market data. Try again shortly.")
    active = {
        x["symbol"] for x in info.get("symbols", [])
        if x.get("status") == "TRADING"
        and x.get("contractType") == "PERPETUAL"
        and x.get("quoteAsset") == "USDT"
    }
    tdf = pd.DataFrame(tickers)
    if tdf.empty:
        return []
    tdf = tdf[tdf["symbol"].isin(active)].copy()
    tdf["quoteVolume"] = pd.to_numeric(tdf["quoteVolume"], errors="coerce")
    tdf = tdf.sort_values("quoteVolume", ascending=False)
    if not scan_all:
        tdf = tdf[tdf["symbol"].isin(WATCHLIST)]
    return tdf["symbol"].tolist()

def candles(symbol, interval):
    raw = get_json("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 100})
    if not raw or len(raw) < 60:
        return None
    cols = ["open_time","open","high","low","close","volume","close_time","quote_volume",
            "trades","taker_buy_base","taker_buy_quote","ignore"]
    df = pd.DataFrame(raw, columns=cols)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Exclude the currently forming candle to avoid repainting.
    return df.iloc[:-1].reset_index(drop=True)

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def indicators(df):
    c, h, l, v = df.close, df.high, df.low, df.volume
    e20, e50, e200 = ema(c,20), ema(c,50), ema(c, min(90, len(c)-1))
    r = rsi(c).iloc[-1]
    macd = ema(c,12) - ema(c,26)
    signal = ema(macd,9)
    hist = macd - signal
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    vol_avg = v.rolling(20).mean().iloc[-1]
    vol_ratio = (v.iloc[-1] / vol_avg) if vol_avg and vol_avg > 0 else 0
    adx_proxy = (abs(e20.iloc[-1]-e50.iloc[-1]) / c.iloc[-1]) * 10000
    return {
        "close": float(c.iloc[-1]), "ema20": float(e20.iloc[-1]),
        "ema50": float(e50.iloc[-1]), "ema200": float(e200.iloc[-1]),
        "rsi": float(r) if pd.notna(r) else 50.0,
        "macd_hist": float(hist.iloc[-1]),
        "atr": float(atr) if pd.notna(atr) else float(c.iloc[-1]) * 0.01,
        "vol_ratio": float(vol_ratio), "trend_strength": float(adx_proxy)
    }

def analyse_symbol(symbol):
    try:
        data = {}
        for tf in INTERVALS:
            df = candles(symbol, tf)
            if df is None:
                return None
            data[tf] = indicators(df)
        a, b, c = data["4h"], data["1h"], data["15m"]
        long_parts = [
            25 if a["close"] > a["ema20"] > a["ema50"] else 0,
            25 if b["close"] > b["ema20"] > b["ema50"] else 0,
            10 if c["close"] > c["ema20"] > c["ema50"] else 0,
            10 if c["macd_hist"] > 0 else 0,
            10 if 52 <= c["rsi"] <= 72 else (5 if 50 <= c["rsi"] < 52 else 0),
            10 if c["vol_ratio"] >= 1.5 else (5 if c["vol_ratio"] >= 1.15 else 0),
            10 if b["trend_strength"] >= 12 else 0
        ]
        short_parts = [
            25 if a["close"] < a["ema20"] < a["ema50"] else 0,
            25 if b["close"] < b["ema20"] < b["ema50"] else 0,
            10 if c["close"] < c["ema20"] < c["ema50"] else 0,
            10 if c["macd_hist"] < 0 else 0,
            10 if 28 <= c["rsi"] <= 48 else (5 if 48 < c["rsi"] <= 50 else 0),
            10 if c["vol_ratio"] >= 1.5 else (5 if c["vol_ratio"] >= 1.15 else 0),
            10 if b["trend_strength"] >= 12 else 0
        ]
        long_score, short_score = sum(long_parts), sum(short_parts)
        side = "LONG" if long_score > short_score else "SHORT"
        score = max(long_score, short_score)
        # Require higher-timeframe alignment, otherwise suppress the setup.
        aligned = ((side == "LONG" and a["close"] > a["ema50"] and b["close"] > b["ema50"]) or
                   (side == "SHORT" and a["close"] < a["ema50"] and b["close"] < b["ema50"]))
        if not aligned or score < 80:
            return None
        entry = c["close"]
        atr = max(c["atr"], entry * 0.002)
        stop_distance = 1.5 * atr
        if side == "LONG":
            sl, tp1, tp2 = entry-stop_distance, entry+1.5*stop_distance, entry+2.5*stop_distance
        else:
            sl, tp1, tp2 = entry+stop_distance, entry-1.5*stop_distance, entry-2.5*stop_distance
        risk_usdt = capital * risk_pct / 100
        position_notional = risk_usdt / (stop_distance / entry)
        margin_required = position_notional / leverage
        return {
            "Symbol": symbol, "Signal": side, "Score": int(score),
            "Entry": entry, "Stop Loss": sl, "TP1": tp1, "TP2": tp2,
            "R:R TP1": "1:1.5", "R:R TP2": "1:2.5",
            "15m RSI": round(c["rsi"],1), "Volume x": round(c["vol_ratio"],2),
            "Risk (USDT)": round(risk_usdt,2),
            "Est. margin (USDT)": round(margin_required,2),
            "Updated": pd.Timestamp.utcnow().strftime("%H:%M:%S UTC")
        }
    except Exception:
        return None

def fmt_price(x):
    if x is None or pd.isna(x): return "-"
    if x >= 1000: return f"{x:,.2f}"
    if x >= 1: return f"{x:.5f}".rstrip("0").rstrip(".")
    return f"{x:.8f}".rstrip("0").rstrip(".")

if "results" not in st.session_state:
    st.session_state.results = None
if "scan_time" not in st.session_state:
    st.session_state.scan_time = None

if run_scan:
    progress = st.progress(0, text="Loading Binance USDT perpetual contracts...")
    status = st.empty()
    try:
        symbols = get_universe()
        total = len(symbols)
        status.info(f"Scanning {total} active USDT perpetual contracts across 15m, 1h and 4h...")
        found = []
        done = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(analyse_symbol, s): s for s in symbols}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    found.append(result)
                done += 1
                if done % 5 == 0 or done == total:
                    progress.progress(done/total, text=f"Analysed {done}/{total} contracts • qualifying setups: {len(found)}")
        st.session_state.results = pd.DataFrame(found).sort_values("Score", ascending=False) if found else pd.DataFrame(columns=["Symbol", "Signal", "Score", "Entry", "Stop Loss", "TP1", "TP2", "R:R TP1", "R:R TP2", "15m RSI", "Volume x", "Risk (USDT)", "Est. margin (USDT)", "Updated"])
        st.session_state.scan_time = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        progress.empty()
        status.success(f"Scan complete: {len(found)} qualifying signals from {total} contracts.")
    except Exception as e:
        st.error(str(e))

st.divider()
left, mid, right = st.columns(3)
df = st.session_state.results
left.metric("Qualifying signals", 0 if df is None else len(df))
mid.metric("Minimum score", f"{min_score}%")
right.metric("Last scan", st.session_state.scan_time or "Not scanned")

if df is None:
    st.info("Set your risk preferences, then press SCAN MARKET. The scanner will only show setups scoring at least 80%.")
elif df.empty:
    st.warning("No qualifying 80%+ setups were found in the last scan. No trade is a valid result.")
else:
    view = df[df["Score"] >= min_score].copy()
    if view.empty:
        st.warning("No signals meet your selected score threshold.")
    else:
        longs = view[view["Signal"]=="LONG"]
        shorts = view[view["Signal"]=="SHORT"]
        c1,c2 = st.columns(2)
        c1.metric("LONG setups", len(longs))
        c2.metric("SHORT setups", len(shorts))
        st.subheader("Qualified futures signals")
        show = view.copy()
        for col in ["Entry","Stop Loss","TP1","TP2"]:
            show[col] = show[col].map(fmt_price)
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download signals as CSV", view.to_csv(index=False).encode("utf-8"),
                           file_name="futures_signals.csv", mime="text/csv")
        st.subheader("Trade plan")
        chosen = st.selectbox("Select a contract", view["Symbol"].tolist())
        row = view[view["Symbol"]==chosen].iloc[0]
        st.markdown(f"### {row['Signal']} · {row['Symbol']} · {row['Score']}% confluence")
        p1,p2,p3,p4 = st.columns(4)
        p1.metric("Entry", fmt_price(row["Entry"]))
        p2.metric("Stop loss", fmt_price(row["Stop Loss"]))
        p3.metric("Take profit 1", fmt_price(row["TP1"]))
        p4.metric("Take profit 2", fmt_price(row["TP2"]))
        st.write(f"**Risk/reward:** TP1 {row['R:R TP1']} · TP2 {row['R:R TP2']}")
        st.write(f"**Estimated risk:** {row['Risk (USDT)']} USDT · **Estimated margin at {leverage}x:** {row['Est. margin (USDT)']} USDT")
        st.caption("Entry is based on the last completed 15m candle close. Market prices can move before you place an order. Re-scan and verify the setup before entry.")

st.divider()
st.warning("Risk notice: A score of 80–100 is a rule-based confluence score, NOT an 80–100% chance of profit. Futures trading with leverage can liquidate your margin. The app does not place orders. Always verify liquidity, spread, funding, contract status and position size before trading.")
st.caption("Data source: Binance public USDⓈ-M Futures REST market-data endpoints. No API key is requested or stored.")
