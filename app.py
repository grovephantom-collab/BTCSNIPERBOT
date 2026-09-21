import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests
import json
import os
from datetime import datetime

# ==============================================================================
# BTC SNIPER 5M - REAL-TIME ON-SCREEN ENTRY / SL / TP AUTO-RENDER ENGINE
# ==============================================================================

BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"
DATA_FILE = "trade_history.json"

def load_data():
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

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def send_tg(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(CHAT_ID).strip(),
        "text": msg
    }
    for _ in range(4):
        try:
            res = requests.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False

def get_cloud_klines():
    urls = [
        "https://api.binance.us/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=35",
        "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=35",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=35"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=2.5)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) >= 20:
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

class AccurateSwingEngine:
    def __init__(self):
        self.state = load_data()
        self.active_trade = self.state.get("active_trade", None)
        self.last_signal_time = 0

    def record_trade(self, trade_type, entry, result, pnl_pts):
        now_str = datetime.now().strftime("%H:%M")
        self.state["total_signals"] += 1
        if "TP" in result:
            self.state["tp_count"] += 1
        elif "SL" in result:
            self.state["sl_count"] += 1

        total = self.state["tp_count"] + self.state["sl_count"]
        if total > 0:
            self.state["win_rate"] = round((self.state["tp_count"] / total) * 100, 1)

        self.state["history"].insert(0, {
            "time": now_str, "type": trade_type, "entry": entry, "result": result, "pts": pnl_pts
        })
        if len(self.state["history"]) > 500:
            self.state["history"].pop()

        self.active_trade = None
        self.state["active_trade"] = None
        save_data(self.state)

    def run(self):
        while True:
            closed, live = get_cloud_klines()
            if closed and live:
                if self.active_trade:
                    self.manage_position(live)
                else:
                    self.detect_accurate_setup(closed, live)
            time.sleep(1.2)

    def manage_position(self, live):
        t = self.active_trade
        t['duration'] = t.get('duration', 0) + 1

        if t['type'] == 'LONG':
            if not t['tp1_hit'] and live['high'] >= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] + 15.0, 1)
                self.state["active_trade"] = t
                save_data(self.state)
                send_tg(f"🎯 BTC LONG TP1 HIT (+{t['tp1_pts']:.0f} pts) at ${t['tp1']:.1f}\nSL shifted to BE (${t['sl']:.1f}). Position is Risk-Free.")

            if live['high'] >= t['tp2']:
                send_tg(f"🚀 BTC LONG RUNNER REACHED (+${t['reward']:.1f}) at ${t['tp2']:.1f}!")
                self.record_trade("LONG", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['low'] <= t['sl']:
                res = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                send_tg(f"🛡️ BTC LONG {res} at ${t['sl']:.1f}")
                self.record_trade("LONG", t['entry'], res, pts)
                return

        elif t['type'] == 'SHORT':
            if not t['tp1_hit'] and live['low'] <= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = round(t['entry'] - 15.0, 1)
                self.state["active_trade"] = t
                save_data(self.state)
                send_tg(f"🎯 BTC SHORT TP1 HIT (+{t['tp1_pts']:.0f} pts) at ${t['tp1']:.1f}\nSL shifted to BE (${t['sl']:.1f}). Position is Risk-Free.")

            if live['low'] <= t['tp2']:
                send_tg(f"🩸 BTC SHORT RUNNER REACHED (+${t['reward']:.1f}) at ${t['tp2']:.1f}!")
                self.record_trade("SHORT", t['entry'], "TP RUNNER", f"+{t['reward']:.0f}")
                return
            elif live['high'] >= t['sl']:
                res = "BE LOCKED" if t['tp1_hit'] else "SL HIT"
                pts = "+15" if t['tp1_hit'] else f"-{t['risk']:.0f}"
                send_tg(f"🛡️ BTC SHORT {res} at ${t['sl']:.1f}")
                self.record_trade("SHORT", t['entry'], res, pts)
                return

    def detect_accurate_setup(self, closed, live):
        now = time.time()
        if now - self.last_signal_time < 120:
            return

        tr_list = []
        for i in range(len(closed) - 14, len(closed)):
            c, p = closed[i], closed[i-1]
            tr_list.append(max(c['high'] - c['low'], abs(c['high'] - p['close']), abs(c['low'] - p['close'])))
        atr = sum(tr_list) / len(tr_list)

        swing_high = max(c['high'] for c in closed[-6:])
        swing_low = min(c['low'] for c in closed[-6:])
        c0 = closed[-1]
        body = live['close'] - live['open']

        long_setup = (
            (live['close'] > swing_high or (live['close'] > c0['high'] and body >= atr * 0.35)) and
            (live['close'] > live['open']) and
            (body >= 20.0)
        )

        short_setup = (
            (live['close'] < swing_low or (live['close'] < c0['low'] and body <= -atr * 0.35)) and
            (live['close'] < live['open']) and
            (body <= -20.0)
        )

        if long_setup:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            sl_candidate = min(live['low'], swing_low) - (atr * 0.3)
            sl = round(sl_candidate, 1)
            risk = round(entry - sl, 1)

            if risk < 80.0: risk = 85.0; sl = round(entry - 85.0, 1)
            elif risk > 150.0: risk = 135.0; sl = round(entry - 135.0, 1)

            tp1_pts = round(risk * 1.0, 1)
            tp1 = round(entry + tp1_pts, 1)
            reward = round(risk * 2.2, 1)
            tp2 = round(entry + reward, 1)

            self.active_trade = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'tp1_pts': tp1_pts, 'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0,
                'timestamp': int(now)
            }
            self.state["active_trade"] = self.active_trade
            save_data(self.state)

            send_tg(
                f"⚡ HIGH ACCURACY BTC LONG (5M)\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🛡️ Structure SL: ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 TP 1: ${tp1:.1f} (+{tp1_pts:.0f} pts Auto BE)\n"
                f"🚀 TP 2: ${tp2:.1f} (+${reward:.1f} Runner)"
            )

        elif short_setup:
            self.last_signal_time = now
            entry = round(live['close'], 1)
            sl_candidate = max(live['high'], swing_high) + (atr * 0.3)
            sl = round(sl_candidate, 1)
            risk = round(sl - entry, 1)

            if risk < 80.0: risk = 85.0; sl = round(entry + 85.0, 1)
            elif risk > 150.0: risk = 135.0; sl = round(entry - 135.0, 1)

            tp1_pts = round(risk * 1.0, 1)
            tp1 = round(entry - tp1_pts, 1)
            reward = round(risk * 2.2, 1)
            tp2 = round(entry - reward, 1)

            self.active_trade = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'tp1_pts': tp1_pts, 'risk': risk, 'reward': reward, 'tp1_hit': False, 'duration': 0,
                'timestamp': int(now)
            }
            self.state["active_trade"] = self.active_trade
            save_data(self.state)

            send_tg(
                f"⚡ HIGH ACCURACY BTC SHORT (5M)\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🛡️ Structure SL: ${sl:.1f} (-${risk:.1f})\n"
                f"🎯 TP 1: ${tp1:.1f} (+{tp1_pts:.0f} pts Auto BE)\n"
                f"🩸 TP 2: ${tp2:.1f} (+${reward:.1f} Runner)"
            )

if "accurate_cloud_worker" not in st.session_state:
    st.session_state["accurate_cloud_worker"] = True
    found = False
    for th in threading.enumerate():
        if th.name == "AccurateSwingWorker":
            found = True
            break
    if not found:
        engine = AccurateSwingEngine()
        t = threading.Thread(target=engine.run, name="AccurateSwingWorker", daemon=True)
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
        
        .stat-card { display: flex; flex-direction: column; min-width: 50px; }
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
            height: 60vh; 
            background: #080a0f; 
        }

        .bottom-bar {
            width: 100vw;
            height: calc(40vh - 38px);
            max-height: 50px;
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
        .history-list { overflow-y: auto; max-height: 280px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ SNIPER 5M <span class="badge-scan">PRO RADAR</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">BIG TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 HISTORY (<span id="hist-count">0</span>)</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">TREND</span>
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
                <span class="cell-head">ACTIVE SETUP</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">STRUCTURE SCANNING</div>
            </div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:12px;">TRADE HISTORY & STATS</b>
                <div style="display:flex; gap:6px; align-items:center;">
                    <button onclick="clearHistoryData()" style="background:#ff3b30; border:none; color:#fff; font-size:9px; font-weight:800; padding:3px 8px; border-radius:3px; cursor:pointer;">CLEAR ALL</button>
                    <button onclick="toggleModal(false)" style="background:transparent; border:none; color:#888; font-size:16px; cursor:pointer; margin-left:4px;">✕</button>
                </div>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin-bottom:10px;">
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>Total Signals</span><b id="stat-total" style="color:#fff;">0</b>
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

        let candles = [];
        let lineEntry = null, lineSL = null, lineTP = null;
        let markersList = [];

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

        // 100% RELIABLE CHART LINES RENDERER
        function drawTradeLinesOnChart() {
            removeTradeLines();
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
                title: 'SL $' + activeTrade.sl.toFixed(1)
            });

            lineTP = series.createPriceLine({
                price: activeTrade.tp2,
                color: '#00e676',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'TP $' + activeTrade.tp2.toFixed(1)
            });
        }

        function removeTradeLines() {
            if (lineEntry) { try { series.removePriceLine(lineEntry); } catch(e){} lineEntry = null; }
            if (lineSL) { try { series.removePriceLine(lineSL); } catch(e){} lineSL = null; }
            if (lineTP) { try { series.removePriceLine(lineTP); } catch(e){} lineTP = null; }
        }

        function updateScreenDisplays() {
            document.getElementById('hist-count').innerText = historyData.length;
            document.getElementById('stat-total').innerText = stats.total;
            document.getElementById('stat-rate').innerText = stats.win_rate + "%";

            const histCont = document.getElementById('history-container');
            if (historyData.length > 0) {
                histCont.innerHTML = "";
                historyData.forEach(item => {
                    let resCol = item.result.includes("TP") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span>${item.time} <b style="color:${typeCol};">${item.type}</b> @ $${item.entry}</span>
                            <span><b style="color:${resCol};">${item.result}</b> (${item.pts} pts)</span>
                        </div>
                    `;
                });
            } else {
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>';
            }

            if (activeTrade) {
                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
                document.getElementById('disp-tp').innerText = "$" + activeTrade.tp2.toFixed(1);
                document.getElementById('val-setup').innerText = activeTrade.type + " RUNNING 🔥";
                document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = "STRUCTURE SCANNING";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }
        }

        // AUTO-DETECT SIGNALS FROM LIVE PRICE SPREAD
        function autoCheckActiveTrade(livePrice) {
            if (candles.length < 10) return;
            const c0 = candles[candles.length - 2];
            const c_live = candles[candles.length - 1];

            // Local real-time sync if state wasn't pushed
            if (!activeTrade) {
                let range = c_live.close - c_live.open;
                let prevHigh = c0.high;
                let prevLow = c0.low;

                if (c_live.close > prevHigh && range >= 22.0) {
                    let entry = c_live.close;
                    let sl = +(c_live.low - 20.0).toFixed(1);
                    let risk = +(entry - sl).toFixed(1);
                    if (risk < 80) { risk = 85; sl = +(entry - 85).toFixed(1); }
                    let tp2 = +(entry + (risk * 2.2)).toFixed(1);

                    activeTrade = { type: "LONG", entry: entry, sl: sl, tp2: tp2, tp1: entry + risk, tp1_hit: false };
                    drawTradeLinesOnChart();
                    updateScreenDisplays();
                } else if (c_live.close < prevLow && range <= -22.0) {
                    let entry = c_live.close;
                    let sl = +(c_live.high + 20.0).toFixed(1);
                    let risk = +(sl - entry).toFixed(1);
                    if (risk < 80) { risk = 85; sl = +(entry + 85).toFixed(1); }
                    let tp2 = +(entry - (risk * 2.2)).toFixed(1);

                    activeTrade = { type: "SHORT", entry: entry, sl: sl, tp2: tp2, tp1: entry - risk, tp1_hit: false };
                    drawTradeLinesOnChart();
                    updateScreenDisplays();
                }
            } else {
                // Check if current trade hit TP or SL
                if (activeTrade.type === "LONG") {
                    if (livePrice >= activeTrade.tp2 || livePrice <= activeTrade.sl) {
                        removeTradeLines();
                        activeTrade = null;
                        updateScreenDisplays();
                    }
                } else if (activeTrade.type === "SHORT") {
                    if (livePrice <= activeTrade.tp2 || livePrice >= activeTrade.sl) {
                        removeTradeLines();
                        activeTrade = null;
                        updateScreenDisplays();
                    }
                }
            }
        }

        function clearHistoryData() {
            historyData = [];
            stats = { total: 0, tp: 0, sl: 0, win_rate: 0 };
            activeTrade = null;
            removeTradeLines();
            updateScreenDisplays();
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

            let isBull = candles[candles.length - 1].close >= candles[candles.length - 8].close;
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
                    drawTradeLinesOnChart();
                    updateScreenDisplays();
                    updateMetricsUI();
                    connectLiveStream();
                }).catch(e => setTimeout(syncCandles, 2000));
        }
        syncCandles();

        function updateLiveCandle(price, rawTimeSec) {
            if (candles.length === 0) return;
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
            autoCheckActiveTrade(price);
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

        updateScreenDisplays();
        window.onresize = () => chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
    </script>
</body>
</html>""".replace("__STATS_PLACEHOLDER__", stats_str).replace("__HISTORY_PLACEHOLDER__", history_str).replace("__TRADE_PLACEHOLDER__", trade_str)

components.html(terminal_html, height=720, scrolling=False)
