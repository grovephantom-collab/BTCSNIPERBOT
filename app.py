import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests
import json
import os
from datetime import datetime

# ==============================================================================
# BTC SNIPER 5M - TRUE 24/7 BACKGROUND ENGINE + REALTIME CHART VISUAL SYNC
# ==============================================================================

BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"
DATA_FILE = "trade_history.json"

def get_default_state():
    return {
        "history": [],
        "total_signals": 0,
        "tp_count": 0,
        "sl_count": 0,
        "win_rate": 0.0,
        "active_trade": None,
        "auto_trade_config": {
            "enabled": True,
            "capital": 100.0,
            "leverage": 10
        }
    }

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                d = json.load(f)
                if "auto_trade_config" not in d:
                    d["auto_trade_config"] = {"enabled": True, "capital": 100.0, "leverage": 10}
                return d
        except Exception:
            return get_default_state()
    return get_default_state()

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

if st.query_params.get("action") == "clear_all":
    save_data(get_default_state())
    st.query_params.clear()
    st.rerun()

if "SHARED_APP_STATE" not in st.session_state:
    st.session_state["SHARED_APP_STATE"] = load_data()

GLOBAL_DATA = st.session_state["SHARED_APP_STATE"]

def send_tg_direct(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(CHAT_ID).strip(), "text": msg}
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False

def get_cloud_klines():
    urls = [
        "https://api.binance.us/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=45",
        "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=45",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=45"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=2.5)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) >= 30:
                    closed = [{
                        'open': float(d[1]), 'high': float(d[2]),
                        'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])
                    } for d in raw[:-1]]
                    cur = raw[-1]
                    live = {
                        'open': float(cur[1]), 'high': float(cur[2]),
                        'low': float(cur[3]), 'close': float(cur[4]), 'vol': float(cur[5])
                    }
                    return closed, live
        except Exception:
            continue
    return None, None

# 24/7 Persistent Server Daemon
class BackgroundCloudDaemon:
    def __init__(self):
        self.active_trade = GLOBAL_DATA.get("active_trade", None)
        self.last_signal_time = 0

    def record_trade(self, trade_type, entry, result, pnl_pts, pnl_usd, qty):
        now_str = datetime.now().strftime("%H:%M")
        GLOBAL_DATA["total_signals"] += 1
        if "TP" in result:
            GLOBAL_DATA["tp_count"] += 1
        elif "SL" in result:
            GLOBAL_DATA["sl_count"] += 1

        total = GLOBAL_DATA["tp_count"] + GLOBAL_DATA["sl_count"]
        if total > 0:
            GLOBAL_DATA["win_rate"] = round((GLOBAL_DATA["tp_count"] / total) * 100, 1)

        GLOBAL_DATA["history"].insert(0, {
            "time": now_str,
            "type": trade_type,
            "entry": float(entry),
            "result": result,
            "pts": pnl_pts,
            "pnl_usd": pnl_usd,
            "qty": qty
        })
        if len(GLOBAL_DATA["history"]) > 500:
            GLOBAL_DATA["history"].pop()

        self.active_trade = None
        GLOBAL_DATA["active_trade"] = None
        save_data(GLOBAL_DATA)

    def run(self):
        while True:
            closed, live = get_cloud_klines()
            if closed and live:
                if self.active_trade:
                    self.manage_active_trade(live)
                else:
                    self.scan_market_breakouts(closed, live)
            time.sleep(1.5)

    def manage_active_trade(self, live):
        t = self.active_trade
        qty = t.get("qty", 0.01)

        if t['type'] == 'LONG':
            # Dynamic Breakeven lock
            if not t['be_hit'] and live['high'] >= (t['entry'] + 180.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] + 25.0, 1)
                GLOBAL_DATA["active_trade"] = t
                save_data(GLOBAL_DATA)
                send_tg_direct(f"🎯 BTC LONG PROTECTED (+180 pts)!\nSL locked to Breakeven (${t['sl']:.1f}). Position is Risk-Free.")

            if live['high'] >= t['tp']:
                pnl_pts = round(t['tp'] - t['entry'], 1)
                pnl_usd = round(pnl_pts * qty, 2)
                send_tg_direct(f"🚀 BTC LONG RUNNER COMPLETED!\nNet Profit: +${pnl_usd} (+{pnl_pts:.0f} pts)\nSold Qty: {qty} BTC @ ${t['tp']:.1f}")
                self.record_trade("LONG", t['entry'], "TP HIT", f"+{pnl_pts:.0f}", f"+${pnl_usd}", qty)
                return
            elif live['low'] <= t['sl']:
                res = "BE LOCKED" if t['be_hit'] else "SL HIT"
                pnl_pts = 25.0 if t['be_hit'] else -(t['entry'] - t['sl'])
                pnl_usd = round(pnl_pts * qty, 2)
                sign = "+" if pnl_usd >= 0 else ""
                send_tg_direct(f"🛡️ BTC LONG {res}\nPnL: {sign}${pnl_usd} ({sign}{pnl_pts:.0f} pts)\nClosed @ ${t['sl']:.1f}")
                self.record_trade("LONG", t['entry'], res, f"{sign}{pnl_pts:.0f}", f"{sign}${pnl_usd}", qty)
                return

        elif t['type'] == 'SHORT':
            if not t['be_hit'] and live['low'] <= (t['entry'] - 180.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] - 25.0, 1)
                GLOBAL_DATA["active_trade"] = t
                save_data(GLOBAL_DATA)
                send_tg_direct(f"🎯 BTC SHORT PROTECTED (+180 pts)!\nSL locked to Breakeven (${t['sl']:.1f}). Position is Risk-Free.")

            if live['low'] <= t['tp']:
                pnl_pts = round(t['entry'] - t['tp'], 1)
                pnl_usd = round(pnl_pts * qty, 2)
                send_tg_direct(f"🩸 BTC SHORT RUNNER COMPLETED!\nNet Profit: +${pnl_usd} (+{pnl_pts:.0f} pts)\nCovered Qty: {qty} BTC @ ${t['tp']:.1f}")
                self.record_trade("SHORT", t['entry'], "TP HIT", f"+{pnl_pts:.0f}", f"+${pnl_usd}", qty)
                return
            elif live['high'] >= t['sl']:
                res = "BE LOCKED" if t['be_hit'] else "SL HIT"
                pnl_pts = 25.0 if t['be_hit'] else -(t['sl'] - t['entry'])
                pnl_usd = round(pnl_pts * qty, 2)
                sign = "+" if pnl_usd >= 0 else ""
                send_tg_direct(f"🛡️ BTC SHORT {res}\nPnL: {sign}${pnl_usd} ({sign}{pnl_pts:.0f} pts)\nClosed @ ${t['sl']:.1f}")
                self.record_trade("SHORT", t['entry'], res, f"{sign}{pnl_pts:.0f}", f"{sign}${pnl_usd}", qty)
                return

    def scan_market_breakouts(self, closed, live):
        now = time.time()
        if now - self.last_signal_time < 180:
            return

        cfg = GLOBAL_DATA.get("auto_trade_config", {"enabled": True, "capital": 100.0, "leverage": 10})
        if not cfg.get("enabled", True):
            return

        # ATR 14 Period calculation
        tr_list = []
        for i in range(len(closed) - 14, len(closed)):
            c, p = closed[i], closed[i-1]
            tr_list.append(max(c['high'] - c['low'], abs(c['high'] - p['close']), abs(c['low'] - p['close'])))
        atr = max(sum(tr_list) / len(tr_list), 250.0)

        # Trend Filter (EMA 30)
        closes = [c['close'] for c in closed]
        k = 2 / (30 + 1)
        ema30 = closes[0]
        for cl in closes[1:]:
            ema30 = (cl * k) + (ema30 * (1 - k))

        is_uptrend = live['close'] > ema30
        is_downtrend = live['close'] < ema30

        lookback = closed[-8:]
        high_range = max(c['high'] for c in lookback)
        low_range = min(c['low'] for c in lookback)
        body = live['close'] - live['open']

        long_cond = is_uptrend and (live['close'] > high_range) and (body >= 28.0)
        short_cond = is_downtrend and (live['close'] < low_range) and (body <= -28.0)

        capital = float(cfg.get("capital", 100.0))
        lev = int(cfg.get("leverage", 10))
        pos_usd = capital * lev

        if long_cond:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            # Safe 1.4x ATR SL Buffer
            risk = round(atr * 1.4, 1)
            sl = round(entry - risk, 1)
            tp = round(entry + (risk * 1.8), 1)

            qty = round(pos_usd / entry, 4)
            if qty <= 0: qty = 0.001

            self.active_trade = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp,
                'risk': risk, 'qty': qty, 'be_hit': False, 'capital': capital, 'leverage': lev
            }
            GLOBAL_DATA["active_trade"] = self.active_trade
            save_data(GLOBAL_DATA)

            send_tg_direct(
                f"⚡ [SNIPER AUTO BUY] BTC LONG\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🛡️ Safe Buffer SL: ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 Big TP: ${tp:.1f} (+${risk * 1.8:.1f})\n"
                f"📦 Qty: {qty} BTC (~${pos_usd:.0f})\n\n"
                f"Protection: 1.4x ATR Volatility Guard"
            )

        elif short_cond:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            risk = round(atr * 1.4, 1)
            sl = round(entry + risk, 1)
            tp = round(entry - (risk * 1.8), 1)

            qty = round(pos_usd / entry, 4)
            if qty <= 0: qty = 0.001

            self.active_trade = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp,
                'risk': risk, 'qty': qty, 'be_hit': False, 'capital': capital, 'leverage': lev
            }
            GLOBAL_DATA["active_trade"] = self.active_trade
            save_data(GLOBAL_DATA)

            send_tg_direct(
                f"⚡ [SNIPER AUTO SELL] BTC SHORT\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🛡️ Safe Buffer SL: ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 Big TP: ${tp:.1f} (+${risk * 1.8:.1f})\n"
                f"📦 Qty: {qty} BTC (~${pos_usd:.0f})\n\n"
                f"Protection: 1.4x ATR Volatility Guard"
            )

# Ensure Single Persistent Background Daemon on Server
if "background_daemon_started" not in st.session_state:
    st.session_state["background_daemon_started"] = True
    found = False
    for th in threading.enumerate():
        if th.name == "SniperBackgroundDaemon" and th.is_alive():
            found = True
            break
    if not found:
        daemon = BackgroundCloudDaemon()
        t = threading.Thread(target=daemon.run, name="SniperBackgroundDaemon", daemon=True)
        t.start()

# --- STREAMLIT DASHBOARD CONFIG ---
st.set_page_config(page_title="BTC SNIPER 5M", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    header, footer, #MainMenu { display: none !important; }
    .stDeployButton, [data-testid="stStatusWidget"], footer, .viewerBadge_container__1QSob { display: none !important; }
    .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
    iframe { width: 100vw !important; height: 100vh !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

current_data = load_data()
history_str = json.dumps(current_data["history"])
stats_str = json.dumps({
    "total": current_data["total_signals"],
    "tp": current_data["tp_count"],
    "sl": current_data["sl_count"],
    "win_rate": current_data["win_rate"]
})
trade_str = json.dumps(current_data.get("active_trade"))
cfg_str = json.dumps(current_data.get("auto_trade_config", {"enabled": True, "capital": 100.0, "leverage": 10}))

terminal_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { background: #080a0f; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100vw; height: 100vh; overflow: hidden; }
        
        .top-nav { 
            display: flex; align-items: center; background: #0d111a; 
            border-bottom: 1px solid #1a2336; padding: 4px 8px; 
            font-size: 11px; height: 38px; gap: 8px; overflow-x: auto; white-space: nowrap; 
        }
        .brand { font-weight: 800; color: #fff; font-size: 10px; display: flex; align-items: center; gap: 4px; }
        .badge-scan { background: #00e676; color: #000; font-size: 8px; padding: 2px 5px; border-radius: 3px; font-weight: 900; }
        
        .stat-card { display: flex; flex-direction: column; min-width: 55px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }
        .stat-val { font-size: 10px; font-weight: 800; color: #fff; }
        
        .btn-history {
            background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40;
            border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer;
        }

        .workspace { 
            display: flex; 
            flex-direction: column; 
            width: 100vw; 
            height: calc(100vh - 38px); 
        }
        
        #chart-zone { 
            width: 100vw; 
            height: 55vh; 
            background: #080a0f; 
        }

        .trade-dock {
            width: 100vw;
            height: 38px;
            background: #0a0e17;
            border-top: 1px solid #1a2336;
            padding: 2px 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 10px;
        }
        .dock-group { display: flex; align-items: center; gap: 6px; }
        .dock-input {
            background: #121824; border: 1px solid #23304a; color: #00e676;
            font-size: 11px; font-weight: 800; border-radius: 4px; padding: 2px 6px; width: 50px; text-align: center;
        }
        .toggle-btn {
            background: #00e676; color: #000; font-size: 9px; font-weight: 900;
            padding: 4px 8px; border-radius: 4px; border: none; cursor: pointer;
        }

        .bottom-bar {
            width: 100vw;
            height: calc(45vh - 76px);
            max-height: 48px;
            background: #0d121c;
            border-top: 1px solid #1a2336;
            padding: 3px 8px;
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1.5fr;
            gap: 6px;
            align-items: center;
        }
        .metric-cell {
            display: flex;
            flex-direction: column;
            justify-content: center;
            background: #101624;
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid #192233;
            height: 36px;
        }
        .cell-head {
            font-size: 7px;
            color: #62697a;
            font-weight: 800;
            text-transform: uppercase;
            line-height: 1;
            margin-bottom: 2px;
        }
        .cell-body {
            font-size: 10px;
            font-weight: 800;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .modal-bg {
            display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 999;
            align-items: center; justify-content: center;
        }
        .modal-box {
            background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px;
            width: 92vw; max-width: 420px; max-height: 80vh; display: flex; flex-direction: column;
            padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }
        .history-list { overflow-y: auto; max-height: 280px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ SNIPER 5M <span class="badge-scan">24/7 CLOUD</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">BIG TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 HISTORY (<span id="hist-count">0</span>)</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">Connecting...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="trade-dock">
            <div class="dock-group">
                <button id="btn-auto-toggle" class="toggle-btn" onclick="toggleAutoTrade()">AUTO TRADE: ON</button>
                <span style="color:#62697a; font-weight:800;">AMT ($):</span>
                <input id="input-amount" class="dock-input" type="number" value="100" onchange="updateCalcQty()">
                <span style="color:#62697a; font-weight:800;">LEV:</span>
                <input id="input-lev" class="dock-input" type="number" value="10" onchange="updateCalcQty()">
            </div>
            <div class="dock-group">
                <span style="color:#62697a;">QTY:</span>
                <b id="calc-qty" style="color:#38bdf8; font-size:11px;">0.0117 BTC</b>
            </div>
        </div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">TREND (EMA 30)</span>
                <div class="cell-body" id="val-trend" style="color:#00e676;">ANALYZING...</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">RSI (14)</span>
                <div class="cell-body" id="val-rsi">--</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">ATR VOL</span>
                <div class="cell-body" id="val-atr" style="color:#f0b90b;">--</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">POSITION STATUS</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">CLOUD RADAR ACTIVE</div>
            </div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:12px;">TRADE HISTORY & ACTUAL P&L</b>
                <div style="display:flex; gap:6px; align-items:center;">
                    <button onclick="clearAllServerHistory()" style="background:#ff3b30; border:none; color:#fff; font-size:9px; font-weight:800; padding:3px 8px; border-radius:3px; cursor:pointer;">CLEAR ALL</button>
                    <button onclick="toggleModal(false)" style="background:transparent; border:none; color:#888; font-size:16px; cursor:pointer; margin-left:4px;">✕</button>
                </div>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin-bottom:10px;">
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>Total Trades</span><b id="stat-total" style="color:#fff;">0</b>
                </div>
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>Win Rate</span><b id="stat-rate" style="color:#00e676;">0.0%</b>
                </div>
            </div>
            <div id="history-container" class="history-list">
                <div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>
            </div>
        </div>
    </div>

    <script>
        const IST_OFFSET = 5.5 * 3600;
        let stats = __STATS_PLACEHOLDER__;
        let historyData = __HISTORY_PLACEHOLDER__;
        let activeTrade = __TRADE_PLACEHOLDER__;
        let cfg = __CFG_PLACEHOLDER__;

        let candles = [];
        let lineEntry = null, lineSL = null, lineTP = null;
        let currentPrice = 85500.0;

        function toggleModal(show) {
            document.getElementById('modal-bg').style.display = show ? 'flex' : 'none';
        }
        function handleBgClick(e) {
            if (e.target.id === 'modal-bg') toggleModal(false);
        }

        function clearAllServerHistory() {
            window.parent.location.search = '?action=clear_all';
        }

        function toggleAutoTrade() {
            cfg.enabled = !cfg.enabled;
            const btn = document.getElementById('btn-auto-toggle');
            btn.innerText = cfg.enabled ? "AUTO TRADE: ON" : "AUTO TRADE: OFF";
            btn.style.background = cfg.enabled ? "#00e676" : "#ff3b30";
            btn.style.color = cfg.enabled ? "#000" : "#fff";
        }

        function updateCalcQty() {
            let amt = parseFloat(document.getElementById('input-amount').value) || 100;
            let lev = parseFloat(document.getElementById('input-lev').value) || 10;
            let qty = ((amt * lev) / currentPrice).toFixed(4);
            document.getElementById('calc-qty').innerText = qty + " BTC";
        }

        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {
            width: chartZone.clientWidth, height: chartZone.clientHeight,
            layout: { background: { color: '#080a0f' }, textColor: '#787b86' },
            grid: { vertLines: { color: '#111622' }, horzLines: { color: '#111622' } },
            rightPriceScale: { borderColor: '#192130' },
            timeScale: { borderColor: '#192130', timeVisible: true, secondsVisible: false },
            localization: {
                timeFormatter: t => {
                    const d = new Date((t + IST_OFFSET) * 1000);
                    return d.toUTCString().match(/\\d{2}:\\d{2}/)[0];
                }
            }
        });

        const series = chart.addCandlestickSeries({
            upColor: '#00E676', downColor: '#FF3B30',
            borderUpColor: '#00E676', borderDownColor: '#FF3B30',
            wickUpColor: '#00E676', wickDownColor: '#FF3B30'
        });

        function renderLines() {
            if (lineEntry) { try { series.removePriceLine(lineEntry); } catch(e){} lineEntry = null; }
            if (lineSL) { try { series.removePriceLine(lineSL); } catch(e){} lineSL = null; }
            if (lineTP) { try { series.removePriceLine(lineTP); } catch(e){} lineTP = null; }

            if (!activeTrade) return;

            lineEntry = series.createPriceLine({
                price: activeTrade.entry,
                color: '#38bdf8',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'ENTRY $' + activeTrade.entry.toFixed(1)
            });

            lineSL = series.createPriceLine({
                price: activeTrade.sl,
                color: '#ff3b30',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'SAFE SL $' + activeTrade.sl.toFixed(1)
            });

            lineTP = series.createPriceLine({
                price: activeTrade.tp,
                color: '#00e676',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'BIG TP $' + activeTrade.tp.toFixed(1)
            });
        }

        function renderUI() {
            document.getElementById('hist-count').innerText = historyData.length;
            document.getElementById('stat-total').innerText = stats.total;
            document.getElementById('stat-rate').innerText = stats.win_rate + "%";

            const histCont = document.getElementById('history-container');
            if (historyData.length > 0) {
                histCont.innerHTML = "";
                historyData.forEach(item => {
                    let resCol = item.result.includes("TP") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    let pnlDisp = item.pnl_usd ? `<b style="color:${resCol}; margin-left:4px;">(${item.pnl_usd})</b>` : '';
                    let qtyDisp = item.qty ? `<span style="color:#62697a; font-size:8px;">[${item.qty} BTC]</span>` : '';
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span>${item.time} <b style="color:${typeCol};">${item.type}</b> ${qtyDisp} @ $${item.entry.toFixed(1)}</span>
                            <span><b style="color:${resCol};">${item.result}</b> ${pnlDisp}</span>
                        </div>
                    `;
                });
            } else {
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>';
            }

            if (activeTrade) {
                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
                document.getElementById('disp-tp').innerText = "$" + activeTrade.tp.toFixed(1);
                document.getElementById('val-setup').innerText = activeTrade.type + " RUNNING 🔥";
                document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = "24/7 CLOUD RADAR ACTIVE";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }
        }

        function updateMetricsUI() {
            if (candles.length < 15) return;
            const closes = candles.map(c => c.close);
            let gains = 0, losses = 0;
            for (let i = closes.length - 14; i < closes.length; i++) {
                let diff = closes[i] - closes[i - 1];
                if (diff >= 0) gains += diff; else losses -= diff;
            }
            let rsi = (100 - (100 / (1 + (losses === 0 ? 100 : gains / losses)))).toFixed(1);
            document.getElementById('val-rsi').innerText = rsi;

            let trSum = 0;
            for (let i = candles.length - 14; i < candles.length; i++) {
                let c = candles[i], p = candles[i - 1];
                trSum += Math.max(c.high - c.low, Math.abs(c.high - p.close), Math.abs(c.low - p.close));
            }
            let atr = (trSum / 14).toFixed(1);
            document.getElementById('val-atr').innerText = "$" + atr;

            let k = 2 / (30 + 1);
            let ema30 = closes[0];
            for (let i = 1; i < closes.length; i++) {
                ema30 = (closes[i] * k) + (ema30 * (1 - k));
            }
            let isBull = closes[closes.length - 1] >= ema30;
            document.getElementById('val-trend').innerText = isBull ? "BULLISH ▲" : "BEARISH ▼";
            document.getElementById('val-trend').style.color = isBull ? "#00e676" : "#ff3b30";
        }

        function get5MBoundary(unixSec) {
            return unixSec - (unixSec % 300);
        }

        function syncCandles() {
            fetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=80')
                .then(r => r.json())
                .then(data => {
                    candles = data.map(d => ({
                        time: get5MBoundary(Math.floor(d[0] / 1000)),
                        open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                    }));
                    series.setData(candles);
                    chart.timeScale().fitContent();
                    renderLines();
                    renderUI();
                    updateMetricsUI();
                    connectLiveStream();
                }).catch(e => setTimeout(syncCandles, 2000));
        }
        syncCandles();

        function updateLiveCandle(price, rawTimeSec) {
            if (candles.length === 0) return;
            currentPrice = price;
            updateCalcQty();

            const barTime = get5MBoundary(rawTimeSec);
            let last = candles[candles.length - 1];

            if (barTime === last.time) {
                last.close = price;
                if (price > last.high) last.high = price;
                if (price < last.low) last.low = price;
                series.update(last);
            } else if (barTime > last.time) {
                const newBar = { time: barTime, open: price, high: price, low: price, close: price };
                candles.push(newBar);
                series.update(newBar);
            }

            document.getElementById('live-price').innerText = "$" + price.toFixed(1);
            updateMetricsUI();
        }

        function connectLiveStream() {
            const ws = new WebSocket("wss://fstream.binance.com/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {
                const k = JSON.parse(e.data).k;
                const candleTimeSec = Math.floor(k.t / 1000);
                const closePrice = parseFloat(k.c);
                updateLiveCandle(closePrice, candleTimeSec);
            };
            ws.onclose = () => setTimeout(connectLiveStream, 1500);
        }

        setInterval(() => {
            fetch('https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT')
                .then(r => r.json())
                .then(p => {
                    const pr = parseFloat(p.price);
                    const nowSec = Math.floor(Date.now() / 1000);
                    updateLiveCandle(pr, nowSec);
                }).catch(err => {});
        }, 1500);

        renderLines();
        renderUI();
        updateCalcQty();
        window.onresize = () => chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
    </script>
</body>
</html>""".replace("__STATS_PLACEHOLDER__", stats_str).replace("__HISTORY_PLACEHOLDER__", history_str).replace("__TRADE_PLACEHOLDER__", trade_str).replace("__CFG_PLACEHOLDER__", cfg_str)

components.html(terminal_html, height=720, scrolling=False)
