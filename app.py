import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import threading
import time
import requests
import json
import os
import uuid
import math
from datetime import datetime

# ==============================================================================
# PRO QUANT ENGINE: 5-ENGINE CORE + PHASE 1 RISK + PHASE 2 HTF & EARLY DETECTION
# ==============================================================================

BOT_TOKEN = "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM"
CHAT_ID = "7886716805"
DB_FILE = "sniper_vault.db"
SHARED_MEMORY_FILE = "sniper_brain_data.json"
WATCHDOG_LOCK = "overseer_watchdog.pid"

# --- 1. LOGGING & DATABASE (VAULT) ---
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

# --- PHASE 1 UI URL ACTION DISPATCHERS ---
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

if st.query_params.get("force_close") == "confirmed":
    act = get_db_state("active_trade")
    if act and isinstance(act, dict) and 'entry' in act:
        now_str = datetime.now().strftime("%H:%M")
        e = float(act['entry'])
        q = float(act.get('qty', 0.01))
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trades (timestamp, symbol, trade_type, entry, exit_price, result, pts, pnl_usd, qty) 
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (now_str, "BTCUSDT", act['type'], e, e, "MANUAL FORCE CLOSE ⚠️", "0", "$0.00", q))
            conn.commit()
            conn.close()
        except: pass
        set_db_state("active_trade", None)
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": str(CHAT_ID).strip(), "text": f"⚠️ [MANUAL OVERRIDE] Position on {act['type']} Force Closed from Dashboard!"}, timeout=3)
        except: pass
    st.query_params.clear()
    st.rerun()

if st.query_params.get("toggle_emergency") == "confirmed":
    curr_kill = get_db_state("kill_switch_active", False)
    new_kill = not curr_kill
    set_db_state("kill_switch_active", new_kill)
    if new_kill:
        set_db_state("active_trade", None)
        status_msg = "🚨 [EMERGENCY STOP ACTIVATED] Bot trading has been FROZEN completely!"
    else:
        status_msg = "🟢 [EMERGENCY STOP RELEASED] Bot trading has resumed regular scanning."
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": str(CHAT_ID).strip(), "text": status_msg}, timeout=3)
    except: pass
    st.query_params.clear()
    st.rerun()

# ZERO-DELAY ASYNC TELEGRAM DISPATCHER
def _send_tg_worker(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(CHAT_ID).strip(), "text": msg}
    try:
        requests.post(url, json=payload, timeout=3)
    except: pass

def send_telegram_alert(msg):
    threading.Thread(target=_send_tg_worker, args=(msg,), daemon=True).start()

# --- 2. SHARED MEMORY / JSON ENGINE ---
def read_shared_memory():
    default_mem = {
        "sentiment_score": 50, "sentiment_label": "NEUTRAL", 
        "last_heartbeat": time.time(), "consecutive_losses": 0, 
        "last_trade_time": 0, "daily_loss_sum": 0.0, 
        "current_day": datetime.now().strftime("%Y-%m-%d"),
        "htf_trend": "NEUTRAL"
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

# --- 3. DATA & NEWS SENTIMENT ENGINE (WITH PHASE 2 HTF 1H BIAS) ---
def run_data_news_engine():
    while True:
        try:
            # Fear & Greed API
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3)
            score = 50
            label = "NEUTRAL"
            if r.status_code == 200:
                score = int(r.json()['data'][0]['value'])
                label = "GREED" if score >= 60 else ("FEAR" if score <= 40 else "NEUTRAL")
            
            # Phase 2: HTF (1H) Trend Direction Fetcher
            htf_trend = "NEUTRAL"
            try:
                r_htf = requests.get("https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=30", timeout=3)
                if r_htf.status_code == 200:
                    raw_htf = r_htf.json()
                    closes = [float(x[4]) for x in raw_htf]
                    # Calculate 1H EMA20
                    k = 2 / (20 + 1)
                    ema20 = closes[0]
                    for cl in closes[1:]:
                        ema20 = (cl * k) + (ema20 * (1 - k))
                    curr_htf_price = closes[-1]
                    if curr_htf_price > ema20 + 15.0:
                        htf_trend = "BULLISH"
                    elif curr_htf_price < ema20 - 15.0:
                        htf_trend = "BEARISH"
            except: pass

            mem = read_shared_memory()
            mem['sentiment_score'] = score
            mem['sentiment_label'] = label
            mem['htf_trend'] = htf_trend
            mem['last_heartbeat'] = time.time()
            write_shared_memory(mem)
        except: pass
        time.sleep(60)

# --- 4. FAST BINANCE DATA FETCHER ---
def fetch_binance_klines():
    urls = [
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=50",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=50"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=2.5)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) >= 30:
                    closed = [{'time': int(d[0]), 'open': float(d[1]), 'high': float(d[2]),
                               'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])} for d in raw[:-1]]
                    live = {'time': int(raw[-1][0]), 'open': float(raw[-1][1]), 'high': float(raw[-1][2]),
                            'low': float(raw[-1][3]), 'close': float(raw[-1][4]), 'vol': float(raw[-1][5])}
                    return closed, live
        except: continue
    return None, None

# --- 5. COMMANDER, RISK GUARD & EXECUTION CORE ---
class MasterCommanderEngine:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.last_trade_bar = 0
        self.last_exit_time = 0
        self.is_closing = False

    def record_to_vault(self, t_type, entry, exit_price, result, pts, pnl_usd, qty):
        now_str = datetime.now().strftime("%H:%M")
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trades (timestamp, symbol, trade_type, entry, exit_price, result, pts, pnl_usd, qty) 
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (now_str, "BTCUSDT", t_type, float(entry), float(exit_price), result, str(pts), str(pnl_usd), float(qty)))
            conn.commit()
            conn.close()
        except: pass

    def manage_position(self, t, live, closed):
        if self.is_closing:
            return

        qty = t.get("qty", 0.01)
        curr_price = float(live['close'])
        entry = float(t['entry'])

        if 'tp1' not in t or not t['tp1']:
            t['tp1'] = round(entry + 110.0 if t['type'] == 'LONG' else entry - 110.0, 1)
        if 'tp2' not in t or not t['tp2']:
            t['tp2'] = round(entry + 220.0 if t['type'] == 'LONG' else entry - 220.0, 1)

        mem = read_shared_memory()
        c0 = closed[-1]

        # LONG POSITION MONITOR
        if t['type'] == 'LONG':
            # 1. TP1 Trigger (+110 pts) -> 50% Profit Book + Breakeven Shift
            if not t.get('tp1_hit', False) and curr_price >= t['tp1']:
                t['tp1_hit'] = True
                t['be_hit'] = True
                t['tp1_bar_time'] = live['time']
                t['sl'] = round(entry + 10.0, 1)
                half_qty = round(qty * 0.5, 4)
                half_usd = round(110.0 * half_qty, 2)
                
                self.record_to_vault("LONG", entry, t['tp1'], "TP1 BOOK (50%) 🎯", "+110", f"+${half_usd:.2f}", half_qty)
                set_db_state("active_trade", t)
                send_telegram_alert(f"🎯 [TP1 HIT] BTC LONG\nPrice: ${curr_price:.1f}\nBooked 50%: +${half_usd:.2f} (+110 pts)\n🛡️ SL Shifted to Breakeven: ${t['sl']:.1f}")

            # 2. MID-WAY CHOP / STALL GUARD
            elif t.get('tp1_hit', False) and (curr_price < t['tp2']) and (curr_price > float(t['sl'])):
                bars_passed = (live['time'] - t.get('tp1_bar_time', live['time'])) // 300000
                is_stalled = (bars_passed >= 2) and (curr_price < c0['low']) and (c0['close'] < c0['open'])
                
                if is_stalled:
                    self.is_closing = True
                    rem_qty = round(qty * 0.5, 4)
                    pts = round(curr_price - entry, 1)
                    rem_usd = round(pts * rem_qty, 2)
                    self.record_to_vault("LONG", entry, curr_price, "CHOP EXIT ⚡", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                    set_db_state("active_trade", None)
                    self.last_exit_time = time.time()
                    self.last_trade_bar = live['time']
                    mem['last_trade_time'] = time.time()
                    write_shared_memory(mem)
                    self.is_closing = False
                    send_telegram_alert(f"⚡ [MID-RUN CHOP EXIT] BTC LONG\nMarket stalling before TP2! Locked profit on current candle.\nExit: ${curr_price:.1f} (+{pts:.0f} pts, +${rem_usd:.2f})")
                    return

            # 3. TP2 Full Hit (+220 pts)
            elif curr_price >= t['tp2']:
                self.is_closing = True
                rem_qty = round(qty * 0.5, 4) if t.get('tp1_hit', False) else qty
                pts = round(t['tp2'] - entry, 1)
                rem_usd = round(pts * rem_qty, 2)
                self.record_to_vault("LONG", entry, t['tp2'], "TP2 FULL HIT 🔥", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                set_db_state("active_trade", None)
                self.last_exit_time = time.time()
                self.last_trade_bar = live['time']
                mem['consecutive_losses'] = 0
                mem['last_trade_time'] = time.time()
                write_shared_memory(mem)
                self.is_closing = False
                send_telegram_alert(f"🚀 [TP2 FULL HIT] BTC LONG Completed!\nFinal Exit: +${rem_usd:.2f} (+{pts:.0f} pts)\nExit Price: ${t['tp2']:.1f}")

            # 4. Breakeven or Stop Loss Exit
            elif curr_price <= float(t['sl']):
                self.is_closing = True
                if t.get('tp1_hit', False):
                    rem_qty = round(qty * 0.5, 4)
                    rem_usd = round(10.0 * rem_qty, 2)
                    self.record_to_vault("LONG", entry, t['sl'], "BE EXIT (50%) 🛡️", "+10", f"+${rem_usd:.2f}", rem_qty)
                    send_telegram_alert(f"🛡️ [EXIT] BTC LONG Breakeven Safe!\nRemaining 50% closed at +$10 cost (+${rem_usd:.2f}).\nExit: ${curr_price:.1f}")
                else:
                    loss_pts = round(entry - t['sl'], 1)
                    loss_usd = round(loss_pts * qty, 2)
                    self.record_to_vault("LONG", entry, t['sl'], "SL HIT 🛑", f"-{loss_pts:.0f}", f"-${loss_usd:.2f}", qty)
                    mem['consecutive_losses'] = mem.get('consecutive_losses', 0) + 1
                    mem['daily_loss_sum'] = mem.get('daily_loss_sum', 0.0) + loss_usd
                    send_telegram_alert(f"🛑 [EXIT] BTC LONG SL Hit\nLoss: -${loss_usd:.2f} (-{loss_pts:.0f} pts)\nExit: ${curr_price:.1f}")
                
                set_db_state("active_trade", None)
                self.last_exit_time = time.time()
                self.last_trade_bar = live['time']
                mem['last_trade_time'] = time.time()
                write_shared_memory(mem)
                self.is_closing = False

        # SHORT POSITION MONITOR
        elif t['type'] == 'SHORT':
            # 1. TP1 Trigger (+110 pts Drop) -> 50% Profit Book + Breakeven Shift
            if not t.get('tp1_hit', False) and curr_price <= t['tp1']:
                t['tp1_hit'] = True
                t['be_hit'] = True
                t['tp1_bar_time'] = live['time']
                t['sl'] = round(entry - 10.0, 1)
                half_qty = round(qty * 0.5, 4)
                half_usd = round(110.0 * half_qty, 2)
                
                self.record_to_vault("SHORT", entry, t['tp1'], "TP1 BOOK (50%) 🎯", "+110", f"+${half_usd:.2f}", half_qty)
                set_db_state("active_trade", t)
                send_telegram_alert(f"🎯 [TP1 HIT] BTC SHORT\nPrice: ${curr_price:.1f}\nBooked 50%: +${half_usd:.2f} (+110 pts)\n🛡️ SL Shifted to Breakeven: ${t['sl']:.1f}")

            # 2. MID-WAY CHOP / STALL GUARD
            elif t.get('tp1_hit', False) and (curr_price > t['tp2']) and (curr_price < float(t['sl'])):
                bars_passed = (live['time'] - t.get('tp1_bar_time', live['time'])) // 300000
                is_stalled = (bars_passed >= 2) and (curr_price > c0['high']) and (c0['close'] > c0['open'])
                
                if is_stalled:
                    self.is_closing = True
                    rem_qty = round(qty * 0.5, 4)
                    pts = round(entry - curr_price, 1)
                    rem_usd = round(pts * rem_qty, 2)
                    self.record_to_vault("SHORT", entry, curr_price, "CHOP EXIT ⚡", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                    set_db_state("active_trade", None)
                    self.last_exit_time = time.time()
                    self.last_trade_bar = live['time']
                    mem['last_trade_time'] = time.time()
                    write_shared_memory(mem)
                    self.is_closing = False
                    send_telegram_alert(f"⚡ [MID-RUN CHOP EXIT] BTC SHORT\nMarket stalling before TP2! Locked profit on current candle.\nExit: ${curr_price:.1f} (+{pts:.0f} pts, +${rem_usd:.2f})")
                    return

            # 3. TP2 Full Hit (+220 pts Drop)
            elif curr_price <= t['tp2']:
                self.is_closing = True
                rem_qty = round(qty * 0.5, 4) if t.get('tp1_hit', False) else qty
                pts = round(entry - t['tp2'], 1)
                rem_usd = round(pts * rem_qty, 2)
                self.record_to_vault("SHORT", entry, t['tp2'], "TP2 FULL HIT 🔥", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                set_db_state("active_trade", None)
                self.last_exit_time = time.time()
                self.last_trade_bar = live['time']
                mem['consecutive_losses'] = 0
                mem['last_trade_time'] = time.time()
                write_shared_memory(mem)
                self.is_closing = False
                send_telegram_alert(f"🩸 [TP2 FULL HIT] BTC SHORT Completed!\nFinal Exit: +${rem_usd:.2f} (+{pts:.0f} pts)\nExit Price: ${t['tp2']:.1f}")

            # 4. Breakeven or Stop Loss Exit
            elif curr_price >= float(t['sl']):
                self.is_closing = True
                if t.get('tp1_hit', False):
                    rem_qty = round(qty * 0.5, 4)
                    rem_usd = round(10.0 * rem_qty, 2)
                    self.record_to_vault("SHORT", entry, t['sl'], "BE EXIT (50%) 🛡️", "+10", f"+${rem_usd:.2f}", rem_qty)
                    send_telegram_alert(f"🛡️ [EXIT] BTC SHORT Breakeven Safe!\nRemaining 50% closed at +$10 cost (+${rem_usd:.2f}).\nExit: ${curr_price:.1f}")
                else:
                    loss_pts = round(t['sl'] - entry, 1)
                    loss_usd = round(loss_pts * qty, 2)
                    self.record_to_vault("SHORT", entry, t['sl'], "SL HIT 🛑", f"-{loss_pts:.0f}", f"-${loss_usd:.2f}", qty)
                    mem['consecutive_losses'] = mem.get('consecutive_losses', 0) + 1
                    mem['daily_loss_sum'] = mem.get('daily_loss_sum', 0.0) + loss_usd
                    send_telegram_alert(f"🛑 [EXIT] BTC SHORT SL Hit\nLoss: -${loss_usd:.2f} (-{loss_pts:.0f} pts)\nExit: ${curr_price:.1f}")
                
                set_db_state("active_trade", None)
                self.last_exit_time = time.time()
                self.last_trade_bar = live['time']
                mem['last_trade_time'] = time.time()
                write_shared_memory(mem)
                self.is_closing = False

    # --- ADVANCED SIGNAL LOGIC: PRE-MOVE SQUEEZE + ANTI-TRAP WICK FILTER + PHASE 2 HTF BIAS ---
    def evaluate_market_moves(self, closed, live):
        if get_db_state("kill_switch_active", False):
            return

        mem = read_shared_memory()
        today = datetime.now().strftime("%Y-%m-%d")
        if mem.get("current_day") != today:
            mem["current_day"] = today
            mem["daily_loss_sum"] = 0.0
            mem["consecutive_losses"] = 0
            write_shared_memory(mem)

        if mem.get("daily_loss_sum", 0.0) >= 10.0:
            return

        if mem.get('consecutive_losses', 0) >= 3:
            if time.time() - mem.get('last_trade_time', 0) < 7200:
                return

        if live['time'] <= self.last_trade_bar:
            return

        if time.time() - self.last_exit_time < 900:
            return

        sent_label = mem.get('sentiment_label', 'NEUTRAL')
        htf_trend = mem.get('htf_trend', 'NEUTRAL')

        # PRE-MOVE COMPRESSION ANALYSIS (3-4 Candles)
        recent_bars = closed[-4:]
        comp_high = max(c['high'] for c in recent_bars)
        comp_low = min(c['low'] for c in recent_bars)
        body_high = max(max(c['open'], c['close']) for c in recent_bars)
        body_low = min(min(c['open'], c['close']) for c in recent_bars)
        squeeze_range = comp_high - comp_low

        # PRE-MOVE FILTER: Squeeze between 35 and 160 pts confirms volatility buildup
        if squeeze_range < 35.0 or squeeze_range > 160.0:
            return

        c0 = closed[-1]
        curr_price = float(live['close'])
        live_open = float(live['open'])

        # EMA9 Alignment
        closes = [c['close'] for c in closed]
        k9 = 2 / 10
        ema9 = closes[0]
        for cl in closes[1:]: ema9 = (cl * k9) + (ema9 * (1 - k9))

        # VOLUME EXPANSION FILTER (Confirming real breakout, no low-volume fakeout)
        avg_vol = sum(c['vol'] for c in closed[-8:]) / 8.0
        has_volume = (c0['vol'] >= avg_vol * 1.15) or (live['vol'] >= avg_vol * 0.6)

        # LATE-ENTRY EXHAUSTION GUARD
        candle_run = abs(curr_price - live_open)
        if candle_run > 110.0:
            return  # Move nikal chuka hai, chasing strictly banned

        # ANTI-TRAP WICK FILTER: Entry triggers right at early ignition (5-15 pts above body)
        is_bottom_pump = (
            (curr_price >= body_high + 5.0) and
            (curr_price > comp_high - 10.0) and
            (curr_price >= live_open + 8.0) and
            (curr_price > ema9) and
            has_volume and
            (sent_label != 'FEAR') and
            (htf_trend != 'BEARISH')  # PHASE 2: Major 1H Downtrend me BUY block
        )

        is_top_dump = (
            (curr_price <= body_low - 5.0) and
            (curr_price < comp_low + 10.0) and
            (curr_price <= live_open - 8.0) and
            (curr_price < ema9) and
            has_volume and
            (sent_label != 'GREED') and
            (htf_trend != 'BULLISH')  # PHASE 2: Major 1H Uptrend me SHORT block
        )

        cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})
        pos_usd = float(cfg['capital']) * int(cfg['leverage'])
        entry = round(curr_price, 1)
        qty = round(pos_usd / entry, 4) or 0.001

        if is_bottom_pump:
            self.last_trade_bar = live['time']
            risk = 110.0
            sl = round(entry - risk, 1)
            tp1 = round(entry + 110.0, 1)
            tp2 = round(entry + 220.0, 1)

            trade_obj = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 
                'tp1': tp1, 'tp2': tp2, 'risk': risk, 
                'qty': qty, 'be_hit': False, 'tp1_hit': False
            }
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [EARLY BREAKOUT CONFIRMED] BTC LONG\n1H Bias: {htf_trend} 🟢\n\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f} (-{risk:.0f} pts)\n🎯 TP1 (50%): ${tp1:.1f} (+110 pts)\n🎯 TP2 (50%): ${tp2:.1f} (+220 pts)\n📦 Qty: {qty} BTC")

        elif is_top_dump:
            self.last_trade_bar = live['time']
            risk = 110.0
            sl = round(entry + risk, 1)
            tp1 = round(entry - 110.0, 1)
            tp2 = round(entry - 220.0, 1)

            trade_obj = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 
                'tp1': tp1, 'tp2': tp2, 'risk': risk, 
                'qty': qty, 'be_hit': False, 'tp1_hit': False
            }
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [EARLY BREAKDOWN CONFIRMED] BTC SHORT\n1H Bias: {htf_trend} 🔴\n\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f} (-{risk:.0f} pts)\n🎯 TP1 (50%): ${tp1:.1f} (+110 pts)\n🎯 TP2 (50%): ${tp2:.1f} (+220 pts)\n📦 Qty: {qty} BTC")

    def run(self):
        while True:
            mem = read_shared_memory()
            mem['commander_heartbeat'] = time.time()
            write_shared_memory(mem)

            closed, live = fetch_binance_klines()
            if closed and live:
                active = get_db_state("active_trade")
                if active: self.manage_position(active, live, closed)
                else: self.evaluate_market_moves(closed, live)

            time.sleep(1.2)

# --- 6. OVERSEER WATCHDOG ---
def run_overseer_watchdog():
    while True:
        try:
            mem = read_shared_memory()
            last_hb = mem.get("commander_heartbeat", time.time())
            if time.time() - last_hb > 45.0:
                send_telegram_alert("⚠️ [WATCHDOG] Engine Freeze Detected! Reviving Background Stream...")
                mem['commander_heartbeat'] = time.time()
                write_shared_memory(mem)
        except: pass
        time.sleep(10)

# --- 24/7 MULTI-ENGINE STARTER ---
@st.cache_resource
def launch_full_architecture():
    eid = str(uuid.uuid4())
    with open(WATCHDOG_LOCK, "w") as f: f.write(eid)

    threading.Thread(target=run_data_news_engine, daemon=False).start()
    cmd = MasterCommanderEngine(eid)
    threading.Thread(target=cmd.run, daemon=False).start()
    threading.Thread(target=run_overseer_watchdog, daemon=False).start()

    send_telegram_alert("⚡ [SYSTEM READY] Phase 1 + Phase 2 (1H Trend + Early Ignition) Online!")
    return cmd

launch_full_architecture()

# -------------------------------------------------------------
# FRONTEND UI & CONTROLS DOCK
# -------------------------------------------------------------
st.set_page_config(page_title="AI SNIPER BOT", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header, footer, #MainMenu { display: none !important; }
.block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
iframe { width: 100vw !important; height: calc(100vh - 5px) !important; border: none !important; display: block !important; }
</style>""", unsafe_allow_html=True)

conn = sqlite3.connect(DB_FILE, timeout=5)
cur = conn.cursor()
cur.execute("SELECT timestamp, trade_type, entry, result, pts, pnl_usd FROM trades ORDER BY id DESC")
rows = cur.fetchall()
history_list = [{"time": r[0], "type": r[1], "entry": r[2], "result": r[3], "pts": r[4], "pnl_usd": r[5]} for r in rows]

cur.execute("SELECT COUNT(*), SUM(CASE WHEN result LIKE '%TP%' OR result LIKE '%BE%' OR result LIKE '%CHOP%' THEN 1 ELSE 0 END) FROM trades")
t_count, win_count = cur.fetchone()
conn.close()

win_rate = round((win_count / t_count) * 100, 1) if t_count > 0 else 0.0
active_trade = get_db_state("active_trade")
kill_switch = get_db_state("kill_switch_active", False)

if active_trade and isinstance(active_trade, dict) and 'entry' in active_trade:
    e = float(active_trade['entry'])
    is_long = active_trade.get('type') == 'LONG'
    if 'tp1' not in active_trade or not active_trade['tp1']:
        active_trade['tp1'] = round(e + 110.0 if is_long else e - 110.0, 1)
    if 'tp2' not in active_trade or not active_trade['tp2']:
        active_trade['tp2'] = round(e + 220.0 if is_long else e - 220.0, 1)
    set_db_state("active_trade", active_trade)

cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})

js_active_trade = json.dumps(active_trade)
js_history = json.dumps(history_list)
js_stats = json.dumps({"total": t_count, "win_rate": win_rate})
js_cfg = json.dumps(cfg)
js_kill = json.dumps(kill_switch)

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

        .badge-scan { background: #00e676; color: #000; font-size: 8px; padding: 2px 4px; border-radius: 3px; font-weight: 900; }
        
        .stat-card { display: flex; flex-direction: column; min-width: 52px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }
        .stat-val { font-size: 10px; font-weight: 800; color: #fff; }
        
        .btn-compact { background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40; border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer; }
        
        .workspace { display: flex; flex-direction: column; width: 100vw; height: calc(100vh - 38px); }
        #chart-zone { width: 100vw; height: 53vh; background: #080a0f; }
        
        .trade-dock { width: 100vw; height: 38px; background: #0a0e17; border-top: 1px solid #1a2336; padding: 0 8px; display: flex; align-items: center; justify-content: space-between; font-size: 10px; }
        .dock-group { display: flex; align-items: center; gap: 5px; }
        .dock-input { background: #121824; border: 1px solid #23304a; color: #00e676; font-size: 10px; font-weight: 800; border-radius: 4px; padding: 2px 4px; width: 44px; text-align: center; }
        
        .btn-override-danger { background: rgba(255, 59, 48, 0.2); color: #ff3b30; border: 1px solid #ff3b30; border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 800; cursor: pointer; }
        .btn-override-warn { background: rgba(240, 185, 11, 0.2); color: #f0b90b; border: 1px solid #f0b90b; border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 800; cursor: pointer; }

        .bottom-bar { width: 100vw; height: 46px; background: #0d121c; border-top: 1px solid #1a2336; padding: 4px 8px; display: grid; grid-template-columns: 1fr 1fr 1fr 1.4fr; gap: 6px; align-items: center; }
        .metric-cell { display: flex; flex-direction: column; justify-content: center; background: #101624; padding: 2px 6px; border-radius: 4px; border: 1px solid #192233; height: 36px; }
        .cell-head { font-size: 7px; color: #62697a; font-weight: 800; text-transform: uppercase; line-height: 1; margin-bottom: 2px; }
        .cell-body { font-size: 9px; font-weight: 800; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); backdrop-filter: blur(5px); z-index: 999; align-items: center; justify-content: center; }
        .modal-box { background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px; width: 90vw; max-width: 400px; max-height: 80vh; display: flex; flex-direction: column; padding: 12px; }
        .history-list { overflow-y: auto; max-height: 250px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }
        
        .btn-modal-clear { 
            margin-top: 10px; 
            background: rgba(255, 59, 48, 0.25); 
            color: #ff3b30; 
            border: 1px solid rgba(255, 59, 48, 0.6); 
            border-radius: 6px; 
            padding: 10px; 
            font-size: 11px; 
            font-weight: 800; 
            cursor: pointer; 
            text-align: center; 
            width: 100%;
            display: block;
            outline: none;
        }
        .btn-modal-clear:active { background: #ff3b30; color: #fff; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">
            <span class="pulse-dot"></span>
            ⚡ QUANT RADAR <span class="badge-scan">PHASE 2</span>
        </div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">TP1 (50%)</div><div id="disp-tp1" class="stat-val" style="color:#00e676;">--</div></div>
        <div class="stat-card"><div class="stat-label">TP2 (50%)</div><div id="disp-tp2" class="stat-val" style="color:#00b0ff;">--</div></div>
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
                <span style="color:#62697a;">POS:</span>
                <b id="calc-qty" style="color:#38bdf8; font-size:10px;">0.0119 BTC</b>
            </div>
            
            <div class="dock-group">
                <button type="button" class="btn-override-warn" onclick="triggerForceClose()">⚡ FORCE CLOSE</button>
                <button type="button" class="btn-override-danger" id="btn-kill" onclick="triggerEmergencyToggle()">🚨 KILL SWITCH</button>
            </div>
        </div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">HTF 1H BIAS</span>
                <div class="cell-body" id="htf-status" style="color:#00e676;">PHASE 2 ACTIVE 🎯</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TP1 TARGET</span>
                <div class="cell-body" style="color:#00e676;">+110 PTS (50%)</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TP2 TARGET</span>
                <div class="cell-body" style="color:#38bdf8;">+220 PTS RUN</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">SCAN STATUS</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">SCANNING SQUEEZE...</div>
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
            <button type="button" class="btn-modal-clear" onclick="triggerVaultClear()">🗑️ ONE-CLICK CLEAR VAULT</button>
        </div>
    </div>

    <script>
        const IST_OFFSET = 5.5 * 3600;
        let activeTrade = __ACTIVE_TRADE__;
        let tradeHistory = __TRADE_HISTORY__;
        let stats = __STATS__;
        let cfg = __CFG__;
        let killActive = __KILL_SWITCH__;

        document.getElementById('input-amount').value = cfg.capital;
        document.getElementById('input-lev').value = cfg.leverage;

        if (killActive) {
            document.getElementById('btn-kill').style.background = "#ff3b30";
            document.getElementById('btn-kill').style.color = "#fff";
            document.getElementById('btn-kill').innerText = "🟢 RESUME BOT";
            document.getElementById('htf-status').innerText = "BOT FROZEN 🛑";
            document.getElementById('htf-status').style.color = "#ff3b30";
        }

        let lineEntry = null, lineSL = null, lineTP1 = null, lineTP2 = null;
        let currentPrice = 84000.0;

        function toggleModal(show) { document.getElementById('modal-bg').style.display = show ? 'flex' : 'none'; }
        function handleBgClick(e) { if (e.target.id === 'modal-bg') toggleModal(false); }
        
        function triggerVaultClear() {
            tradeHistory = [];
            stats.total = 0;
            stats.win_rate = 0.0;
            document.getElementById('stat-total').innerText = "0";
            document.getElementById('stat-rate').innerText = "0.0%";
            document.getElementById('hist-count').innerText = "0";
            document.getElementById('history-container').innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">Vault Clean (0 trades)...</div>';
            
            try {
                window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?clear_vault=confirmed";
            } catch(e) {
                window.location.href = window.location.pathname + "?clear_vault=confirmed";
            }
        }

        function triggerForceClose() {
            if (!activeTrade) { alert("No active trade to close!"); return; }
            if (confirm("Force close active position at market price?")) {
                try {
                    window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?force_close=confirmed";
                } catch(e) {
                    window.location.href = window.location.pathname + "?force_close=confirmed";
                }
            }
        }

        function triggerEmergencyToggle() {
            let msg = killActive ? "Resume bot execution?" : "EMERGENCY STOP: Freeze all trading activities?";
            if (confirm(msg)) {
                try {
                    window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?toggle_emergency=confirmed";
                } catch(e) {
                    window.location.href = window.location.pathname + "?toggle_emergency=confirmed";
                }
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

        function clearAllLines() {
            if (lineEntry) { try { series.removePriceLine(lineEntry); } catch(e){} lineEntry = null; }
            if (lineSL) { try { series.removePriceLine(lineSL); } catch(e){} lineSL = null; }
            if (lineTP1) { try { series.removePriceLine(lineTP1); } catch(e){} lineTP1 = null; }
            if (lineTP2) { try { series.removePriceLine(lineTP2); } catch(e){} lineTP2 = null; }
        }

        function renderMasterInterface() {
            clearAllLines();

            if (activeTrade && activeTrade.entry) {
                let entryVal = parseFloat(activeTrade.entry);
                let slVal = parseFloat(activeTrade.sl);
                let isLong = activeTrade.type === "LONG";

                let tp1Val = activeTrade.tp1 ? parseFloat(activeTrade.tp1) : (isLong ? (entryVal + 110.0) : (entryVal - 110.0));
                let tp2Val = activeTrade.tp2 ? parseFloat(activeTrade.tp2) : (isLong ? (entryVal + 220.0) : (entryVal - 220.0));

                lineEntry = series.createPriceLine({ 
                    price: entryVal, color: '#38bdf8', lineWidth: 2, 
                    lineStyle: LightweightCharts.LineStyle.Dashed, 
                    axisLabelVisible: true, 
                    title: 'ENTRY $' + entryVal.toFixed(1) 
                });
                
                lineSL = series.createPriceLine({ 
                    price: slVal, color: '#ff3b30', lineWidth: 2, 
                    lineStyle: LightweightCharts.LineStyle.Solid, 
                    axisLabelVisible: true, 
                    title: (activeTrade.be_hit ? 'BE SL $' : 'SAFE SL$') + slVal.toFixed(1) 
                });

                if (!activeTrade.tp1_hit) {
                    lineTP1 = series.createPriceLine({ 
                        price: tp1Val, color: '#00e676', lineWidth: 2, 
                        lineStyle: LightweightCharts.LineStyle.Solid, 
                        axisLabelVisible: true, 
                        title: 'TP1 (50%) $' + tp1Val.toFixed(1) 
                    });
                }

                lineTP2 = series.createPriceLine({ 
                    price: tp2Val, color: '#00b0ff', lineWidth: 2, 
                    lineStyle: LightweightCharts.LineStyle.Solid, 
                    axisLabelVisible: true, 
                    title: 'TP2 (50%) $' + tp2Val.toFixed(1) 
                });

                document.getElementById('disp-entry').innerText = "$" + entryVal.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + slVal.toFixed(1);
                document.getElementById('disp-tp1').innerText = activeTrade.tp1_hit ? "BOOKED ✅" : ("$" + tp1Val.toFixed(1));
                document.getElementById('disp-tp2').innerText = "$" + tp2Val.toFixed(1);

                document.getElementById('val-setup').innerText = "RIDING " + activeTrade.type + (activeTrade.tp1_hit ? " (BE SHIELD)" : "") + " 🚀";
                document.getElementById('val-setup').style.color = isLong ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp1').innerText = "--";
                document.getElementById('disp-tp2').innerText = "--";
                document.getElementById('val-setup').innerText = killActive ? "BOT STOPPED (KILL SWITCH)" : "SCANNING SQUEEZE...";
                document.getElementById('val-setup').style.color = killActive ? "#ff3b30" : "#38bdf8";
            }

            document.getElementById('hist-count').innerText = stats.total;
            document.getElementById('stat-total').innerText = stats.total;
            document.getElementById('stat-rate').innerText = stats.win_rate + "%";

            const histCont = document.getElementById('history-container');
            if (tradeHistory.length > 0) {
                histCont.innerHTML = "";
                tradeHistory.forEach(item => {
                    let resCol = item.result.includes("TP") || item.result.includes("BE") || item.result.includes("CHOP") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    let pnlDisp = item.pnl_usd ? `<b style="color:${resCol}; margin-left:4px;">(${item.pnl_usd})</b>` : '';
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span>${item.time} <b style="color:${typeCol};">${item.type}</b> @ $${parseFloat(item.entry).toFixed(1)}</span>
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
                    let cdata = data.map(d => ({ 
                        time: (d[0] - (d[0] % 300000)) / 1000, 
                        open: parseFloat(d[1]), 
                        high: parseFloat(d[2]), 
                        low: parseFloat(d[3]), 
                        close: parseFloat(d[4]) 
                    }));
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

                if (activeTrade && activeTrade.entry) {
                    let isLong = activeTrade.type === "LONG";
                    let slVal = parseFloat(activeTrade.sl);
                    let tp2Val = activeTrade.tp2 ? parseFloat(activeTrade.tp2) : (isLong ? (activeTrade.entry + 220) : (activeTrade.entry - 220));

                    if (isLong && (price <= slVal || price >= tp2Val)) {
                        activeTrade = null;
                        renderMasterInterface();
                    } else if (!isLong && (price >= slVal || price <= tp2Val)) {
                        activeTrade = null;
                        renderMasterInterface();
                    }
                }

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
                          .replace("__CFG__", js_cfg)\
                          .replace("__KILL_SWITCH__", js_kill)

components.html(final_html, height=710, scrolling=False)
