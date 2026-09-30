import streamlit as st
import sqlite3, threading, time, requests, json, os, shutil, logging
from datetime import datetime

st.set_page_config(page_title="QUANT RADAR PRO", layout="wide")

# ============================ CONFIG ============================
# Aapke hardcoded credentials fallback me set hain taaki env missing hone par bhi alert aaye
BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM")
CHAT_ID = os.getenv("TG_CHAT_ID", "7886716805")
DB_FILE = "sniper_vault_v2.db"

ACCOUNT_USD = 10.0
MARGIN_USD = 2.5
LEVERAGE = 10                      # notional = 25 USD
DAILY_DD_LIMIT = 2.0               # -2 USD => 24h freeze
MAX_CONSEC_LOSS = 3
COOLDOWN_SEC = 180
FEE_RATE = 0.0004                  # taker fee per side
RR = 2.5                           # reward : risk
ATR_SL_MULT = 1.5
MIN_ATR_PCT = 0.0012               # min 0.12% ATR on 5m
VOL_SPIKE_MULT = 1.3               # 1.5x ki jagah 1.3x safe rakha hai taaki valid moves miss na ho
OB_LONG_MIN, OB_SHORT_MAX = 0.95, 1.05
FUNDING_LIMIT = 0.0005
FNG_LONG_MAX, FNG_SHORT_MIN = 85, 15

WATCHLIST = ["SOLUSDT", "DOGEUSDT", "BTCUSDT"]
PAIRS = {  # min_qty, qty_dec, price_dec
    "BTCUSDT": (0.001, 3, 1),
    "SOLUSDT": (0.01, 2, 2),
    "DOGEUSDT": (1, 0, 5),
}
BASE = "https://data-api.binance.vision/api/v3"

logging.basicConfig(filename="bot_errors.log", level=logging.ERROR)

# ============================ DB ============================
DB_LOCK = threading.Lock()

def db(q, p=(), fetch=None):
    with DB_LOCK:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        try:
            cur = conn.execute(q, p)
            res = cur.fetchall() if fetch == "all" else cur.fetchone() if fetch == "one" else None
            conn.commit()
            return res
        finally:
            conn.close()

def init_db():
    db("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, epoch REAL, symbol TEXT,
        side TEXT, entry REAL, exit_price REAL, qty REAL, result TEXT, pnl REAL)""")
    db("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
    db("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, msg TEXT)")
init_db()

def get_state(k, default=None):
    try:
        r = db("SELECT value FROM state WHERE key=?", (k,), "one")
        return json.loads(r[0]) if r else default
    except Exception:
        return default

def set_state(k, v):
    db("INSERT OR REPLACE INTO state (key,value) VALUES (?,?)", (k, json.dumps(v)))

def log(msg):
    try:
        db("INSERT INTO logs (ts,msg) VALUES (?,?)", (datetime.now().strftime("%m-%d %H:%M:%S"), msg))
    except Exception:
        pass

# ============================ ALERTS ============================
def send_alert(msg):
    def w():
        if not BOT_TOKEN or not CHAT_ID:
            return
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          json={"chat_id": str(CHAT_ID).strip(), "text": msg}, timeout=5)
        except Exception:
            pass
    threading.Thread(target=w, daemon=True).start()

# ============================ INDICATORS ============================
def ema_series(v, p):
    k = 2 / (p + 1)
    out = [v[0]]
    for x in v[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out

def atr(c, p=14):
    trs = [max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]),
               abs(c[i]["low"] - c[i - 1]["close"])) for i in range(1, len(c))]
    return sum(trs[-p:]) / max(1, min(p, len(trs)))

# ============================ DATA ============================
def klines(sym, interval, limit):
    try:
        r = requests.get(f"{BASE}/klines?symbol={sym}&interval={interval}&limit={limit}", timeout=3)
        raw = r.json()
        rows = [{"time": int(d[0]), "open": float(d[1]), "high": float(d[2]),
                 "low": float(d[3]), "close": float(d[4]), "vol": float(d[5])} for d in raw]
        return rows[:-1], rows[-1]
    except Exception:
        return None, None

def last_price(sym):
    try:
        return float(requests.get(f"{BASE}/ticker/price?symbol={sym}", timeout=2).json()["price"])
    except Exception:
        return None

def orderbook_imbalance(sym):
    try:
        d = requests.get(f"{BASE}/depth?symbol={sym}&limit=20", timeout=2.5).json()
        bids = sum(float(x[1]) for x in d["bids"])
        asks = sum(float(x[1]) for x in d["asks"])
        return bids / asks if asks else None
    except Exception:
        return None

def funding_rate(sym):
    try:
        r = requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}", timeout=2.5).json()
        return float(r["lastFundingRate"])
    except Exception:
        return None

_fng = {"v": None, "t": 0}
def fear_greed():
    if time.time() - _fng["t"] < 300:
        return _fng["v"]
    try:
        _fng["v"] = int(requests.get("https://api.alternative.me/fng/", timeout=3).json()["data"][0]["value"])
        _fng["t"] = time.time()
    except Exception:
        pass
    return _fng["v"]

# ============================ THREAD 2: ANALYSIS ============================
def analyze(sym):
    c1h, _ = klines(sym, "1h", 60)
    if not c1h:
        return "NEUTRAL", None
    e20 = ema_series([x["close"] for x in c1h], 20)
    if c1h[-1]["close"] > e20[-1] and e20[-1] >= e20[-3]:
        trend = "BULLISH"
    elif c1h[-1]["close"] < e20[-1] and e20[-1] <= e20[-3]:
        trend = "BEARISH"
    else:
        trend = "SIDEWAYS"

    c5, live = klines(sym, "5m", 60)
    if not c5 or len(c5) < 30:
        return trend, None
    closes = [x["close"] for x in c5]
    e9, e21 = ema_series(closes, 9), ema_series(closes, 21)
    last = c5[-1]
    a = atr(c5)
    price = live["close"]

    if a / price < MIN_ATR_PCT:
        return trend, None
    avg_vol = sum(x["vol"] for x in c5[-21:-1]) / 20
    if last["vol"] < VOL_SPIKE_MULT * avg_vol:
        return trend, None

    lows, highs = [x["low"] for x in c5], [x["high"] for x in c5]
    higher_low = min(lows[-6:]) >= min(lows[-12:-6])
    lower_high = max(highs[-6:]) <= max(highs[-12:-6])

    side = None
    if (trend in ["BULLISH", "SIDEWAYS"] and e9[-1] > e21[-1] and last["low"] <= e21[-1] * 1.002
            and last["close"] > last["open"] and higher_low and price > last["high"]):
        side = "LONG"
    elif (trend in ["BEARISH", "SIDEWAYS"] and e9[-1] < e21[-1] and last["high"] >= e21[-1] * 0.998
            and last["close"] < last["open"] and lower_high and price < last["low"]):
        side = "SHORT"
    if not side:
        return trend, None

    imb = orderbook_imbalance(sym)
    # Fail-open guard: sirf tab block kare jab extreme orderbook opposite ho
    if imb is not None:
        if (side == "LONG" and imb < OB_LONG_MIN) or (side == "SHORT" and imb > OB_SHORT_MAX):
            return trend, None

    fr = funding_rate(sym)
    if fr is not None and ((side == "LONG" and fr > FUNDING_LIMIT) or (side == "SHORT" and fr < -FUNDING_LIMIT)):
        return trend, None

    fg = fear_greed()
    if fg is not None and ((side == "LONG" and fg > FNG_LONG_MAX) or (side == "SHORT" and fg < FNG_SHORT_MIN)):
        return trend, None

    return trend, {"type": side, "price": price, "atr": a, "bar": last["time"]}

def thread_analysis():
    while True:
        try:
            trends, signals = {}, {}
            for sym in WATCHLIST:
                t, sig = analyze(sym)
                trends[sym] = t
                if sig:
                    signals[sym] = sig
                time.sleep(0.4)
            set_state("trends", trends)
            set_state("signals", signals)
            set_state("hb_analysis", time.time())
        except Exception as e:
            logging.exception("analysis")
            log(f"analysis err: {e}")
        time.sleep(3)

# ============================ THREAD 3: RISK ============================
def midnight_epoch():
    n = datetime.now()
    return datetime(n.year, n.month, n.day).timestamp()

def thread_risk():
    while True:
        try:
            now = time.time()
            if now >= get_state("freeze_until", 0):
                ref = max(midnight_epoch(), get_state("risk_ref", 0))
                rows = db("SELECT pnl FROM trades WHERE epoch>? ORDER BY id DESC", (ref,), "all")
                pnls = [r[0] for r in rows] if rows else []
                day_pnl = sum(pnls)
                streak = len(pnls) >= MAX_CONSEC_LOSS and all(p <= 0 for p in pnls[:MAX_CONSEC_LOSS])
                if day_pnl <= -DAILY_DD_LIMIT or streak:
                    set_state("freeze_until", now + 86400)
                    set_state("risk_ref", now + 86400)
                    send_alert(f"🚨 RISK SHIELD: drawdown {day_pnl:.2f}$ / loss streak. Bot 24h frozen.")
                    log("risk freeze triggered")
            set_state("hb_risk", now)
        except Exception as e:
            logging.exception("risk")
        time.sleep(10)

# ============================ THREAD 4: EXECUTION ============================
def close_trade(t, exit_price, result):
    if get_state("active_trade") is None:
        return
    set_state("active_trade", None)
    d = 1 if t["type"] == "LONG" else -1
    gross = (exit_price - t["entry"]) * t["qty"] * d
    fees = t["entry"] * t["qty"] * FEE_RATE * 2
    net = round(gross - fees, 4)
    now = datetime.now()
    db("INSERT INTO trades (ts,epoch,symbol,side,entry,exit_price,qty,result,pnl) VALUES (?,?,?,?,?,?,?,?,?)",
       (now.strftime("%Y-%m-%d %H:%M"), time.time(), t["symbol"], t["type"], t["entry"],
        exit_price, t["qty"], result, net))
    set_state("last_exit", time.time())
    send_alert(f"{'✅' if net > 0 else '🛑'} {t['symbol']} {t['type']} {result}\nNet PnL: {net:+.3f}$ (fees incl.)")

def manage_trade(t):
    sym = t["symbol"]
    p = last_price(sym)
    if p is None:
        return
    long_ = t["type"] == "LONG"
    risk = abs(t["entry"] - t["init_sl"])
    moved = (p - t["entry"]) if long_ else (t["entry"] - p)

    # Move SL to Breakeven after +1R Move
    if moved >= risk and not t.get("be"):
        buf = t["entry"] * FEE_RATE * 3
        t["sl"] = round(t["entry"] + buf if long_ else t["entry"] - buf, PAIRS[sym][2])
        t["be"] = True
        set_state("active_trade", t)
        send_alert(f"🛡️ {sym} SL moved to break-even")

    if (long_ and p >= t["tp"]) or (not long_ and p <= t["tp"]):
        return close_trade(t, t["tp"], "TP HIT 🔥")
    if (long_ and p <= t["sl"]) or (not long_ and p >= t["sl"]):
        return close_trade(t, p, "TRAILED EXIT 🛡️" if t.get("be") else "SL HIT 🛑")

    if t.get("be") and time.time() - t.get("last_trail", 0) > 10:
        t["last_trail"] = time.time()
        c5, _ = klines(sym, "5m", 40)
        if c5:
            e21 = ema_series([x["close"] for x in c5], 21)[-1]
            if (long_ and c5[-1]["close"] < e21) or (not long_ and c5[-1]["close"] > e21):
                close_trade(t, p, "EMA21 TRAIL EXIT 🛡️")

def try_entry():
    if get_state("kill_switch", False) or time.time() < get_state("freeze_until", 0):
        return
    if time.time() - get_state("last_exit", 0) < COOLDOWN_SEC:
        return
    if time.time() - get_state("hb_analysis", 0) > 30:
        return
    signals = get_state("signals", {}) or {}
    done = get_state("last_bar", {}) or {}
    for sym in WATCHLIST:
        s = signals.get(sym)
        if not s or s["bar"] <= done.get(sym, 0):
            continue
        min_qty, qdec, pdec = PAIRS[sym]
        notional = MARGIN_USD * LEVERAGE
        qty = round(notional / s["price"], qdec)
        if qdec == 0:
            qty = int(qty)
        if qty < min_qty:
            done[sym] = s["bar"]
            set_state("last_bar", done)
            continue
        dist = min(max(ATR_SL_MULT * s["atr"], s["price"] * 0.005), s["price"] * 0.015)
        long_ = s["type"] == "LONG"
        sl = round(s["price"] - dist if long_ else s["price"] + dist, pdec)
        tp = round(s["price"] + dist * RR if long_ else s["price"] - dist * RR, pdec)
        trade = {"symbol": sym, "type": s["type"], "entry": round(s["price"], pdec),
                 "sl": sl, "init_sl": sl, "tp": tp, "qty": qty, "be": False}
        set_state("active_trade", trade)
        done[sym] = s["bar"]
        set_state("last_bar", done)
        send_alert(f"⚡ {sym} {s['type']} (PAPER)\nEntry: {trade['entry']}\nSL: {sl}\nTP: {tp}\nQty: {qty}")
        return

def thread_execution():
    while True:
        try:
            t = get_state("active_trade")
            manage_trade(t) if t else try_entry()
            set_state("hb_exec", time.time())
        except Exception as e:
            logging.exception("exec")
            log(f"exec err: {e}")
        time.sleep(1)

# ============================ THREAD 5: WATCHDOG ============================
THREADS = {}
def start(name, fn):
    th = threading.Thread(target=fn, daemon=True, name=name)
    th.start()
    THREADS[name] = (th, fn)

def thread_watchdog():
    last_backup, last_day = 0, datetime.now().day
    while True:
        try:
            for name, (th, fn) in list(THREADS.items()):
                if not th.is_alive():
                    log(f"restarting {name}")
                    send_alert(f"♻️ Watchdog restarted {name}")
                    start(name, fn)
            if time.time() - last_backup > 3600:
                shutil.copy(DB_FILE, DB_FILE + ".bak")
                last_backup = time.time()
            if datetime.now().day != last_day:
                last_day = datetime.now().day
                rows = db("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM trades WHERE epoch>?",
                          (time.time() - 86400,), "one")
                send_alert(f"📊 Daily summary: {rows[0]} trades, PnL {rows[1]:+.2f}$")
            set_state("hb_watchdog", time.time())
        except Exception:
            logging.exception("watchdog")
        time.sleep(30)

@st.cache_resource
def launch():
    start("analysis", thread_analysis)
    start("risk", thread_risk)
    start("execution", thread_execution)
    threading.Thread(target=thread_watchdog, daemon=True, name="watchdog").start()
    send_alert("🟢 Quant Radar online (CLEAN PAPER mode).")
    return True
launch()

# ============================ DASHBOARD ============================
st.markdown("<style>.block-container{padding-top:1rem}</style>", unsafe_allow_html=True)
st.title("📡 QUANT RADAR PRO")

@st.fragment(run_every=2)
def dashboard():
    rows = db("SELECT ts,symbol,side,entry,exit_price,result,pnl FROM trades ORDER BY id DESC LIMIT 50", fetch="all")
    total = db("SELECT COUNT(*), COALESCE(SUM(pnl),0), COALESCE(SUM(pnl>0),0) FROM trades", fetch="one")
    n = total[0] if total else 0
    pnl_sum = total[1] if total else 0.0
    wins = total[2] if total else 0
    wr = round(wins / n * 100, 1) if n else 0.0
    freeze = get_state("freeze_until", 0)
    killed = get_state("kill_switch", False)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Balance (paper)", f"${ACCOUNT_USD + pnl_sum:.2f}")
    c2.metric("Trades", n)
    c3.metric("Win rate", f"{wr}%")
    status = "FROZEN" if time.time() < freeze else "KILLED" if killed else "RUNNING"
    c4.metric("Status", status)

    trends = get_state("trends", {}) or {}
    st.caption("1H trend: " + " | ".join(f"{k}: {v}" for k, v in trends.items()))

    t = get_state("active_trade")
    if t:
        p = last_price(t["symbol"]) or t["entry"]
        d = 1 if t["type"] == "LONG" else -1
        live = (p - t["entry"]) * t["qty"] * d
        st.success(f"{t['symbol']} {t['type']} | Entry {t['entry']} | Now {p} | SL {t['sl']} | "
                   f"TP {t['tp']} | Live PnL {live:+.3f}$")
    else:
        st.info("No active trade (Scanning Watchlist...)")

    b1, b2 = st.columns(2)
    if b1.button("🛑 Kill switch OFF" if killed else "🛑 Kill switch ON", key="ks"):
        set_state("kill_switch", not killed)
    if b2.button("⚠️ Force close", key="fc") and t:
        close_trade(t, last_price(t["symbol"]) or t["entry"], "MANUAL ⚠️")

    if rows:
        st.dataframe([{"time": r[0], "symbol": r[1], "side": r[2], "entry": r[3],
                       "exit": r[4], "result": r[5], "net pnl $": r[6]} for r in rows],
                     use_container_width=True, hide_index=True)
    with st.expander("System logs"):
        logs = db("SELECT ts,msg FROM logs ORDER BY id DESC LIMIT 15", fetch="all") or []
        for r in logs:
            st.text(f"{r[0]}  {r[1]}")
dashboard()
