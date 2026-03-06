"""
S4 Regime Breakout Strategy Engine
Regime detection, signal generation, and live price fetching for Nifty 100 NSE stocks.
"""

import datetime
import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Constants / Config
# ---------------------------------------------------------------------------

CAPITAL = 2_000_000
COST_PER_SIDE = 0.00148
MAX_WEIGHT = 0.15
MIN_STOCKS = 5

S4R = {
    'BULL':    dict(TOP_QUINTILE=0.25, TARGET_VOL=0.18, VOL_SCALE_CAP=1.5, MOM_SKIP=3,  MIN_EQUITY=0.50),
    'NEUTRAL': dict(TOP_QUINTILE=0.20, TARGET_VOL=0.14, VOL_SCALE_CAP=1.2, MOM_SKIP=5,  MIN_EQUITY=0.30),
    'BEAR':    dict(TOP_QUINTILE=0.15, TARGET_VOL=0.10, VOL_SCALE_CAP=1.0, MOM_SKIP=10, MIN_EQUITY=0.15),
}

S4B = dict(
    MOM_LOOKBACK=126,
    SMA_TREND=100,
    VOL_LOOKBACK=21,
    BREADTH_SMA=200,
    BULL_BREADTH=0.60,
    BEAR_BREADTH=0.35,
    HI52_PROX=0.95,
)

REBAL_MAP = {
    'BULL':    'Every Friday',
    'NEUTRAL': 'Every 2 weeks',
    'BEAR':    '1st Friday of month',
}

# ---------------------------------------------------------------------------
# Nifty 100 Ticker Map  (clean name → Yahoo Finance symbol)
# ---------------------------------------------------------------------------

NIFTY100 = {
    'RELIANCE':   'RELIANCE.NS',   'TCS':          'TCS.NS',
    'HDFCBANK':   'HDFCBANK.NS',   'INFY':         'INFY.NS',
    'ICICIBANK':  'ICICIBANK.NS',  'HINDUNILVR':   'HINDUNILVR.NS',
    'BHARTIARTL': 'BHARTIARTL.NS', 'SBIN':         'SBIN.NS',
    'ITC':        'ITC.NS',        'KOTAKBANK':    'KOTAKBANK.NS',
    'LT':         'LT.NS',         'AXISBANK':     'AXISBANK.NS',
    'WIPRO':      'WIPRO.NS',      'ASIANPAINT':   'ASIANPAINT.NS',
    'MARUTI':     'MARUTI.NS',     'TATAMOTORS':   'TMCV.NS',
    'SUNPHARMA':  'SUNPHARMA.NS',  'HCLTECH':      'HCLTECH.NS',
    'NTPC':       'NTPC.NS',       'TITAN':        'TITAN.NS',
    'BAJFINANCE': 'BAJFINANCE.NS', 'POWERGRID':    'POWERGRID.NS',
    'ULTRACEMCO': 'ULTRACEMCO.NS', 'NESTLEIND':    'NESTLEIND.NS',
    'TATASTEEL':  'TATASTEEL.NS',  'TECHM':        'TECHM.NS',
    'ONGC':       'ONGC.NS',       'ADANIPORTS':   'ADANIPORTS.NS',
    'JSWSTEEL':   'JSWSTEEL.NS',   'INDUSINDBK':   'INDUSINDBK.NS',
    'COALINDIA':  'COALINDIA.NS',  'BAJAJFINSV':   'BAJAJFINSV.NS',
    'GRASIM':     'GRASIM.NS',     'HDFCLIFE':     'HDFCLIFE.NS',
    'BPCL':       'BPCL.NS',       'DIVISLAB':     'DIVISLAB.NS',
    'DRREDDY':    'DRREDDY.NS',    'CIPLA':        'CIPLA.NS',
    'EICHERMOT':  'EICHERMOT.NS',  'SBILIFE':      'SBILIFE.NS',
    'APOLLOHOSP': 'APOLLOHOSP.NS', 'TRENT':        'TRENT.NS',
    'PERSISTENT': 'PERSISTENT.NS', 'ZOMATO':       'ETERNAL.NS',
    'TATACONSUM': 'TATACONSUM.NS', 'DABUR':        'DABUR.NS',
    'BRITANNIA':  'BRITANNIA.NS',  'HEROMOTOCO':   'HEROMOTOCO.NS',
    'BAJAJ-AUTO': 'BAJAJ-AUTO.NS', 'HINDALCO':     'HINDALCO.NS',
    'ADANIENT':   'ADANIENT.NS',   'M&M':          'M&M.NS',
    'SHRIRAMFIN': 'SHRIRAMFIN.NS', 'PIDILITIND':   'PIDILITIND.NS',
    'HAVELLS':    'HAVELLS.NS',    'DLF':          'DLF.NS',
    'ABB':        'ABB.NS',        'GODREJCP':     'GODREJCP.NS',
    'SIEMENS':    'SIEMENS.NS',    'TORNTPHARM':   'TORNTPHARM.NS',
    'LTIM':       'LTIM.NS',       'BANKBARODA':   'BANKBARODA.NS',
    'CANBK':      'CANBK.NS',      'PNB':          'PNB.NS',
    'IDFCFIRSTB': 'IDFCFIRSTB.NS', 'VEDL':         'VEDL.NS',
    'JINDALSTEL': 'JINDALSTEL.NS', 'TATAPOWER':    'TATAPOWER.NS',
    'IOC':        'IOC.NS',        'GAIL':         'GAIL.NS',
    'BEL':        'BEL.NS',        'HAL':          'HAL.NS',
    'IRCTC':      'IRCTC.NS',      'INDUSTOWER':   'INDUSTOWER.NS',
    'NAUKRI':     'NAUKRI.NS',     'MAXHEALTH':    'MAXHEALTH.NS',
    'LICI':       'LICI.NS',       'POLYCAB':      'POLYCAB.NS',
    'SOLARINDS':  'SOLARINDS.NS',  'OFSS':         'OFSS.NS',
    'MPHASIS':    'MPHASIS.NS',    'COLPAL':       'COLPAL.NS',
    'MARICO':     'MARICO.NS',     'BERGEPAINT':   'BERGEPAINT.NS',
    'AMBUJACEM':  'AMBUJACEM.NS',  'ACC':          'ACC.NS',
    'LUPIN':      'LUPIN.NS',      'AUROPHARMA':   'AUROPHARMA.NS',
    'BIOCON':     'BIOCON.NS',     'MOTHERSON':    'MOTHERSON.NS',
    'BOSCHLTD':   'BOSCHLTD.NS',   'PAGEIND':      'PAGEIND.NS',
    'PIIND':      'PIIND.NS',      'CHOLAFIN':     'CHOLAFIN.NS',
    'MUTHOOTFIN': 'MUTHOOTFIN.NS', 'PFC':          'PFC.NS',
    'RECLTD':     'RECLTD.NS',     'NHPC':         'NHPC.NS',
    'IRFC':       'IRFC.NS',       'JIOFIN':       'JIOFIN.NS',
    'ATGL':       'ATGL.NS',
}

# Reverse map: Yahoo symbol → clean name
_YAHOO_TO_CLEAN = {v: k for k, v in NIFTY100.items()}


# ---------------------------------------------------------------------------
# 1. fetch_universe
# ---------------------------------------------------------------------------

def fetch_universe(period: str = '2y') -> pd.DataFrame:
    """
    Download 2-year daily close prices for all NIFTY100 tickers.

    Returns a DataFrame with clean ticker names as columns and
    DatetimeIndex as rows.  Missing values are forward-filled (limit=5).
    """
    tickers_yahoo = list(NIFTY100.values())
    print(f"Fetching {len(tickers_yahoo)} tickers from Yahoo Finance …")

    raw = yf.download(
        tickers_yahoo,
        period=period,
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    # yfinance returns multi-level columns when >1 ticker
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw['Close']
    else:
        prices = raw[['Close']]

    # Forward-fill then drop columns with too many NaNs
    prices = prices.ffill(limit=5)

    # Rename columns from Yahoo symbols to clean names
    prices.columns = [_YAHOO_TO_CLEAN.get(c, c) for c in prices.columns]

    # Keep only NIFTY100 clean names
    valid_cols = [c for c in prices.columns if c in NIFTY100]
    failed = [c for c in NIFTY100 if c not in valid_cols]
    if failed:
        print(f"  ⚠  Failed / missing tickers: {failed}")

    prices = prices[valid_cols].dropna(how='all')
    print(f"  ✓  {len(valid_cols)} tickers loaded, {len(prices)} trading days")
    return prices


# ---------------------------------------------------------------------------
# 2. detect_regime
# ---------------------------------------------------------------------------

def detect_regime(prices: pd.DataFrame):
    """
    Detect the current market regime.

    Returns: (regime_str, breadth, vol_fast, vol_slow)
    """
    cfg = S4B
    if len(prices) < cfg['BREADTH_SMA']:
        return 'NEUTRAL', 0.5, 0.0, 0.0

    # Breadth: fraction of stocks above their 200-day SMA
    sma200 = prices.rolling(cfg['BREADTH_SMA']).mean()
    above = (prices > sma200).iloc[-1]
    breadth = float(above.mean())

    # Equal-weight portfolio returns
    rets = prices.pct_change().dropna()
    eq_rets = rets.mean(axis=1)

    vol_fast = float(eq_rets.tail(21).std() * np.sqrt(252))
    vol_slow = float(eq_rets.tail(63).std() * np.sqrt(252))

    # Regime rules
    vol_expanding = vol_fast > vol_slow * 1.2
    if breadth >= cfg['BULL_BREADTH'] and not vol_expanding:
        regime = 'BULL'
    elif breadth <= cfg['BEAR_BREADTH'] or vol_expanding:
        regime = 'BEAR'
    else:
        regime = 'NEUTRAL'

    return regime, breadth, vol_fast, vol_slow


# ---------------------------------------------------------------------------
# 3. generate_signals
# ---------------------------------------------------------------------------

def generate_signals(prices: pd.DataFrame):
    """
    Full S4 signal pipeline.

    Returns:
        signals (dict)  – high-level summary + holdings
        details (DataFrame) – per-ticker details
    """
    cfg_b = S4B
    regime, breadth, vol_fast, vol_slow = detect_regime(prices)
    cfg_r = S4R[regime]

    mom_lookback = cfg_b['MOM_LOOKBACK']
    mom_skip     = cfg_r['MOM_SKIP']
    sma_trend    = cfg_b['SMA_TREND']
    vol_lookback = cfg_b['VOL_LOOKBACK']
    hi52_prox    = cfg_b['HI52_PROX']
    top_q        = cfg_r['TOP_QUINTILE']
    target_vol   = cfg_r['TARGET_VOL']
    vol_cap      = cfg_r['VOL_SCALE_CAP']
    min_equity   = cfg_r['MIN_EQUITY']

    if len(prices) < max(mom_lookback + mom_skip, sma_trend, 252) + 5:
        raise ValueError("Insufficient price history for signal generation.")

    latest = prices.iloc[-1]
    sma100 = prices.rolling(sma_trend).mean().iloc[-1]

    # 1. Filter: above SMA(100)
    above_sma = latest[latest > sma100].index.tolist()
    n_above_sma = len(above_sma)

    # 2. Momentum = return from (lookback + skip) days ago to (skip) days ago
    p_end   = prices.iloc[-(mom_skip + 1)]
    p_start = prices.iloc[-(mom_lookback + mom_skip + 1)]
    momentum = (p_end / p_start - 1).reindex(above_sma).dropna()

    # 3. Filter positive momentum
    momentum = momentum[momentum > 0]
    n_positive_mom = len(momentum)

    if n_positive_mom < MIN_STOCKS:
        # Relax to at least MIN_STOCKS by taking top by momentum
        mom_all = (p_end / p_start - 1).reindex(above_sma).dropna().sort_values(ascending=False)
        momentum = mom_all.head(MIN_STOCKS)
        n_positive_mom = len(momentum)

    # 4. 52-week high proximity breakout bonus
    hi52 = prices.tail(252).max().reindex(momentum.index).fillna(latest.reindex(momentum.index))
    proximity = (latest.reindex(momentum.index) / hi52).fillna(0)
    breakout_bonus = (proximity >= hi52_prox).astype(float)

    # 5. Composite rank
    mom_rank = momentum.rank(pct=True)
    composite = mom_rank * 0.7 + breakout_bonus * 0.3

    # 6. Select top quintile
    n_select = max(MIN_STOCKS, int(np.ceil(len(composite) * top_q)))
    selected = composite.nlargest(n_select).index.tolist()

    # 7. Inverse-volatility × momentum-tilt weighting
    vols = prices[selected].pct_change().dropna().tail(vol_lookback).std() * np.sqrt(252)
    vols = vols.replace(0, np.nan).fillna(vols.mean())
    inv_vol = 1.0 / vols
    mom_tilt = momentum.reindex(selected).fillna(0)
    mom_tilt = (mom_tilt - mom_tilt.min()) / (mom_tilt.max() - mom_tilt.min() + 1e-10)

    raw_w = (inv_vol * (0.7 + 0.3 * mom_tilt))
    weights = raw_w / raw_w.sum()

    # 8. Clip to MAX_WEIGHT and renormalize
    weights = weights.clip(upper=MAX_WEIGHT)
    weights = weights / weights.sum()

    # 9. Apply minimum equity floor
    total_equity_w = weights.sum()
    if total_equity_w < min_equity:
        weights = weights * (min_equity / total_equity_w)

    # 10. Vol-scale to target vol
    port_vol = float(
        prices[selected].pct_change().dropna().tail(63)
        .dot(weights.reindex(selected).fillna(0))
        .std() * np.sqrt(252)
    )
    vol_scale = min(target_vol / port_vol, vol_cap) if port_vol > 0 else 1.0
    weights = weights * vol_scale
    weights = weights.clip(upper=MAX_WEIGHT)
    # Renormalize after clipping
    weights = weights / weights.sum() * weights.sum()

    # Build holdings
    holdings = {}
    details_rows = []
    total_capital = CAPITAL * float(weights.sum())
    for ticker in selected:
        w = float(weights.get(ticker, 0))
        price = float(latest.get(ticker, 0))
        if price <= 0:
            continue
        alloc = CAPITAL * w
        qty = int(alloc / price)
        hi52_val = float(hi52.get(ticker, price))
        ann_vol = float(vols.get(ticker, 0))
        mom_val = float(momentum.get(ticker, 0))
        holdings[ticker] = {'weight': round(w, 4), 'qty': qty, 'price': round(price, 2)}
        details_rows.append({
            'ticker':    ticker,
            'weight':    round(w, 4),
            'qty':       qty,
            'price':     round(price, 2),
            'value':     round(qty * price, 2),
            'momentum':  round(mom_val * 100, 2),
            'ann_vol':   round(ann_vol * 100, 2),
            'hi52_prox': round(float(proximity.get(ticker, 0)) * 100, 2),
        })

    details = pd.DataFrame(details_rows)

    # Next rebalance date (next Friday)
    today = datetime.date.today()
    days_until_friday = (4 - today.weekday()) % 7
    next_friday = today + datetime.timedelta(days=days_until_friday if days_until_friday > 0 else 7)

    signals = {
        'date':            today.isoformat(),
        'regime':          regime,
        'breadth':         round(breadth * 100, 1),
        'vol_fast':        round(vol_fast * 100, 2),
        'vol_slow':        round(vol_slow * 100, 2),
        'vol_scale':       round(vol_scale, 3),
        'total_weight':    round(float(weights.sum()), 4),
        'next_rebalance':  next_friday.isoformat(),
        'n_above_sma':     n_above_sma,
        'n_positive_mom':  n_positive_mom,
        'holdings':        holdings,
    }

    return signals, details


# ---------------------------------------------------------------------------
# 4. fetch_live_prices
# ---------------------------------------------------------------------------

def fetch_live_prices(tickers: list) -> dict:
    """
    Fetch current prices for a list of clean ticker names.

    Returns {clean_ticker: price}.
    """
    yahoo_symbols = [NIFTY100[t] for t in tickers if t in NIFTY100]
    if not yahoo_symbols:
        return {}

    result = {}
    try:
        data = yf.download(yahoo_symbols, period='2d', auto_adjust=True, progress=False, threads=True)
        if isinstance(data.columns, pd.MultiIndex):
            close = data['Close']
        else:
            close = data[['Close']]
        latest = close.iloc[-1]
        for col in latest.index:
            clean = _YAHOO_TO_CLEAN.get(col, col)
            if clean in tickers:
                result[clean] = round(float(latest[col]), 2)
    except Exception as exc:
        print(f"fetch_live_prices error: {exc}")

    return result
