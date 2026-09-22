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
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=50",
        "https://api.binance.us/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=50"
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=3)
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

# -------------------------------------------------------------
# EARLY DETECTION ENGINE (Bottom Hunter & Liquidity Grab)
# -------------------------------------------------------------
class EarlyMoveBrain:
    @staticmethod
    def detect_early_reversal(closed):
        c0 = closed[-1] # Abhi abhi close hui candle
        c1 = closed[-2]
        c2 = closed[-3]

        range0 = max(c0['high'] - c0['low'], 1.0)
        body0 = c0['close'] - c0['open']
        lower_wick0 = min(c0['open'], c0['close']) - c0['low']
        upper_wick0 = c0['high'] - max(c0['open'], c0['close'])

        # Simple RSI (14 period)
        closes = [c['close'] for c in closed[-15:]]
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            if diff >= 0: gains.append(diff); losses.append(0)
            else: gains.append(0); losses.append(abs(diff))
        avg_gain = sum(gains) / len(gains) if gains else 0.001
        avg_loss = sum(losses) / len(losses) if losses else 0.001
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # 1. EARLY BOTTOM LONG (Move aane se pehle entry)
        # Condition: Pichle low ko chhoo kar rejection wick banayi, RSI low tha, aur pehli reversal candle green ban gayi
        lowest_prev = min(c['low'] for c in closed[-6:-1])
        is_bottom_sweep = (c0['low'] <= lowest_prev) and (lower_wick0 / range0 >= 0.40) and (c0['close'] > c0['open'])
        is_oversold_turn = (rsi <= 40) and (body0 > 12.0) and (c0['close'] > c1['close'])

        if is_bottom_sweep or is_oversold_turn:
            return "LONG", c0['low'], "Bottom Liquidity Reversal (Pre-Move Sniper)"

        # 2. EARLY TOP SHORT (Dumping se pehle entry)
        highest_prev = max(c['high'] for c in closed[-6:-1])
        is_top_sweep = (c0['high'] >= highest_prev) and (upper_wick0 / range0 >= 0.40) and (c0['close'] < c0['open'])
        is_overbought_turn = (rsi >= 60) and (body0 < -12.0) and (c0['close'] < c1['close'])

        if is_top_sweep or is_overbought_turn:
            return "SHORT", c0['high'], "Top Exhaustion Rejection (Pre-Move Sniper)"

        return None, 0, "Wait for Setup"

# -------------------------------------------------------------
# EXECUTION & SENTIMENT ENGINES
# -------------------------------------------------------------
class MasterCommander:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.last_candle_time = 0

    def run(self):
        while True:
            try:
                with open(LOCK_FILE, "r") as f:
                    if f.read().strip() != self.engine_id: break
            except: pass

            closed, live = fetch_binance_klines()
            if closed and live:
                active = get_db_state("active_trade")
                if active:
                    self.manage_position(active, live)
                else:
                    self.hunt_early_entry(closed, live)

            time.sleep(2)

    def manage_position(self, t, live):
        qty = t.get("qty", 0.01)
        if t['type'] == 'LONG':
            # +70 pts par Safe Breakeven
            if not t.get('be_hit', False) and live['high'] >= (t['entry'] + 70.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] + 15.0, 1)
                set_db_state("active_trade", t)
                send_telegram_alert(f"🛡️ [EARLY ENTRY SAFE] BTC LONG +70 Pts In Profit!\nSL moved to ${t['sl']:.1f} (Risk Free).")

            if live['high'] >= t['tp']:
                pts = round(t['tp'] - t['entry'], 1)
                usd = round(pts * qty, 2)
                self.record(t, t['tp'], "TP HIT 🎯", f"+{pts:.0f}", f"+${usd}")
                send_telegram_alert(f"🚀 [EARLY SNIPER TP HIT] BTC LONG\nGain: +${usd} (+{pts:.0f} pts)\nExit: ${t['tp']:.1f}")
            elif live['low'] <= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                pts = 15.0 if t.get('be_hit', False) else -(t['entry'] - t['sl'])
                usd = round(pts * qty, 2)
                sign = "+" if usd >= 0 else ""
                self.record(t, t['sl'], res, f"{sign}{pts:.0f}", f"{sign}${usd}")
                send_telegram_alert(f"🛡️ [EXIT] BTC LONG {res}\nPnL: {sign}${usd} ({sign}{pts:.0f} pts)")

        elif t['type'] == 'SHORT':
            if not t.get('be_hit', False) and live['low'] <= (t['entry'] - 70.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] - 15.0, 1)
                set_db_state("active_trade", t)
                send_telegram_alert(f"🛡️ [EARLY ENTRY SAFE] BTC SHORT +70 Pts In Profit!\nSL moved to ${t['sl']:.1f} (Risk Free).")

            if live['low'] <= t['tp']:
                pts = round(t['entry'] - t['tp'], 1)
                usd = round(pts * qty, 2)
                self.record(t, t['tp'], "TP HIT 🎯", f"+{pts:.0f}", f"+${usd}")
                send_telegram_alert(f"🩸 [EARLY SNIPER TP HIT] BTC SHORT\nGain: +${usd} (+{pts:.0f} pts)\nExit: ${t['tp']:.1f}")
            elif live['high'] >= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                pts = 15.0 if t.get('be_hit', False) else -(t['sl'] - t['entry'])
                usd = round(pts * qty, 2)
                sign = "+" if usd >= 0 else ""
                self.record(t, t['sl'], res, f"{sign}{pts:.0f}", f"{sign}${usd}")
                send_telegram_alert(f"🛡️ [EXIT] BTC SHORT {res}\nPnL: {sign}${usd} ({sign}{pts:.0f} pts)")

    def hunt_early_entry(self, closed, live):
        if live['time'] <= self.last_candle_time: return
        self.last_candle_time = live['time']

        c0 = closed[-1]
        side, structure_level, reason = EarlyMoveBrain.detect_early_reversal(closed)

        if not side: return

        entry = round(c0['close'], 1)
        cfg = get_db_state("config", {"capital": 100.0, "leverage": 10})
        pos_usd = float(cfg['capital']) * int(cfg['leverage'])
        qty = round(pos_usd / entry, 4) or 0.001

        # Super Tight SL: Candle ke bottom/top se sirf 35 points bahar
        if side == "LONG":
            sl = round(structure_level - 35.0, 1)
            risk = entry - sl
            if risk > 120.0: sl = round(entry - 85.0, 1) # Max cap
            tp = round(entry + 180.0, 1) # Full ride target
            trade_obj = {'type': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp, 'qty': qty, 'be_hit': False}
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [EARLY BOTTOM ENTRY] BTC LONG\n\n📍 Bottom Entry: ${entry:.1f}\n🛡️ Tight SL: ${sl:.1f} (Just Below Bottom Wick)\n🎯 Target TP: ${tp:.1f} (+180 pts)\n🧠 Logic: {reason}\n📦 Pos: {qty} BTC")

        elif side == "SHORT":
            sl = round(structure_level + 35.0, 1)
            risk = sl - entry
            if risk > 120.0: sl = round(entry + 85.0, 1)
            tp = round(entry - 180.0, 1)
            trade_obj = {'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp, 'qty': qty, 'be_hit': False}
            set_db_state("active_trade", trade_obj)
            send_telegram_alert(f"⚡ [EARLY TOP ENTRY] BTC SHORT\n\n📍 Top Entry: ${entry:.1f}\n🛡️ Tight SL: ${sl:.1f} (Just Above Top Wick)\n🎯 Target TP: ${tp:.1f} (-180 pts)\n🧠 Logic: {reason}\n📦 Pos: {qty} BTC")

    def record(self, t, exit_price, result, pts, pnl_usd):
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

@st.cache_resource
def boot():
    eid = str(uuid.uuid4())
    with open(LOCK_FILE, "w") as f: f.write(eid)
    threading.Thread(target=MasterCommander(eid).run, daemon=True).start()
    send_telegram_alert("🎯 [EARLY REVERSAL BRAIN ACTIVE] Bottom & Top Sweep Mode Ready.")
    return eid

boot()

# -------------------------------------------------------------
# UI VIEW
# -------------------------------------------------------------
st.set_page_config(page_title="AI CRYPTO SNIPER", page_icon="⚡", layout="wide")
st.markdown("""<style>header, footer, #MainMenu { display: none !important; } .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; } iframe { width: 100vw !important; height: 100vh !important; border: none !important; }</style>""", unsafe_allow_html=True)

active_trade = get_db_state("active_trade")
js_active_trade = json.dumps(active_trade)

terminal_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background: #080a0f; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; overflow: hidden; }}
        .nav {{ display: flex; align-items: center; background: #0d111a; border-bottom: 1px solid #1a2336; padding: 6px 12px; height: 42px; gap: 12px; }}
        .brand {{ font-weight: 800; color: #fff; font-size: 11px; }}
        .badge {{ background: #38bdf8; color: #000; font-size: 9px; padding: 2px 6px; border-radius: 3px; font-weight: 900; }}
        #chart-zone {{ width: 100vw; height: calc(100vh - 42px); }}
    </style>
</head>
<body>
    <div class="nav">
        <div class="brand">⚡ EARLY SNIPER <span class="badge">BOTTOM/TOP REVERSAL</span></div>
        <div style="margin-left: auto;"><b id="live-price" style="color: #f0b90b; font-size: 13px;">Connecting...</b></div>
    </div>
    <div id="chart-zone"></div>
    <script>
        const IST_OFFSET = 5.5 * 3600;
        let activeTrade = {js_active_trade};
        let lineEntry = null, lineSL = null, lineTP = null;

        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {{
            width: chartZone.clientWidth, height: chartZone.clientHeight,
            layout: {{ background: {{ color: '#080a0f' }}, textColor: '#787b86' }},
            grid: {{ vertLines: {{ color: '#111622' }}, horzLines: {{ color: '#111622' }} }},
            rightPriceScale: {{ borderColor: '#192130' }},
            timeScale: {{ borderColor: '#192130', timeVisible: true, secondsVisible: false }},
            localization: {{ timeFormatter: t => {{ const d = new Date((t + IST_OFFSET) * 1000); return d.toUTCString().match(/\\d{{2}}:\\d{{2}}/)[0]; }} }}
        }});

        const series = chart.addCandlestickSeries({{ upColor: '#00E676', downColor: '#FF3B30', borderUpColor: '#00E676', borderDownColor: '#FF3B30', wickUpColor: '#00E676', wickDownColor: '#FF3B30' }});

        function renderLines() {{
            if (lineEntry) try {{ series.removePriceLine(lineEntry); }} catch(e){{}}
            if (lineSL) try {{ series.removePriceLine(lineSL); }} catch(e){{}}
            if (lineTP) try {{ series.removePriceLine(lineTP); }} catch(e){{}}
            if (activeTrade) {{
                lineEntry = series.createPriceLine({{ price: activeTrade.entry, color: '#38bdf8', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'EARLY ENTRY' }});
                lineSL = series.createPriceLine({{ price: activeTrade.sl, color: '#ff3b30', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'TIGHT SL' }});
                lineTP = series.createPriceLine({{ price: activeTrade.tp, color: '#00e676', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'TARGET' }});
            }}
        }}

        fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=100')
            .then(r => r.json())
            .then(data => {{
                let cdata = data.map(d => ({{ time: (d[0] - (d[0] % 300000)) / 1000, open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]) }}));
                series.setData(cdata);
                renderLines();
                const ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
                ws.onmessage = (e) => {{
                    const k = JSON.parse(e.data).k;
                    const price = parseFloat(k.c);
                    document.getElementById('live-price').innerText = "$" + price.toFixed(1);
                    let last = cdata[cdata.length - 1];
                    const barTime = (k.t - (k.t % 300000)) / 1000;
                    if (barTime === last.time) {{
                        last.close = price;
                        if (price > last.high) last.high = price;
                        if (price < last.low) last.low = price;
                        series.update(last);
                    }} else if (barTime > last.time) {{
                        cdata.push({{ time: barTime, open: price, high: price, low: price, close: price }});
                        series.update(cdata[cdata.length - 1]);
                        setTimeout(() => window.parent.location.reload(), 6000);
                    }}
                }};
            }});
    </script>
</body>
</html>"""

components.html(terminal_html, height=720, scrolling=False)
