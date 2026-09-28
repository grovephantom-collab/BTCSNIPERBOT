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
# PHASE 1: INSTITUTIONAL OI DELTA + 2-3 HR SWING SNIPER + TRAILING ENGINE
# ==============================================================================

BOT_TOKEN = "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM"
CHAT_ID = "7886716805"
DISCORD_WEBHOOK_URL = ""  # Optional: Discord webhook URL yahan paste kar sakte hain
DB_FILE = "sniper_vault.db"
SHARED_MEMORY_FILE = "sniper_brain_data.json"
WATCHDOG_LOCK = "overseer_watchdog.pid"

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

# --- ALERTS ENGINE (TELEGRAM + DISCORD) ---
def _send_tg_worker(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(CHAT_ID).strip(), "text": msg}
    try:
        requests.post(url, json=payload, timeout=3)
    except: pass

    if DISCORD_WEBHOOK_URL.strip():
        try:
            requests.post(DISCORD_WEBHOOK_URL.strip(), json={"content": msg}, timeout=3)
        except: pass

def send_alert(msg):
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
        "oi_delta": 0.0,          # Open Interest percentage change (Phase 1)
        "oi_current": 0.0,
        "atr_val": 45.0,
        "paper_trading": True     # True: Paper Mode, False: Live
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

# --- UTILITIES: ATR & EMA ---
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

# --- 3. DATA & DERIVATIVES FLOW ENGINE (OPEN INTEREST & FUNDING) ---
def run_data_news_engine():
    prev_oi = None
    while True:
        try:
            # 1. 1-Hour Macro Trend
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

            # 2. Binance Futures Open Interest (Institutional Position Flow)
            oi_val = 0.0
            oi_delta_pct = 0.0
            try:
                r_oi = requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT", timeout=3)
                if r_oi.status_code == 200:
                    oi_val = float(r_oi.json().get('openInterest', 0.0))
                    if prev_oi and prev_oi > 0:
                        oi_delta_pct = round(((oi_val - prev_oi) / prev_oi) * 100, 2)
                    prev_oi = oi_val
            except: pass

            # 3. Funding Rate
            funding_rate = 0.0
            try:
                r_fund = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", timeout=3)
                if r_fund.status_code == 200:
                    funding_rate = float(r_fund.json().get('lastFundingRate', 0.0))
            except: pass

            # 4. Volatility (ATR)
            atr_val = 45.0
            try:
                r_k = requests.get("https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=40", timeout=3)
                if r_k.status_code == 200:
                    raw_k = r_k.json()
                    k_list = [{'high': float(x[2]), 'low': float(x[3]), 'close': float(x[4])} for x in raw_k]
                    atr_val = calculate_atr(k_list, 14)
            except: pass

            mem = read_shared_memory()
            mem['htf_trend'] = htf_trend
            mem['funding_rate'] = funding_rate
            mem['oi_current'] = oi_val
            mem['oi_delta'] = oi_delta_pct
            mem['atr_val'] = atr_val
            mem['last_heartbeat'] = time.time()
            write_shared_memory(mem)
        except: pass
        time.sleep(35)

# --- 4. FAST BINANCE DATA FETCHERS ---
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

def fetch_binance_1m_klines():
    urls = [
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=30",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=30"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=2.0)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) >= 15:
                    closed = [{'time': int(d[0]), 'open': float(d[1]), 'high': float(d[2]),
                               'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])} for d in raw[:-1]]
                    return closed
        except: continue
    return None

# --- 5. COMMANDER ENGINE (OPEN INTEREST EXPANSION + 2-3 HR RUN) ---
class MasterCommanderEngine:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.last_trade_bar = 0
        self.last_exit_bar = 0
        self.locked_closing_id = None
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

        closes_5m = [c['close'] for c in closed]
        ema21 = calculate_ema(closes_5m, 21)

        # LONG POSITION MONITOR
        if t['type'] == 'LONG':
            # Profit Trailing: +200 pts ke baad EMA 21 ke niche lock hota rahega
            if (curr_price - entry) >= 200.0 and ema21 > float(t['sl']):
                t['sl'] = round(ema21 - 15.0, 1)
                t['trailed'] = True
                set_db_state("active_trade", t)

            # DIRECT MEGA TP HIT (2-3 Hr Target)
            if curr_price >= t['tp']:
                self.locked_closing_id = curr_trade_ref
                self.sl_locked = False
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                pts = round(t['tp'] - entry, 1)
                pnl_usd = round(pts * qty, 2)
                self.record_to_vault("LONG", entry, t['tp'], "INSTITUTIONAL TP 🔥", f"+{pts:.0f}", f"+${pnl_usd:.2f}", qty)
                self.last_trade_bar = live['time']
                send_alert(f"🚀 [INSTITUTIONAL 2-3 HR TP HIT] BTC LONG\nTarget: ${t['tp']:.1f}\nPoints: +{pts:.0f} pts | Profit: +${pnl_usd:.2f}")

            # SL YA TRAILING SL HIT
            elif curr_price <= float(t['sl']):
                if self.sl_locked: return
                self.sl_locked = True
                self.locked_closing_id = curr_trade_ref
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                pts = round(curr_price - entry, 1)
                pnl_usd = round(pts * qty, 2)
                res_type = "TRAILED PROFIT EXIT 🛡️" if pts > 0 else "SL HIT 🛑"
                pts_sign = f"+{pts:.0f}" if pts > 0 else f"{pts:.0f}"
                usd_sign = f"+${pnl_usd:.2f}" if pnl_usd > 0 else f"-${abs(pnl_usd):.2f}"
                
                self.record_to_vault("LONG", entry, t['sl'], res_type, pts_sign, usd_sign, qty)
                self.last_trade_bar = live['time']
                send_alert(f"{'🛡️' if pts > 0 else '🛑'} [EXIT] BTC LONG {res_type}\nPoints: {pts_sign} | PnL: {usd_sign}\nExit: ${curr_price:.1f}")

        # SHORT POSITION MONITOR
        elif t['type'] == 'SHORT':
            if (entry - curr_price) >= 200.0 and ema21 < float(t['sl']):
                t['sl'] = round(ema21 + 15.0, 1)
                t['trailed'] = True
                set_db_state("active_trade", t)

            if curr_price <= t['tp']:
                self.locked_closing_id = curr_trade_ref
                self.sl_locked = False
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                pts = round(entry - t['tp'], 1)
                pnl_usd = round(pts * qty, 2)
                self.record_to_vault("SHORT", entry, t['tp'], "INSTITUTIONAL TP 🔥", f"+{pts:.0f}", f"+${pnl_usd:.2f}", qty)
                self.last_trade_bar = live['time']
                send_alert(f"🩸 [INSTITUTIONAL 2-3 HR TP HIT] BTC SHORT\nTarget: ${t['tp']:.1f}\nPoints: +{pts:.0f} pts | Profit: +${pnl_usd:.2f}")

            elif curr_price >= float(t['sl']):
                if self.sl_locked: return
                self.sl_locked = True
                self.locked_closing_id = curr_trade_ref
                set_db_state("active_trade", None)
                set_db_state("last_exit_epoch", time.time())
                self.last_exit_bar = live['time']

                pts = round(entry - curr_price, 1)
                pnl_usd = round(pts * qty, 2)
                res_type = "TRAILED PROFIT EXIT 🛡️" if pts > 0 else "SL HIT 🛑"
                pts_sign = f"+{pts:.0f}" if pts > 0 else f"{pts:.0f}"
                usd_sign = f"+${pnl_usd:.2f}" if pnl_usd > 0 else f"-${abs(pnl_usd):.2f}"

                self.record_to_vault("SHORT", entry, t['sl'], res_type, pts_sign, usd_sign, qty)
                self.last_trade_bar = live['time']
                send_alert(f"{'🛡️' if pts > 0 else '🛑'} [EXIT] BTC SHORT {res_type}\nPoints: {pts_sign} | PnL: {usd_sign}\nExit: ${curr_price:.1f}")

    def evaluate_market_moves(self, closed, live):
        if get_db_state("kill_switch_active", False):
            return

        last_exit_epoch = get_db_state("last_exit_epoch", 0)
        if time.time() - last_exit_epoch < 900:
            return

        if self.last_exit_bar > 0:
            bars_since_exit = (live['time'] - self.last_exit_bar) // 300000
            if bars_since_exit < 2:
                return

        consec_losses, daily_loss = check_db_risk_guard()
        if daily_loss >= 10.0:
            return

        if consec_losses >= 3 and (time.time() - last_exit_epoch < 7200):
            return

        if live['time'] <= self.last_trade_bar:
            return

        mem = read_shared_memory()
        htf_trend = mem.get('htf_trend', 'NEUTRAL')
        funding_rate = mem.get('funding_rate', 0.0)
        oi_delta = mem.get('oi_delta', 0.0)
        atr_val = mem.get('atr_val', 45.0)

        # 5M Trend Direction
        closes_5m = [c['close'] for c in closed]
        ema9_5m = calculate_ema(closes_5m, 9)
        ema21_5m = calculate_ema(closes_5m, 21)

        htf_allows_long = (htf_trend in ['BULLISH', 'NEUTRAL'])
        htf_allows_short = (htf_trend in ['BEARISH', 'NEUTRAL'])
        is_funding_safe_long = funding_rate <= 0.0006
        is_funding_safe_short = funding_rate >= -0.0006

        # Exhaustion Guard
        recent_12 = closed[-12:]
        h12 = max(c['high'] for c in recent_12)
        l12 = min(c['low'] for c in recent_12)
        total_hour_run = h12 - l12
        max_run_limit = max(500.0, atr_val * 8.0)

        curr_price = float(live['close'])
        is_dump_exhausted = (curr_price <= l12 + 50.0) and (total_hour_run > max_run_limit)
        is_pump_exhausted = (curr_price >= h12 - 50.0) and (total_hour_run > max_run_limit)

        # 1-MINUTE LEAD ENGINE WITH FALLBACK
        klines_1m = fetch_binance_1m_klines()
        if not klines_1m or len(klines_1m) < 10:
            m1_c0 = {'close': live['close'], 'open': live['open']}
            has_lead_vol = True
            ema5_1m = ema9_5m
            ema13_1m = ema21_5m
        else:
            m1_c0 = klines_1m[-1]
            m1_closes = [c['close'] for c in klines_1m]
            ema5_1m = calculate_ema(m1_closes, 5)
            ema13_1m = calculate_ema(m1_closes, 13)
            avg_vol_1m = sum(c['vol'] for c in klines_1m[-6:]) / 6.0
            has_lead_vol = m1_c0['vol'] >= (avg_vol_1m * 1.05)

        # OPEN INTEREST FILTER (PHASE 1 UPGRADE):
        # Move ke waqt Open Interest ka collapse nahi hona chahiye
        is_oi_healthy_long = (oi_delta >= -0.5)
        is_oi_healthy_short = (oi_delta >= -0.5)

        is_early_long = (
            (ema9_5m >= ema21_5m) and
            (ema5_1m > ema13_1m) and
            (m1_c0['close'] > ema5_1m) and
            (m1_c0['close'] > m1_c0['open']) and
            has_lead_vol and
            is_oi_healthy_long and
            htf_allows_long and
            is_funding_safe_long and
            not is_pump_exhausted
        )

        is_early_short = (
            (ema9_5m <= ema21_5m) and
            (ema5_1m < ema13_1m) and
            (m1_c0['close'] < ema5_1m) and
            (m1_c0['close'] < m1_c0['open']) and
            has_lead_vol and
            is_oi_healthy_short and
            htf_allows_short and
            is_funding_safe_short and
            not is_dump_exhausted
        )

        cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})
        pos_usd = float(cfg['capital']) * int(cfg['leverage'])
        entry = round(curr_price, 1)
        qty = round(pos_usd / entry, 4) or 0.001

        # 2-3 HOUR MEGA SWING TARGETS
        dyn_sl_pts = round(max(90.0, min(160.0, atr_val * 2.2)), 1)
        dyn_tp_pts = round(max(700.0, min(1300.0, atr_val * 14.0)), 1)

        if is_early_long:
            self.last_trade_bar = live['time']
            self.locked_closing_id = None
            self.sl_locked = False
            sl = round(entry - dyn_sl_pts, 1)
            tp = round(entry + dyn_tp_pts, 1)

            trade_obj = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 
                'tp': tp, 'risk': dyn_sl_pts, 
                'qty': qty, 'trailed': False
            }
            set_db_state("active_trade", trade_obj)
            send_alert(
                f"⚡ [2-3 HR INSTITUTIONAL SWING] BTC LONG\n"
                f"1H Trend: {htf_trend} 🟢 | OI Delta: {oi_delta:+.2f}%\n"
                f"Volume Flow: Confirmed 🚀\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🎯 Expected 2-3 Hr Target: ${tp:.1f} (+{dyn_tp_pts:.0f} pts)\n"
                f"🛡️ Initial Invalidation (SL): ${sl:.1f} (-{dyn_sl_pts:.0f} pts)\n"
                f"📦 Size: {qty} BTC"
            )

        elif is_early_short:
            self.last_trade_bar = live['time']
            self.locked_closing_id = None
            self.sl_locked = False
            sl = round(entry + dyn_sl_pts, 1)
            tp = round(entry - dyn_tp_pts, 1)

            trade_obj = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 
                'tp': tp, 'risk': dyn_sl_pts, 
                'qty': qty, 'trailed': False
            }
            set_db_state("active_trade", trade_obj)
            send_alert(
                f"⚡ [2-3 HR INSTITUTIONAL SWING] BTC SHORT\n"
                f"1H Trend: {htf_trend} 🔴 | OI Delta: {oi_delta:+.2f}%\n"
                f"Volume Flow: Confirmed 🩸\n\n"
                f"📍 Entry: ${entry:.1f}\n"
                f"🎯 Expected 2-3 Hr Target: ${tp:.1f} (-{dyn_tp_pts:.0f} pts)\n"
                f"🛡️ Initial Invalidation (SL): ${sl:.1f} (+{dyn_sl_pts:.0f} pts)\n"
                f"📦 Size: {qty} BTC"
            )

    def run(self):
        while True:
            mem = read_shared_memory()
            mem['commander_heartbeat'] = time.time()
            write_shared_memory(mem)

            closed, live = fetch_binance_klines()
            if closed and live:
                active = get_db_state("active_trade")
                if active: 
                    self.manage_position(active, live, closed)
                else: 
                    self.evaluate_market_moves(closed, live)

            time.sleep(0.5)

# --- 6. WATCHDOG FAILOVER ---
def run_overseer_watchdog():
    while True:
        try:
            mem = read_shared_memory()
            last_hb = mem.get("commander_heartbeat", time.time())
            if time.time() - last_hb > 45.0:
                send_alert("⚠️ [WATCHDOG] Engine Freeze Detected! Reviving Background Stream...")
                mem['commander_heartbeat'] = time.time()
                write_shared_memory(mem)
        except: pass
        time.sleep(10)

# --- ENGINE STARTER ---
@st.cache_resource
def launch_full_architecture():
    eid = str(uuid.uuid4())
    with open(WATCHDOG_LOCK, "w") as f: f.write(eid)

    threading.Thread(target=run_data_news_engine, daemon=False).start()
    cmd = MasterCommanderEngine(eid)
    threading.Thread(target=cmd.run, daemon=False).start()
    threading.Thread(target=run_overseer_watchdog, daemon=False).start()

    send_alert("⚡ [PHASE 1 ACTIVATED] Open Interest Flow & 2-3 Hr Trend Rider Online!")
    return cmd

launch_full_architecture()

# -------------------------------------------------------------
# FRONTEND UI & CONTROLS DOCK (FLICKER-FREE AUTO-SYNC)
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

    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result LIKE '%TP%' OR result LIKE '%TRAILED%' THEN 1 ELSE 0 END) FROM trades")
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
        
        .stat-card { display: flex; flex-direction: column; min-width: 60px; }
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
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">
            <span class="pulse-dot"></span>
            ⚡ QUANT RADAR <span class="badge-scan">PHASE 1: OI ACTIVE</span>
        </div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SL / TRAIL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">2-3 HR TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
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
                <span class="cell-head">DERIVATIVES FLOW</span>
                <div class="cell-body" id="htf-status" style="color:#00e676;">OI & FUNDING ACTIVE</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TARGET HORIZON</span>
                <div class="cell-body" style="color:#00e676;">2 - 3 HOURS WAVE</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TRAILING SYSTEM</span>
                <div class="cell-body" style="color:#38bdf8;">5M EMA21 DYNAMIC</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">SCAN STATUS</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">SCANNING INSTITUTIONAL MOVE...</div>
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

        let lineEntry = null, lineSL = null, lineTP = null;
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
            if (lineTP) { try { series.removePriceLine(lineTP); } catch(e){} lineTP = null; }
        }

        function renderMasterInterface() {
            clearAllLines();

            if (activeTrade && activeTrade.entry) {
                let entryVal = parseFloat(activeTrade.entry);
                let slVal = parseFloat(activeTrade.sl);
                let tpVal = parseFloat(activeTrade.tp);
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
                    title: (activeTrade.trailed ? 'TRAILED SL $' : 'SAFE SL$') + slVal.toFixed(1) 
                });

                lineTP = series.createPriceLine({ 
                    price: tpVal, color: '#00e676', lineWidth: 2, 
                    lineStyle: LightweightCharts.LineStyle.Solid, 
                    axisLabelVisible: true, 
                    title: '2-3 HR TP $' + tpVal.toFixed(1) 
                });

                document.getElementById('disp-entry').innerText = "$" + entryVal.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + slVal.toFixed(1);
                document.getElementById('disp-tp').innerText = "$" + tpVal.toFixed(1);

                document.getElementById('val-setup').innerText = "RIDING " + activeTrade.type + (activeTrade.trailed ? " (TRAILED)" : "") + " 🚀";
                document.getElementById('val-setup').style.color = isLong ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = killActive ? "BOT STOPPED (KILL SWITCH)" : "SCANNING INSTITUTIONAL MOVE...";
                document.getElementById('val-setup').style.color = killActive ? "#ff3b30" : "#38bdf8";
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
                    let tpVal = parseFloat(activeTrade.tp);

                    if (isLong && (price <= slVal || price >= tpVal)) {
                        activeTrade = null;
                        renderMasterInterface();
                    } else if (!isLong && (price >= slVal || price <= tpVal)) {
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
