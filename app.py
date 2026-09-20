import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests
import json
import os
from datetime import datetime

# ==============================================================================
# ENTERPRISE PRE-MOVE RADAR - FIXED BOTTOM FIT & PERSISTENT TELEGRAM BOT
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

def send_tg_sync(text):
    """Reliable sync sender with retry mechanism"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    for _ in range(3):
        try:
            res = requests.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False

def send_tg(text):
    threading.Thread(target=send_tg_sync, args=(text,), daemon=True).start()

class InstitutionalMasterEngine:
    def __init__(self):
        self.active_trade = GLOBAL_STATE.get("active_trade", None)
        self.last_signal_time = 0

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

    def run_forever(self):
        while True:
            try:
                res = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=30", timeout=4)
                if res.status_code == 200:
                    r_5m = res.json()
                    if isinstance(r_5m, list) and len(r_5m) >= 15:
                        candles = [{
                            'open': float(d[1]), 'high': float(d[2]),
                            'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5]),
                            'taker_vol': float(d[9])
                        } for d in r_5m[:-1]]

                        live_kline = r_5m[-1]
                        live = {
                            'open': float(live_kline[1]),
                            'high': float(live_kline[2]),
                            'low': float(live_kline[3]),
                            'close': float(live_kline[4]),
                            'vol': float(live_kline[5]),
                            'taker_vol': float(live_kline[9])
                        }

                        if self.active_trade:
                            self.manage_active_trade(live)
                        else:
                            self.scan_immediate_impulse(candles, live)
            except Exception:
                pass
            time.sleep(2.0)

    def manage_active_trade(self, live):
        t = self.active_trade
        t['duration'] += 1

        if t['type'] == 'LONG':
            if not t['tp1_hit'] and live['high'] >= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] + 15.0, 1)
                GLOBAL_STATE["active_trade"] = t
                save_data_to_file(GLOBAL_STATE)
                send_tg(f"🎯 *TARGET 1 HIT (+90 pts)*\n\nBTC Long: `${t['tp1']:.1f}`\nSL shifted to Breakeven (`${t['sl']:.1f}`).")

            if live['high'] >= t['tp2']:
                send_tg(f"🚀 *RUNNER TARGET HIT (+${t['reward']:.1f})*\n\nBTC Long hit `${t['tp2']:.1f}`!")
                self.record_history_and_clear("LONG", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['low'] <= t['sl']:
                status = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                send_tg(f"🛡️ *{status}*\n\nBTC Long closed at `${t['sl']:.1f}`.")
                self.record_history_and_clear("LONG", t['entry'], status, pts)
                return

            if t['duration'] >= 12 and not t['tp1_hit'] and live['close'] < (t['entry'] + 10.0):
                send_tg(f"⚠️ *TIME EXIT*\n\nBTC Long closed safely at `${live['close']:.1f}`.")
                self.record_history_and_clear("LONG", t['entry'], "TIME EXIT", "-5")

        elif t['type'] == 'SHORT':
            if not t['tp1_hit'] and live['low'] <= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] - 15.0, 1)
                GLOBAL_STATE["active_trade"] = t
                save_data_to_file(GLOBAL_STATE)
                send_tg(f"🎯 *TARGET 1 HIT (+90 pts)*\n\nBTC Short: `${t['tp1']:.1f}`\nSL shifted to Breakeven (`${t['sl']:.1f}`).")

            if live['low'] <= t['tp2']:
                send_tg(f"🩸 *RUNNER TARGET HIT (+${t['reward']:.1f})*\n\nBTC Short hit `${t['tp2']:.1f}`!")
                self.record_history_and_clear("SHORT", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['high'] >= t['sl']:
                status = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                send_tg(f"🛡️ *{status}*\n\nBTC Short closed at `${t['sl']:.1f}`.")
                self.record_history_and_clear("SHORT", t['entry'], status, pts)
                return

            if t['duration'] >= 12 and not t['tp1_hit'] and live['close'] > (t['entry'] - 10.0):
                send_tg(f"⚠️ *TIME EXIT*\n\nBTC Short closed safely at `${live['close']:.1f}`.")
                self.record_history_and_clear("SHORT", t['entry'], "TIME EXIT", "-5")

    def scan_immediate_impulse(self, candles, live):
        now = time.time()
        if now - self.last_signal_time < 90:
            return

        c0 = candles[-1]
        recent_low = min(c['low'] for c in candles[-8:])
        recent_high = max(c['high'] for c in candles[-8:])

        taker_buy = live['taker_vol']
        taker_sell = max(0.1, live['vol'] - live['taker_vol'])
        buy_ratio = taker_buy / taker_sell
        sell_ratio = taker_sell / max(0.1, taker_buy)

        long_cond = (
            (live['close'] > live['open']) and
            (live['close'] > c0['high'] or buy_ratio >= 1.05) and
            (live['low'] <= recent_low * 1.002 or buy_ratio >= 1.2)
        )
        short_cond = (
            (live['close'] < live['open']) and
            (live['close'] < c0['low'] or sell_ratio >= 1.05) and
            (live['high'] >= recent_high * 0.998 or sell_ratio >= 1.2)
        )

        if long_cond:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            sl = round(min(live['low'], c0['low']) - 12.0, 1)
            risk = round(entry - sl, 1)
            if risk < 60.0: risk = 70.0; sl = round(entry - 70.0, 1)
            if risk > 140.0: risk = 130.0; sl = round(entry - 130.0, 1)

            tp1 = round(entry + 90.0, 1)
            reward = round(risk * 2.2, 1)
            tp2 = round(entry + reward, 1)

            self.active_trade = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0
            }
            GLOBAL_STATE["active_trade"] = self.active_trade
            save_data_to_file(GLOBAL_STATE)

            send_tg(
                f"⚡ *BTC LONG SIGNAL (5M)*\n\n"
                f"📍 *Entry:* `${entry:.1f}`\n"
                f"🛡️ *SL:* `${sl:.1f}` (-${risk:.1f})\n"
                f"🎯 *TP 1:* `${tp1:.1f}` (+90 pts Auto BE)\n"
                f"🚀 *TP 2:* `${tp2:.1f}` (+${reward:.1f})\n\n"
                f"🌊 *Setup:* Institutional Swing Long"
            )

        elif short_cond:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            sl = round(max(live['high'], c0['high']) + 12.0, 1)
            risk = round(sl - entry, 1)
            if risk < 60.0: risk = 70.0; sl = round(entry + 70.0, 1)
            if risk > 140.0: risk = 130.0; sl = round(entry - 130.0, 1)

            tp1 = round(entry - 90.0, 1)
            reward = round(risk * 2.2, 1)
            tp2 = round(entry - reward, 1)

            self.active_trade = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0
            }
            GLOBAL_STATE["active_trade"] = self.active_trade
            save_data_to_file(GLOBAL_STATE)

            send_tg(
                f"⚡ *BTC SHORT SIGNAL (5M)*\n\n"
                f"📍 *Entry:* `${entry:.1f}`\n"
                f"🛡️ *SL:* `${sl:.1f}` (-${risk:.1f})\n"
                f"🎯 *TP 1:* `${tp1:.1f}` (+90 pts Auto BE)\n"
                f"🩸 *TP 2:* `${tp2:.1f}` (+${reward:.1f})\n\n"
                f"🌊 *Setup:* Institutional Swing Short"
            )

# Persistent daemon starter
if "engine_worker_running" not in st.session_state:
    st.session_state["engine_worker_running"] = True
    active_thread = None
    for th in threading.enumerate():
        if th.name == "SolidTelegramWorker" and th.is_alive():
            active_thread = th
            break
    if not active_thread:
        eng = InstitutionalMasterEngine()
        t = threading.Thread(target=eng.run_forever, name="SolidTelegramWorker", daemon=True)
        t.start()
        # Test notification to confirm connection is active
        send_tg("✅ *BTC RADAR ENGINE LIVE*\nListening to real-time 5M Binance order flow...")

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

current_data = load_saved_data()
history_str = json.dumps(current_data["history"])
stats_str = json.dumps({
    "total": current_data["total_signals"],
    "tp": current_data["tp_count"],
    "sl": current_data["sl_count"],
    "win_rate": current_data["win_rate"]
})
trade_str = json.dumps(current_data.get("active_trade"))

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
        .badge-scan { background: #161f30; color: #38bdf8; font-size: 8px; padding: 1px 4px; border-radius: 3px; font-weight: 700; }
        .stat-card { display: flex; flex-direction: column; min-width: 45px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 700; }
        .stat-val { font-size: 9px; font-weight: 700; color: #fff; }
        
        .btn-history {
            background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40;
            border-radius: 4px; padding: 2px 6px; font-size: 8px; font-weight: 700; cursor: pointer;
        }

        .workspace { 
            display: flex; 
            flex-direction: column; 
            width: 100vw; 
            height: calc(100vh - 38px); 
        }
        
        /* CHART TAKES ENTIRE AVAILABLE HEIGHT */
        #chart-zone { 
            width: 100vw; 
            flex: 1; 
            background: #080a0f; 
        }

        /* EXACT POSITIONING MATCHING THE SCREENSHOT RED LINE */
        .bottom-bar {
            width: 100vw;
            height: 48px;
            background: #0d121c;
            border-top: 1px solid #1a2336;
            padding: 4px 8px;
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
            padding: 3px 6px;
            border-radius: 4px;
            border: 1px solid #192233;
            height: 38px;
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
            font-size: 10.5px;
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
            width: 90vw; max-width: 400px; max-height: 80vh; display: flex; flex-direction: column;
            padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }
        .history-list { overflow-y: auto; max-height: 250px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #151d2b; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ SNIPER 5M <span class="badge-scan">SCANNING</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">BIG TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 HISTORY</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 8px;">
            <b id="live-price" style="color: #f0b90b; font-size: 11px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">TREND</span>
                <div class="cell-body" id="val-trend" style="color:#00e676;">BULLISH ▲</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">RSI (14)</span>
                <div class="cell-body" id="val-rsi">52.0</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">ATR VOL</span>
                <div class="cell-body" id="val-atr" style="color:#f0b90b;">$62.0</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">ACTIVE SETUP</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">RADAR ACTIVE</div>
            </div>
        </div>
    </div>

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
            document.getElementById('val-setup').innerText = activeTrade.type + " ACTIVE";
            document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
        } else {
            document.getElementById('disp-entry').innerText = "--";
            document.getElementById('disp-sl').innerText = "--";
            document.getElementById('disp-tp').innerText = "--";
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

        const IST_OFFSET = 5.5 * 3600;

        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {
            width: chartZone.clientWidth, height: chartZone.clientHeight,
            layout: { background: { color: '#080a0f' }, textColor: '#787b86' },
            grid: { vertLines: { color: '#111622' }, horzLines: { color: '#111622' } },
            rightPriceScale: { borderColor: '#192130' },
            timeScale: { 
                borderColor: '#192130', 
                timeVisible: true, 
                secondsVisible: false
            },
            localization: {
                timeFormatter: businessDayOrTimestamp => {
                    const d = new Date((businessDayOrTimestamp + IST_OFFSET) * 1000);
                    return d.toUTCString().match(/\\d{2}:\\d{2}/)[0];
                }
            }
        });

        const series = chart.addCandlestickSeries({
            upColor: '#00E676', downColor: '#FF3B30',
            borderUpColor: '#00E676', borderDownColor: '#FF3B30',
            wickUpColor: '#00E676', wickDownColor: '#FF3B30'
        });

        let candles = [];
        let ws = null;
        let lastWsPing = Date.now();

        function updateFrontendMetrics() {
            if (candles.length < 15) return;
            const closes = candles.map(c => c.close);
            
            let gains = 0, losses = 0;
            for (let i = closes.length - 14; i < closes.length; i++) {
                let diff = closes[i] - closes[i - 1];
                if (diff >= 0) gains += diff;
                else losses -= diff;
            }
            let rs = losses === 0 ? 100 : gains / losses;
            let rsi = (100 - (100 / (1 + rs))).toFixed(1);
            document.getElementById('val-rsi').innerText = rsi;

            let trSum = 0;
            for (let i = candles.length - 14; i < candles.length; i++) {
                let c = candles[i], p = candles[i - 1];
                trSum += Math.max(c.high - c.low, Math.abs(c.high - p.close), Math.abs(c.low - p.close));
            }
            let atr = (trSum / 14).toFixed(1);
            document.getElementById('val-atr').innerText = "$" + atr;

            let lastC = candles[candles.length - 1].close;
            let firstC = candles[candles.length - 8].close;
            let isBull = lastC >= firstC;
            document.getElementById('val-trend').innerText = isBull ? "BULLISH ▲" : "BEARISH ▼";
            document.getElementById('val-trend').style.color = isBull ? "#00e676" : "#ff3b30";

            if (!activeTrade) {
                let lastRange = candles[candles.length - 1].high - candles[candles.length - 1].low;
                let avgRange = trSum / 14;
                if (lastRange > avgRange * 1.15) {
                    document.getElementById('val-setup').innerText = "HIGH MOMENTUM";
                    document.getElementById('val-setup').style.color = "#00e676";
                } else {
                    document.getElementById('val-setup').innerText = "RADAR ACTIVE";
                    document.getElementById('val-setup').style.color = "#38bdf8";
                }
            }
        }

        function syncData() {
            fetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=80')
                .then(r => r.json())
                .then(data => {
                    candles = data.map(d => ({
                        time: Math.floor(d[0] / 1000) + IST_OFFSET,
                        open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                    }));
                    series.setData(candles);
                    chart.timeScale().fitContent();
                    updateFrontendMetrics();
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
                    time: Math.floor(k.t / 1000) + IST_OFFSET, 
                    open: parseFloat(k.o), 
                    high: parseFloat(k.h), 
                    low: parseFloat(k.l), 
                    close: parseFloat(k.c) 
                };
                document.getElementById('live-price').innerText = "$" + c.close.toFixed(1);
                series.update(c);
                if (candles.length > 0) {
                    const last = candles[candles.length - 1];
                    if (last.time === c.time) candles[last] = c;
                    else if (c.time > last.time) candles.push(c);
                }
                updateFrontendMetrics();
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
