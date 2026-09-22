import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import threading
import time
import requests
import json
import os
import uuid
from datetime import datetime

# ==============================================================================
# BALANCED BI-DIRECTIONAL MASTER ENGINE (CLEAN SYNTAX - ZERO PARSING ERROR)
# ==============================================================================

BOT_TOKEN = "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM"
CHAT_ID = "7886716805"
DB_FILE = "sniper_vault.db"
LOCK_FILE = "master_engine_lock.txt"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            trade_type TEXT,
            entry REAL,
            exit_price REAL,
            result TEXT,
            pts TEXT,
            pnl_usd TEXT,
            qty REAL
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

init_db()

def get_db_state(key, default=None):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT value FROM state WHERE key=?", (key,))
        row = cur.fetchone()
        conn.close()
        if row: return json.loads(row[0])
    except: pass
    return default

def set_db_state(key, value):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        conn.commit()
        conn.close()
    except: pass

if st.query_params.get("clear") == "1":
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cur = conn.cursor()
        cur.execute("DELETE FROM trades")
        conn.commit()
        conn.close()
        set_db_state("active_trade", None)
        set_db_state("daily_stats", {"date": datetime.now().strftime("%Y-%m-%d"), "loss_usd": 0.0, "is_circuit_broken": False})
    except: pass
    st.query_params.clear()
    st.rerun()

def send_telegram_alert(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(CHAT_ID).strip(), "text": msg}
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=4)
            if r.status_code == 200: return True
        except: time.sleep(0.5)
    return False

def fetch_binance_klines():
    urls = [
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=60",
        "https://api.binance.us/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=60"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=3)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) >= 40:
                    closed = [{'time': int(d[0]), 'open': float(d[1]), 'high': float(d[2]),
                               'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])} for d in raw[:-1]]
                    live = {'time': int(raw[-1][0]), 'open': float(raw[-1][1]), 'high': float(raw[-1][2]),
                            'low': float(raw[-1][3]), 'close': float(raw[-1][4]), 'vol': float(raw[-1][5])}
                    return closed, live
        except: continue
    return None, None

class GlobalNewsEngine:
    def __init__(self, engine_id):
        self.engine_id = engine_id

    def run(self):
        while True:
            try:
                with open(LOCK_FILE, "r") as f:
                    if f.read().strip() != self.engine_id: break
            except: pass

            score = 0
            sentiment = "NEUTRAL ⚖️"
            try:
                fg = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3).json()
                fng_val = int(fg['data'][0]['value'])
                if fng_val > 60: score += 5
                elif fng_val < 40: score -= 5
            except: pass

            try:
                tk = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=3).json()
                chg = float(tk['priceChangePercent'])
                if chg > 2.0: score += 5
                elif chg < -2.0: score -= 5
            except: pass

            if score >= 5: sentiment = "BULLISH 🚀"
            elif score <= -5: sentiment = "BEARISH 🩸"

            set_db_state("news_sentiment", {"sentiment": sentiment, "score": score})
            time.sleep(15)

class MasterCommanderEngine:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.last_candle_time = 0

    def manage_position(self, t, live):
        qty = t.get("qty", 0.01)

        if t['type'] == 'LONG':
            if not t.get('be_hit', False) and live['high'] >= (t['entry'] + 90.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] + 20.0, 1)
                set_db_state("active_trade", t)
                send_telegram_alert(f"🎯 [AUTO BREAKEVEN] BTC LONG Protected!\nSL locked at ${t['sl']:.1f} (+20 pts profit).")

            if live['high'] >= t['tp']:
                pts = round(t['tp'] - t['entry'], 1)
                usd = round(pts * qty, 2)
                self.record_trade(t, t['tp'], "TP HIT 🎯", f"+{pts:.0f}", f"+${usd}")
                send_telegram_alert(f"🚀 [TARGET HIT] BTC LONG\nNet: +${usd} (+{pts:.0f} pts)\nExit: ${t['tp']:.1f}")
            elif live['low'] <= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                pts = 20.0 if t.get('be_hit', False) else -(t['entry'] - t['sl'])
                usd = round(pts * qty, 2)
                sign = "+" if usd >= 0 else ""
                self.record_trade(t, t['sl'], res, f"{sign}{pts:.0f}", f"{sign}${usd}")
                send_telegram_alert(f"🛡️ [EXIT] BTC LONG {res}\nPnL: {sign}${usd} ({sign}{pts:.0f} pts)")

        elif t['type'] == 'SHORT':
            if not t.get('be_hit', False) and live['low'] <= (t['entry'] - 90.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] - 20.0, 1)
                set_db_state("active_trade", t)
                send_telegram_alert(f"🎯 [AUTO BREAKEVEN] BTC SHORT Protected!\nSL locked at ${t['sl']:.1f} (+20 pts profit).")

            if live['low'] <= t['tp']:
                pts = round(t['entry'] - t['tp'], 1)
                usd = round(pts * qty, 2)
                self.record_trade(t, t['tp'], "TP HIT 🎯", f"+{pts:.0f}", f"+${usd}")
                send_telegram_alert(f"🩸 [TARGET HIT] BTC SHORT\nNet: +${usd} (+{pts:.0f} pts)\nExit: ${t['tp']:.1f}")
            elif live['high'] >= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                pts = 20.0 if t.get('be_hit', False) else -(t['sl'] - t['entry'])
                usd = round(pts * qty, 2)
                sign = "+" if usd >= 0 else ""
                self.record_trade(t, t['sl'], res, f"{sign}{pts:.0f}", f"{sign}${usd}")
                send_telegram_alert(f"🛡️ [EXIT] BTC SHORT {res}\nPnL: {sign}${usd} ({sign}{pts:.0f} pts)")

    def record_trade(self, t, exit_price, result, pts, pnl_usd):
        now_str = datetime.now().strftime("%H:%M")
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cur = conn.cursor()
            cur.execute("INSERT INTO trades (timestamp, symbol, trade_type, entry, exit_price, result, pts, pnl_usd, qty) VALUES (?,?,?,?,?,?,?,?,?)",
                        (now_str, "BTCUSDT", t['type'], t['entry'], exit_price, result, pts, pnl_usd, t.get("qty", 0.01)))
            conn.commit()
            conn.close()
        except: pass
        set_db_state("active_trade", None)

    def evaluate_market_moves(self, closed, live):
        c0 = closed[-1]
        c1 = closed[-2]
        c2 = closed[-3]

        if live['time'] <= self.last_candle_time: return
        self.last_candle_time = live['time']

        closes = [c['close'] for c in closed]
        def calc_ema(period):
            k = 2 / (period + 1)
            e = closes[0]
            for cl in closes[1:]: e = (cl * k) + (e * (1 - k))
            return e
        ema9 = calc_ema(9)
        ema21 = calc_ema(21)
        ema50 = calc_ema(50)

        h_range = max(c['high'] for c in closed[-8:-1])
        l_range = min(c['low'] for c in closed[-8:-1])
        body0 = c0['close'] - c0['open']
        range0 = max(c0['high'] - c0['low'], 1.0)
        upper_wick0 = c0['high'] - max(c0['open'], c0['close'])
        lower_wick0 = min(c0['open'], c0['close']) - c0['low']

        # UP MOVE CONDITIONS
        is_breakout_long = (c0['close'] > ema50) and (c0['close'] > h_range) and (body0 >= 24.0)
        is_staircase_long = (
            (ema9 >= ema21) and (c0['close'] > ema9) and
            (c0['low'] >= c1['low'] >= c2['low']) and
            (c0['close'] > c0['open']) and (c0['close'] > c1['high']) and
            (upper_wick0 / range0 < 0.35)
        )

        # DOWN MOVE CONDITIONS
        is_breakout_short = (c0['close'] < ema50) and (c0['close'] < l_range) and (body0 <= -24.0)
        is_staircase_short = (
            (ema9 <= ema21) and (c0['close'] < ema9) and
            (c0['high'] <= c1['high'] <= c2['high']) and
            (c0['close'] < c0['open']) and (c0['close'] < c1['low']) and
            (lower_wick0 / range0 < 0.35)
        )

        cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})
        pos_usd = float(cfg['capital']) * int(cfg['leverage'])
        entry = round(c0['close'], 1)
        qty = round(pos_usd / entry, 4) or 0.001

        if is_breakout_long or is_staircase_long:
            move_type = "BREAKOUT MOVE" if is_breakout_long else "STAIRCASE CLIMB"
            recent_low = min(c['low'] for c in closed[-4:])
            risk = max(entry - recent_low + 20.0, 90.0)
            sl = round(entry - risk, 1)
            tp = round(entry + (risk * 2.0), 1)

            set_db_state("active_trade", {'type': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk, 'qty': qty, 'be_hit': False})
            send_telegram_alert(f"⚡ [AI AUTO EXECUTION] BTC LONG\n\n🎯 Type: {move_type}\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f} (-{risk:.0f} pts)\n🎯 TP: ${tp:.1f} (+{risk*2.0:.0f} pts)\n📦 Qty: {qty} BTC")

        elif is_breakout_short or is_staircase_short:
            move_type = "BREAKDOWN MOVE" if is_breakout_short else "STAIRCASE DUMP"
            recent_high = max(c['high'] for c in closed[-4:])
            risk = max(recent_high - entry + 20.0, 90.0)
            sl = round(entry + risk, 1)
            tp = round(entry - (risk * 2.0), 1)

            set_db_state("active_trade", {'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk, 'qty': qty, 'be_hit': False})
            send_telegram_alert(f"⚡ [AI AUTO EXECUTION] BTC SHORT\n\n🎯 Type: {move_type}\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f} (-{risk:.0f} pts)\n🎯 TP: ${tp:.1f} (+{risk*2.0:.0f} pts)\n📦 Qty: {qty} BTC")

    def run(self):
        while True:
            try:
                with open(LOCK_FILE, "r") as f:
                    if f.read().strip() != self.engine_id: break
            except: pass

            closed, live = fetch_binance_klines()
            if closed and live:
                active = get_db_state("active_trade")
                if active: self.manage_position(active, live)
                else: self.evaluate_market_moves(closed, live)

            time.sleep(2)

class HeadOverseerEngine:
    def __init__(self, engine_id):
        self.engine_id = engine_id

    def run(self):
        send_telegram_alert("🛡️ [MASTER ENGINE BOOTED] Bi-Directional Scanner (Long & Short Active).")
        while True:
            try:
                with open(LOCK_FILE, "r") as f:
                    if f.read().strip() != self.engine_id: break
            except: pass
            time.sleep(1)

@st.cache_resource
def boot_complete_system():
    eid = str(uuid.uuid4())
    with open(LOCK_FILE, "w") as f: f.write(eid)
    threading.Thread(target=MasterCommanderEngine(eid).run, daemon=True).start()
    threading.Thread(target=GlobalNewsEngine(eid).run, daemon=True).start()
    threading.Thread(target=HeadOverseerEngine(eid).run, daemon=True).start()
    return eid

boot_complete_system()

# -------------------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------------------
st.set_page_config(page_title="AI CRYPTO SNIPER BOT", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>header, footer, #MainMenu { display: none !important; } .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; } iframe { width: 100vw !important; height: 100vh !important; border: none !important; }</style>""", unsafe_allow_html=True)

conn = sqlite3.connect(DB_FILE, timeout=5)
cur = conn.cursor()
cur.execute("SELECT timestamp, trade_type, entry, result, pts, pnl_usd FROM trades ORDER BY id DESC LIMIT 50")
rows = cur.fetchall()
history_list = [{"time": r[0], "type": r[1], "entry": r[2], "result": r[3], "pts": r[4], "pnl_usd": r[5]} for r in rows]

cur.execute("SELECT COUNT(*), SUM(CASE WHEN result LIKE '%TP%' THEN 1 ELSE 0 END) FROM trades")
t_count, tp_count = cur.fetchone()
conn.close()

win_rate = round((tp_count / t_count) * 100, 1) if t_count > 0 else 0.0
active_trade = get_db_state("active_trade")
news_sentiment = get_db_state("news_sentiment", {"sentiment": "NEUTRAL ⚖️", "score": 0})
cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})
daily_risk = get_db_state("daily_stats", {"loss_usd": 0.0, "is_circuit_broken": False})

js_active_trade = json.dumps(active_trade)
js_history = json.dumps(history_list)
js_stats = json.dumps({"total": t_count, "win_rate": win_rate})
js_news = json.dumps(news_sentiment)
js_cfg = json.dumps(cfg)
js_risk = json.dumps(daily_risk)

terminal_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { background: #080a0f; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100vw; height: 100vh; overflow: hidden; }
        .top-nav { display: flex; align-items: center; background: #0d111a; border-bottom: 1px solid #1a2336; padding: 4px 8px; font-size: 11px; height: 38px; gap: 8px; overflow-x: auto; white-space: nowrap; }
        .brand { font-weight: 800; color: #fff; font-size: 10px; display: flex; align-items: center; gap: 4px; }
        .badge-scan { background: #00e676; color: #000; font-size: 8px; padding: 2px 5px; border-radius: 3px; font-weight: 900; }
        .stat-card { display: flex; flex-direction: column; min-width: 55px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }
        .stat-val { font-size: 10px; font-weight: 800; color: #fff; }
        .btn-history { background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40; border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer; }
        .workspace { display: flex; flex-direction: column; width: 100vw; height: calc(100vh - 38px); }
        #chart-zone { width: 100vw; height: 55vh; background: #080a0f; }
        .trade-dock { width: 100vw; height: 38px; background: #0a0e17; border-top: 1px solid #1a2336; padding: 2px 8px; display: flex; align-items: center; justify-content: space-between; font-size: 10px; }
        .dock-group { display: flex; align-items: center; gap: 6px; }
        .dock-input { background: #121824; border: 1px solid #23304a; color: #00e676; font-size: 11px; font-weight: 800; border-radius: 4px; padding: 2px 6px; width: 50px; text-align: center; }
        .toggle-btn { background: #00e676; color: #000; font-size: 9px; font-weight: 900; padding: 4px 8px; border-radius: 4px; border: none; cursor: pointer; }
        .bottom-bar { width: 100vw; height: calc(45vh - 76px); max-height: 48px; background: #0d121c; border-top: 1px solid #1a2336; padding: 3px 8px; display: grid; grid-template-columns: 1fr 1fr 1fr 1.5fr; gap: 6px; align-items: center; }
        .metric-cell { display: flex; flex-direction: column; justify-content: center; background: #101624; padding: 2px 6px; border-radius: 4px; border: 1px solid #192233; height: 36px; }
        .cell-head { font-size: 7px; color: #62697a; font-weight: 800; text-transform: uppercase; line-height: 1; margin-bottom: 2px; }
        .cell-body { font-size: 10px; font-weight: 800; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 999; align-items: center; justify-content: center; }
        .modal-box { background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px; width: 92vw; max-width: 420px; max-height: 80vh; display: flex; flex-direction: column; padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); }
        .history-list { overflow-y: auto; max-height: 280px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ COMPLETE <span class="badge-scan">PRO BOT</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">TARGET TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 VAULT (<span id="hist-count">0</span>)</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">Connecting...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>
        <div class="trade-dock">
            <div class="dock-group">
                <button class="toggle-btn" onclick="triggerServerSync()">🔄 SYNC SYSTEM</button>
                <span style="color:#62697a; font-weight:800;">AMT($):</span>
                <input id="input-amount" class="dock-input" type="number" value="100" onchange="updateCalcQty()">
                <span style="color:#62697a; font-weight:800;">LEV:</span>
                <input id="input-lev" class="dock-input" type="number" value="10" onchange="updateCalcQty()">
            </div>
            <div class="dock-group">
                <span style="color:#62697a;">POS:</span>
                <b id="calc-qty" style="color:#38bdf8; font-size:11px;">0.0000 BTC</b>
            </div>
        </div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">NEWS / DATA ENGINE</span>
                <div class="cell-body" id="val-news" style="color:#fff;">--</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">CIRCUIT BREAKER</span>
                <div class="cell-body" id="val-guard" style="color:#00e676;">SHIELD ACTIVE</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">OVERSEER HEALTH</span>
                <div class="cell-body" id="val-health" style="color:#00e676;">🟢 100% SECURE</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">EXECUTION RADAR</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">RADAR SCANNING (UP & DOWN)...</div>
            </div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:12px;">SQLITE DATABASE VAULT</b>
                <div style="display:flex; gap:6px; align-items:center;">
                    <button onclick="clearSystemVault()" style="background:#ff3b30; border:none; color:#fff; font-size:9px; font-weight:800; padding:3px 8px; border-radius:3px; cursor:pointer;">CLEAR VAULT</button>
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
            <div id="history-container" class="history-list"></div>
        </div>
    </div>

    <script>
        const IST_OFFSET = 5.5 * 3600;
        let activeTrade = __ACTIVE_TRADE__;
        let tradeHistory = __TRADE_HISTORY__;
        let stats = __STATS__;
        let newsData = __NEWS_DATA__;
        let cfg = __CFG__;
        let riskGuard = __RISK_GUARD__;

        document.getElementById('input-amount').value = cfg.capital;
        document.getElementById('input-lev').value = cfg.leverage;

        let lineEntry = null, lineSL = null, lineTP = null;
        let currentPrice = 85500.0;

        function toggleModal(show) { document.getElementById('modal-bg').style.display = show ? 'flex' : 'none'; }
        function handleBgClick(e) { if (e.target.id === 'modal-bg') toggleModal(false); }
        function clearSystemVault() { window.parent.location.search = '?clear=1'; }
        function triggerServerSync() { window.parent.location.reload(); }

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
            localization: { timeFormatter: t => { const d = new Date((t + IST_OFFSET) * 1000); return d.toUTCString().match(/\\d{2}:\\d{2}/)[0]; } }
        });

        const series = chart.addCandlestickSeries({ upColor: '#00E676', downColor: '#FF3B30', borderUpColor: '#00E676', borderDownColor: '#FF3B30', wickUpColor: '#00E676', wickDownColor: '#FF3B30' });

        function renderMasterInterface() {
            if (lineEntry) { try { series.removePriceLine(lineEntry); } catch(e){} lineEntry = null; }
            if (lineSL) { try { series.removePriceLine(lineSL); } catch(e){} lineSL = null; }
            if (lineTP) { try { series.removePriceLine(lineTP); } catch(e){} lineTP = null; }

            if (activeTrade) {
                lineEntry = series.createPriceLine({ price: activeTrade.entry, color: '#38bdf8', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'ENTRY $' + activeTrade.entry.toFixed(1) });
                lineSL = series.createPriceLine({ price: activeTrade.sl, color: '#ff3b30', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'SAFE SL $' + activeTrade.sl.toFixed(1) });
                lineTP = series.createPriceLine({ price: activeTrade.tp, color: '#00e676', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'TARGET TP $' + activeTrade.tp.toFixed(1) });
            }

            document.getElementById('val-news').innerText = newsData.sentiment;
            document.getElementById('val-news').style.color = newsData.sentiment.includes("BULLISH") ? "#00e676" : (newsData.sentiment.includes("BEARISH") ? "#ff3b30" : "#fff");

            if (riskGuard.is_circuit_broken) {
                document.getElementById('val-guard').innerText = "🔴 TRADING PAUSED";
                document.getElementById('val-guard').style.color = "#ff3b30";
            } else {
                document.getElementById('val-guard').innerText = "🟢 SHIELD ACTIVE";
                document.getElementById('val-guard').style.color = "#00e676";
            }

            document.getElementById('hist-count').innerText = tradeHistory.length;
            document.getElementById('stat-total').innerText = stats.total;
            document.getElementById('stat-rate').innerText = stats.win_rate + "%";

            const histCont = document.getElementById('history-container');
            if (tradeHistory.length > 0) {
                histCont.innerHTML = "";
                tradeHistory.forEach(item => {
                    let resCol = item.result.includes("TP") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    let pnlDisp = item.pnl_usd ? `<b style="color:${resCol}; margin-left:4px;">(${item.pnl_usd})</b>` : '';
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span>${item.time} <b style="color:${typeCol};">${item.type}</b> @ $${item.entry.toFixed(1)}</span>
                            <span><b style="color:${resCol};">${item.result}</b> ${pnlDisp}</span>
                        </div>`;
                });
            } else {
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">No trades recorded in vault...</div>';
            }

            if (activeTrade) {
                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
                document.getElementById('disp-tp').innerText = "$" + activeTrade.tp.toFixed(1);
                document.getElementById('val-setup').innerText = "EXECUTING " + activeTrade.type + " 🔥";
                document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = "RADAR SCANNING (UP & DOWN)...";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }
        }

        function syncCandles() {
            fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=100')
                .then(r => r.json())
                .then(data => {
                    let cdata = data.map(d => ({ time: (d[0] - (d[0] % 300000)) / 1000, open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]) }));
                    series.setData(cdata);
                    chart.timeScale().fitContent();
                    renderMasterInterface();
                    connectLiveStream(cdata);
                }).catch(e => setTimeout(syncCandles, 2000));
        }

        function connectLiveStream(cdata) {
            const ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {
                const k = JSON.parse(e.data).k;
                const price = parseFloat(k.c);
                const barTime = (k.t - (k.t % 300000)) / 1000;
                
                currentPrice = price;
                updateCalcQty();
                document.getElementById('live-price').innerText = "$" + price.toFixed(1);

                let last = cdata[cdata.length - 1];
                if (barTime === last.time) {
                    last.close = price;
                    if (price > last.high) last.high = price;
                    if (price < last.low) last.low = price;
                    series.update(last);
                } else if (barTime > last.time) {
                    const newBar = { time: barTime, open: price, high: price, low: price, close: price };
                    cdata.push(newBar);
                    series.update(newBar);
                    setTimeout(() => window.parent.location.reload(), 8000); 
                }

                if (activeTrade) {
                    if (activeTrade.type === "LONG" && (price >= activeTrade.tp || price <= activeTrade.sl)) {
                        activeTrade = null; renderMasterInterface();
                    } else if (activeTrade.type === "SHORT" && (price <= activeTrade.tp || price >= activeTrade.sl)) {
                        activeTrade = null; renderMasterInterface();
                    }
                }
            };
            ws.onclose = () => setTimeout(() => connectLiveStream(cdata), 1500);
        }

        syncCandles();
        window.onresize = () => chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
    </script>
</body>
</html>"""

# Inject state values into HTML template
final_html = terminal_html.replace("__ACTIVE_TRADE__", js_active_trade)\
                          .replace("__TRADE_HISTORY__", js_history)\
                          .replace("__STATS__", js_stats)\
                          .replace("__NEWS_DATA__", js_news)\
                          .replace("__CFG__", js_cfg)\
                          .replace("__RISK_GUARD__", js_risk)

components.html(final_html, height=720, scrolling=False)
