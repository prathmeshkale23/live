"""
app.py — Flask server for the S4 Regime Breakout paper trading application.
"""

import glob
import json
import os
import threading
import datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

import s4_engine as engine
import paper_trader as pt

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

DATA_DIR     = os.getcwd()
EXCEL_FILE   = os.path.join(DATA_DIR, 's4_paper_trading.xlsx')
CONFIG_FILE  = os.path.join(DATA_DIR, 's4_config.json')

DEFAULT_CONFIG = {
    'starting_capital': 2_000_000,
    'commission':       0.00148,
    'max_weight':       0.15,
    'min_stocks':       5,
    'warning_dd':      -20.0,
    'hard_stop_dd':    -30.0,
    'mom_lookback':     126,
    'sma_trend':        100,
    'breadth_sma':      200,
    'bull_breadth':     0.60,
    'bear_breadth':     0.35,
    'hi52_prox':        0.95,
}

# ---------------------------------------------------------------------------
# Global signal state
# ---------------------------------------------------------------------------

signal_status = {
    'status':   'idle',   # idle | running | complete | error
    'progress': '',
    'signals':  None,
    'details':  None,
    'error':    None,
}
signal_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            # Fill any missing keys with defaults
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def _save_config(cfg: dict):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


def _load_latest_signals():
    """Scan for most recent s4_signals_*.json file."""
    pattern = os.path.join(DATA_DIR, 's4_signals_*.json')
    files   = sorted(glob.glob(pattern), reverse=True)
    if files:
        try:
            with open(files[0]) as f:
                return json.load(f)
        except Exception:
            pass
    # Also check in-memory
    with signal_lock:
        return signal_status.get('signals')


def _save_signals(signals: dict):
    date_str  = signals.get('date', datetime.date.today().isoformat())
    filename  = os.path.join(DATA_DIR, f"s4_signals_{date_str}.json")
    with open(filename, 'w') as f:
        json.dump(signals, f, indent=2)


def _regime_meta(regime):
    meta = {
        'BULL':    ('text-green-400',  '🐂', 'Momentum Mode — Full Allocation'),
        'NEUTRAL': ('text-yellow-400', '⚖️', 'Balanced Mode — Reduced Allocation'),
        'BEAR':    ('text-red-400',    '🐻', 'Defensive Mode — Minimum Allocation'),
    }
    return meta.get(regime, meta['NEUTRAL'])


def _fmt(val):
    """Shorthand for format_indian."""
    return pt.format_indian(val)


def _build_portfolio_context(holdings, cash, signals=None):
    """Build template context dict for portfolio/dashboard."""
    positions = []
    holdings_value = 0.0

    for ticker, h in holdings.items():
        qty        = h.get('qty', 0)
        avg        = h.get('avg_price', 0)
        cur        = h.get('current_price', avg)
        val        = qty * cur
        pnl        = (cur - avg) * qty
        pnl_pct    = ((cur / avg) - 1) * 100 if avg else 0
        holdings_value += val
        positions.append({
            'ticker':    ticker,
            'qty':       qty,
            'avg_price': round(avg, 2),
            'ltp':       round(cur, 2),
            'value':     round(val, 2),
            'value_str': _fmt(val),
            'pnl':       round(pnl, 2),
            'pnl_pct':   round(pnl_pct, 2),
        })

    portfolio_value = holdings_value + cash
    total_pnl       = portfolio_value - engine.CAPITAL
    total_return_pct = ((portfolio_value / engine.CAPITAL) - 1) * 100 if engine.CAPITAL else 0

    peak     = pt._load_peak()
    drawdown = ((portfolio_value / peak) - 1) * 100 if peak else 0

    # Day P&L — from live prices if available, else 0
    day_pnl = sum(p.get('day_pnl', 0) for p in positions)

    portfolio = {
        'value':     round(portfolio_value, 2),
        'value_str': _fmt(portfolio_value),
        'pnl':       round(total_pnl, 2),
        'pnl_str':   _fmt(total_pnl),
        'pnl_pct':   round(total_return_pct, 2),
        'day_pnl':   round(day_pnl, 2),
        'day_pct':   0.0,
        'drawdown':  round(drawdown, 2),
        'cash':      round(cash, 2),
        'cash_str':  _fmt(cash),
    }

    return portfolio, positions


# ---------------------------------------------------------------------------
# Routes — HTML pages
# ---------------------------------------------------------------------------

@app.route('/')
def dashboard():
    holdings, cash = pt.load_portfolio(EXCEL_FILE)
    signals = _load_latest_signals() or {}
    regime  = signals.get('regime', 'NEUTRAL')
    color, icon, regime_msg = _regime_meta(regime)
    next_rebalance = signals.get('next_rebalance', '—')
    cfg = _load_config()
    kill_switch_dd = cfg.get('warning_dd', -20.0)

    portfolio, positions = _build_portfolio_context(holdings, cash, signals)

    # Regime details
    regime_details = {
        'breadth':    signals.get('breadth', 0),
        'vol_fast':   signals.get('vol_fast', 0),
        'vol_slow':   signals.get('vol_slow', 0),
        'vol_scale':  signals.get('vol_scale', 1),
        'n_above_sma': signals.get('n_above_sma', 0),
        'n_positive_mom': signals.get('n_positive_mom', 0),
    }

    return render_template(
        'dashboard.html',
        regime=regime,
        regime_color=color,
        regime_icon=icon,
        regime_msg=regime_msg,
        next_rebalance=next_rebalance,
        portfolio=portfolio,
        positions=positions,
        kill_switch_dd=kill_switch_dd,
        regime_details=regime_details,
        rebal_map=engine.REBAL_MAP,
        active_page='dashboard',
        excel_file=EXCEL_FILE,
    )


@app.route('/portfolio')
def portfolio_page():
    holdings, cash = pt.load_portfolio(EXCEL_FILE)
    signals = _load_latest_signals() or {}
    regime  = signals.get('regime', 'NEUTRAL')
    color, icon, regime_msg = _regime_meta(regime)

    portfolio, positions = _build_portfolio_context(holdings, cash, signals)

    # Chart data
    weight_labels = [p['ticker'] for p in positions]
    weight_data   = [round(p['value'] / portfolio['value'] * 100, 2) if portfolio['value'] else 0
                     for p in positions]
    pnl_labels    = [p['ticker'] for p in positions]
    pnl_data      = [p['pnl'] for p in positions]

    return render_template(
        'portfolio.html',
        regime=regime,
        regime_color=color,
        regime_icon=icon,
        regime_msg=regime_msg,
        portfolio=portfolio,
        positions=positions,
        weight_labels_json=json.dumps(weight_labels),
        weight_data_json=json.dumps(weight_data),
        pnl_labels_json=json.dumps(pnl_labels),
        pnl_data_json=json.dumps(pnl_data),
        active_page='portfolio',
    )


@app.route('/rebalance')
def rebalance():
    return render_template('rebalance.html', active_page='rebalance')


@app.route('/equity')
def equity():
    dates, values = pt.get_equity_history(EXCEL_FILE)
    stats         = pt.get_stats(EXCEL_FILE)
    return render_template(
        'equity.html',
        dates_json=json.dumps(dates),
        equity_json=json.dumps(values),
        stats=stats,
        active_page='equity',
    )


@app.route('/history')
def history():
    trades = pt.get_trade_history(EXCEL_FILE)
    total_buys      = sum(1 for t in trades if t.get('Action') == 'BUY')
    total_sells     = sum(1 for t in trades if t.get('Action') == 'SELL')
    total_turnover  = sum(float(t.get('Value', 0) or 0) for t in trades)
    total_commission= sum(float(t.get('Commission', 0) or 0) for t in trades)
    return render_template(
        'history.html',
        trades=trades,
        total_trades=len(trades),
        total_buys=total_buys,
        total_sells=total_sells,
        total_turnover=round(total_turnover, 2),
        total_turnover_str=_fmt(total_turnover),
        total_commission=round(total_commission, 2),
        total_commission_str=_fmt(total_commission),
        active_page='history',
    )


@app.route('/settings')
def settings():
    cfg = _load_config()
    return render_template('settings.html', config=cfg, active_page='settings')


@app.route('/update_settings', methods=['POST'])
def update_settings():
    cfg = _load_config()
    float_fields = [
        'commission', 'max_weight', 'warning_dd', 'hard_stop_dd',
        'bull_breadth', 'bear_breadth', 'hi52_prox',
    ]
    int_fields = ['starting_capital', 'min_stocks', 'mom_lookback', 'sma_trend', 'breadth_sma']

    for field in float_fields:
        val = request.form.get(field)
        if val is not None:
            try:
                cfg[field] = float(val)
            except ValueError:
                pass

    for field in int_fields:
        val = request.form.get(field)
        if val is not None:
            try:
                cfg[field] = int(val)
            except ValueError:
                pass

    _save_config(cfg)
    return redirect(url_for('settings', saved=1))


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route('/api/generate-signals', methods=['POST'])
def api_generate_signals():
    with signal_lock:
        if signal_status['status'] == 'running':
            return jsonify({'status': 'already_running'})
        signal_status['status']   = 'running'
        signal_status['progress'] = 'Starting signal generation…'
        signal_status['signals']  = None
        signal_status['details']  = None
        signal_status['error']    = None

    def _run():
        try:
            with signal_lock:
                signal_status['progress'] = f'Fetching {len(engine.NIFTY100)} stocks from Yahoo Finance…'
            prices = engine.fetch_universe()
            with signal_lock:
                signal_status['progress'] = 'Running S4 strategy pipeline…'
            signals, details = engine.generate_signals(prices)
            _save_signals(signals)
            details_list = details.to_dict(orient='records') if details is not None else []
            with signal_lock:
                signal_status['status']  = 'complete'
                signal_status['signals'] = signals
                signal_status['details'] = details_list
                signal_status['progress'] = 'Done'
        except Exception as exc:
            with signal_lock:
                signal_status['status'] = 'error'
                signal_status['error']  = str(exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({'status': 'started'})


@app.route('/api/status', methods=['GET'])
def api_status():
    with signal_lock:
        return jsonify(dict(signal_status))


@app.route('/api/execute-trades', methods=['POST'])
def api_execute_trades():
    with signal_lock:
        signals = signal_status.get('signals')

    if not signals:
        signals = _load_latest_signals()

    if not signals:
        return jsonify({'status': 'error', 'message': 'No signals available. Generate signals first.'})

    try:
        holdings, cash = pt.load_portfolio(EXCEL_FILE)
        sells, buys, portfolio_value = pt.compute_trades(holdings, cash, signals)
        updated_holdings, new_cash, new_pv = pt.execute_trades(
            EXCEL_FILE, holdings, cash, sells, buys, signals
        )
        trades_executed = len(sells) + len(buys)
        return jsonify({
            'status':           'success',
            'trades_executed':  trades_executed,
            'portfolio_value':  round(new_pv, 2),
            'portfolio_value_str': _fmt(new_pv),
        })
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)})


@app.route('/api/update-prices', methods=['POST'])
def api_update_prices():
    try:
        holdings, _ = pt.load_portfolio(EXCEL_FILE)
        if not holdings:
            return jsonify({'status': 'ok', 'message': 'No holdings to update.'})
        live_prices = engine.fetch_live_prices(list(holdings.keys()))
        summary = pt.update_prices(EXCEL_FILE, live_prices)
        summary['status'] = 'ok'
        summary['portfolio_value_str'] = _fmt(summary['portfolio_value'])
        return jsonify(summary)
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _bootstrap():
    """Ensure required files exist on startup."""
    if not os.path.exists(EXCEL_FILE):
        pt.create_workbook(EXCEL_FILE)
        print(f"Created {EXCEL_FILE}")
    if not os.path.exists(CONFIG_FILE):
        _save_config(DEFAULT_CONFIG)
        print(f"Created {CONFIG_FILE}")


if __name__ == '__main__':
    _bootstrap()
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=5000)
