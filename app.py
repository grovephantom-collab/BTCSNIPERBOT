import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests
import json
import os
from datetime import datetime

# ==============================================================================
# EXACT ORIGINAL DASHBOARD (IMAGE RESTORED + POPUP HISTORY + TELEGRAM FIXED)
# ==============================================================================

BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"
DATA_FILE = "trade_history.json"

def load_saved_data():
    default_data = {
        "history": [],
        "total_signals": 0,
        "tp_count": 0,
        "sl_count": 0,
        "win_rate": 0.0,
        "active_trade": None
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return default_data
    return default_data

def save_data_to_file(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

if "SHARED_DATA" not in st.session_state:
    st.session_state["SHARED_DATA"] = load_saved_data()

GLOBAL_STATE = st.session_state["SHARED_DATA"]

# Reliable Direct Telegram Dispatcher
def send_tg(text):
    def _dispatch():
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        for _ in range(3):
            try:
                res = requests.post(url, json=payload, timeout=5)
                if res.status_code == 200:
                    break
            except Exception:
                time.sleep(1)
    threading.Thread(target=_dispatch, daemon=True).start()

def calc_rsi(closes, period=14):
    if len(closes) <= period:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def calc_atr(candles, p=14):
    if len(candles) <= p:
        return 60.0
    trs = []
    start_idx = max(1, len(candles) - p)
    for i in range(start_idx, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        prev_c = candles[i-1]['close']
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return round(max(25.0, sum(trs) / max(1, len(trs))), 1)

class InstitutionalMasterEngine:
    def __init__(self):
        self.active_trade = GLOBAL_STATE.get("active_trade", None)
        self.last_candle_time = 0
        self.sentiment_score = 50
        self.market_sentiment = "NEUTRAL"
        self.last_sentiment_check = 0
        self.live_rsi = 50.0
        self.live_atr = 60.0
        self.live_trend = "BULL"
        self.setup_score = 30
        
        # Test alert on boot
        send_tg(
            "🟢 <b>SNIPER 5M SYSTEM ONLINE</b>\n\n"
            "• UI Restored: Institutional Setup & Metrics View\n"
            "• Popup History: Enabled\n"
            "• Live Alerts: Active 24/7"
        )

    def record_history_and_clear(self, trade_type, entry, result, pnl_pts):
        now_str = datetime.now().strftime("%H:%M")

        GLOBAL_STATE["total_signals"] += 1
        if "TP" in result or "RUNNER" in result:
            GLOBAL_STATE["tp_count"] += 1
        elif "SL" in result:
            GLOBAL_STATE["sl_count"] += 1

        total_closed = GLOBAL_STATE["tp_count"] + GLOBAL_STATE["sl_count"]
        if total_closed > 0:
            GLOBAL_STATE["win_rate"] = round((GLOBAL_STATE["tp_count"] / total_closed) * 100, 1)

        record = {
            "time": now_str,
            "type": trade_type,
            "entry": entry,
            "result": result,
            "pts": pnl_pts
        }
        GLOBAL_STATE["history"].insert(0, record)
        if len(GLOBAL_STATE["history"]) > 50:
            GLOBAL_STATE["history"].pop()

        self.active_trade = None
        GLOBAL_STATE["active_trade"] = None
        save_data_to_file(GLOBAL_STATE)

    def fetch_global_sentiment(self):
        now = time.time()
        if now - self.last_sentiment_check >= 600:
            self.last_sentiment_check = now
            try:
                r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=4)
                if r.status_code == 200:
                    data = r.json()
                    self.sentiment_score = int(data['data'][0]['value'])
                    self.market_sentiment = data['data'][0]['value_classification'].upper()
            except Exception:
                pass
        return self.sentiment_score, self.market_sentiment

    def start(self):
        while True:
            try:
                res = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=45", timeout=5)
                r_1h = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=50", timeout=5)

                if res.status_code == 200 and r_1h.status_code == 200:
                    r_5m = res.json()
                    r_1h_data = r_1h.json()

                    if isinstance(r_5m, list) and isinstance(r_1h_data, list) and len(r_5m) >= 25:
                        closed_kline = r_5m[-2]
                        live_kline = r_5m[-1]
                        c_time = int(closed_kline[0] / 1000)

                        candles = [{
                            'time': int(d[0]/1000), 'open': float(d[1]), 'high': float(d[2]),
                            'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5]),
                            'taker_vol': float(d[9])
                        } for d in r_5m[:-1]]

                        closes_5m = [c['close'] for c in candles]
                        self.live_rsi = calc_rsi(closes_5m, 14)
                        self.live_atr = calc_atr(candles, 14)

                        closes_1h = [float(d[4]) for d in r_1h_data[:-1]]
                        ema50_1h = sum(closes_1h[-35:]) / len(closes_1h[-35:])
                        self.live_trend = "BULL" if closes_1h[-1] >= ema50_1h else "BEAR"

                        live = {
                            'high': float(live_kline[2]),
                            'low': float(live_kline[3]),
                            'close': float(live_kline[4])
                        }

                        sentiment_val, sentiment_label = self.fetch_global_sentiment()

                        if self.active_trade:
                            self.manage_active_trade(live)

                        if not self.active_trade and c_time > self.last_candle_time:
                            self.last_candle_time = c_time
                            self.evaluate_full_confluence(candles, sentiment_val, sentiment_label)
            except Exception:
                pass
            time.sleep(3)

    def manage_active_trade(self, live):
        t = self.active_trade
        t['duration'] += 1

        if t['type'] == 'LONG':
            if not t['tp1_hit'] and live['high'] >= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] + 15.0, 1)
                GLOBAL_STATE["active_trade"] = t
                save_data_to_file(GLOBAL_STATE)
                send_tg(f"🎯 <b>TARGET 1 HIT (+90 pts)</b>\n\nBTC Long: ${t['tp1']:.1f}\nSL shifted to Breakeven (${t['sl']:.1f}). Position is Risk-Free.")

            if live['high'] >= t['tp2']:
                send_tg(f"🚀 <b>RUNNER HIT (+${t['reward']:.1f})</b>\n\nBTC Long hit target ${t['tp2']:.1f}! Screen display cleared.")
                self.record_history_and_clear("LONG", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['low'] <= t['sl']:
                status = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                send_tg(f"🛡️ <b>{status}</b>\n\nBTC Long exited at ${t['sl']:.1f}. Screen cleared.")
                self.record_history_and_clear("LONG", t['entry'], status, pts)
                return

            if t['duration'] >= 7 and not t['tp1_hit'] and live['close'] < (t['entry'] + 15.0):
                send_tg(f"⚠️ <b>TIME STALL EXIT</b>\n\nClosed at ${live['close']:.1f}. Screen cleared.")
                self.record_history_and_clear("LONG", t['entry'], "TIME EXIT", "-5")

        elif t['type'] == 'SHORT':
            if not t['tp1_hit'] and live['low'] <= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] - 15.0, 1)
                GLOBAL_STATE["active_trade"] = t
                save_data_to_file(GLOBAL_STATE)
                send_tg(f"🎯 <b>TARGET 1 HIT (+90 pts)</b>\n\nBTC Short: ${t['tp1']:.1f}\nSL shifted to Breakeven (${t['sl']:.1f}). Position is Risk-Free.")

            if live['low'] <= t['tp2']:
                send_tg(f"🩸 <b>RUNNER HIT (+${t['reward']:.1f})</b>\n\nBTC Short hit target ${t['tp2']:.1f}! Screen display cleared.")
                self.record_history_and_clear("SHORT", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['high'] >= t['sl']:
                status = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                send_tg(f"🛡️ <b>{status}</b>\n\nBTC Short exited at ${t['sl']:.1f}. Screen cleared.")
                self.record_history_and_clear("SHORT", t['entry'], status, pts)
                return

            if t['duration'] >= 7 and not t['tp1_hit'] and live['close'] > (t['entry'] - 15.0):
                send_tg(f"⚠️ <b>TIME STALL EXIT</b>\n\nClosed at ${live['close']:.1f}. Screen cleared.")
                self.record_history_and_clear("SHORT", t['entry'], "TIME EXIT", "-5")

    def evaluate_full_confluence(self, candles, sentiment_val, sentiment_label):
        c0 = candles[-1]
        c1 = candles[-2]

        lookback_lows = [c['low'] for c in candles[-16:-3]]
        lookback_highs = [c['high'] for c in candles[-16:-3]]
        recent_low = min(lookback_lows)
        recent_high = max(lookback_highs)

        avg_vol = sum(c['vol'] for c in candles[-7:-1]) / 6.0
        c0_taker_buy = c0['taker_vol']
        c0_taker_sell = c0['vol'] - c0['taker_vol']
        c0_delta = c0_taker_buy - c0_taker_sell

        buy_pressure_ratio = c0_taker_buy / max(1.0, c0_taker_sell)
        sell_pressure_ratio = c0_taker_sell / max(1.0, c0_taker_buy)

        valid_long = (
            (c1['low'] < recent_low) and
            (c0['close'] > c1['open']) and
            (c0['close'] > c0['open']) and
            (buy_pressure_ratio >= 1.25) and
            (c0['vol'] >= avg_vol * 1.1) and
            (c0_delta > 0) and
            (sentiment_val >= 20)
        )

        valid_short = (
            (c1['high'] > recent_high) and
            (c0['close'] < c1['open']) and
            (c0['close'] < c0['open']) and
            (sell_pressure_ratio >= 1.25) and
            (c0['vol'] >= avg_vol * 1.1) and
            (c0_delta < 0) and
            (sentiment_val <= 85)
        )

        if valid_long:
            self.setup_score = 90
            entry = round(c0['close'], 1)
            sl = round(c1['low'] - 10.0, 1)
            risk = round(entry - sl, 1)
            if risk < 65.0: risk = 75.0; sl = round(entry - 75.0, 1)
            if risk > 145.0: risk = 135.0; sl = round(entry - 135.0, 1)

            tp1 = round(entry + 90.0, 1)
            reward = round(risk * 2.3, 1)
            tp2 = round(entry + reward, 1)

            self.active_trade = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0
            }
            GLOBAL_STATE["active_trade"] = self.active_trade
            save_data_to_file(GLOBAL_STATE)

            send_tg(
                f"⚡ <b>ACCURATE BTC LONG (PRE-MOVE)</b>\n\n"
                f"📍 <b>Entry:</b> ${entry:.1f}\n"
                f"🛡️ <b>Shield SL:</b> ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 <b>TP 1:</b> ${tp1:.1f} (+90 pts Auto BE)\n"
                f"🚀 <b>TP 2:</b> ${tp2:.1f} (+${reward:.1f} Runner)\n\n"
                f"🌊 <b>Context:</b> Bear Trap Swept (${recent_low:.1f}) | Buy Vol Ratio {buy_pressure_ratio:.2f}x"
            )

        elif valid_short:
            self.setup_score = 90
            entry = round(c0['close'], 1)
            sl = round(c1['high'] + 10.0, 1)
            risk = round(sl - entry, 1)
            if risk < 65.0: risk = 75.0; sl = round(entry + 75.0, 1)
            if risk > 145.0: risk = 135.0; sl = round(entry - 135.0, 1)

            tp1 = round(entry - 90.0, 1)
            reward = round(risk * 2.3, 1)
            tp2 = round(entry - reward, 1)

            self.active_trade = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0
            }
            GLOBAL_STATE["active_trade"] = self.active_trade
            save_data_to_file(GLOBAL_STATE)

            send_tg(
                f"⚡ <b>ACCURATE BTC SHORT (PRE-MOVE)</b>\n\n"
                f"📍 <b>Entry:</b> ${entry:.1f}\n"
                f"🛡️ <b>Shield SL:</b> ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 <b>TP 1:</b> ${tp1:.1f} (+90 pts Auto BE)\n"
                f"🩸 <b>TP 2:</b> ${tp2:.1f} (+${reward:.1f} Runner)\n\n"
                f"🌊 <b>Context:</b> Bull Trap Swept (${recent_high:.1f}) | Sell Vol Ratio {sell_pressure_ratio:.2f}x"
            )
        else:
            self.setup_score = 30

engine_instance = None
if "engine_worker" not in st.session_state:
    st.session_state["engine_worker"] = True
    found = False
    for th in threading.enumerate():
        if th.name == "ExactRestoredWorker":
            found = True
            break
    if not found:
        eng = InstitutionalMasterEngine()
        engine_instance = eng
        t = threading.Thread(target=eng.start, name="ExactRestoredWorker", daemon=True)
        t.start()

# --- STREAMLIT CLEAN VIEWPORT ---
st.set_page_config(page_title="BTC SNIPER 5M", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    header, footer, #MainMenu { display: none !important; }
    .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
    iframe { width: 100vw !important; height: 100vh !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

current_data = load_saved_data()
history_str = json.dumps(current_data["history"])
stats_str = json.dumps({
    "total": current_data["total_signals"],
    "tp": current_data["tp_count"],
    "sl": current_data["sl_count"],
    "win_rate": current_data["win_rate"]
})
trade_str = json.dumps(current_data.get("active_trade"))

# Image layout exact restoration
terminal_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { background: #080a0f; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100vw; height: 100vh; overflow: hidden; }
        
        /* EXACT TOP BAR */
        .top-nav { 
            display: flex; align-items: center; background: #0d111a; 
            border-bottom: 1px solid #1a2336; padding: 6px 10px; 
            font-size: 11px; height: 44px; gap: 8px; overflow-x: auto; white-space: nowrap; 
        }
        .brand { font-weight: 800; color: #fff; font-size: 11px; display: flex; align-items: center; gap: 4px; }
        .badge-scan { background: #161f30; color: #38bdf8; font-size: 8px; padding: 2px 5px; border-radius: 3px; font-weight: 700; }
        .stat-card { display: flex; flex-direction: column; min-width: 50px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 700; }
        .stat-val { font-size: 10px; font-weight: 700; color: #fff; }
        
        .btn-history {
            background: #141c2c;
            color: #38bdf8;
            border: 1px solid #1f2a40;
            border-radius: 4px;
            padding: 3px 7px;
            font-size: 9px;
            font-weight: 700;
            cursor: pointer;
        }

        /* 2-HALF WORKSPACE */
        .workspace { display: flex; flex-direction: column; width: 100vw; height: calc(100vh - 44px); }
        #chart-zone { width: 100vw; height: 50%; background: #080a0f; }

        /* EXACT LOWER HALF RESTORATION (MATCHING USER SCREENSHOT) */
        .lower-deck {
            width: 100vw; height: 50%; background: #080b11;
            border-top: 1px solid #141b27; padding: 10px;
            display: flex; flex-direction: column; gap: 8px;
        }
        
        .score-card {
            background: #0d121c; border: 1px solid #151d2d; border-radius: 6px;
            padding: 10px 12px; display: flex; justify-content: space-between; align-items: center;
        }
        .score-left { display: flex; flex-direction: column; }
        .score-label { font-size: 8px; color: #62697a; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
        .score-val { font-size: 20px; font-weight: 800; color: #fff; margin-top: 2px; }
        .score-right { display: flex; flex-direction: column; align-items: flex-end; }
        .score-tag { background: #131a26; color: #78859e; font-size: 9px; padding: 2px 6px; border-radius: 3px; font-weight: 700; }
        .score-sub { font-size: 9px; color: #4e5668; margin-top: 3px; }

        .dual-deck {
            display: grid; grid-template-columns: 1fr 1fr; gap: 8px; flex: 1;
        }
        .mini-card {
            background: #0d121c; border: 1px solid #151d2d; border-radius: 6px;
            padding: 8px 10px; display: flex; flex-direction: column; justify-content: space-between;
        }
        .mini-card-title { font-size: 8px; color: #62697a; font-weight: 800; text-transform: uppercase; margin-bottom: 4px; }
        .row-item { display: flex; justify-content: space-between; font-size: 10px; padding: 3px 0; border-bottom: 1px solid #121824; }
        .row-item:last-child { border-bottom: none; }

        /* MODAL DRAWER FOR HISTORY POPUP */
        .modal-bg {
            display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 999;
            align-items: center; justify-content: center;
        }
        .modal-box {
            background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px;
            width: 90vw; max-width: 400px; max-height: 80vh; display: flex; flex-direction: column;
            padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }
        .history-list { overflow-y: auto; max-height: 250px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #151d2b; }
    </style>
</head>
<body>
    <!-- TOP BAR -->
    <div class="top-nav">
        <div class="brand">⚡ SNIPER 5M <span class="badge-scan">SCANNING</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">BIG TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 HISTORY</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 8px;">
            <b id="live-price" style="color: #f0b90b; font-size: 13px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <!-- UPPER HALF: CANDLESTICK CHART -->
        <div id="chart-zone"></div>

        <!-- LOWER HALF: EXACT MATCH TO USER'S IMAGE -->
        <div class="lower-deck">
            <!-- INSTITUTIONAL SCORE BANNER -->
            <div class="score-card">
                <div class="score-left">
                    <span class="score-label">INSTITUTIONAL SETUP</span>
                    <span class="score-val" id="score-text">30 / 100</span>
                </div>
                <div class="score-right">
                    <span class="score-tag">MONITORING SQUEEZE</span>
                    <span class="score-sub">Only Closed 5M Candles</span>
                </div>
            </div>

            <!-- DUAL CARDS: METRICS & TRADE INFO -->
            <div class="dual-deck">
                <!-- CARD 1: METRICS -->
                <div class="mini-card">
                    <div class="mini-card-title">METRICS</div>
                    <div class="row-item"><span>Trend</span><b id="val-trend" style="color:#ff3b30;">BEAR</b></div>
                    <div class="row-item"><span>RSI</span><b id="val-rsi" style="color:#fff;">66.5</b></div>
                    <div class="row-item"><span>ATR</span><b id="val-atr" style="color:#f0b90b;">$60.8</b></div>
                </div>

                <!-- CARD 2: TRADE INFO -->
                <div class="mini-card">
                    <div class="mini-card-title">TRADE INFO</div>
                    <div class="row-item"><span>Reward</span><b id="val-reward" style="color:#00e676;">--</b></div>
                    <div class="row-item"><span>Risk</span><b id="val-risk" style="color:#ff3b30;">--</b></div>
                    <div class="row-item"><span>Alerts</span><b style="color:#00e676;">TG Active ✅</b></div>
                </div>
            </div>
        </div>
    </div>

    <!-- POPUP HISTORY MODAL -->
    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:12px;">PERFORMANCE & SAVED SIGNALS</b>
                <button onclick="toggleModal(false)" style="background:transparent; border:none; color:#888; font-size:16px; cursor:pointer;">✕</button>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin-bottom:10px;">
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>Total Signals</span><b id="stat-total" style="color:#fff;">0</b>
                </div>
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>Win Rate</span><b id="stat-rate" style="color:#00e676;">0.0%</b>
                </div>
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>TP Hit</span><b id="stat-tp" style="color:#00e676;">0 TP</b>
                </div>
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>SL Hit</span><b id="stat-sl" style="color:#ff3b30;">0 SL</b>
                </div>
            </div>
            <div style="font-size:9px; color:#62697a; font-weight:700; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>TIME | DIRECTION</span>
                <span>RESULT | PTS</span>
            </div>
            <div id="history-container" class="history-list">
                <div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>
            </div>
        </div>
    </div>

    <script>
        const stats = __STATS_PLACEHOLDER__;
        const historyData = __HISTORY_PLACEHOLDER__;
        const activeTrade = __TRADE_PLACEHOLDER__;

        if (activeTrade) {
            document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
            document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
            document.getElementById('disp-tp').innerText = "$" + activeTrade.tp2.toFixed(1);
            document.getElementById('val-reward').innerText = "+$" + activeTrade.reward.toFixed(1);
            document.getElementById('val-risk').innerText = "-$" + activeTrade.risk.toFixed(1);
            document.getElementById('score-text').innerText = "90 / 100";
            document.getElementById('score-text').style.color = "#00e676";
        } else {
            document.getElementById('disp-entry').innerText = "--";
            document.getElementById('disp-sl').innerText = "--";
            document.getElementById('disp-tp').innerText = "--";
            document.getElementById('val-reward').innerText = "--";
            document.getElementById('val-risk').innerText = "--";
            document.getElementById('score-text').innerText = "30 / 100";
            document.getElementById('score-text').style.color = "#fff";
        }

        document.getElementById('stat-total').innerText = stats.total;
        document.getElementById('stat-tp').innerText = stats.tp + " TP";
        document.getElementById('stat-sl').innerText = stats.sl + " SL";
        document.getElementById('stat-rate').innerText = stats.win_rate + "%";

        const histCont = document.getElementById('history-container');
        if (historyData && historyData.length > 0) {
            histCont.innerHTML = "";
            historyData.forEach(item => {
                let resCol = item.result.includes("TP") ? "#00e676" : (item.result.includes("SL") ? "#ff3b30" : "#38bdf8");
                let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                histCont.innerHTML += `
                    <div class="history-item">
                        <span>${item.time} <b style="color:${typeCol};">${item.type}</b> @ $${item.entry.toFixed(1)}</span>
                        <span><b style="color:${resCol};">${item.result}</b> (${item.pts} pts)</span>
                    </div>
                `;
            });
        }

        function toggleModal(show) {
            document.getElementById('modal-bg').style.display = show ? 'flex' : 'none';
        }
        function handleBgClick(e) {
            if (e.target.id === 'modal-bg') toggleModal(false);
        }

        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {
            width: chartZone.clientWidth, height: chartZone.clientHeight,
            layout: { background: { color: '#080a0f' }, textColor: '#787b86' },
            grid: { vertLines: { color: '#111622' }, horzLines: { color: '#111622' } },
            rightPriceScale: { borderColor: '#192130' },
            timeScale: { borderColor: '#192130', timeVisible: true, secondsVisible: false }
        });

        const series = chart.addCandlestickSeries({
            upColor: '#00E676', downColor: '#FF3B30',
            borderUpColor: '#00E676', borderDownColor: '#FF3B30',
            wickUpColor: '#00E676', wickDownColor: '#FF3B30'
        });

        let candles = [];
        let ws = null;
        let lastWsPing = Date.now();

        function syncData() {
            fetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=80')
                .then(r => r.json())
                .then(data => {
                    candles = data.map(d => ({
                        time: Math.floor(d[0] / 1000),
                        open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                    }));
                    series.setData(candles);
                    chart.timeScale().fitContent();
                    connectWS();
                }).catch(e => setTimeout(syncData, 3000));
        }
        syncData();

        function connectWS() {
            if (ws) { try { ws.close(); } catch(e) {} }
            ws = new WebSocket("wss://fstream.binance.com/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {
                lastWsPing = Date.now();
                const k = JSON.parse(e.data).k;
                const c = { 
                    time: Math.floor(k.t / 1000), open: parseFloat(k.o), 
                    high: parseFloat(k.h), low: parseFloat(k.l), close: parseFloat(k.c) 
                };
                document.getElementById('live-price').innerText = "$" + c.close.toFixed(1);
                series.update(c);
                if (candles.length > 0) {
                    const last = candles.length - 1;
                    if (candles[last].time === c.time) candles[last] = c;
                    else if (c.time > candles[last].time) candles.push(c);
                }
            };
            ws.onclose = () => { setTimeout(connectWS, 1500); };
        }

        setInterval(() => {
            if (Date.now() - lastWsPing > 4000) {
                fetch('https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT')
                    .then(r => r.json())
                    .then(p => {
                        const pr = parseFloat(p.price);
                        document.getElementById('live-price').innerText = "$" + pr.toFixed(1);
                        if (candles.length > 0) {
                            const last = candles[candles.length - 1];
                            last.close = pr;
                            last.high = Math.max(last.high, pr);
                            last.low = Math.min(last.low, pr);
                            series.update(last);
                        }
                    }).catch(err => {});
                connectWS();
            }
        }, 3000);

        window.onresize = () => {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        };
    </script>
</body>
</html>""".replace("__STATS_PLACEHOLDER__", stats_str).replace("__HISTORY_PLACEHOLDER__", history_str).replace("__TRADE_PLACEHOLDER__", trade_str)

components.html(terminal_html, height=850, scrolling=False)
