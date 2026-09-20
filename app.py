import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests
import json
import os
from datetime import datetime

# ==============================================================================
# BTC SNIPER 5M - 100% LIVE TICKING CHART + COMPACT ELEVATED BOTTOM LAYOUT
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

def send_telegram_alert(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(CHAT_ID).strip(),
        "text": msg
    }
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=4)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False

def trigger_tg(text):
    threading.Thread(target=send_telegram_alert, args=(text,), daemon=True).start()

class InstantBreakoutEngine:
    def __init__(self):
        self.active_trade = GLOBAL_STATE.get("active_trade", None)
        self.last_signal_time = 0

    def record_history(self, trade_type, entry, result, pnl_pts):
        now_str = datetime.now().strftime("%H:%M")
        GLOBAL_STATE["total_signals"] += 1
        if "TP" in result:
            GLOBAL_STATE["tp_count"] += 1
        elif "SL" in result:
            GLOBAL_STATE["sl_count"] += 1

        total = GLOBAL_STATE["tp_count"] + GLOBAL_STATE["sl_count"]
        if total > 0:
            GLOBAL_STATE["win_rate"] = round((GLOBAL_STATE["tp_count"] / total) * 100, 1)

        GLOBAL_STATE["history"].insert(0, {
            "time": now_str, "type": trade_type, "entry": entry, "result": result, "pts": pnl_pts
        })
        if len(GLOBAL_STATE["history"]) > 40:
            GLOBAL_STATE["history"].pop()

        self.active_trade = None
        GLOBAL_STATE["active_trade"] = None
        save_data_to_file(GLOBAL_STATE)

    def run_forever(self):
        while True:
            try:
                r = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=25", timeout=3)
                if r.status_code == 200:
                    raw = r.json()
                    if isinstance(raw, list) and len(raw) >= 10:
                        closed_candles = [{
                            'open': float(d[1]), 'high': float(d[2]),
                            'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])
                        } for d in raw[:-1]]

                        cur = raw[-1]
                        live = {
                            'open': float(cur[1]), 'high': float(cur[2]),
                            'low': float(cur[3]), 'close': float(cur[4]), 'vol': float(cur[5])
                        }

                        if self.active_trade:
                            self.manage_position(live)
                        else:
                            self.scan_breakout(closed_candles, live)
            except Exception:
                pass
            time.sleep(1.5)

    def manage_position(self, live):
        t = self.active_trade
        t['duration'] = t.get('duration', 0) + 1

        if t['type'] == 'LONG':
            if not t['tp1_hit'] and live['high'] >= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] + 15.0, 1)
                GLOBAL_STATE["active_trade"] = t
                save_data_to_file(GLOBAL_STATE)
                trigger_tg(f"🎯 BTC LONG TP1 HIT (+90 pts) at ${t['tp1']:.1f}\nSL shifted to BE:${t['sl']:.1f}")

            if live['high'] >= t['tp2']:
                trigger_tg(f"🚀 BTC LONG RUNNER HIT (+${t['reward']:.1f}) at${t['tp2']:.1f}!")
                self.record_history("LONG", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['low'] <= t['sl']:
                res = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                trigger_tg(f"🛡️ BTC LONG {res} at ${t['sl']:.1f}")
                self.record_history("LONG", t['entry'], res, pts)
                return

        elif t['type'] == 'SHORT':
            if not t['tp1_hit'] and live['low'] <= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] - 15.0, 1)
                GLOBAL_STATE["active_trade"] = t
                save_data_to_file(GLOBAL_STATE)
                trigger_tg(f"🎯 BTC SHORT TP1 HIT (+90 pts) at ${t['tp1']:.1f}\nSL shifted to BE:${t['sl']:.1f}")

            if live['low'] <= t['tp2']:
                trigger_tg(f"🩸 BTC SHORT RUNNER HIT (+${t['reward']:.1f}) at${t['tp2']:.1f}!")
                self.record_history("SHORT", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['high'] >= t['sl']:
                res = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                trigger_tg(f"🛡️ BTC SHORT {res} at ${t['sl']:.1f}")
                self.record_history("SHORT", t['entry'], res, pts)
                return

    def scan_breakout(self, closed_candles, live):
        now = time.time()
        if now - self.last_signal_time < 60:
            return

        c_last = closed_candles[-1]
        high_3 = max(c['high'] for c in closed_candles[-4:])
        low_3 = min(c['low'] for c in closed_candles[-4:])

        long_breakout = (live['close'] > high_3 and live['close'] > live['open'] + 10)
        short_breakout = (live['close'] < low_3 and live['close'] < live['open'] - 10)

        if long_breakout:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            sl = round(min(live['low'], c_last['low']) - 15.0, 1)
            risk = round(entry - sl, 1)
            if risk < 60.0: risk = 70.0; sl = round(entry - 70.0, 1)
            if risk > 130.0: risk = 120.0; sl = round(entry - 120.0, 1)

            tp1 = round(entry + 90.0, 1)
            reward = round(risk * 2.2, 1)
            tp2 = round(entry + reward, 1)

            self.active_trade = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0
            }
            GLOBAL_STATE["active_trade"] = self.active_trade
            save_data_to_file(GLOBAL_STATE)

            trigger_tg(
                f"⚡ BTC LONG SIGNAL (5M BREAKOUT)\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🛡️ SL: ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 TP 1: ${tp1:.1f} (+90 pts Auto BE)\n"
                f"🚀 TP 2: ${tp2:.1f} (+${reward:.1f})\n\n"
                f"Status: High Momentum Impulse"
            )

        elif short_breakout:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            sl = round(max(live['high'], c_last['high']) + 15.0, 1)
            risk = round(sl - entry, 1)
            if risk < 60.0: risk = 70.0; sl = round(entry + 70.0, 1)
            if risk > 130.0: risk = 120.0; sl = round(entry - 120.0, 1)

            tp1 = round(entry - 90.0, 1)
            reward = round(risk * 2.2, 1)
            tp2 = round(entry - reward, 1)

            self.active_trade = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0
            }
            GLOBAL_STATE["active_trade"] = self.active_trade
            save_data_to_file(GLOBAL_STATE)

            trigger_tg(
                f"⚡ BTC SHORT SIGNAL (5M BREAKOUT)\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🛡️ SL: ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 TP 1: ${tp1:.1f} (+90 pts Auto BE)\n"
                f"🩸 TP 2: ${tp2:.1f} (+${reward:.1f})\n\n"
                f"Status: Bearish Impulse Breakdown"
            )

if "engine_worker_running" not in st.session_state:
    st.session_state["engine_worker_running"] = True
    active_thread = None
    for th in threading.enumerate():
        if th.name == "BTCBreakoutEngineWorker" and th.is_alive():
            active_thread = th
            break
    if not active_thread:
        engine = InstantBreakoutEngine()
        t = threading.Thread(target=engine.run_forever, name="BTCBreakoutEngineWorker", daemon=True)
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
        
        /* CHART THODA CHHOTA KIYA GAYA HAI TA-KI NICHE KA BAR UPAR RED LINE PAR AAYE */
        #chart-zone { 
            width: 100vw; 
            height: 60vh; 
            background: #080a0f; 
        }

        /* EXACT POSITION LOCKED AT RED LINE LEVEL */
        .bottom-bar {
            width: 100vw;
            height: calc(40vh - 38px);
            max-height: 52px;
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
                }).catch(e => setTimeout(syncData, 2000));
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
                    if (last.time === c.time) candles[candles.length - 1] = c;
                    else if (c.time > last.time) candles.push(c);
                }
                updateFrontendMetrics();
            };
            ws.onclose = () => { setTimeout(connectWS, 1000); };
        }

        // Fast 1.5-second Realtime Poller (Never Freezes even if WS drops)
        setInterval(() => {
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
        }, 1500);

        window.onresize = () => {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        };
    </script>
</body>
</html>""".replace("__STATS_PLACEHOLDER__", stats_str).replace("__HISTORY_PLACEHOLDER__", history_str).replace("__TRADE_PLACEHOLDER__", trade_str)

components.html(terminal_html, height=720, scrolling=False)
