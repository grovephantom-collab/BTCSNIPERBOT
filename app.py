import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import threading
import time
import requests
import json
import os
import uuid
import hmac
import hashlib
from datetime import datetime

# ==============================================================================
# MULTI-ASSET QUANT RADAR: BTCUSDT | SOLUSDT | DOGEUSDT ($10 ACCOUNT ENGINE)
# ==============================================================================

BOT_TOKEN = "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM"
CHAT_ID = "7886716805"
DISCORD_WEBHOOK_URL = ""
DB_FILE = "sniper_vault.db"
SHARED_MEMORY_FILE = "sniper_brain_data.json"

BINANCE_API_KEY = ""
BINANCE_API_SECRET = ""
PAPER_TRADING_MODE = True

WATCHLIST = ["SOLUSDT", "DOGEUSDT", "BTCUSDT"]  # SOL aur DOGE priority pe

PAIR_CONFIG = {
    "BTCUSDT": {"min_sl_pct": 0.0060, "tp_pct": 0.0180, "round_dec": 1, "qty_dec": 3, "min_qty": 0.001},
    "SOLUSDT": {"min_sl_pct": 0.0080, "tp_pct": 0.0240, "round_dec": 2, "qty_dec": 2, "min_qty": 0.1},
    "DOGEUSDT": {"min_sl_pct": 0.0100, "tp_pct": 0.0300, "round_dec": 5, "qty_dec": 0, "min_qty": 50}
}

# --- 1. LOGGING & DATABASE ---
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
            qty REAL,
            UNIQUE(timestamp, symbol, trade_type, entry, result)
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

def check_db_risk_guard():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT result FROM trades ORDER BY id DESC LIMIT 5")
        rows = cur.fetchall()
        consecutive_losses = 0
        for r in rows:
            res = r[0].upper()
            if "SL HIT" in res:
                consecutive_losses += 1
            else:
                break
        
        today_date = datetime.now().strftime("%Y-%m-%d")
        cur.execute("SELECT pnl_usd FROM trades WHERE timestamp LIKE ? AND result LIKE '%SL HIT%'", (f"{today_date}%",))
        sl_rows = cur.fetchall()
        daily_loss_sum = 0.0
        for r in sl_rows:
            try:
                val = float(str(r[0]).replace("$", "").replace("(", "").replace(")", "").replace("-", "").strip())
                daily_loss_sum += val
            except: pass
            
        conn.close()
        return consecutive_losses, daily_loss_sum
    except:
        return 0, 0.0

# --- ALERTS ENGINE ---
def _send_tg_worker(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(CHAT_ID).strip(), "text": msg}
    try:
        requests.post(url, json=payload, timeout=4)
    except: pass

def send_alert(msg):
    threading.Thread(target=_send_tg_worker, args=(msg,), daemon=True).start()

# --- 2. SHARED MEMORY ENGINE ---
def read_shared_memory():
    default_mem = {
        "trends_1h": {s: "NEUTRAL" for s in WATCHLIST},
        "risk_circuit_broken": False,
        "commander_heartbeat": time.time(),
        "candidate_signals": {}
    }
    if not os.path.exists(SHARED_MEMORY_FILE):
        return default_mem
    try:
        with open(SHARED_MEMORY_FILE, "r") as f: return json.load(f)
    except:
        return default_mem

def write_shared_memory(data):
    try:
        with open(SHARED_MEMORY_FILE, "w") as f: json.dump(data, f)
    except: pass

def calculate_ema(prices, period):
    if len(prices) < period: return prices[-1]
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def fetch_pair_klines(symbol, interval="5m", limit=40):
    urls = [
        f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=2.5)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) >= 20:
                    closed = [{'time': int(d[0]), 'open': float(d[1]), 'high': float(d[2]),
                               'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])} for d in raw[:-1]]
                    live = {'time': int(raw[-1][0]), 'open': float(raw[-1][1]), 'high': float(raw[-1][2]),
                            'low': float(raw[-1][3]), 'close': float(raw[-1][4]), 'vol': float(raw[-1][5])}
                    return closed, live
        except: continue
    return None, None

# --- THREAD 2: QUALITY PULLBACK & REJECTION ENGINE ---
def run_thread2_analysis_engine():
    while True:
        try:
            mem = read_shared_memory()
            trends = mem.get("trends_1h", {})
            candidate_signals = {}

            for sym in WATCHLIST:
                # 1. 1-Hour Trend Direction
                try:
                    r_1h = requests.get(f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=1h&limit=30", timeout=2.5)
                    if r_1h.status_code == 200:
                        closes_1h = [float(x[4]) for x in r_1h.json()]
                        ema20_1h = calculate_ema(closes_1h, 20)
                        last_c = closes_1h[-1]
                        trends[sym] = "BULLISH" if last_c > ema20_1h else "BEARISH"
                except: pass

                # 2. 5-Minute Pullback / Rejection Setup
                closed_5m, live_5m = fetch_pair_klines(sym, "5m", 35)
                if closed_5m and live_5m:
                    closes_5m = [c['close'] for c in closed_5m]
                    ema9 = calculate_ema(closes_5m, 9)
                    ema21 = calculate_ema(closes_5m, 21)
                    curr_p = float(live_5m['close'])
                    
                    last_c = closed_5m[-1]
                    htf = trends.get(sym, "NEUTRAL")

                    # REJECTION SHORT: 1H Bearish + Price EMA 21 ke paas aakar red candle banayi (Pullback Short)
                    is_short_setup = (
                        htf == "BEARISH" and
                        ema9 < ema21 and
                        last_c['high'] >= ema21 * 0.999 and  # EMA 21 ko test kiya
                        last_c['close'] < last_c['open'] and # Red rejection candle
                        curr_p < last_c['low']              # Break of low
                    )

                    # BOUNCE LONG: 1H Bullish + Price EMA 21 ke paas support leke green candle banayi
                    is_long_setup = (
                        htf == "BULLISH" and
                        ema9 > ema21 and
                        last_c['low'] <= ema21 * 1.001 and   # EMA 21 ko test kiya
                        last_c['close'] > last_c['open'] and # Green bounce candle
                        curr_p > last_c['high']             # Break of high
                    )

                    if is_short_setup:
                        candidate_signals[sym] = {"type": "SHORT", "price": curr_p, "time": live_5m['time']}
                    elif is_long_setup:
                        candidate_signals[sym] = {"type": "LONG", "price": curr_p, "time": live_5m['time']}

                time.sleep(0.5)

            mem["trends_1h"] = trends
            mem["candidate_signals"] = candidate_signals
            write_shared_memory(mem)
        except: pass
        time.sleep(2)

# --- THREAD 3: HARD RISK & MONEY MANAGEMENT ---
def run_thread3_risk_manager():
    alert_already_sent = False
    while True:
        try:
            consec_losses, daily_loss = check_db_risk_guard()
            mem = read_shared_memory()
            if daily_loss >= 2.50 or consec_losses >= 3:
                mem['risk_circuit_broken'] = True
                write_shared_memory(mem)
                if not alert_already_sent:
                    send_alert(f"🚨 [RISK MANAGER ALERT] Max Daily Drawdown (-${daily_loss:.2f}) reached! Trading paused for safety.")
                    alert_already_sent = True
            else:
                if mem.get('risk_circuit_broken', False):
                    mem['risk_circuit_broken'] = False
                    write_shared_memory(mem)
                alert_already_sent = False
        except: pass
        time.sleep(15)

# --- THREAD 4: EXECUTION & POSITION LIFECYCLE ---
class MasterExecutionLifecycleEngine:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.last_trade_bar = {}
        self.locked_closing_id = None
        self.sl_locked = False

    def record_to_vault(self, symbol, t_type, entry, exit_price, result, pts, pnl_usd, qty):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO trades (timestamp, symbol, trade_type, entry, exit_price, result, pts, pnl_usd, qty) 
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (now_str, symbol, t_type, float(entry), float(exit_price), result, str(pts), str(pnl_usd), float(qty)))
            conn.commit()
            conn.close()
        except: pass

    def manage_active_lifecycle(self, t):
        sym = t.get('symbol', 'SOLUSDT')
        closed, live = fetch_pair_klines(sym, "5m", 30)
        if not closed or not live: return

        curr_trade_ref = f"{sym}_{t.get('type')}_{t.get('entry')}"
        if self.locked_closing_id == curr_trade_ref: return

        qty = float(t.get("qty", 0.1))
        curr_price = float(live['close'])
        entry = float(t['entry'])

        cfg = PAIR_CONFIG[sym]
        dec = cfg["round_dec"]

        # Trailing SL on +1% Move
        if t['type'] == 'LONG':
            if curr_price > entry * 1.01 and float(t['sl']) < entry:
                t['sl'] = round(entry * 1.002, dec) # Breakeven lock
                t['trailed'] = True
                set_db_state("active_trade", t)

            if curr_price >= t['tp']:
                self.locked_closing_id = curr_trade_ref
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                pnl_usd = round((curr_price - entry) * qty, 2)
                self.record_to_vault(sym, "LONG", entry, t['tp'], "DIRECT MEGA TP 🔥", f"+{round(t['tp']-entry, dec)}", f"+${pnl_usd:.2f}", qty)
                send_alert(f"🚀 [DIRECT TP HIT] {sym} LONG!\nProfit: +${pnl_usd:.2f}\nExit: ${t['tp']}")

            elif curr_price <= float(t['sl']):
                self.locked_closing_id = curr_trade_ref
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                pnl_usd = round((curr_price - entry) * qty, 2)
                res_type = "TRAILED PROFIT 🛡️" if pnl_usd > 0 else "SL HIT 🛑"
                usd_disp = f"+${pnl_usd:.2f}" if pnl_usd > 0 else f"-${abs(pnl_usd):.2f}"
                self.record_to_vault(sym, "LONG", entry, t['sl'], res_type, f"{round(curr_price-entry, dec)}", usd_disp, qty)
                send_alert(f"{'🛡️' if pnl_usd > 0 else '🛑'} [EXIT] {sym} LONG {res_type}\nPnL: {usd_disp}\nExit: ${curr_price}")

        elif t['type'] == 'SHORT':
            if curr_price < entry * 0.99 and float(t['sl']) > entry:
                t['sl'] = round(entry * 0.998, dec) # Breakeven lock
                t['trailed'] = True
                set_db_state("active_trade", t)

            if curr_price <= t['tp']:
                self.locked_closing_id = curr_trade_ref
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                pnl_usd = round((entry - curr_price) * qty, 2)
                self.record_to_vault(sym, "SHORT", entry, t['tp'], "DIRECT MEGA TP 🔥", f"+{round(entry-t['tp'], dec)}", f"+${pnl_usd:.2f}", qty)
                send_alert(f"🩸 [DIRECT TP HIT] {sym} SHORT!\nProfit: +${pnl_usd:.2f}\nExit:${t['tp']}")

            elif curr_price >= float(t['sl']):
                self.locked_closing_id = curr_trade_ref
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                pnl_usd = round((entry - curr_price) * qty, 2)
                res_type = "TRAILED PROFIT 🛡️" if pnl_usd > 0 else "SL HIT 🛑"
                usd_disp = f"+${pnl_usd:.2f}" if pnl_usd > 0 else f"-${abs(pnl_usd):.2f}"
                self.record_to_vault(sym, "SHORT", entry, t['sl'], res_type, f"{round(entry-curr_price, dec)}", usd_disp, qty)
                send_alert(f"{'🛡️' if pnl_usd > 0 else '🛑'} [EXIT] {sym} SHORT {res_type}\nPnL: {usd_disp}\nExit: ${curr_price}")

    def evaluate_and_execute(self):
        mem = read_shared_memory()
        if get_db_state("kill_switch_active", False) or mem.get("risk_circuit_broken", False):
            return

        last_exit_epoch = get_db_state("last_exit_epoch", 0)
        if time.time() - last_exit_epoch < 180: # 3 min wait after trade
            return

        candidate_signals = mem.get("candidate_signals", {})
        if not candidate_signals: return

        for sym in WATCHLIST:
            sig = candidate_signals.get(sym)
            if not sig: continue

            last_bar = self.last_trade_bar.get(sym, 0)
            if sig['time'] <= last_bar: continue

            cfg = PAIR_CONFIG[sym]
            dec = cfg["round_dec"]
            curr_p = sig['price']

            # Fixed Capital Allocation ($2.50 Margin @ 10x Lev = $25 Position)
            raw_qty = 25.0 / curr_p
            qty = max(cfg["min_qty"], round(raw_qty, cfg["qty_dec"]))
            if cfg["qty_dec"] == 0: qty = int(qty)

            if sig['type'] == "LONG":
                self.last_trade_bar[sym] = sig['time']
                sl = round(curr_p * (1 - cfg["min_sl_pct"]), dec)
                tp = round(curr_p * (1 + cfg["tp_pct"]), dec)

                trade_obj = {'symbol': sym, 'type': 'LONG', 'entry': round(curr_p, dec), 'sl': sl, 'tp': tp, 'qty': qty, 'trailed': False}
                set_db_state("active_trade", trade_obj)
                send_alert(f"⚡ [PULLBACK SWING] {sym} LONG 🟢\n📍 Entry: ${curr_p}\n🎯 DIRECT TP: ${tp}\n🛡️ SL: ${sl}\n📦 Qty: {qty}")
                break

            elif sig['type'] == "SHORT":
                self.last_trade_bar[sym] = sig['time']
                sl = round(curr_p * (1 + cfg["min_sl_pct"]), dec)
                tp = round(curr_p * (1 - cfg["tp_pct"]), dec)

                trade_obj = {'symbol': sym, 'type': 'SHORT', 'entry': round(curr_p, dec), 'sl': sl, 'tp': tp, 'qty': qty, 'trailed': False}
                set_db_state("active_trade", trade_obj)
                send_alert(f"⚡ [PULLBACK SWING] {sym} SHORT 🔴\n📍 Entry: ${curr_p}\n🎯 DIRECT TP: ${tp}\n🛡️ SL: ${sl}\n📦 Qty: {qty}")
                break

    def run(self):
        while True:
            mem = read_shared_memory()
            mem['commander_heartbeat'] = time.time()
            write_shared_memory(mem)

            active = get_db_state("active_trade")
            if active:
                self.manage_active_lifecycle(active)
            else:
                self.evaluate_and_execute()
            time.sleep(1.0)

# --- START BOT ---
@st.cache_resource
def launch_chart_architecture():
    eid = str(uuid.uuid4())
    threading.Thread(target=run_thread2_analysis_engine, daemon=False).start()
    threading.Thread(target=run_thread3_risk_manager, daemon=False).start()
    cmd = MasterExecutionLifecycleEngine(eid)
    threading.Thread(target=cmd.run, daemon=False).start()
    send_alert("🟢 [PULLBACK RADAR LIVE] Scanning SOL, DOGE & BTC Pullbacks...")
    return cmd

launch_chart_architecture()

# -------------------------------------------------------------
# FRONTEND UI
# -------------------------------------------------------------
st.set_page_config(page_title="QUANT RADAR PRO", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header, footer, #MainMenu { display: none !important; }
.block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
iframe { width: 100vw !important; height: calc(100vh - 5px) !important; border: none !important; display: block !important; }
</style>""", unsafe_allow_html=True)

if st.query_params.get("clear_vault") == "confirmed":
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        cur = conn.cursor()
        cur.execute("DELETE FROM trades")
        conn.commit()
        conn.close()
        set_db_state("active_trade", None)
        set_db_state("last_exit_epoch", 0)
    except: pass
    st.query_params.clear()
    st.rerun()

if st.query_params.get("force_close") == "confirmed":
    act = get_db_state("active_trade")
    if act and isinstance(act, dict) and 'entry' in act:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        e = float(act['entry'])
        q = float(act.get('qty', 0.1))
        sym = act.get('symbol', 'SOLUSDT')
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO trades (timestamp, symbol, trade_type, entry, exit_price, result, pts, pnl_usd, qty) 
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (now_str, sym, act['type'], e, e, "MANUAL OVERRIDE ⚠️", "0", "$0.00", q))
            conn.commit()
            conn.close()
        except: pass
        set_db_state("active_trade", None)
        set_db_state("last_exit_epoch", time.time())
    st.query_params.clear()
    st.rerun()

@st.fragment(run_every=2)
def render_live_dashboard():
    conn = sqlite3.connect(DB_FILE, timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT timestamp, symbol, trade_type, entry, result, pts, pnl_usd FROM trades ORDER BY id DESC")
    rows = cur.fetchall()
    history_list = [{"time": r[0].split(" ")[-1] if " " in r[0] else r[0], "symbol": r[1], "type": r[2], "entry": r[3], "result": r[4], "pts": r[5], "pnl_usd": r[6]} for r in rows]

    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result LIKE '%TP%' OR result LIKE '%TRAILED%' THEN 1 ELSE 0 END) FROM trades")
    t_count, win_count = cur.fetchone()
    conn.close()

    win_rate = round((win_count / t_count) * 100, 1) if t_count > 0 else 0.0
    active_trade = get_db_state("active_trade")

    js_active_trade = json.dumps(active_trade)
    js_history = json.dumps(history_list)
    js_stats = json.dumps({"total": t_count, "win_rate": win_rate})

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
        .brand { font-weight: 800; color: #fff; font-size: 11px; display: flex; align-items: center; gap: 5px; }
        .pulse-dot { width: 7px; height: 7px; background: #00e676; border-radius: 50%; box-shadow: 0 0 8px #00e676; animation: blinker 1.2s cubic-bezier(0.5, 0, 1, 1) infinite alternate; }
        @keyframes blinker { from { opacity: 1; transform: scale(1); } to { opacity: 0.25; transform: scale(0.7); } }
        .pair-btn { background: #141c2c; border: 1px solid #1f2a40; color: #8892b0; border-radius: 4px; padding: 2px 7px; font-size: 9px; font-weight: 800; cursor: pointer; }
        .pair-btn.active { background: #00e676; color: #000; border-color: #00e676; }
        .stat-card { display: flex; flex-direction: column; min-width: 60px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }
        .stat-val { font-size: 10px; font-weight: 800; color: #fff; }
        .btn-compact { background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40; border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer; }
        .workspace { display: flex; flex-direction: column; width: 100vw; height: calc(100vh - 38px); }
        #chart-zone { width: 100vw; height: 53vh; background: #080a0f; }
        .trade-dock { width: 100vw; height: 38px; background: #0a0e17; border-top: 1px solid #1a2336; padding: 0 8px; display: flex; align-items: center; justify-content: space-between; font-size: 10px; }
        .dock-group { display: flex; align-items: center; gap: 8px; }
        .btn-override-warn { background: rgba(240, 185, 11, 0.2); color: #f0b90b; border: 1px solid #f0b90b; border-radius: 4px; padding: 3px 6px; font-size: 9px; font-weight: 800; cursor: pointer; }
        .bottom-bar { width: 100vw; height: 46px; background: #0d121c; border-top: 1px solid #1a2336; padding: 4px 8px; display: grid; grid-template-columns: 1fr 1fr 1fr 1.2fr; gap: 6px; align-items: center; }
        .metric-cell { display: flex; flex-direction: column; justify-content: center; background: #101624; padding: 2px 6px; border-radius: 4px; border: 1px solid #192233; height: 36px; }
        .cell-head { font-size: 7px; color: #62697a; font-weight: 800; text-transform: uppercase; line-height: 1; margin-bottom: 2px; }
        .cell-body { font-size: 9px; font-weight: 800; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); backdrop-filter: blur(5px); z-index: 999; align-items: center; justify-content: center; }
        .modal-box { background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px; width: 90vw; max-width: 400px; max-height: 80vh; display: flex; flex-direction: column; padding: 12px; }
        .history-list { overflow-y: auto; max-height: 250px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }
        .btn-modal-clear { margin-top: 10px; background: rgba(255, 59, 48, 0.25); color: #ff3b30; border: 1px solid rgba(255, 59, 48, 0.6); border-radius: 6px; padding: 10px; font-size: 11px; font-weight: 800; cursor: pointer; text-align: center; width: 100%; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand"><span class="pulse-dot"></span> ⚡ QUANT</div>
        <button class="pair-btn active" id="tab-SOL" onclick="switchPair('SOLUSDT')">SOL</button>
        <button class="pair-btn" id="tab-DOGE" onclick="switchPair('DOGEUSDT')">DOGE</button>
        <button class="pair-btn" id="tab-BTC" onclick="switchPair('BTCUSDT')">BTC</button>
        <div class="stat-card"><div class="stat-label">ACTIVE</div><div id="disp-sym" class="stat-val" style="color:#f0b90b;">NONE</div></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">DIRECT TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-compact" onclick="toggleModal(true)">📜 VAULT (<span id="hist-count">0</span>)</button>
        <button class="btn-compact" onclick="window.parent.location.reload()">🔄</button>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>
        <div class="trade-dock">
            <div class="dock-group">
                <span style="color:#62697a; font-weight:800;">ACCOUNT:</span>
                <b style="color:#00e676; font-size:10px;">$10.00 BASE</b>
                <span style="color:#62697a;">| MARGIN:</span>
                <b style="color:#38bdf8; font-size:10px;">$2.50 (10x)</b>
            </div>
            <div class="dock-group">
                <button type="button" class="btn-override-warn" onclick="triggerForceClose()">⚡ FORCE CLOSE</button>
            </div>
        </div>
        <div class="bottom-bar">
            <div class="metric-cell"><span class="cell-head">THREAD 3 RISK</span><div class="cell-body" style="color:#00e676;">-$2.50 GUARD</div></div>
            <div class="metric-cell"><span class="cell-head">VIEWING</span><div class="cell-body" id="val-viewing" style="color:#38bdf8;">SOLUSDT (5M LIVE)</div></div>
            <div class="metric-cell"><span class="cell-head">TARGET PROFILE</span><div class="cell-body" style="color:#00e676;">100% DIRECT TP</div></div>
            <div class="metric-cell"><span class="cell-head">SETUP</span><div class="cell-body" id="val-setup" style="color:#38bdf8;">WAITING FOR PULLBACK...</div></div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:11px;">MULTI-ASSET VAULT</b>
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
            <button type="button" class="btn-modal-clear" onclick="triggerVaultClear()">🗑️ CLEAR VAULT</button>
        </div>
    </div>

    <script>
        const IST_OFFSET = 5.5 * 3600;
        let activeTrade = __ACTIVE_TRADE__;
        let tradeHistory = __TRADE_HISTORY__;
        let stats = __STATS__;

        let activeChartSymbol = (activeTrade && activeTrade.symbol) ? activeTrade.symbol : "SOLUSDT";
        let liveSocket = null;
        let cdata = [];

        function toggleModal(show) { document.getElementById('modal-bg').style.display = show ? 'flex' : 'none'; }
        function handleBgClick(e) { if (e.target.id === 'modal-bg') toggleModal(false); }
        
        function triggerVaultClear() {
            try { window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?clear_vault=confirmed"; }
            catch(e) { window.location.href = window.location.pathname + "?clear_vault=confirmed"; }
        }

        function triggerForceClose() {
            if (!activeTrade) { alert("No active trade to close!"); return; }
            if (confirm("Force close active position?")) {
                try { window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?force_close=confirmed"; }
                catch(e) { window.location.href = window.location.pathname + "?force_close=confirmed"; }
            }
        }

        function switchPair(sym) {
            activeChartSymbol = sym;
            document.querySelectorAll('.pair-btn').forEach(b => b.classList.remove('active'));
            if (sym === 'SOLUSDT') document.getElementById('tab-SOL').classList.add('active');
            if (sym === 'DOGEUSDT') document.getElementById('tab-DOGE').classList.add('active');
            if (sym === 'BTCUSDT') document.getElementById('tab-BTC').classList.add('active');
            document.getElementById('val-viewing').innerText = sym + " (5M LIVE)";
            if (liveSocket) { liveSocket.close(); liveSocket = null; }
            syncCandles();
        }

        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {
            width: chartZone.clientWidth, height: chartZone.clientHeight,
            layout: { background: { color: '#080a0f' }, textColor: '#787b86' },
            grid: { vertLines: { color: '#111622' }, horzLines: { color: '#111622' } },
            rightPriceScale: { borderColor: '#192130' },
            timeScale: { 
                borderColor: '#192130', timeVisible: true, secondsVisible: false,
                tickMarkFormatter: (time) => {
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

        let lineEntry = null, lineSL = null, lineTP = null;
        function clearAllLines() {
            if (lineEntry) { try { series.removePriceLine(lineEntry); } catch(e){} lineEntry = null; }
            if (lineSL) { try { series.removePriceLine(lineSL); } catch(e){} lineSL = null; }
            if (lineTP) { try { series.removePriceLine(lineTP); } catch(e){} lineTP = null; }
        }

        function renderMasterInterface() {
            clearAllLines();
            if (activeTrade && activeTrade.entry) {
                let isCurrentChart = (activeTrade.symbol === activeChartSymbol);
                if (isCurrentChart) {
                    let entryVal = parseFloat(activeTrade.entry);
                    let slVal = parseFloat(activeTrade.sl);
                    let tpVal = parseFloat(activeTrade.tp);

                    lineEntry = series.createPriceLine({ price: entryVal, color: '#38bdf8', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'ENTRY' });
                    lineSL = series.createPriceLine({ price: slVal, color: '#ff3b30', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'SL' });
                    lineTP = series.createPriceLine({ price: tpVal, color: '#00e676', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'DIRECT TP' });
                }

                document.getElementById('disp-sym').innerText = activeTrade.symbol;
                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry;
                document.getElementById('disp-tp').innerText = "$" + activeTrade.tp;
                document.getElementById('val-setup').innerText = "RIDING " + activeTrade.symbol + " " + activeTrade.type + " 🚀";
                document.getElementById('val-setup').style.color = (activeTrade.type === "LONG") ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-sym').innerText = "SCANNING";
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = "SCANNING REJECTIONS ON SOL, DOGE & BTC...";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }

            document.getElementById('hist-count').innerText = stats.total;
            document.getElementById('stat-total').innerText = stats.total;
            document.getElementById('stat-rate').innerText = stats.win_rate + "%";

            const histCont = document.getElementById('history-container');
            if (tradeHistory.length > 0) {
                histCont.innerHTML = "";
                tradeHistory.forEach(item => {
                    let resCol = item.result.includes("TP") || item.result.includes("TRAILED") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    let pnlDisp = item.pnl_usd ? `<b style="color:${resCol}; margin-left:4px;">(${item.pnl_usd})</b>` : '';
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span><b>${item.symbol || 'SOL'}</b> ${item.time} <b style="color:${typeCol};">${item.type}</b> @ $${item.entry}</span>
                            <span><b style="color:${resCol};">${item.result}</b> ${pnlDisp}</span>
                        </div>`;
                });
            } else {
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">Vault Clean (0 trades)...</div>';
            }
        }

        function connectLiveStream() {
            if (liveSocket) { liveSocket.close(); }
            const streamSymbol = activeChartSymbol.toLowerCase();
            liveSocket = new WebSocket(`wss://stream.binance.com:9443/ws/${streamSymbol}@kline_5m`);

            liveSocket.onmessage = (e) => {
                const data = JSON.parse(e.data);
                const k = data.k;
                const price = parseFloat(k.c);
                const barTime = (k.t - (k.t % 300000)) / 1000;

                if (cdata.length > 0) {
                    let last = cdata[cdata.length - 1];
                    if (barTime === last.time) {
                        last.close = price;
                        if (price > last.high) last.high = price;
                        if (price < last.low) last.low = price;
                        series.update(last);
                    } else if (barTime > last.time) {
                        const newBar = { time: barTime, open: parseFloat(k.o), high: parseFloat(k.h), low: parseFloat(k.l), close: price };
                        cdata.push(newBar);
                        series.update(newBar);
                    }
                }
            };
            liveSocket.onerror = () => { setTimeout(connectLiveStream, 2000); };
        }

        function syncCandles() {
            fetch('https://data-api.binance.vision/api/v3/klines?symbol=' + activeChartSymbol + '&interval=5m&limit=100')
                .then(r => r.json())
                .then(data => {
                    cdata = data.map(d => ({ 
                        time: (d[0] - (d[0] % 300000)) / 1000, 
                        open: parseFloat(d[1]), high: parseFloat(d[2]), 
                        low: parseFloat(d[3]), close: parseFloat(d[4]) 
                    }));
                    series.setData(cdata);
                    chart.timeScale().fitContent();
                    renderMasterInterface();
                    connectLiveStream();
                }).catch(e => setTimeout(syncCandles, 2000));
        }

        syncCandles();
        window.onresize = () => chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
    </script>
</body>
</html>"""

    final_html = terminal_html.replace("__ACTIVE_TRADE__", js_active_trade)\
                              .replace("__TRADE_HISTORY__", js_history)\
                              .replace("__STATS__", js_stats)

    components.html(final_html, height=710, scrolling=False)

render_live_dashboard()
