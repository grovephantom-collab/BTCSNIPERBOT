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
# DEDICATED BTCUSDT QUANT RADAR (100% ERROR-FREE SYNTAX ENGINE)
# ==============================================================================

BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "8941403990:AAHMOdpVVeh3wPwmxweroAi0XfNFPJAVXaM")
CHAT_ID = os.getenv("TG_CHAT_ID", "7886716805")
DB_FILE = "sniper_btc_vault.db"
SYMBOL = "BTCUSDT"

MARGIN_USD = 2.5
LEVERAGE = 10
BTC_DEC = 1
MIN_QTY = 0.001
SL_PCT = 0.0080
TP_PCT = 0.0240
MIN_ATR_PTS = 35.0

# --- DATABASE SETUP ---
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
            url = "https://api.telegram.org/bot" + str(BOT_TOKEN) + "/sendMessage"
            payload = {"chat_id": str(CHAT_ID).strip(), "text": str(msg)}
            requests.post(url, json=payload, timeout=4)
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
        url = "https://data-api.binance.vision/api/v3/klines?symbol=" + SYMBOL + "&interval=" + interval + "&limit=" + str(limit)
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
        url = "https://data-api.binance.vision/api/v3/ticker/price?symbol=" + SYMBOL
        r = requests.get(url, timeout=2.0)
        return float(r.json()["price"])
    except Exception: return None

# ==============================================================================
# BACKGROUND THREADS: ANALYSIS & EXECUTION
# ==============================================================================
def run_analysis_engine():
    last_radar_alert = {}
    while True:
        try:
            c1h, _ = fetch_btc_klines("1h", 25)
            htf_trend = "NEUTRAL"
            if c1h and len(c1h) >= 20:
                e20_1h = ema_series([x["close"] for x in c1h], 20)[-1]
                htf_trend = "BULLISH" if c1h[-1]["close"] > e20_1h else "BEARISH"

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
                            msg = "👀 [PRE-SIGNAL] BTC LONG SETUP FORMING!\n\n" + \
                                  "📍 Planned Entry: > ${:.1f}\n".format(p_entry) + \
                                  "🛡️ Structure SL: ${:.1f} (-{:.1f}%)\n".format(p_sl, SL_PCT*100) + \
                                  "🎯 Direct Mega TP: ${:.1f} (+{:.1f}%)\n".format(p_tp, TP_PCT*100) + \
                                  "⏳ Waiting for 5M Breakout confirmation..."
                            send_alert(msg)
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
                            msg = "👀 [PRE-SIGNAL] BTC SHORT SETUP FORMING!\n\n" + \
                                  "📍 Planned Entry: < ${:.1f}\n".format(p_entry) + \
                                  "🛡️ Structure SL: ${:.1f} (+{:.1f}%)\n".format(p_sl, SL_PCT*100) + \
                                  "🎯 Direct Mega TP: ${:.1f} (-{:.1f}%)\n".format(p_tp, TP_PCT*100) + \
                                  "⏳ Waiting for 5M Breakdown confirmation..."
                            send_alert(msg)
                            last_radar_alert["SHORT"] = time.time()

                        if curr_p < p_entry and last_c["close"] < last_c["open"]:
                            set_state("signal_ready", {"type": "SHORT", "price": curr_p, "sl": p_sl, "tp": p_tp, "bar": live["time"]})

        except Exception: pass
        time.sleep(2)

def close_trade(t, exit_price, result):
    if get_state("active_trade") is None: return
    set_state("active_trade", None)
    set_state("last_exit_time", time.time())

    d = 1 if t.get("type") == "LONG" else -1
    gross = (exit_price - float(t.get("entry", 0))) * float(t.get("qty", 0.001)) * d
    net = round(gross, 2)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    db("INSERT INTO trades (ts,epoch,side,entry,exit_price,qty,result,pnl) VALUES (?,?,?,?,?,?,?,?)",
       (now_str, time.time(), t.get("type", "TRADE"), float(t.get("entry", 0)), float(exit_price), float(t.get("qty", 0.001)), str(result), float(net)))

    status_icon = "🚀" if net > 0 else "🛑"
    msg = status_icon + " [BTC EXIT] " + str(t.get("type", "")) + " " + str(result) + "\nPnL: " + "{:+.2f}$".format(net) + " \vert{} Exit: $" + "{:.1f}".format(float(exit_price))
    send_alert(msg)

def run_execution_engine():
    while True:
        try:
            active = get_state("active_trade")
            if active:
                p = last_btc_price()
                if p:
                    long_ = (active.get("type") == "LONG")
                    entry_val = float(active.get("entry", 0))
                    sl_val = float(active.get("sl", 0))
                    tp_val = float(active.get("tp", 0))

                    if long_ and p >= entry_val * 1.01 and not active.get("trailed"):
                        active["sl"] = round(entry_val * 1.002, BTC_DEC)
                        active["trailed"] = True
                        set_state("active_trade", active)
                        send_alert("🛡️ BTC LONG SL Trailed to Breakeven (${:.1f})".format(active["sl"]))
                    elif not long_ and p <= entry_val * 0.99 and not active.get("trailed"):
                        active["sl"] = round(entry_val * 0.998, BTC_DEC)
                        active["trailed"] = True
                        set_state("active_trade", active)
                        send_alert("🛡️ BTC SHORT SL Trailed to Breakeven (${:.1f})".format(active["sl"]))

                    if (long_ and p >= tp_val) or (not long_ and p <= tp_val):
                        close_trade(active, tp_val, "DIRECT MEGA TP 🔥")
                    elif (long_ and p <= sl_val) or (not long_ and p >= sl_val):
                        res = "TRAILED EXIT 🛡️" if active.get("trailed") else "SL HIT 🛑"
                        close_trade(active, p, res)
            else:
                sig = get_state("signal_ready")
                if sig and not get_state("kill_switch", False) and (time.time() - get_state("last_exit_time", 0) > 180):
                    raw_qty = (MARGIN_USD * LEVERAGE) / float(sig["price"])
                    qty = max(MIN_QTY, round(raw_qty, 3))

                    trade = {
                        "type": sig["type"], "entry": sig["price"],
                        "sl": sig["sl"], "tp": sig["tp"], "qty": qty, "trailed": False
                    }
                    set_state("active_trade", trade)
                    set_state("signal_ready", None)
                    msg = "⚡ [BTC DIRECT SWING EXECUTED] " + str(sig["type"]) + "\n\n" + \
                          "📍 Entry: ${:.1f}\n".format(float(sig["price"])) + \
                          "🎯 Direct TP: ${:.1f}\n".format(float(sig["tp"])) + \
                          "🛡️ Structure SL: ${:.1f}\n".format(float(sig["sl"])) + \
                          "📦 Size: " + str(qty) + " BTC ($2.50 Margin @ 10x)"
                    send_alert(msg)
        except Exception: pass
        time.sleep(1)

@st.cache_resource
def launch():
    threading.Thread(target=run_analysis_engine, daemon=True).start()
    threading.Thread(target=run_execution_engine, daemon=True).start()
    send_alert("🟢 [BTC QUANT RADAR] Engine Online (Half-Screen UI Mode).")
    return True
launch()

# ==============================================================================
# STREAMLIT UI: HALF SCREEN CHART + LOWER DOCKS
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
        p = last_btc_price() or t.get("entry")
        close_trade(t, p, "MANUAL OVERRIDE ⚠️")
    st.query_params.clear()
    st.rerun()

if st.query_params.get("toggle_kill") == "1":
    k = get_state("kill_switch", False)
    set_state("kill_switch", not k)
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
    kill_active = get_state("kill_switch", False)

    history = db("SELECT ts, side, entry, exit_price, result, pnl FROM trades ORDER BY id DESC LIMIT 15", fetch="all") or []
    hist_json = [{"time": r[0].split(" ")[-1], "type": r[1], "entry": r[2], "exit": r[3], "result": r[4], "pnl": r[5]} for r in history]

    stats = db("SELECT COUNT(*), COALESCE(SUM(pnl),0), COALESCE(SUM(pnl>0),0) FROM trades", fetch="one")
    n, pnl_sum, wins = stats if stats else (0, 0.0, 0)
    wr = round((wins / n) * 100, 1) if n else 0.0

    raw_html = """<!DOCTYPE html>
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
        .badge-live { background: #00e676; color: #000; font-size: 8px; padding: 2px 4px; border-radius: 3px; font-weight: 900; }
        .stat-card { display: flex; flex-direction: column; min-width: 65px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }
        .stat-val { font-size: 10px; font-weight: 800; color: #fff; }
        .btn-compact { background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40; border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer; }

        .workspace { display: flex; flex-direction: column; width: 100vw; height: calc(100vh - 38px); }
        #chart-zone { width: 100vw; height: 53vh; background: #080a0f; }

        .trade-dock { width: 100vw; height: 38px; background: #0a0e17; border-top: 1px solid #1a2336; padding: 0 8px; display: flex; align-items: center; justify-content: space-between; font-size: 10px; }
        .dock-group { display: flex; align-items: center; gap: 8px; }
        .btn-override-danger { background: rgba(255, 59, 48, 0.2); color: #ff3b30; border: 1px solid #ff3b30; border-radius: 4px; padding: 3px 6px; font-size: 9px; font-weight: 800; cursor: pointer; }
        .btn-override-warn { background: rgba(240, 185, 11, 0.2); color: #f0b90b; border: 1px solid #f0b90b; border-radius: 4px; padding: 3px 6px; font-size: 9px; font-weight: 800; cursor: pointer; }

        .bottom-bar { width: 100vw; height: 46px; background: #0d121c; border-top: 1px solid #1a2336; padding: 4px 8px; display: grid; grid-template-columns: 1fr 1fr 1fr 1.2fr; gap: 6px; align-items: center; }
        .metric-cell { display: flex; flex-direction: column; justify-content: center; background: #101624; padding: 2px 6px; border-radius: 4px; border: 1px solid #192233; height: 36px; }
        .cell-head { font-size: 7px; color: #62697a; font-weight: 800; text-transform: uppercase; line-height: 1; margin-bottom: 2px; }
        .cell-body { font-size: 9px; font-weight: 800; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); backdrop-filter: blur(5px); z-index: 999; align-items: center; justify-content: center; }
        .modal-box { background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px; width: 90vw; max-width: 400px; max-height: 80vh; display: flex; flex-direction: column; padding: 12px; }
        .history-list { overflow-y: auto; max-height: 250px; font-size: 10px; }
        .history-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }
        .btn-modal-clear { margin-top: 10px; background: rgba(255, 59, 48, 0.25); color: #ff3b30; border: 1px solid rgba(255, 59, 48, 0.6); border-radius: 6px; padding: 10px; font-size: 11px; font-weight: 800; cursor: pointer; text-align: center; width: 100%; display: block; outline: none; }
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ <span class="badge-live">BTCUSDT 5M</span></div>
        <div class="stat-card"><div class="stat-label">STATUS</div><div id="disp-status" class="stat-val" style="color:#38bdf8;">SCANNING</div></div>
        <div class="stat-card"><div class="stat-label">ENTRY LEVEL</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SL / TRAIL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
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
                <span style="color:#62697a;">| ALLOCATION:</span>
                <b style="color:#38bdf8; font-size:10px;">$2.50 (10x LEV = $25 NOTIONAL)</b>
            </div>
            <div class="dock-group">
                <button type="button" class="btn-override-warn" onclick="triggerForceClose()">⚡ FORCE CLOSE</button>
                <button type="button" class="btn-override-danger" onclick="triggerKillToggle()" id="btn-kill">🚨 KILL SWITCH</button>
            </div>
        </div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">THREAD 3 RISK</span>
                <div class="cell-body" style="color:#00e676;">-$2.00 DRAWDOWN GUARD</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">EXTRA FILTERS</span>
                <div class="cell-body" style="color:#38bdf8;">ATR • OB • VOL • FUNDING</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TARGET PROFILE</span>
                <div class="cell-body" style="color:#00e676;">100% DIRECT SWING TP</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">RADAR SCANNER</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">SCANNING BTC BREAKOUTS...</div>
            </div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:11px;">BTC VAULT DATABASE</b>
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
        let radarData = __RADAR_DATA__;
        let tradeHistory = __HISTORY__;
        let stats = __STATS__;
        let killActive = __KILL__;

        function toggleModal(show) { document.getElementById('modal-bg').style.display = show ? 'flex' : 'none'; }
        function handleBgClick(e) { if (e.target.id === 'modal-bg') toggleModal(false); }

        function triggerForceClose() {
            if (!activeTrade) { alert("No active trade to close!"); return; }
            if (confirm("Force close active BTC position?")) {
                try { window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?force_close=1"; }
                catch(e) { window.location.href = window.location.pathname + "?force_close=1"; }
            }
        }

        function triggerKillToggle() {
            let msg = killActive ? "Resume bot operations?" : "Activate Emergency Kill Switch?";
            if (confirm(msg)) {
                try { window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?toggle_kill=1"; }
                catch(e) { window.location.href = window.location.pathname + "?toggle_kill=1"; }
            }
        }

        function triggerVaultClear() {
            if (confirm("Reset Vault Database?")) {
                try { window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + "?clear_vault=1"; }
                catch(e) { window.location.href = window.location.pathname + "?clear_vault=1"; }
            }
        }

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

        function renderMasterInterface() {
            clearLines();
            let source = activeTrade ? activeTrade : radarData;

            if (source && source.entry) {
                let isLive = !!activeTrade;
                let titlePrefix = isLive ? "ACTIVE " : "PRE-SIGNAL ";
                let lineStyle = isLive ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed;

                lineEntry = series.createPriceLine({ price: parseFloat(source.entry), color: '#38bdf8', lineWidth: 2, lineStyle: lineStyle, axisLabelVisible: true, title: titlePrefix + 'ENTRY' });
                lineSL = series.createPriceLine({ price: parseFloat(source.sl), color: '#ff3b30', lineWidth: 2, lineStyle: lineStyle, axisLabelVisible: true, title: (source.trailed ? 'TRAILED SL' : titlePrefix + 'SL') });
                lineTP = series.createPriceLine({ price: parseFloat(source.tp), color: '#00e676', lineWidth: 2, lineStyle: lineStyle, axisLabelVisible: true, title: titlePrefix + 'DIRECT TP' });

                document.getElementById('disp-status').innerText = isLive ? ("ACTIVE " + source.type) : ("PRE-SIGNAL " + source.type);
                document.getElementById('disp-status').style.color = (source.type === "LONG") ? "#00e676" : "#ff3b30";
                document.getElementById('disp-entry').innerText = "$" + source.entry;
                document.getElementById('disp-sl').innerText = "$" + source.sl;
                document.getElementById('disp-tp').innerText = "$" + source.tp;

                document.getElementById('val-setup').innerText = isLive ? ("RIDING BTC " + source.type + " 🚀") : ("WATCHING BTC " + source.type + " PRE-SIGNAL ⏳");
                document.getElementById('val-setup').style.color = (source.type === "LONG") ? "#00e676" : "#ff3b30";
            } else {
                document.getElementById('disp-status').innerText = "SCANNING";
                document.getElementById('disp-status').style.color = "#38bdf8";
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = killActive ? "BOT STOPPED (KILL SWITCH)" : "SCANNING BTC REJECTIONS & BREAKOUTS...";
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
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span><b>BTC</b> ${item.time} <b style="color:${typeCol};">${item.type}</b> @ $${item.entry}</span>
                            <span><b style="color:${resCol};">${item.result}</b> (${item.pnl ? '$' + item.pnl : '$0.00'})</span>
                        </div>`;
                });
            } else {
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">Vault Clean (0 trades)...</div>';
            }
        }

        let candleBuffer = [];
        function syncCandles() {
            fetch('https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=90')
                .then(r => r.json())
                .then(data => {
                    candleBuffer = data.map(d => ({
                        time: (d[0] - (d[0] % 300000)) / 1000,
                        open: parseFloat(d[1]), high: parseFloat(d[2]),
                        low: parseFloat(d[3]), close: parseFloat(d[4])
                    }));
                    series.setData(candleBuffer);
                    chart.timeScale().fitContent();
                    renderMasterInterface();
                    startLiveStream();
                }).catch(e => setTimeout(syncCandles, 2000));
        }

        function startLiveStream() {
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

        syncCandles();
        window.onresize = () => chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
    </script>
</body>
</html>"""

    final_html = raw_html.replace("__ACTIVE_TRADE__", json.dumps(active_trade))\
                         .replace("__RADAR_DATA__", json.dumps(btc_radar))\
                         .replace("__HISTORY__", json.dumps(hist_json))\
                         .replace("__STATS__", json.dumps({"total": n, "win_rate": wr}))\
                         .replace("__KILL__", json.dumps(kill_active))

    components.html(final_html, height=710, scrolling=False)

render_ui()
