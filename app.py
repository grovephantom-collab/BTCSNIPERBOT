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
# PRO QUANT ENGINE: CLOSED-CANDLE TREND STRUCTURE + HARD RISK LOCK + DYNAMIC ATR
# ==============================================================================

BOT_TOKEN = "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM"
CHAT_ID = "7886716805"
DB_FILE = "sniper_vault.db"
SHARED_MEMORY_FILE = "sniper_brain_data.json"
WATCHDOG_LOCK = "overseer_watchdog.pid"

# --- 1. LOGGING & DATABASE (SQLITE WITH UNIQUE RESTRAINT) ---
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

# --- UI ACTION DISPATCHERS ---
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
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        e = float(act['entry'])
        q = float(act.get('qty', 0.01))
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO trades (timestamp, symbol, trade_type, entry, exit_price, result, pts, pnl_usd, qty) 
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (now_str, "BTCUSDT", act['type'], e, e, "MANUAL FORCE CLOSE ⚠️", "0", "$0.00", q))
            conn.commit()
            conn.close()
        except: pass
        set_db_state("active_trade", None)
        set_db_state("last_exit_epoch", time.time())
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
        "htf_trend": "NEUTRAL",
        "funding_rate": 0.0,
        "book_imbalance": 1.0,
        "ai_score": 75,
        "atr_val": 45.0
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

# --- PHASE 4 ML UTILITIES: RSI & ATR ENGINE ---
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50.0
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def calculate_atr(klines, period=14):
    if len(klines) < period + 1: return 45.0
    trs = []
    for i in range(1, len(klines)):
        h = klines[i]['high']
        l = klines[i]['low']
        prev_c = klines[i-1]['close']
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 1)

def calculate_ema(prices, period):
    if len(prices) < period: return prices[-1]
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

# --- 3. DATA, SENTIMENT, MICRO-DATA & PHASE 4 AI/ML ENGINE ---
def run_data_news_engine():
    while True:
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3)
            score = 50
            label = "NEUTRAL"
            if r.status_code == 200:
                score = int(r.json()['data'][0]['value'])
                label = "GREED" if score >= 60 else ("FEAR" if score <= 40 else "NEUTRAL")
            
            htf_trend = "NEUTRAL"
            try:
                r_htf = requests.get("https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=40", timeout=3)
                if r_htf.status_code == 200:
                    raw_htf = r_htf.json()
                    closes = [float(x[4]) for x in raw_htf]
                    ema20 = calculate_ema(closes, 20)
                    curr_htf_price = closes[-1]
                    if curr_htf_price > ema20 + 20.0:
                        htf_trend = "BULLISH"
                    elif curr_htf_price < ema20 - 20.0:
                        htf_trend = "BEARISH"
            except: pass

            funding_rate = 0.0
            try:
                r_fund = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", timeout=3)
                if r_fund.status_code == 200:
                    funding_rate = float(r_fund.json().get('lastFundingRate', 0.0))
            except: pass

            book_imbalance = 1.0
            try:
                r_depth = requests.get("https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=20", timeout=3)
                if r_depth.status_code == 200:
                    depth_data = r_depth.json()
                    total_bids = sum(float(x[1]) for x in depth_data.get('bids', []))
                    total_asks = sum(float(x[1]) for x in depth_data.get('asks', []))
                    if total_asks > 0:
                        book_imbalance = round(total_bids / total_asks, 2)
            except: pass

            ai_score = 75
            atr_val = 45.0
            try:
                r_k = requests.get("https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=40", timeout=3)
                if r_k.status_code == 200:
                    raw_k = r_k.json()
                    k_list = [{'high': float(x[2]), 'low': float(x[3]), 'close': float(x[4])} for x in raw_k]
                    closes_5m = [x['close'] for x in k_list]
                    rsi = calculate_rsi(closes_5m, 14)
                    atr_val = calculate_atr(k_list, 14)
                    
                    base_prob = 70
                    if 45 <= rsi <= 65: base_prob += 10
                    elif rsi > 75 or rsi < 25: base_prob -= 15
                    if 35 <= atr_val <= 110: base_prob += 10
                    ai_score = max(40, min(95, base_prob))
            except: pass

            mem = read_shared_memory()
            mem['sentiment_score'] = score
            mem['sentiment_label'] = label
            mem['htf_trend'] = htf_trend
            mem['funding_rate'] = funding_rate
            mem['book_imbalance'] = book_imbalance
            mem['ai_score'] = ai_score
            mem['atr_val'] = atr_val
            mem['last_heartbeat'] = time.time()
            write_shared_memory(mem)
        except: pass
        time.sleep(40)

# --- 4. FAST BINANCE DATA FETCHER ---
def fetch_binance_klines():
    urls = [
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=60",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=60"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=2.5)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) >= 35:
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
        self.last_exit_bar = 0
        self.locked_closing_id = None
        self.tp1_locked = False
        self.sl_locked = False

    def record_to_vault(self, t_type, entry, exit_price, result, pts, pnl_usd, qty):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO trades (timestamp, symbol, trade_type, entry, exit_price, result, pts, pnl_usd, qty) 
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (now_str, "BTCUSDT", t_type, float(entry), float(exit_price), result, str(pts), str(pnl_usd), float(qty)))
            conn.commit()
            conn.close()
        except: pass

    def manage_position(self, t, live, closed):
        curr_trade_ref = f"{t.get('type')}_{t.get('entry')}"
        if self.locked_closing_id == curr_trade_ref:
            return

        qty = float(t.get("qty", 0.01))
        curr_price = float(live['close'])
        entry = float(t['entry'])

        c0 = closed[-1]

        # LONG POSITION MONITOR
        if t['type'] == 'LONG':
            # Dynamic TP1 Hit Check
            if not t.get('tp1_hit', False) and not self.tp1_locked and curr_price >= t['tp1']:
                self.tp1_locked = True
                t['tp1_hit'] = True
                t['be_hit'] = True
                t['tp1_bar_time'] = live['time']
                t['sl'] = round(entry + 10.0, 1)  # Breakeven shifted
                half_qty = round(qty * 0.5, 4)
                booked_pts = round(t['tp1'] - entry, 1)
                half_usd = round(booked_pts * half_qty, 2)
                
                set_db_state("active_trade", t)
                self.record_to_vault("LONG", entry, t['tp1'], "TP1 BOOK (50%) 🎯", f"+{booked_pts:.0f}", f"+${half_usd:.2f}", half_qty)
                send_telegram_alert(f"🎯 [TP1 HIT] BTC LONG\nPrice: ${curr_price:.1f}\nBooked 50%: +${half_usd:.2f} (+{booked_pts:.0f} pts)\n🛡️ SL Shifted to Breakeven: ${t['sl']:.1f}")

            elif t.get('tp1_hit', False) and (curr_price < t['tp2']) and (curr_price > float(t['sl'])):
                bars_passed = (live['time'] - t.get('tp1_bar_time', live['time'])) // 300000
                is_stalled = (bars_passed >= 2) and (curr_price < c0['low']) and (c0['close'] < c0['open'])
                
                if is_stalled:
                    self.locked_closing_id = curr_trade_ref
                    self.tp1_locked = False
                    self.sl_locked = False
                    set_db_state("active_trade", None)
                    set_db_state("last_exit_epoch", time.time())
                    self.last_exit_bar = live['time']
                    
                    rem_qty = round(qty * 0.5, 4)
                    pts = round(curr_price - entry, 1)
                    rem_usd = round(pts * rem_qty, 2)
                    self.record_to_vault("LONG", entry, curr_price, "CHOP EXIT ⚡", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                    
                    self.last_trade_bar = live['time']
                    send_telegram_alert(f"⚡ [MID-RUN CHOP EXIT] BTC LONG\nMarket stalling before TP2! Locked profit on current candle.\nExit: ${curr_price:.1f} (+{pts:.0f} pts, +${rem_usd:.2f})")
                    return

            elif curr_price >= t['tp2']:
                self.locked_closing_id = curr_trade_ref
                self.tp1_locked = False
                self.sl_locked = False
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                rem_qty = round(qty * 0.5, 4) if t.get('tp1_hit', False) else qty
                pts = round(t['tp2'] - entry, 1)
                rem_usd = round(pts * rem_qty, 2)
                self.record_to_vault("LONG", entry, t['tp2'], "TP2 FULL HIT 🔥", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                
                self.last_trade_bar = live['time']
                send_telegram_alert(f"🚀 [TP2 FULL HIT] BTC LONG Completed!\nFinal Exit: +${rem_usd:.2f} (+{pts:.0f} pts)\nExit Price: ${t['tp2']:.1f}")

            elif curr_price <= float(t['sl']):
                if self.sl_locked: return
                self.sl_locked = True
                self.locked_closing_id = curr_trade_ref
                self.tp1_locked = False
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                if t.get('tp1_hit', False):
                    rem_qty = round(qty * 0.5, 4)
                    rem_usd = round(10.0 * rem_qty, 2)
                    self.record_to_vault("LONG", entry, t['sl'], "BE EXIT (50%) 🛡️", "+10", f"+${rem_usd:.2f}", rem_qty)
                    send_telegram_alert(f"🛡️ [EXIT] BTC LONG Breakeven Safe!\nRemaining 50% closed at +$10 cost (+${rem_usd:.2f}).\nExit: ${curr_price:.1f}")
                else:
                    loss_pts = round(entry - t['sl'], 1)
                    loss_usd = round(loss_pts * qty, 2)
                    self.record_to_vault("LONG", entry, t['sl'], "SL HIT 🛑", f"-{loss_pts:.0f}", f"-${loss_usd:.2f}", qty)
                    send_telegram_alert(f"🛑 [EXIT] BTC LONG SL Hit\nLoss: -${loss_usd:.2f} (-{loss_pts:.0f} pts)\nExit: ${curr_price:.1f}")
                
                self.last_trade_bar = live['time']

        # SHORT POSITION MONITOR
        elif t['type'] == 'SHORT':
            # Dynamic TP1 Hit Check
            if not t.get('tp1_hit', False) and not self.tp1_locked and curr_price <= t['tp1']:
                self.tp1_locked = True
                t['tp1_hit'] = True
                t['be_hit'] = True
                t['tp1_bar_time'] = live['time']
                t['sl'] = round(entry - 10.0, 1)  # Breakeven shifted
                half_qty = round(qty * 0.5, 4)
                booked_pts = round(entry - t['tp1'], 1)
                half_usd = round(booked_pts * half_qty, 2)
                
                set_db_state("active_trade", t)
                self.record_to_vault("SHORT", entry, t['tp1'], "TP1 BOOK (50%) 🎯", f"+{booked_pts:.0f}", f"+${half_usd:.2f}", half_qty)
                send_telegram_alert(f"🎯 [TP1 HIT] BTC SHORT\nPrice: ${curr_price:.1f}\nBooked 50%: +${half_usd:.2f} (+{booked_pts:.0f} pts)\n🛡️ SL Shifted to Breakeven: ${t['sl']:.1f}")

            elif t.get('tp1_hit', False) and (curr_price > t['tp2']) and (curr_price < float(t['sl'])):
                bars_passed = (live['time'] - t.get('tp1_bar_time', live['time'])) // 300000
                is_stalled = (bars_passed >= 2) and (curr_price > c0['high']) and (c0['close'] > c0['open'])
                
                if is_stalled:
                    self.locked_closing_id = curr_trade_ref
                    self.tp1_locked = False
                    self.sl_locked = False
                    set_db_state("active_trade", None)
                    set_db_state("last_exit_epoch", time.time())
                    self.last_exit_bar = live['time']

                    rem_qty = round(qty * 0.5, 4)
                    pts = round(entry - curr_price, 1)
                    rem_usd = round(pts * rem_qty, 2)
                    self.record_to_vault("SHORT", entry, curr_price, "CHOP EXIT ⚡", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                    
                    self.last_trade_bar = live['time']
                    send_telegram_alert(f"⚡ [MID-RUN CHOP EXIT] BTC SHORT\nMarket stalling before TP2! Locked profit on current candle.\nExit: ${curr_price:.1f} (+{pts:.0f} pts, +${rem_usd:.2f})")
                    return

            elif curr_price <= t['tp2']:
                self.locked_closing_id = curr_trade_ref
                self.tp1_locked = False
                self.sl_locked = False
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                rem_qty = round(qty * 0.5, 4) if t.get('tp1_hit', False) else qty
                pts = round(entry - t['tp2'], 1)
                rem_usd = round(pts * rem_qty, 2)
                self.record_to_vault("SHORT", entry, t['tp2'], "TP2 FULL HIT 🔥", f"+{pts:.0f}", f"+${rem_usd:.2f}", rem_qty)
                
                self.last_trade_bar = live['time']
                send_telegram_alert(f"🩸 [TP2 FULL HIT] BTC SHORT Completed!\nFinal Exit: +${rem_usd:.2f} (+{pts:.0f} pts)\nExit Price: ${t['tp2']:.1f}")

            elif curr_price >= float(t['sl']):
                if self.sl_locked: return
                self.sl_locked = True
                self.locked_closing_id = curr_trade_ref
                self.tp1_locked = False
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                if t.get('tp1_hit', False):
                    rem_qty = round(qty * 0.5, 4)
                    rem_usd = round(10.0 * rem_qty, 2)
                    self.record_to_vault("SHORT", entry, t['sl'], "BE EXIT (50%) 🛡️", "+10", f"+${rem_usd:.2f}", rem_qty)
                    send_telegram_alert(f"🛡️ [EXIT] BTC SHORT Breakeven Safe!\nRemaining 50% closed at +$10 cost (+${rem_usd:.2f}).\nExit: ${curr_price:.1f}")
                else:
                    loss_pts = round(t['sl'] - entry, 1)
                    loss_usd = round(loss_pts * qty, 2)
                    self.record_to_vault("SHORT", entry, t['sl'], "SL HIT 🛑", f"-{loss_pts:.0f}", f"-${loss_usd:.2f}", qty)
                    send_telegram_alert(f"🛑 [EXIT] BTC SHORT SL Hit\nLoss: -${loss_usd:.2f} (-{loss_pts:.0f} pts)\nExit: ${curr_price:.1f}")
                
                self.last_trade_bar = live['time']

    # --- ADVANCED SIGNAL LOGIC: CANDLE CLOSE STRUCTURE + 4 ENGINES ---
    def evaluate_market_moves(self, closed, live):
        if get_db_state("kill_switch_active", False):
            return

        # 1. HARD 15-MINUTE (900s) EXIT COOLDOWN
        last_exit_epoch = get_db_state("last_exit_epoch", 0)
        if time.time() - last_exit_epoch < 900:
            return

        if self.last_exit_bar > 0:
            bars_since_exit = (live['time'] - self.last_exit_bar) // 300000
            if bars_since_exit < 3:
                return

        # 2. SQLITE RISK BARRIER: 3 LOSSES & -$10 LIMIT
        consec_losses, daily_loss = check_db_risk_guard()
        if daily_loss >= 10.0:
            return

        if consec_losses >= 3:
            if time.time() - last_exit_epoch < 7200:
                return

        # Bar Lock: ek candle par sirf ek hi trade ho sakti hai
        if live['time'] <= self.last_trade_bar:
            return

        # Running tick execution block (Candle ke pehle 20 second me fresh close par entry)
        candle_elapsed = (time.time() * 1000 - live['time']) / 1000
        if candle_elapsed > 120.0:
            return

        mem = read_shared_memory()
        sent_label = mem.get('sentiment_label', 'NEUTRAL')
        htf_trend = mem.get('htf_trend', 'NEUTRAL')
        funding_rate = mem.get('funding_rate', 0.0)
        book_imbalance = mem.get('book_imbalance', 1.0)
        ai_score = mem.get('ai_score', 75)
        atr_val = mem.get('atr_val', 45.0)

        # AI Confidence Gate
        if ai_score < 65:
            return

        # Exhaustion Shield (Pichle 1 ghante ka run check)
        recent_12 = closed[-12:]
        h12 = max(c['high'] for c in recent_12)
        l12 = min(c['low'] for c in recent_12)
        total_hour_run = h12 - l12
        max_run_limit = max(450.0, atr_val * 7.5)

        curr_price = float(live['close'])
        is_dump_exhausted = (curr_price <= l12 + 60.0) and (total_hour_run > max_run_limit)
        is_pump_exhausted = (curr_price >= h12 - 60.0) and (total_hour_run > max_run_limit)

        if is_dump_exhausted or is_pump_exhausted:
            return

        # Candle Analysis on CLOSED candle (c0)
        c0 = closed[-1]
        c1 = closed[-2]
        c0_range = max(1.0, c0['high'] - c0['low'])
        c0_body = abs(c0['close'] - c0['open'])
        c0_upper_wick = c0['high'] - max(c0['open'], c0['close'])
        c0_lower_wick = min(c0['open'], c0['close']) - c0['low']

        # Wick Rejection Gate
        if (c0_lower_wick / c0_range) >= 0.40 or (c0_upper_wick / c0_range) >= 0.40:
            return

        # Body strength gate (Chop doji candles ko reject karega)
        if (c0_body / c0_range) < 0.50:
            return

        # EMAs on 5m Closed Data
        closes = [c['close'] for c in closed]
        ema9 = calculate_ema(closes, 9)
        ema21 = calculate_ema(closes, 21)

        # Volume Expansion Gate
        avg_vol = sum(c['vol'] for c in closed[-8:]) / 8.0
        has_volume = c0['vol'] >= avg_vol * 1.25

        # Funding & Depth Safe Checks
        is_funding_safe_long = funding_rate <= 0.0006
        is_funding_safe_short = funding_rate >= -0.0006
        has_bid_support = book_imbalance >= 0.85
        has_ask_pressure = book_imbalance <= 1.25

        # --- RIGID ENTRY CONDITIONS (CONFIRMED STRUCTURE BREAK) ---
        is_bullish_breakout = (
            (c0['close'] > c0['open']) and
            (c0['close'] > ema9) and
            (ema9 > ema21) and
            (c0['close'] > c1['high']) and
            has_volume and
            (sent_label != 'FEAR') and
            (htf_trend == 'BULLISH') and  # 1H Supreme Court Aligned
            is_funding_safe_long and
            has_bid_support and
            not is_pump_exhausted
        )

        is_bearish_breakdown = (
            (c0['close'] < c0['open']) and
            (c0['close'] < ema9) and
            (ema9 < ema21) and
            (c0['close'] < c1['low']) and
            has_volume and
            (sent_label != 'GREED') and
            (htf_trend == 'BEARISH') and  # 1H Supreme Court Aligned
            is_funding_safe_short and
            has_ask_pressure and
            not is_dump_exhausted
        )

        cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})
        pos_usd = float(cfg['capital']) * int(cfg['leverage'])
        entry = round(curr_price, 1)
        qty = round(pos_usd / entry, 4) or 0.001

        # DYNAMIC ATR CALCULATION
        dyn_sl_pts = round(max(45.0, min(160.0, atr_val * 1.5)), 1)
        dyn_tp1_pts = round(max(40.0, min(140.0, atr_val * 1.2)), 1)
        dyn_tp2_pts = round(max(80.0, min(280.0, atr_val * 2.4)), 1)

        if is_bullish_breakout:
            self.last_trade_bar = live['time']
            self.locked_closing_id = None
            self.tp1_locked = False
            self.sl_locked = False
            sl = round(entry - dyn_sl_pts, 1)
            tp1 = round(entry + dyn_tp1_pts, 1)
            tp2 = round(entry + dyn_tp2_pts, 1)

            trade_obj = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 
                'tp1': tp1, 'tp2': tp2, 'risk': dyn_sl_pts, 
                'qty': qty, 'be_hit': False, 'tp1_hit': False
            }
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [CONFIRMED 5M BREAKOUT] BTC LONG\n1H Trend: {htf_trend} 🟢 | AI Score: {ai_score}%\nDepth: {book_imbalance}x | Vol: +{int((c0['vol']/avg_vol - 1)*100)}%\n\n📍 Entry: ${entry:.1f}\n🛡️ Dynamic SL: ${sl:.1f} (-{dyn_sl_pts:.0f} pts)\n🎯 TP1 (50%): ${tp1:.1f} (+{dyn_tp1_pts:.0f} pts)\n🎯 TP2 (50%): ${tp2:.1f} (+{dyn_tp2_pts:.0f} pts)\n📦 Qty: {qty} BTC")

        elif is_bearish_breakdown:
            self.last_trade_bar = live['time']
            self.locked_closing_id = None
            self.tp1_locked = False
            self.sl_locked = False
            sl = round(entry + dyn_sl_pts, 1)
            tp1 = round(entry - dyn_tp1_pts, 1)
            tp2 = round(entry - dyn_tp2_pts, 1)

            trade_obj = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 
                'tp1': tp1, 'tp2': tp2, 'risk': dyn_sl_pts, 
                'qty': qty, 'be_hit': False, 'tp1_hit': False
            }
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [CONFIRMED 5M BREAKDOWN] BTC SHORT\n1H Trend: {htf_trend} 🔴 | AI Score: {ai_score}%\nDepth: {book_imbalance}x | Vol: +{int((c0['vol']/avg_vol - 1)*100)}%\n\n📍 Entry: ${entry:.1f}\n🛡️ Dynamic SL: ${sl:.1f} (-{dyn_sl_pts:.0f} pts)\n🎯 TP1 (50%): ${tp1:.1f} (+{dyn_tp1_pts:.0f} pts)\n🎯 TP2 (50%): ${tp2:.1f} (+{dyn_tp2_pts:.0f} pts)\n📦 Qty: {qty} BTC")

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

    send_telegram_alert("⚡ [SYSTEM READY] Precision Trend Structure & Dynamic ATR Online!")
    return cmd

launch_full_architecture()

# -------------------------------------------------------------
# FRONTEND UI & CONTROLS DOCK (FLICKER-FREE FRAGMENT AUTO-SYNC)
# -------------------------------------------------------------
st.set_page_config(page_title="AI SNIPER BOT", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header, footer, #MainMenu { display: none !important; }
.block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
iframe { width: 100vw !important; height: calc(100vh - 5px) !important; border: none !important; display: block !important; }
</style>""", unsafe_allow_html=True)

@st.fragment(run_every=2)
def render_live_dashboard():
    conn = sqlite3.connect(DB_FILE, timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT timestamp, trade_type, entry, result, pts, pnl_usd FROM trades ORDER BY id DESC")
    rows = cur.fetchall()
    history_list = [{"time": r[0].split(" ")[-1] if " " in r[0] else r[0], "type": r[1], "entry": r[2], "result": r[3], "pts": r[4], "pnl_usd": r[5]} for r in rows]

    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result LIKE '%TP%' OR result LIKE '%BE%' OR result LIKE '%CHOP%' THEN 1 ELSE 0 END) FROM trades")
    t_count, win_count = cur.fetchone()
    conn.close()

    win_rate = round((win_count / t_count) * 100, 1) if t_count > 0 else 0.0
    active_trade = get_db_state("active_trade")
    kill_switch = get_db_state("kill_switch_active", False)

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
            ⚡ QUANT RADAR <span class="badge-scan">DYNAMIC STRUCTURE</span>
        </div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">DYN SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">DYN TP1</div><div id="disp-tp1" class="stat-val" style="color:#00e676;">--</div></div>
        <div class="stat-card"><div class="stat-label">DYN TP2</div><div id="disp-tp2" class="stat-val" style="color:#00b0ff;">--</div></div>
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
                <span class="cell-head">LOCK SYSTEM</span>
                <div class="cell-body" id="htf-status" style="color:#00e676;">SQLITE RISK GATE 🛡️</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TP1 TARGET</span>
                <div class="cell-body" style="color:#00e676;">DYNAMIC (50%)</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TP2 TARGET</span>
                <div class="cell-body" style="color:#38bdf8;">DYNAMIC RUN</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">SCAN STATUS</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">AWAITING CONFIRMATION...</div>
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
                let tp1Val = parseFloat(activeTrade.tp1);
                let tp2Val = parseFloat(activeTrade.tp2);
                let isLong = activeTrade.type === "LONG";

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
                document.getElementById('val-setup').innerText = killActive ? "BOT STOPPED (KILL SWITCH)" : "AWAITING CONFIRMATION...";
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
                    let tp2Val = parseFloat(activeTrade.tp2);

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

render_live_dashboard()
