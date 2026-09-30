import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import threading
import time
import requests
import json
import os
from datetime import datetime

# ==============================================================================
# DEDICATED BTCUSDT QUANT RADAR (PRE-SIGNAL + LIVE OVERLAYS)
# ==============================================================================

BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM")
CHAT_ID = os.getenv("TG_CHAT_ID", "7886716805")
DB_FILE = "sniper_btc_vault.db"
SYMBOL = "BTCUSDT"

# Risk / Capital Specs for $10 Account ($2.50 Margin @ 10x Lev = $25 Position)
MARGIN_USD = 2.5
LEVERAGE = 10
BTC_DEC = 1
MIN_QTY = 0.001
SL_PCT = 0.0080    # ~0.80% Breathing Room SL (~$650-$700 on 83k)
TP_PCT = 0.0240    # 1:3 RR Direct 100% TP (~$2000 Target)
MIN_ATR_PTS = 35.0

# --- DATABASE SETUP ---
DB_LOCK = threading.Lock()

def db(q, p=(), fetch=None):
    with DB_LOCK:
        conn = sqlite3.connect(DB_FILE, timeout=12)
        try:
            cur = conn.execute(q, p)
            res = cur.fetchall() if fetch == "all" else cur.fetchone() if fetch == "one" else None
            conn.commit()
            return res
        finally:
            conn.close()

def init_db():
    db("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, epoch REAL,
        side TEXT, entry REAL, exit_price REAL, qty REAL, result TEXT, pnl REAL)""")
    db("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
init_db()

def get_state(k, default=None):
    try:
        r = db("SELECT value FROM state WHERE key=?", (k,), "one")
        return json.loads(r[0]) if r else default
    except Exception:
        return default

def set_state(k, v):
    db("INSERT OR REPLACE INTO state (key,value) VALUES (?,?)", (k, json.dumps(v)))

# --- TELEGRAM ALERTS ---
def send_alert(msg):
    def _worker():
        if not BOT_TOKEN or not CHAT_ID: return
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          json={"chat_id": str(CHAT_ID).strip(), "text": msg}, timeout=4)
        except Exception: pass
    threading.Thread(target=_worker, daemon=True).start()

# --- UTILITIES ---
def ema_series(v, p):
    if len(v) < p: return v[-1] if v else 0.0
    k = 2 / (p + 1)
    out = [v[0]]
    for x in v[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out

def atr(c, p=14):
    if len(c) < p + 1: return 0.0
    trs = [max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]),
               abs(c[i]["low"] - c[i - 1]["close"])) for i in range(1, len(c))]
    return sum(trs[-p:]) / max(1, min(p, len(trs)))

def fetch_btc_klines(interval, limit=35):
    try:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={SYMBOL}&interval={interval}&limit={limit}"
        r = requests.get(url, timeout=2.5)
        if r.status_code == 200:
            raw = r.json()
            if isinstance(raw, list) and len(raw) >= 15:
                closed = [{'time': int(d[0]), 'open': float(d[1]), 'high': float(d[2]),
                           'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])} for d in raw[:-1]]
                live = {'time': int(raw[-1][0]), 'open': float(raw[-1][1]), 'high': float(raw[-1][2]),
                        'low': float(raw[-1][3]), 'close': float(raw[-1][4]), 'vol': float(raw[-1][5])}
                return closed, live
    except Exception: pass
    return None, None

def last_btc_price():
    try:
        r = requests.get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={SYMBOL}", timeout=2.0)
        return float(r.json()["price"])
    except Exception: return None

# ==============================================================================
# THREAD: PRE-SIGNAL ANALYSIS ENGINE
# ==============================================================================
def run_analysis_engine():
    last_radar_alert = {}
    while True:
        try:
            # 1. 1H Trend
            c1h, _ = fetch_btc_klines("1h", 25)
            htf_trend = "NEUTRAL"
            if c1h and len(c1h) >= 20:
                e20_1h = ema_series([x["close"] for x in c1h], 20)[-1]
                htf_trend = "BULLISH" if c1h[-1]["close"] > e20_1h else "BEARISH"

            # 2. 5M Pullback / Pre-Signal
            c5, live = fetch_btc_klines("5m", 30)
            if c5 and live:
                closes = [x["close"] for x in c5]
                e9 = ema_series(closes, 9)[-1]
                e21 = ema_series(closes, 21)[-1]
                curr_p = live["close"]
                last_c = c5[-1]
                a_val = atr(c5, 14)

                if a_val >= MIN_ATR_PTS:
                    forming_long = (htf_trend == "BULLISH" and e9 > e21 and last_c["low"] <= e21 * 1.002)
                    forming_short = (htf_trend == "BEARISH" and e9 < e21 and last_c["high"] >= e21 * 0.998)

                    if forming_long:
                        p_entry = round(last_c["high"], BTC_DEC)
                        p_sl = round(p_entry * (1 - SL_PCT), BTC_DEC)
                        p_tp = round(p_entry * (1 + TP_PCT), BTC_DEC)
                        
                        radar = {"type": "LONG", "entry": p_entry, "sl": p_sl, "tp": p_tp, "time": time.time()}
                        set_state("btc_radar", radar)

                        if time.time() - last_radar_alert.get("LONG", 0) > 300:
                            send_alert(
                                f"👀 [PRE-SIGNAL] BTC LONG SETUP FORMING!\n\n"
                                f"📍 Planned Entry: > ${p_entry:.1f}\n"
                                f"🛡️ Planned SL: ${p_sl:.1f} (-{SL_PCT*100:.1f}%)\n"
                                f"🎯 Planned Direct TP: ${p_tp:.1f} (+{TP_PCT*100:.1f}%)\n"
                                f"⏳ Breakout confirm hone ka wait ho raha hai..."
                            )
                            last_radar_alert["LONG"] = time.time()

                        if curr_p > p_entry and last_c["close"] > last_c["open"]:
                            set_state("signal_ready", {"type": "LONG", "price": curr_p, "sl": p_sl, "tp": p_tp, "bar": live["time"]})

                    elif forming_short:
                        p_entry = round(last_c["low"], BTC_DEC)
                        p_sl = round(p_entry * (1 + SL_PCT), BTC_DEC)
                        p_tp = round(p_entry * (1 - TP_PCT), BTC_DEC)
                        
                        radar = {"type": "SHORT", "entry": p_entry, "sl": p_sl, "tp": p_tp, "time": time.time()}
                        set_state("btc_radar", radar)

                        if time.time() - last_radar_alert.get("SHORT", 0) > 300:
                            send_alert(
                                f"👀 [PRE-SIGNAL] BTC SHORT SETUP FORMING!\n\n"
                                f"📍 Planned Entry: < ${p_entry:.1f}\n"
                                f"🛡️ Planned SL: ${p_sl:.1f} (+{SL_PCT*100:.1f}%)\n"
                                f"🎯 Planned Direct TP: ${p_tp:.1f} (-{TP_PCT*100:.1f}%)\n"
                                f"⏳ Breakdown confirm hone ka wait ho raha hai..."
                            )
                            last_radar_alert["SHORT"] = time.time()

                        if curr_p < p_entry and last_c["close"] < last_c["open"]:
                            set_state("signal_ready", {"type": "SHORT", "price": curr_p, "sl": p_sl, "tp": p_tp, "bar": live["time"]})

        except Exception: pass
        time.sleep(2)

# ==============================================================================
# THREAD: EXECUTION & POSITION LIFECYCLE
# ==============================================================================
def close_trade(t, exit_price, result):
    if get_state("active_trade") is None: return
    set_state("active_trade", None)
    set_state("last_exit_time", time.time())

    d = 1 if t["type"] == "LONG" else -1
    gross = (exit_price - t["entry"]) * t["qty"] * d
    net = round(gross, 2)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    db("INSERT INTO trades (ts,epoch,side,entry,exit_price,qty,result,pnl) VALUES (?,?,?,?,?,?,?,?)",
       (now_str, time.time(), t["type"], t["entry"], exit_price, t["qty"], result, net))

    send_alert(f"{'🚀' if net > 0 else '🛑'} [BTC TRADE CLOSED] {t['type']} {result}\nPnL: {net:+.2f}$ | Exit: ${exit_price:.1f}")

def run_execution_engine():
    while True:
        try:
            active = get_state("active_trade")
            if active:
                p = last_btc_price()
                if p:
                    long_ = active["type"] == "LONG"
                    # Breakeven Lock after +1%
                    if long_ and p >= active["entry"] * 1.01 and not active.get("trailed"):
                        active["sl"] = round(active["entry"] * 1.002, BTC_DEC)
                        active["trailed"] = True
                        set_state("active_trade", active)
                        send_alert(f"🛡️ BTC LONG SL Breakeven par lock hua (${active['sl']:.1f})")
                    elif not long_ and p <= active["entry"] * 0.99 and not active.get("trailed"):
                        active["sl"] = round(active["entry"] * 0.998, BTC_DEC)
                        active["trailed"] = True
                        set_state("active_trade", active)
                        send_alert(f"🛡️️ BTC SHORT SL Breakeven par lock hua (${active['sl']:.1f})")

                    if (long_ and p >= active["tp"]) or (not long_ and p <= active["tp"]):
                        close_trade(active, active["tp"], "DIRECT MEGA TP 🔥")
                    elif (long_ and p <= active["sl"]) or (not long_ and p >= active["sl"]):
                        res = "TRAILED SL 🛡️️" if active.get("trailed") else "SL HIT 🛑"
                        close_trade(active, p, res)
            else:
                sig = get_state("signal_ready")
                if sig and (time.time() - get_state("last_exit_time", 0) > 180):
                    raw_qty = (MARGIN_USD * LEVERAGE) / sig["price"]
                    qty = max(MIN_QTY, round(raw_qty, 3))

                    trade = {
                        "type": sig["type"], "entry": sig["price"],
                        "sl": sig["sl"], "tp": sig["tp"], "qty": qty, "trailed": False
                    }
                    set_state("active_trade", trade)
                    set_state("signal_ready", None)
                    send_alert(
                        f"⚡ [BTC ORDER EXECUTED] {sig['type']}\n\n"
                        f"📍 Entry: ${sig['price']:.1f}\n"
                        f"🎯 Direct Mega TP: ${sig['tp']:.1f}\n"
                        f"🛡️ Structure SL: ${sig['sl']:.1f}\n"
                        f"📦 Size: {qty} BTC"
                    )
        except Exception: pass
        time.sleep(1)

@st.cache_resource
def launch():
    threading.Thread(target=run_analysis_engine, daemon=True).start()
    threading.Thread(target=run_execution_engine, daemon=True).start()
    send_alert("🟢 [BTC QUANT RADAR LIVE] Monitoring Bitcoin Setups...")
    return True
launch()

# ==============================================================================
# STREAMLIT UI & LIVE LIGHTWEIGHT-CHART
# ==============================================================================
st.set_page_config(page_title="BTC QUANT RADAR", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header, footer, #MainMenu { display: none !important; }
.block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
iframe { width: 100vw !important; height: calc(100vh - 5px) !important; border: none !important; }
</style>""", unsafe_allow_html=True)

if st.query_params.get("force_close") == "1":
    t = get_state("active_trade")
    if t:
        p = last_btc_price() or t["entry"]
        close_trade(t, p, "MANUAL OVERRIDE ⚠️")
    st.query_params.clear()
    st.rerun()

if st.query_params.get("clear_vault") == "1":
    db("DELETE FROM trades")
    set_state("active_trade", None)
    st.query_params.clear()
    st.rerun()

@st.fragment(run_every=2)
def render_ui():
    active_trade = get_state("active_trade")
    btc_radar = get_state("btc_radar")

    stats = db("SELECT COUNT(*), COALESCE(SUM(pnl),0), COALESCE(SUM(pnl>0),0) FROM trades", fetch="one")
    n, pnl_sum, wins = stats if stats else (0, 0.0, 0)
    wr = round((wins / n) * 100, 1) if n else 0.0

    raw_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #080a0f; color: #d1d4dc; font-family: -apple-system, sans-serif; width: 100vw; height: 100vh; overflow: hidden; }
        .nav-bar { height: 40px; background: #0e131f; border-bottom: 1px solid #1a2233; display: flex; align-items: center; padding: 0 10px; gap: 12px; font-size: 11px; }
        .stat-tag { display: flex; flex-direction: column; }
        .stat-t-label { font-size: 7px; color: #64748b; font-weight: 800; }
        .stat-t-val { font-size: 10px; font-weight: 800; color: #fff; }
        #chart-zone { width: 100vw; height: calc(100vh - 86px); background: #080a0f; }
        .bottom-dock { height: 46px; background: #0d121c; border-top: 1px solid #1a2233; display: flex; align-items: center; justify-content: space-between; padding: 0 10px; font-size: 11px; }
        .btn-override { background: rgba(255, 59, 48, 0.2); color: #ff3b30; border: 1px solid #ff3b30; padding: 4px 8px; border-radius: 4px; font-weight: 800; cursor: pointer; }
        .btn-vault { background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 4px 8px; border-radius: 4px; font-weight: 800; cursor: pointer; }
    </style>
</head>
<body>
    <div class="nav-bar">
        <b style="color:#f0b90b; font-size:12px;">⚡ BTCUSDT RADAR</b>
        <div class="stat-tag"><span class="stat-t-label">RADAR STATUS</span><span id="txt-status" class="stat-t-val" style="color:#38bdf8;">SCANNING</span></div>
        <div class="stat-tag"><span class="stat-t-label">ENTRY LEVEL</span><span id="txt-entry" class="stat-t-val" style="color:#38bdf8;">--</span></div>
        <div class="stat-tag"><span class="stat-t-label">STRUCTURE SL</span><span id="txt-sl" class="stat-t-val" style="color:#ff3b30;">--</span></div>
        <div class="stat-tag"><span class="stat-t-label">DIRECT TP</span><span id="txt-tp" class="stat-t-val" style="color:#00e676;">--</span></div>
    </div>

    <div id="chart-zone"></div>

    <div class="bottom-dock">
        <div>
            <span>CAPITAL: <b style="color:#00e676;">$10.00</b> | MARGIN: <b style="color:#38bdf8;">$2.50 (10x)</b> | WIN RATE: <b id="ui-wr" style="color:#f0b90b;">0.0%</b></span>
        </div>
        <div style="display:flex; gap:6px;">
            <button class="btn-override" onclick="triggerForceClose()">⚠️ FORCE CLOSE</button>
            <button class="btn-vault" onclick="triggerClearVault()">🗑️ CLEAR VAULT</button>
        </div>
    </div>

    <script>
        const IST_OFFSET = 5.5 * 3600;
        let activeTrade = __ACTIVE_TRADE__;
        let radarData = __RADAR_DATA__;
        let wrVal = __WR__;
        document.getElementById('ui-wr').innerText = wrVal + "%";

        let candleBuffer = [];
        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {
            width: chartZone.clientWidth, height: chartZone.clientHeight,
            layout: { background: { color: '#080a0f' }, textColor: '#787b86' },
            grid: { vertLines: { color: '#111622' }, horzLines: { color: '#111622' } },
            rightPriceScale: { borderColor: '#192130', autoScale: true },
            timeScale: { 
                borderColor: '#192130', timeVisible: true, secondsVisible: false,
                tickMarkFormatter: (t) => {
                    const d = new Date((t + IST_OFFSET) * 1000);
                    return d.getUTCHours().toString().padStart(2, '0') + ':' + d.getUTCMinutes().toString().padStart(2, '0');
                }
            }
        });

        const series = chart.addCandlestickSeries({
            upColor: '#00E676', downColor: '#FF3B30',
            borderUpColor: '#00E676', borderDownColor: '#FF3B30',
            wickUpColor: '#00E676', wickDownColor: '#FF3B30'
        });

        let lineEntry = null, lineSL = null, lineTP = null;
        function clearLines() {
            if (lineEntry) { try { series.removePriceLine(lineEntry); } catch(e){} lineEntry = null; }
            if (lineSL) { try { series.removePriceLine(lineSL); } catch(e){} lineSL = null; }
            if (lineTP) { try { series.removePriceLine(lineTP); } catch(e){} lineTP = null; }
        }

        function updateOverlayLines() {
            clearLines();
            let source = activeTrade ? activeTrade : radarData;

            if (source && source.entry) {
                let isLive = !!activeTrade;
                let titlePrefix = isLive ? "ACTIVE " : "PRE-SIGNAL ";
                let lineStyle = isLive ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed;

                lineEntry = series.createPriceLine({ price: parseFloat(source.entry), color: '#38bdf8', lineWidth: 2, lineStyle: lineStyle, axisLabelVisible: true, title: titlePrefix + 'ENTRY' });
                lineSL = series.createPriceLine({ price: parseFloat(source.sl), color: '#ff3b30', lineWidth: 2, lineStyle: lineStyle, axisLabelVisible: true, title: titlePrefix + 'SL' });
                lineTP = series.createPriceLine({ price: parseFloat(source.tp), color: '#00e676', lineWidth: 2, lineStyle: lineStyle, axisLabelVisible: true, title: titlePrefix + 'TP' });

                document.getElementById('txt-status').innerText = isLive ? ("ACTIVE " + source.type) : ("PRE-SIGNAL " + source.type);
                document.getElementById('txt-status').style.color = (source.type === "LONG") ? "#00e676" : "#ff3b30";
                document.getElementById('txt-entry').innerText = "$" + source.entry;
                document.getElementById('txt-sl').innerText = "$" + source.sl;
                document.getElementById('txt-tp').innerText = "$" + source.tp;
            } else {
                document.getElementById('txt-status').innerText = "MONITORING PULLBACKS";
                document.getElementById('txt-status').style.color = "#38bdf8";
                document.getElementById('txt-entry').innerText = "--";
                document.getElementById('txt-sl').innerText = "--";
                document.getElementById('txt-tp').innerText = "--";
            }
        }

        function loadBtcData() {
            fetch('https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=80')
                .then(r => r.json())
                .then(data => {
                    candleBuffer = data.map(d => ({
                        time: (d[0] - (d[0] % 300000)) / 1000,
                        open: parseFloat(d[1]), high: parseFloat(d[2]),
                        low: parseFloat(d[3]), close: parseFloat(d[4])
                    }));
                    series.setData(candleBuffer);
                    chart.timeScale().fitContent();
                    updateOverlayLines();
                    startWebSocket();
                }).catch(e => setTimeout(loadBtcData, 2000));
        }

        function startWebSocket() {
            const ws = new WebSocket('wss://stream.binance.com:9443/ws/btcusdt@kline_5m');
            ws.onmessage = (e) => {
                const k = JSON.parse(e.data).k;
                const price = parseFloat(k.c);
                const barTime = (k.t - (k.t % 300000)) / 1000;

                if (candleBuffer.length > 0) {
                    let last = candleBuffer[candleBuffer.length - 1];
                    if (barTime === last.time) {
                        last.close = price;
                        if (price > last.high) last.high = price;
                        if (price < last.low) last.low = price;
                        series.update(last);
                    } else if (barTime > last.time) {
                        const newBar = { time: barTime, open: parseFloat(k.o), high: parseFloat(k.h), low: parseFloat(k.l), close: price };
                        candleBuffer.push(newBar);
                        series.update(newBar);
                    }
                }
            };
        }

        function triggerForceClose() {
            if (confirm("Close active BTC trade?")) {
                try { window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?force_close=1"; }
                catch(e) { window.location.href = window.location.pathname + "?force_close=1"; }
            }
        }
        function triggerClearVault() {
            if (confirm("Reset BTC Vault?")) {
                try { window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?clear_vault=1"; }
                catch(e) { window.location.href = window.location.pathname + "?clear_vault=1"; }
            }
        }

        loadBtcData();
        window.onresize = () => chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
    </script>
</body>
</html>"""

    final_html = raw_html.replace("__ACTIVE_TRADE__", json.dumps(active_trade))\
                         .replace("__RADAR_DATA__", json.dumps(btc_radar))\
                         .replace("__WR__", str(wr))

    components.html(final_html, height=720, scrolling=False)

render_ui()
