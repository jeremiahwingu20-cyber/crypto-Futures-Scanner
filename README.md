# Crypto Futures Signal Scanner

A separate Streamlit dashboard that scans active Binance USDⓈ-M USDT perpetual contracts and displays only technical setups scoring 80% or higher.

## Included
- All active USDT-margined perpetual contracts (or optional top contracts by 24h quote volume)
- 15m, 1h and 4h completed-candle analysis
- EMA trend, RSI, MACD histogram, volume expansion and higher-timeframe alignment
- LONG and SHORT candidates
- Entry, ATR-based stop loss, TP1, TP2 and risk/reward
- Estimated risk and margin reference
- CSV export
- Public market data only; no Binance API key and no order execution

## Run on Windows / Mac / Linux
1. Install Python 3.10 or newer.
2. Extract this ZIP.
3. Open a terminal in the extracted folder.
4. Run:
   ```bash
   python -m venv .venv
   ```
5. Activate it:
   - Windows: `.venv\Scripts\activate`
   - Mac/Linux: `source .venv/bin/activate`
6. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
7. Start:
   ```bash
   streamlit run app.py
   ```
8. Open the local URL shown in the terminal (normally http://localhost:8501).

## Phone use
The easiest option is to deploy the app to a trusted Python hosting provider, then open its private URL in your phone browser. You can also run it on a computer and access it over the same Wi-Fi by starting Streamlit with `--server.address 0.0.0.0`, then opening the computer's local IP and port 8501 on your phone. Do not expose an unsecured local server to the public internet.

## Important limitations
- Binance API availability may vary by country/network. This app uses public endpoints and does not bypass regional restrictions.
- A full-market scan can take several minutes and may be slowed by exchange rate limits or network errors.
- The scanner classifies the whole available USDT perpetual universe; "meme coin" is not a separate Binance contract type.
- Scores are rule-based technical confluence scores, not statistically calibrated win probabilities.
- Entry is the last completed 15-minute candle close. It is not a guaranteed fill price.
- SL and targets are ATR-based planning levels, not exchange orders. The app does not connect to your account or execute trades.
- The risk/margin estimate is approximate and excludes fees, funding, slippage, maintenance margin and liquidation mechanics. Confirm position size in Binance before trading.
- Backtest and paper-trade the rules before using real money. A strict 80% threshold may produce no signals on some scans.
