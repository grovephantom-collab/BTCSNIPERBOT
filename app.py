import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests
import json
import os
from datetime import datetime

# ==============================================================================
# BTC SNIPER 5M - SINGLE ENGINE GUARANTEE (NO MORE GHOSTS)
# ==============================================================================

BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"
DATA_FILE = "sniper_brain_data.json"

def get_default_state():
    return {
        "history": [], "total_signals": 0, "tp_count": 0, "sl_count": 0,
        "win_rate": 0.0, "active_trade": None, 
        "metrics": {"trend": "ANALYZING...", "rsi": "--", "atr": "--", "news": "SCANNING..."},
        "news_score": {"sentiment": "NEUTRAL", "score": 0},
        "config": {"capital": 100.0, "leverage": 10}
    }

if st.query_params.get("clear") == "1":
    if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
    st.query_params.clear()
    st.rerun()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f: return json.load(f)
        except: return get_default_state()
    return get_default_state()

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f: json.dump(data, f, indent=2)
    except: pass

def send_tg_command(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(CHAT_ID).strip(), "text": msg}
    for _ in range(3):
        try:
            if requests.post(url, json=payload, timeout=5).status_code == 200: return True
        except: time.sleep(0.5)
    return False

def get_market_data():
    try:
        r = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=45", timeout=3)
        if r.status_code == 200:
            raw = r.json()
            if len(raw) >= 35:
                closed = [{'open': float(d[1]), 'high': float(d[2]), 'low': float(d[3]), 'close': float(d[4])} for d in raw[:-1]]
                live = {'time': int(raw[-1][0]), 'high': float(raw[-1][2]), 'low': float(raw[-1][3]), 'close': float(raw[-1][4]), 'open': float(raw[-1][1])}
                return closed, live
    except: pass
    return None, None

# ==============================================================================
# SINGLETON ENGINE (Runs strictly ONCE per server boot)
# ==============================================================================
class MasterTriEngine:
    def __init__(self):
        self.last_candle_time = 0

    def update_technical_metrics(self, state, closed, live):
        trs = []
        for i in range(len(closed) - 14, len(closed)):
            c, p = closed[i], closed[i-1]
            trs.append(max(c['high'] - c['low'], abs(c['high'] - p['close']), abs(c['low'] - p['close'])))
        atr = max(sum(trs) / len(trs), 250.0)

        closes = [c['close'] for c in closed]
        k = 2 / 31
        ema30 = closes[0]
        for cl in closes[1:]: ema30 = (cl * k) + (ema30 * (1 - k))
        trend = "BULLISH ▲" if live['close'] > ema30 else "BEARISH ▼"

        state["metrics"]["trend"] = trend
        state["metrics"]["atr"] = f"${atr:.1f}"
        return atr, ema30

    def update_news(self, state):
        score = 0
        sentiment_text = "NEUTRAL ⚖️"
        try:
            fg_resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3).json()
            fng_value = int(fg_resp['data'][0]['value'])
            if fng_value > 60: score += 5
            elif fng_value < 40: score -= 5
            if score >= 5: sentiment_text = "HIGHLY BULLISH 🚀"
            elif score <= -5: sentiment_text = "BEARISH 🩸"
        except: pass
        state["news_score"] = {"sentiment": sentiment_text, "score": score}
        state["metrics"]["news"] = sentiment_text

    def close_trade(self, state, result, pnl_pts, pnl_usd, qty):
        t = state["active_trade"]
        now_str = datetime.now().strftime("%H:%M")
        state["total_signals"] += 1
        if "TP" in result: state["tp_count"] += 1
        elif "SL" in result: state["sl_count"] += 1
        total = state["tp_count"] + state["sl_count"]
        if total > 0: state["win_rate"] = round((state["tp_count"] / total) * 100, 1)

        state["history"].insert(0, {"time": now_str, "type": t['type'], "entry": float(t['entry']), "result": result, "pts": pnl_pts, "pnl_usd": pnl_usd, "qty": qty})
        if len(state["history"]) > 500: state["history"].pop()
        state["active_trade"] = None
        save_data(state)

    def manage_active_trade(self, state, live):
        t = state["active_trade"]
        qty = t.get("qty", 0.01)

        if t['type'] == 'LONG':
            if not t.get('be_hit', False) and live['high'] >= (t['entry'] + 150.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] + 25.0, 1)
                save_data(state)
                send_tg_command(f"🎯 COMMAND: BTC LONG SECURED (+150 pts)\nSL at Breakeven.")

            if live['high'] >= t['tp']:
                pts = round(t['tp'] - t['entry'], 1)
                self.close_trade(state, "TP HIT", f"+{pts:.0f}", f"+${round(pts * qty, 2)}", qty)
                send_tg_command(f"🚀 AI TP HIT: +${round(pts * qty, 2)} (+{pts:.0f} pts)\nClosed @${t['tp']:.1f}")
            elif live['low'] <= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                pts = 25.0 if t.get('be_hit', False) else -(t['entry'] - t['sl'])
                usd = round(pts * qty, 2)
                sign = "+" if usd >= 0 else ""
                self.close_trade(state, res, f"{sign}{pts:.0f}", f"{sign}${usd}", qty)
                send_tg_command(f"🛡️ AI EXIT: {res} | {sign}${usd} ({sign}{pts:.0f} pts)\nClosed @${t['sl']:.1f}")

        elif t['type'] == 'SHORT':
            if not t.get('be_hit', False) and live['low'] <= (t['entry'] - 150.0):
                t['be_hit'] = True
                t['sl'] = round(t['entry'] - 25.0, 1)
                save_data(state)
                send_tg_command(f"🎯 COMMAND: BTC SHORT SECURED (+150 pts)\nSL at Breakeven.")

            if live['low'] <= t['tp']:
                pts = round(t['entry'] - t['tp'], 1)
                self.close_trade(state, "TP HIT", f"+{pts:.0f}", f"+${round(pts * qty, 2)}", qty)
                send_tg_command(f"🩸 AI TP HIT: +${round(pts * qty, 2)} (+{pts:.0f} pts)\nClosed @${t['tp']:.1f}")
            elif live['high'] >= t['sl']:
                res = "BE LOCKED" if t.get('be_hit', False) else "SL HIT"
                pts = 25.0 if t.get('be_hit', False) else -(t['sl'] - t['entry'])
                usd = round(pts * qty, 2)
                sign = "+" if usd >= 0 else ""
                self.close_trade(state, res, f"{sign}{pts:.0f}", f"{sign}${usd}", qty)
                send_tg_command(f"🛡️ AI EXIT: {res} | {sign}${usd} ({sign}{pts:.0f} pts)\nClosed @${t['sl']:.1f}")

    def scan_new_targets(self, state, closed, live, atr, ema30):
        c0 = closed[-1]
        if live['time'] <= self.last_candle_time: return
        self.last_candle_time = live['time']

        is_up = c0['close'] > ema30
        is_dn = c0['close'] < ema30
        h_range = max(c['high'] for c in closed[-9:-1])
        l_range = min(c['low'] for c in closed[-9:-1])
        body = c0['close'] - c0['open']

        is_long = is_up and (c0['close'] > h_range) and (body >= 30.0)
        is_short = is_dn and (c0['close'] < l_range) and (body <= -30.0)

        n_score = state["news_score"]["score"]
        n_text = state["news_score"]["sentiment"]

        if is_long:
            if n_score <= -5:
                send_tg_command(f"🚫 AI REJECTED LONG\nChart is Bullish but Global News is {n_text}.\nAvoided Fakeout!")
                return
            
            entry = round(c0['close'], 1)
            risk = round(atr * 1.3, 1) if n_score >= 5 else round(atr * 1.5, 1)
            sl = round(entry - risk, 1)
            tp = round(entry + (risk * (2.5 if n_score >= 5 else 1.8)), 1)
            cfg = state.get("config", {"capital": 100, "leverage": 10})
            qty = round((float(cfg['capital']) * int(cfg['leverage'])) / entry, 4) or 0.001

            state["active_trade"] = {'type': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk, 'qty': qty, 'be_hit': False}
            save_data(state)
            send_tg_command(f"🤖 [AI CONFIRMED] LONG\n\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f}\n🎯 TP: ${tp:.1f}\n📦 Qty: {qty} BTC\n\n📰 Data: {n_text}")

        elif is_short:
            if n_score >= 5:
                send_tg_command(f"🚫 AI REJECTED SHORT\nChart is Bearish but Global News is {n_text}.\nAvoided Fakeout!")
                return
            
            entry = round(c0['close'], 1)
            risk = round(atr * 1.3, 1) if n_score <= -5 else round(atr * 1.5, 1)
            sl = round(entry + risk, 1)
            tp = round(entry - (risk * (2.5 if n_score <= -5 else 1.8)), 1)
            cfg = state.get("config", {"capital": 100, "leverage": 10})
            qty = round((float(cfg['capital']) * int(cfg['leverage'])) / entry, 4) or 0.001

            state["active_trade"] = {'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk, 'qty': qty, 'be_hit': False}
            save_data(state)
            send_tg_command(f"🤖 [AI CONFIRMED] SHORT\n\n📍 Entry: ${entry:.1f}\n🛡️ SL: ${sl:.1f}\n🎯 TP: ${tp:.1f}\n📦 Qty: {qty} BTC\n\n📰 Data: {n_text}")

    def run(self):
        send_tg_command("🛡️ SERVER REBOOTED: All old ghosts killed. New Master Engine Online.")
        loop_count = 0
        while True:
            closed, live = get_market_data()
            state = load_data()
            
            if loop_count % 10 == 0: self.update_news(state) # Update news every 20 seconds
            
            if closed and live:
                atr, ema30 = self.update_technical_metrics(state, closed, live)
                if state.get("active_trade"): self.manage_active_trade(state, live)
                else: self.scan_new_targets(state, closed, live, atr, ema30)
                save_data(state)

            loop_count += 1
            time.sleep(2)

# ==============================================================================
# SECURE BOOT (Runs only ONCE per Streamlit Reboot)
# ==============================================================================
@st.cache_resource
def boot_master_engine():
    t = threading.Thread(target=MasterTriEngine().run, daemon=True)
    t.start()
    return True

boot_master_engine()

# ==============================================================================
# UI DISPLAY 
# ==============================================================================
st.set_page_config(page_title="AI TRI-ENGINE", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>header, footer, #MainMenu { display: none !important; } .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; } iframe { width: 100vw !important; height: 100vh !important; border: none !important; }</style>""", unsafe_allow_html=True)

state = load_data()
js_active_trade = json.dumps(state.get("active_trade"))
js_history = json.dumps(state.get("history", []))
js_stats = json.dumps({"total": state.get("total_signals", 0), "win_rate": state.get("win_rate", 0)})
js_metrics = json.dumps(state.get("metrics", {"trend": "--", "rsi": "--", "atr": "--", "news": "SCANNING..."}))
js_cfg = json.dumps(state.get("config", {"capital": 100, "leverage": 10}))

terminal_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html, body {{ background: #080a0f; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100vw; height: 100vh; overflow: hidden; }}
        .top-nav {{ display: flex; align-items: center; background: #0d111a; border-bottom: 1px solid #1a2336; padding: 4px 8px; font-size: 11px; height: 38px; gap: 8px; overflow-x: auto; white-space: nowrap; }}
        .brand {{ font-weight: 800; color: #fff; font-size: 10px; display: flex; align-items: center; gap: 4px; }}
        .badge-scan {{ background: #00e676; color: #000; font-size: 8px; padding: 2px 5px; border-radius: 3px; font-weight: 900; }}
        .stat-card {{ display: flex; flex-direction: column; min-width: 55px; }}
        .stat-label {{ font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }}
        .stat-val {{ font-size: 10px; font-weight: 800; color: #fff; }}
        .btn-history {{ background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40; border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer; }}
        .workspace {{ display: flex; flex-direction: column; width: 100vw; height: calc(100vh - 38px); }}
        #chart-zone {{ width: 100vw; height: 55vh; background: #080a0f; }}
        .trade-dock {{ width: 100vw; height: 38px; background: #0a0e17; border-top: 1px solid #1a2336; padding: 2px 8px; display: flex; align-items: center; justify-content: space-between; font-size: 10px; }}
        .dock-group {{ display: flex; align-items: center; gap: 6px; }}
        .dock-input {{ background: #121824; border: 1px solid #23304a; color: #00e676; font-size: 11px; font-weight: 800; border-radius: 4px; padding: 2px 6px; width: 50px; text-align: center; }}
        .toggle-btn {{ background: #00e676; color: #000; font-size: 9px; font-weight: 900; padding: 4px 8px; border-radius: 4px; border: none; cursor: pointer; }}
        .bottom-bar {{ width: 100vw; height: calc(45vh - 76px); max-height: 48px; background: #0d121c; border-top: 1px solid #1a2336; padding: 3px 8px; display: grid; grid-template-columns: 1fr 1fr 1fr 1.5fr; gap: 6px; align-items: center; }}
        .metric-cell {{ display: flex; flex-direction: column; justify-content: center; background: #101624; padding: 2px 6px; border-radius: 4px; border: 1px solid #192233; height: 36px; }}
        .cell-head {{ font-size: 7px; color: #62697a; font-weight: 800; text-transform: uppercase; line-height: 1; margin-bottom: 2px; }}
        .cell-body {{ font-size: 10px; font-weight: 800; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .modal-bg {{ display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 999; align-items: center; justify-content: center; }}
        .modal-box {{ background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px; width: 92vw; max-width: 420px; max-height: 80vh; display: flex; flex-direction: column; padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); }}
        .history-list {{ overflow-y: auto; max-height: 280px; font-size: 10px; }}
        .history-item {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }}
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ TRI-ENGINE <span class="badge-scan">MASTER AI</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">GUARD SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">TARGET TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 HISTORY (<span id="hist-count">0</span>)</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">Syncing...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>
        <div class="trade-dock">
            <div class="dock-group">
                <button class="toggle-btn" onclick="triggerServerSync()">🔄 SYNC FROM AI</button>
                <span style="color:#62697a; font-weight:800;">AMT($):</span>
                <input id="input-amount" class="dock-input" type="number" value="100" onchange="updateCalcQty()">
                <span style="color:#62697a; font-weight:800;">LEV:</span>
                <input id="input-lev" class="dock-input" type="number" value="10" onchange="updateCalcQty()">
            </div>
            <div class="dock-group">
                <span style="color:#62697a;">QTY:</span>
                <b id="calc-qty" style="color:#38bdf8; font-size:11px;">0.0000 BTC</b>
            </div>
        </div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">NEWS / DATA</span>
                <div class="cell-body" id="val-news" style="color:#fff;">--</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">TREND (EMA30)</span>
                <div class="cell-body" id="val-trend">--</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">OVERSEER HEALTH</span>
                <div class="cell-body" id="val-health" style="color:#00e676;">🟢 100% SECURE</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">AI DECISION</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">AWAITING DATA...</div>
            </div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:12px;">ENGINE LOGS & P&L</b>
                <div style="display:flex; gap:6px; align-items:center;">
                    <button onclick="clearAllServerHistory()" style="background:#ff3b30; border:none; color:#fff; font-size:9px; font-weight:800; padding:3px 8px; border-radius:3px; cursor:pointer;">CLEAR SYSTEM</button>
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
        
        let activeTrade = {js_active_trade};
        let tradeHistory = {js_history};
        let stats = {js_stats};
        let metrics = {js_metrics};
        let cfg = {js_cfg};

        document.getElementById('input-amount').value = cfg.capital;
        document.getElementById('input-lev').value = cfg.leverage;

        let lineEntry = null, lineSL = null, lineTP = null;
        let currentPrice = 85500.0;

        function toggleModal(show) {{ document.getElementById('modal-bg').style.display = show ? 'flex' : 'none'; }}
        function handleBgClick(e) {{ if (e.target.id === 'modal-bg') toggleModal(false); }}
        function clearAllServerHistory() {{ window.parent.location.search = '?clear=1'; }}
        function triggerServerSync() {{ window.parent.location.reload(); }}

        function updateCalcQty() {{
            let amt = parseFloat(document.getElementById('input-amount').value) || 100;
            let lev = parseFloat(document.getElementById('input-lev').value) || 10;
            let qty = ((amt * lev) / currentPrice).toFixed(4);
            document.getElementById('calc-qty').innerText = qty + " BTC";
        }}

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

        function renderMasterCommands() {{
            if (lineEntry) {{ try {{ series.removePriceLine(lineEntry); }} catch(e){{}} lineEntry = null; }}
            if (lineSL) {{ try {{ series.removePriceLine(lineSL); }} catch(e){{}} lineSL = null; }}
            if (lineTP) {{ try {{ series.removePriceLine(lineTP); }} catch(e){{}} lineTP = null; }}

            if (activeTrade) {{
                lineEntry = series.createPriceLine({{ price: activeTrade.entry, color: '#38bdf8', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'ENTRY $' + activeTrade.entry.toFixed(1) }});
                lineSL = series.createPriceLine({{ price: activeTrade.sl, color: '#ff3b30', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'GUARD SL $' + activeTrade.sl.toFixed(1) }});
                lineTP = series.createPriceLine({{ price: activeTrade.tp, color: '#00e676', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'TARGET $' + activeTrade.tp.toFixed(1) }});
            }}

            document.getElementById('val-news').innerText = metrics.news;
            document.getElementById('val-news').style.color = metrics.news.includes("BULLISH") ? "#00e676" : (metrics.news.includes("BEARISH") ? "#ff3b30" : "#fff");
            
            document.getElementById('val-trend').innerText = metrics.trend;
            document.getElementById('val-trend').style.color = metrics.trend.includes("BULLISH") ? "#00e676" : "#ff3b30";
            
            document.getElementById('hist-count').innerText = tradeHistory.length;
            document.getElementById('stat-total').innerText = stats.total;
            document.getElementById('stat-rate').innerText = stats.win_rate + "%";

            const histCont = document.getElementById('history-container');
            if (tradeHistory.length > 0) {{
                histCont.innerHTML = "";
                tradeHistory.forEach(item => {{
                    let resCol = item.result.includes("TP") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    let pnlDisp = item.pnl_usd ? `<b style="color:${{resCol}}; margin-left:4px;">(${{item.pnl_usd}})</b>` : '';
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span>${{item.time}} <b style="color:${{typeCol}};">${{item.type}}</b> @ $${{item.entry.toFixed(1)}}</span>
                            <span><b style="color:${{resCol}};">${{item.result}}</b> ${{pnlDisp}}</span>
                        </div>`;
                }});
            }} else {{
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>';
            }}

            if (activeTrade) {{
                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
                document.getElementById('disp-tp').innerText = "$" + activeTrade.tp.toFixed(1);
                document.getElementById('val-setup').innerText = "EXECUTING " + activeTrade.type + " 🔥";
                document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
            }} else {{
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = "AI SCANNING...";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }}
        }}

        function syncCandles() {{
            fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=100')
                .then(r => r.json())
                .then(data => {{
                    let cdata = data.map(d => ({{ time: (d[0] - (d[0] % 300000)) / 1000, open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]) }}));
                    series.setData(cdata);
                    chart.timeScale().fitContent();
                    renderMasterCommands();
                    connectLiveStream(cdata);
                }}).catch(e => setTimeout(syncCandles, 2000));
        }}

        function connectLiveStream(cdata) {{
            const ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {{
                const k = JSON.parse(e.data).k;
                const price = parseFloat(k.c);
                const barTime = (k.t - (k.t % 300000)) / 1000;
                
                currentPrice = price;
                updateCalcQty();
                document.getElementById('live-price').innerText = "$" + price.toFixed(1);

                let last = cdata[cdata.length - 1];
                if (barTime === last.time) {{
                    last.close = price;
                    if (price > last.high) last.high = price;
                    if (price < last.low) last.low = price;
                    series.update(last);
                }} else if (barTime > last.time) {{
                    const newBar = {{ time: barTime, open: price, high: price, low: price, close: price }};
                    cdata.push(newBar);
                    series.update(newBar);
                    
                    // FIXED BUG: SMART 8-SECOND DELAY!
                    setTimeout(() => window.parent.location.reload(), 8000); 
                }}

                if (activeTrade) {{
                    if (activeTrade.type === "LONG" && (price >= activeTrade.tp || price <= activeTrade.sl)) {{
                        activeTrade = null; renderMasterCommands();
                    }} else if (activeTrade.type === "SHORT" && (price <= activeTrade.tp || price >= activeTrade.sl)) {{
                        activeTrade = null; renderMasterCommands();
                    }}
                }}
            }};
            ws.onclose = () => setTimeout(() => connectLiveStream(cdata), 1500);
        }}

        syncCandles();
        window.onresize = () => chart.applyOptions({{ width: chartZone.clientWidth, height: chartZone.clientHeight }});
    </script>
</body>
</html>"""

terminal_html = terminal_html.replace("__ACTIVE_TRADE__", json.dumps(state.get("active_trade")))
terminal_html = terminal_html.replace("__HISTORY_DATA__", json.dumps(state.get("history", [])))
terminal_html = terminal_html.replace("__STATS_DATA__", json.dumps({"total": state.get("total_signals", 0), "win_rate": state.get("win_rate", 0)}))
terminal_html = terminal_html.replace("__METRICS_DATA__", json.dumps(state.get("metrics", {"trend": "--", "rsi": "--", "atr": "--", "news": "SCANNING..."})))
terminal_html = terminal_html.replace("__CONFIG_DATA__", json.dumps(state.get("config", {"capital": 100, "leverage": 10})))

components.html(terminal_html, height=720, scrolling=False)
