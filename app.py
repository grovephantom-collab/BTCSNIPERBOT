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
# PRO QUANT ENGINE: DUAL TP (TP1/TP2) + VOLUME FILTER + SAFE VAULT + LIVE SYNC
# ==============================================================================

BOT_TOKEN = "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM"
CHAT_ID = "7886716805"
DB_FILE = "sniper_vault.db"
LOCK_FILE = "engine_process.pid"

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

# Direct Query Clear Handler (Triggered only from inside Vault modal)
if st.query_params.get("clear_vault") == "confirmed":
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cur = conn.cursor()
        cur.execute("DELETE FROM trades")
        conn.commit()
        conn.close()
        set_db_state("active_trade", None)
    except: pass
    st.query_params.clear()
    st.rerun()

def get_db_state(key, default=None):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT value FROM state WHERE key=?", (key,))
        row = cur.fetchone()
        conn.close()
        if row and row[0]: return json.loads(row[0])
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

def send_telegram_alert(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(CHAT_ID).strip(), "text": msg}
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200: return True
        except: time.sleep(0.5)
    return False

def fetch_binance_klines():
    urls = [
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=70",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=70",
        "https://api.binance.us/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=70"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=4)
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

class MasterCommanderEngine:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.last_candle_checked = 0

    def manage_position(self, t, live):
        qty = t.get("qty", 0.01)
        curr_price = live['close']

        # ==================== LONG POSITION ====================
        if t['type'] == 'LONG':
            # 1. TP1 Trigger (+110 pts) -> 50% Profit Book + BE Lock
            if not t.get('tp1_hit', False) and curr_price >= t['tp1']:
                t['tp1_hit'] = True
                t['be_hit'] = True
                t['sl'] = round(t['entry'] + 10.0, 1) # Shift SL to +10 cost
                half_usd = round(110.0 * (qty * 0.5), 2)
                t['realized_pnl'] = t.get('realized_pnl', 0.0) + half_usd
                set_db_state("active_trade", t)
                send_telegram_alert(f"🎯 [TP1 HIT] BTC LONG\nPrice: ${curr_price:.1f}\nBooked 50%: +${half_usd:.2f} (+110 pts)\n🛡️ SL Shifted to Breakeven: ${t['sl']:.1f}")

            # 2. TP2 Trigger (+220 pts) -> Full Final Exit
            elif curr_price >= t['tp2']:
                rem_usd = round((t['tp2'] - t['entry']) * (qty * 0.5), 2)
                total_usd = round(t.get('realized_pnl', 0.0) + rem_usd, 2)
                pts = round(t['tp2'] - t['entry'], 1)
                self.record_trade(t, t['tp2'], "TP2 HIT 🎯🔥", f"+{pts:.0f}", f"+${total_usd:.2f}")
                send_telegram_alert(f"🚀 [TP2 FULL HIT] BTC LONG Completed!\nFinal PnL: +${total_usd:.2f} (+{pts:.0f} pts)\nExit: ${t['tp2']:.1f}")

            # 3. Stop Loss / Breakeven Hit
            elif curr_price <= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                if t.get('tp1_hit', False):
                    # TP1 already booked, remaining hit at +10 pts
                    final_usd = round(t.get('realized_pnl', 0.0) + (10.0 * (qty * 0.5)), 2)
                    pts_str = "+60 pts net"
                    res = "TP1 + BE SECURE"
                else:
                    final_usd = round(-(t['entry'] - t['sl']) * qty, 2)
                    pts_str = f"-{t['entry'] - t['sl']:.0f}"

                sign = "+" if final_usd >= 0 else ""
                self.record_trade(t, t['sl'], res, pts_str, f"{sign}${final_usd:.2f}")
                send_telegram_alert(f"🛡️ [EXIT] BTC LONG {res}\nNet PnL: {sign}${final_usd:.2f} ({pts_str})\nExit: ${curr_price:.1f}")

        # ==================== SHORT POSITION ====================
        elif t['type'] == 'SHORT':
            # 1. TP1 Trigger (+110 pts Drop) -> 50% Profit Book + BE Lock
            if not t.get('tp1_hit', False) and curr_price <= t['tp1']:
                t['tp1_hit'] = True
                t['be_hit'] = True
                t['sl'] = round(t['entry'] - 10.0, 1) # Shift SL to -10 cost
                half_usd = round(110.0 * (qty * 0.5), 2)
                t['realized_pnl'] = t.get('realized_pnl', 0.0) + half_usd
                set_db_state("active_trade", t)
                send_telegram_alert(f"🎯 [TP1 HIT] BTC SHORT\nPrice: ${curr_price:.1f}\nBooked 50%: +${half_usd:.2f} (+110 pts)\n🛡️ SL Shifted to Breakeven: ${t['sl']:.1f}")

            # 2. TP2 Trigger (+220 pts Drop) -> Full Final Exit
            elif curr_price <= t['tp2']:
                rem_usd = round((t['entry'] - t['tp2']) * (qty * 0.5), 2)
                total_usd = round(t.get('realized_pnl', 0.0) + rem_usd, 2)
                pts = round(t['entry'] - t['tp2'], 1)
                self.record_trade(t, t['tp2'], "TP2 HIT 🎯🩸", f"+{pts:.0f}", f"+${total_usd:.2f}")
                send_telegram_alert(f"🩸 [TP2 FULL HIT] BTC SHORT Completed!\nFinal PnL: +${total_usd:.2f} (+{pts:.0f} pts)\nExit: ${t['tp2']:.1f}")

            # 3. Stop Loss / Breakeven Hit
            elif curr_price >= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                if t.get('tp1_hit', False):
                    final_usd = round(t.get('realized_pnl', 0.0) + (10.0 * (qty * 0.5)), 2)
                    pts_str = "+60 pts net"
                    res = "TP1 + BE SECURE"
                else:
                    final_usd = round(-(t['sl'] - t['entry']) * qty, 2)
                    pts_str = f"-{t['sl'] - t['entry']:.0f}"

                sign = "+" if final_usd >= 0 else ""
                self.record_trade(t, t['sl'], res, pts_str, f"{sign}${final_usd:.2f}")
                send_telegram_alert(f"🛡️ [EXIT] BTC SHORT {res}\nNet PnL: {sign}${final_usd:.2f} ({pts_str})\nExit: ${curr_price:.1f}")

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

        # Candle Close Check (Har 5m candle close par sirf 1 baar scan hoga)
        if c0['time'] <= self.last_candle_checked:
            return
        self.last_candle_checked = c0['time']

        closes = [c['close'] for c in closed]
        def calc_ema(period):
            k = 2 / (period + 1)
            e = closes[0]
            for cl in closes[1:]: e = (cl * k) + (e * (1 - k))
            return e
        ema9 = calc_ema(9)
        ema21 = calc_ema(21)

        # Volume Average Filter (Avoid fakeouts without volume)
        avg_vol = sum(c['vol'] for c in closed[-15:]) / 15.0
        has_volume = c0['vol'] >= (avg_vol * 0.85)

        body0 = c0['close'] - c0['open']
        range0 = max(c0['high'] - c0['low'], 1.0)
        lower_wick0 = min(c0['open'], c0['close']) - c0['low']
        upper_wick0 = c0['high'] - max(c0['open'], c0['close'])

        # Long Confirmation: EMA alignment + No upper wick trap + Solid volume
        is_solid_long = (
            (c0['close'] > c0['open']) and 
            (c0['close'] > ema9) and (ema9 > ema21) and
            (upper_wick0 / range0 < 0.28) and
            has_volume and (body0 >= 22.0)
        )

        # Short Confirmation: EMA alignment + No lower wick trap (bounce-back shield) + Solid volume
        is_solid_short = (
            (c0['close'] < c0['open']) and 
            (c0['close'] < ema9) and (ema9 < ema21) and
            (lower_wick0 / range0 < 0.28) and # Rejection wick filter
            has_volume and (body0 <= -22.0)
        )

        cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})
        pos_usd = float(cfg['capital']) * int(cfg['leverage'])
        entry = round(live['close'], 1)
        qty = round(pos_usd / entry, 4) or 0.001

        if is_solid_long:
            recent_low = min(c['low'] for c in closed[-3:])
            risk = max(entry - recent_low + 20.0, 95.0)
            if risk > 160.0: risk = 130.0
            sl = round(entry - risk, 1)
            tp1 = round(entry + 110.0, 1)
            tp2 = round(entry + 220.0, 1)

            trade_obj = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 
                'tp1': tp1, 'tp2': tp2, 'risk': risk, 
                'qty': qty, 'be_hit': False, 'tp1_hit': False, 'realized_pnl': 0.0
            }
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [SMART EXECUTION] BTC LONG\n\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f} (-{risk:.0f} pts)\n🎯 TP1 (50%): ${tp1:.1f} (+110 pts)\n🎯 TP2 (50%): ${tp2:.1f} (+220 pts)\n📦 Qty: {qty} BTC")

        elif is_solid_short:
            recent_high = max(c['high'] for c in closed[-3:])
            risk = max(recent_high - entry + 20.0, 95.0)
            if risk > 160.0: risk = 130.0
            sl = round(entry + risk, 1)
            tp1 = round(entry - 110.0, 1)
            tp2 = round(entry - 220.0, 1)

            trade_obj = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 
                'tp1': tp1, 'tp2': tp2, 'risk': risk, 
                'qty': qty, 'be_hit': False, 'tp1_hit': False, 'realized_pnl': 0.0
            }
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [SMART EXECUTION] BTC SHORT\n\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f} (-{risk:.0f} pts)\n🎯 TP1 (50%): ${tp1:.1f} (+110 pts)\n🎯 TP2 (50%): ${tp2:.1f} (+220 pts)\n📦 Qty: {qty} BTC")

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

            time.sleep(1.5)

# Thread Bootstrapper
if "engine_started" not in st.session_state:
    st.session_state.engine_started = True
    eid = str(uuid.uuid4())
    try:
        with open(LOCK_FILE, "w") as f: f.write(eid)
    except: pass
    threading.Thread(target=MasterCommanderEngine(eid).run, daemon=True).start()

# -------------------------------------------------------------
# STREAMLIT ZERO-MARGIN FRAME
# -------------------------------------------------------------
st.set_page_config(page_title="AI SNIPER BOT", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header, footer, #MainMenu { display: none !important; }
.block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
iframe { width: 100vw !important; height: calc(100vh - 5px) !important; border: none !important; display: block !important; }
</style>""", unsafe_allow_html=True)

conn = sqlite3.connect(DB_FILE, timeout=5)
cur = conn.cursor()
cur.execute("SELECT timestamp, trade_type, entry, result, pts, pnl_usd FROM trades ORDER BY id DESC LIMIT 50")
rows = cur.fetchall()
history_list = [{"time": r[0], "type": r[1], "entry": r[2], "result": r[3], "pts": r[4], "pnl_usd": r[5]} for r in rows]

cur.execute("SELECT COUNT(*), SUM(CASE WHEN result LIKE '%TP%' OR result LIKE '%BE%' THEN 1 ELSE 0 END) FROM trades")
t_count, win_count = cur.fetchone()
conn.close()

win_rate = round((win_count / t_count) * 100, 1) if t_count > 0 else 0.0
active_trade = get_db_state("active_trade")
cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})

js_active_trade = json.dumps(active_trade)
js_history = json.dumps(history_list)
js_stats = json.dumps({"total": t_count, "win_rate": win_rate})
js_cfg = json.dumps(cfg)

terminal_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { background: #080a0f; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100vw; height: 100vh; overflow: hidden; }
        
        .top-nav { display: flex; align-items: center; background: #0d111a; border-bottom: 1px solid #1a2336; padding: 0 8px; font-size: 11px; height: 38px; gap: 8px; overflow-x: auto; white-space: nowrap; }
        .brand { font-weight: 800; color: #fff; font-size: 11px; display: flex; align-items: center; gap: 4px; }
        .badge-scan { background: #00e676; color: #000; font-size: 8px; padding: 2px 4px; border-radius: 3px; font-weight: 900; }
        
        .stat-card { display: flex; flex-direction: column; min-width: 52px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }
        .stat-val { font-size: 10px; font-weight: 800; color: #fff; }
        
        .btn-compact { background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40; border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer; }
        
        .workspace { display: flex; flex-direction: column; width: 100vw; height: calc(100vh - 38px); }
        #chart-zone { width: 100vw; height: 55vh; background: #080a0f; }
        
        .trade-dock { width: 100vw; height: 36px; background: #0a0e17; border-top: 1px solid #1a2336; padding: 0 8px; display: flex; align-items: center; justify-content: space-between; font-size: 10px; }
        .dock-group { display: flex; align-items: center; gap: 5px; }
        .dock-input { background: #121824; border: 1px solid #23304a; color: #00e676; font-size: 10px; font-weight: 800; border-radius: 4px; padding: 2px 4px; width: 44px; text-align: center; }
        
        .bottom-bar { width: 100vw; height: 46px; background: #0d121c; border-top: 1px solid #1a2336; padding: 4px 8px; display: grid; grid-template-columns: 1fr 1fr 1fr 1.4fr; gap: 6px; align-items: center; }
        .metric-cell { display: flex; flex-direction: column; justify-content: center; background: #101624; padding: 2px 6px; border-radius: 4px; border: 1px solid #192233; height: 36px; }
        .cell-head { font-size: 7px; color: #62697a; font-weight: 800; text-transform: uppercase; line-height: 1; margin-bottom: 2px; }
        .cell-body { font-size: 9px; font-weight: 800; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); backdrop-filter: blur(5px); z-index: 999; align-items: center; justify-content: center; }
        .modal-box { background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px; width: 90vw; max-width: 400px; max-height: 80vh; display: flex; flex-direction: column; padding: 12px; }
        .history-list { overflow-y: auto; max-height: 250px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }
        .btn-modal-clear { margin-top: 10px; background: rgba(255, 59, 48, 0.15); color: #ff3b30; border: 1px solid rgba(255, 59, 48, 0.4); border-radius: 4px; padding: 6px; font-size: 10px; font-weight: 800; cursor: pointer; text-align: center; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ EARLY <span class="badge-scan">RADAR</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">TP1 (50%)</div><div id="disp-tp1" class="stat-val" style="color:#00e676;">--</div></div>
        <div class="stat-card"><div class="stat-label">TP2 (50%)</div><div id="disp-tp2" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-compact" onclick="toggleModal(true)">📜 VAULT (<span id="hist-count">0</span>)</button>
        <button class="btn-compact" onclick="window.parent.location.reload()">🔄</button>
        <div style="margin-left: auto; display: flex; align-items: center;">
            <b id="live-price" style="color: #f0b90b; font-size: 11px;">$84,000.0</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>
        <div class="trade-dock">
            <div class="dock-group">
                <span style="color:#62697a; font-weight:800;">AMT($):</span>
                <input id="input-amount" class="dock-input" type="number" value="100" onchange="updateCalcQty()">
                <span style="color:#62697a; font-weight:800;">LEV:</span>
                <input id="input-lev" class="dock-input" type="number" value="10" onchange="updateCalcQty()">
            </div>
            <div class="dock-group">
                <span style="color:#62697a;">POS:</span>
                <b id="calc-qty" style="color:#38bdf8; font-size:10px;">0.0119 BTC</b>
            </div>
        </div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">STATUS</span>
                <div class="cell-body" style="color:#00e676;">DUAL-TP ON 🎯</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TP1 SHIELD</span>
                <div class="cell-body" style="color:#00e676;">+110 PTS (50%)</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TP2 TARGET</span>
                <div class="cell-body" style="color:#38bdf8;">+220 PTS RUN</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">RADAR SCANNER</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">SCANNING MOMENTUM...</div>
            </div>
        </div>
    </div>

    <!-- VAULT POPUP MODAL -->
    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:11px;">SQLITE VAULT (PROTECTED TRADES)</b>
                <button onclick="toggleModal(false)" style="background:transparent; border:none; color:#888; font-size:16px; cursor:pointer;">✕</button>
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
            <div class="btn-modal-clear" onclick="triggerVaultClear()">🗑️ CLEAR VAULT DATABASE</div>
        </div>
    </div>

    <script>
        const IST_OFFSET = 5.5 * 3600;
        let activeTrade = __ACTIVE_TRADE__;
        let tradeHistory = __TRADE_HISTORY__;
        let stats = __STATS__;
        let cfg = __CFG__;

        document.getElementById('input-amount').value = cfg.capital;
        document.getElementById('input-lev').value = cfg.leverage;

        let lineEntry = null, lineSL = null, lineTP1 = null, lineTP2 = null;
        let currentPrice = 84000.0;

        function toggleModal(show) { document.getElementById('modal-bg').style.display = show ? 'flex' : 'none'; }
        function handleBgClick(e) { if (e.target.id === 'modal-bg') toggleModal(false); }
        
        function triggerVaultClear() {
            if (confirm("Are you sure you want to permanently clear all vault trades?")) {
                window.parent.location.href = window.parent.location.pathname + "?clear_vault=confirmed";
            }
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
            timeScale: { 
                borderColor: '#192130', 
                timeVisible: true, 
                secondsVisible: false,
                tickMarkFormatter: (time) => {
                    const date = new Date((time + IST_OFFSET) * 1000);
                    return date.getUTCHours().toString().padStart(2, '0') + ':' + date.getUTCMinutes().toString().padStart(2, '0');
                }
            },
            localization: { 
                timeFormatter: (time) => { 
                    const date = new Date((time + IST_OFFSET) * 1000); 
                    return date.getUTCHours().toString().padStart(2, '0') + ':' + date.getUTCMinutes().toString().padStart(2, '0');
                } 
            }
        });

        const series = chart.addCandlestickSeries({ 
            upColor: '#00E676', downColor: '#FF3B30', 
            borderUpColor: '#00E676', borderDownColor: '#FF3B30', 
            wickUpColor: '#00E676', wickDownColor: '#FF3B30' 
        });

        function renderMasterInterface() {
            if (lineEntry) { try { series.removePriceLine(lineEntry); } catch(e){} lineEntry = null; }
            if (lineSL) { try { series.removePriceLine(lineSL); } catch(e){} lineSL = null; }
            if (lineTP1) { try { series.removePriceLine(lineTP1); } catch(e){} lineTP1 = null; }
            if (lineTP2) { try { series.removePriceLine(lineTP2); } catch(e){} lineTP2 = null; }

            if (activeTrade) {
                lineEntry = series.createPriceLine({ price: activeTrade.entry, color: '#38bdf8', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'ENTRY $' + activeTrade.entry.toFixed(1) });
                lineSL = series.createPriceLine({ price: activeTrade.sl, color: '#ff3b30', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'SAFE SL $' + activeTrade.sl.toFixed(1) });
                lineTP1 = series.createPriceLine({ price: activeTrade.tp1, color: '#00e676', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'TP1 (50%) $' + activeTrade.tp1.toFixed(1) });
                lineTP2 = series.createPriceLine({ price: activeTrade.tp2, color: '#00b0ff', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'TP2 (50%) $' + activeTrade.tp2.toFixed(1) });

                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
                document.getElementById('disp-tp1').innerText = "$" + activeTrade.tp1.toFixed(1);
                document.getElementById('disp-tp2').innerText = "$" + activeTrade.tp2.toFixed(1);
                document.getElementById('val-setup').innerText = "RIDING " + activeTrade.type + " 🚀";
                document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp1').innerText = "--";
                document.getElementById('disp-tp2').innerText = "--";
                document.getElementById('val-setup').innerText = "SCANNING MOMENTUM...";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }

            document.getElementById('hist-count').innerText = tradeHistory.length;
            document.getElementById('stat-total').innerText = stats.total;
            document.getElementById('stat-rate').innerText = stats.win_rate + "%";

            const histCont = document.getElementById('history-container');
            if (tradeHistory.length > 0) {
                histCont.innerHTML = "";
                tradeHistory.forEach(item => {
                    let resCol = item.result.includes("TP") || item.result.includes("BE") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    let pnlDisp = item.pnl_usd ? `<b style="color:${resCol}; margin-left:4px;">(${item.pnl_usd})</b>` : '';
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span>${item.time} <b style="color:${typeCol};">${item.type}</b> @ $${item.entry.toFixed(1)}</span>
                            <span><b style="color:${resCol};">${item.result}</b> ${pnlDisp}</span>
                        </div>`;
                });
            } else {
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">Vault Clean (0 trades)...</div>';
            }
        }

        function syncCandles() {
            fetch('https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=100')
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
                }
            };
            ws.onclose = () => setTimeout(() => connectLiveStream(cdata), 1500);
        }

        syncCandles();
        window.onresize = () => chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
    </script>
</body>
</html>"""

final_html = terminal_html.replace("__ACTIVE_TRADE__", js_active_trade)\
                          .replace("__TRADE_HISTORY__", js_history)\
                          .replace("__STATS__", js_stats)\
                          .replace("__CFG__", js_cfg)

components.html(final_html, height=710, scrolling=False)
