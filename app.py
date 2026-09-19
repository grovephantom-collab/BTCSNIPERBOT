import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests
import json
import websocket

# --- BACKGROUND TRADING ENGINE (RUNS 24/7 INDEPENDENT OF BROWSER) ---
BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"

def send_tg(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except Exception:
        pass

def calc_ema(period, values):
    k = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = (v * k) + (ema * (1 - k))
    return ema

def calc_atr(candles, p=14):
    if len(candles) < p + 1:
        return 120.0
    trs = []
    for i in range(len(candles)-p, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        prev_c = candles[i-1]['close']
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return sum(trs) / p

def calc_rsi(closes, p=14):
    if len(closes) < p + 1:
        return 50.0
    gains, losses = [], []
    for i in range(len(closes)-p, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains) / p
    avg_loss = sum(losses) / p
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

class BotEngine:
    def __init__(self):
        self.candles = []
        self.active_trade = None
        self.last_candle_time = 0
        self.last_alert_time = 0

    def init_history(self):
        try:
            r = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=120", timeout=10)
            data = r.json()
            self.candles = [{
                'time': int(d[0]/1000),
                'open': float(d[1]), 'high': float(d[2]),
                'low': float(d[3]), 'close': float(d[4]),
                'volume': float(d[5])
            } for d in data]
        except Exception:
            pass

    def evaluate(self, current_candle):
        if len(self.candles) < 60:
            return

        closes = [c['close'] for c in self.candles]
        atr = calc_atr(self.candles, 14)
        ema20 = calc_ema(20, closes)
        ema50 = calc_ema(50, closes)
        rsi = calc_rsi(closes, 14)
        is_bullish = ema20 > ema50

        # ACTIVE POSITION TARGET / SL MONITORING
        if self.active_trade:
            if self.active_trade['type'] == 'LONG':
                if current_candle['high'] >= self.active_trade['tp']:
                    send_tg(f"🎯 *TARGET HIT (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Long target reached at ${self.active_trade['tp']:.1f}! Position Closed.")
                    self.active_trade = None
                elif current_candle['low'] <= self.active_trade['sl']:
                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Long exited at ${current_candle['low']:.1f}.")
                    self.active_trade = None
            elif self.active_trade['type'] == 'SHORT':
                if current_candle['low'] <= self.active_trade['tp']:
                    send_tg(f"🎯 *TARGET HIT (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Short target reached at ${self.active_trade['tp']:.1f}! Position Closed.")
                    self.active_trade = None
                elif current_candle['high'] >= self.active_trade['sl']:
                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Short exited at ${current_candle['high']:.1f}.")
                    self.active_trade = None
            return

        # NEW INSTITUTIONAL MOVE TRIGGER (ONLY ON COMPLETED CANDLE TIME TO PREVENT DUPLICATES)
        c0 = self.candles[-1]
        if c0['time'] <= self.last_alert_time:
            return

        prev5 = self.candles[-8:-1]
        range_high = max(c['high'] for c in prev5)
        range_low = min(c['low'] for c in prev5)
        body_size = abs(c0['close'] - c0['open'])

        score = 0
        bias = "NONE"

        if c0['close'] > range_high and c0['close'] > ema20 and is_bullish:
            bias = "LONG"
            score += 45
        elif c0['close'] < range_low and c0['close'] < ema20 and not is_bullish:
            bias = "SHORT"
            score += 45

        if body_size >= (atr * 0.70):
            score += 35

        if bias == "LONG" and rsi >= 54:
            score += 20
        elif bias == "SHORT" and rsi <= 46:
            score += 20

        if score >= 80:
            p = c0['close']
            risk = max(120.0, min(180.0, atr * 1.2))
            reward = risk * 2.2

            if bias == "LONG":
                sl = p - risk
                tp = p + reward
                self.active_trade = {'type': 'LONG', 'entry': p, 'sl': sl, 'tp': tp, 'risk': risk, 'reward': reward}
                self.last_alert_time = c0['time']
                send_tg(f"🔥 *ACCURATE BTC 5M BUY*\\n\\n💰 *Entry:* ${p:.1f}\\n🛡️ *Safe SL:* ${sl:.1f} (-${risk:.1f})\\n🎯 *Big Target:* ${tp:.1f} (+${reward:.1f})\\n📊 *RR:* 1:2.2\\n⚡ _Institutional Breakout Confirmed_")
            elif bias == "SHORT":
                sl = p + risk
                tp = p - reward
                self.active_trade = {'type': 'SHORT', 'entry': p, 'sl': sl, 'tp': tp, 'risk': risk, 'reward': reward}
                self.last_alert_time = c0['time']
                send_tg(f"🔥 *ACCURATE BTC 5M SELL*\\n\\n💰 *Entry:* ${p:.1f}\\n🛡️ *Safe SL:* ${sl:.1f} (-${risk:.1f})\\n🎯 *Big Target:* ${tp:.1f} (+${reward:.1f})\\n📊 *RR:* 1:2.2\\n⚡ _Institutional Breakdown Confirmed_")

    def run_ws(self):
        while True:
            try:
                self.init_history()
                def on_message(ws, msg):
                    d = json.loads(msg)
                    k = d['k']
                    candle = {
                        'time': int(k['t']/1000),
                        'open': float(k['o']), 'high': float(k['h']),
                        'low': float(k['l']), 'close': float(k['c']),
                        'volume': float(k['v'])
                    }
                    if len(self.candles) > 0:
                        if self.candles[-1]['time'] == candle['time']:
                            self.candles[-1] = candle
                        else:
                            self.candles.append(candle)
                            if len(self.candles) > 200:
                                self.candles.pop(0)
                    self.evaluate(candle)

                ws = websocket.WebSocketApp(
                    "wss://stream.binance.com:9443/ws/btcusdt@kline_5m",
                    on_message=on_message
                )
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                time.sleep(3)

# START SINGLETON THREAD ON CLOUD
if "bg_engine_started" not in st.session_state:
    st.session_state["bg_engine_started"] = True
    for t in threading.enumerate():
        if t.name == "BTCSniperWorker":
            break
    else:
        engine = BotEngine()
        th = threading.Thread(target=engine.run_ws, name="BTCSniperWorker", daemon=True)
        th.start()

# --- STREAMLIT UI ---
st.set_page_config(page_title="BTC SNIPER 5M", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    header, footer, #MainMenu { display: none !important; }
    .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
    iframe { width: 100vw !important; height: 100vh !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

terminal_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            background: #080a0f;
            color: #d1d4dc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
        }
        .top-nav {
            display: flex;
            align-items: center;
            background: #0d111a;
            border-bottom: 1px solid #1a2336;
            padding: 6px 10px;
            font-size: 11px;
            height: 38px;
            gap: 10px;
        }
        .workspace {
            display: flex;
            flex-direction: column;
            width: 100vw;
            height: calc(100vh - 38px);
        }
        #chart-zone {
            width: 100vw;
            height: 52vh;
            background: #080a0f;
        }
        .side-bar {
            width: 100vw;
            height: calc(48vh - 38px);
            background: #0b0f17;
            border-top: 1px solid #161d2b;
            padding: 8px 10px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }
        .card {
            background: #101520;
            border: 1px solid #1a2233;
            border-radius: 6px;
            padding: 6px 8px;
            font-size: 11px;
        }
        .card-full { grid-column: span 2; }
        .row {
            display: flex;
            justify-content: space-between;
            padding: 2px 0;
            font-size: 10px;
            border-bottom: 1px solid #151c2a;
        }
        .row:last-child { border-bottom: none; }
    </style>
</head>
<body>
    <div class="top-nav">
        <b style="color:#fff;">⚡ BTC SNIPER 5M</b>
        <span style="color:#00e676; font-size:10px; font-weight:700;">● CLOUD WORKER ACTIVE</span>
        <b id="price" style="margin-left:auto; color:#f0b90b; font-size:12px;">...</b>
    </div>
    <div class="workspace">
        <div id="chart-zone"></div>
        <div class="side-bar">
            <div class="card card-full">
                <div style="font-size:9px; color:#848e9c; font-weight:700;">24/7 SERVER STATUS</div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                    <span style="color:#00e676; font-weight:800; font-size:12px;">BACKGROUND BOT RUNNING ✅</span>
                    <span style="font-size:9px; color:#62697a;">Zero Re-triggers</span>
                </div>
            </div>
            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:3px;">EXECUTION</div>
                <div class="row"><span>Alerts</span><b style="color:#00e676;">Telegram Direct</b></div>
                <div class="row"><span>Timeframe</span><b style="color:#fff;">5M Institutional</b></div>
            </div>
            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:3px;">PROFILE</div>
                <div class="row"><span>Target</span><b style="color:#00e676;">1:2.2 RR ($250+)</b></div>
                <div class="row"><span>Protection</span><b style="color:#ff3b30;">ATR Safe Buffer</b></div>
            </div>
        </div>
    </div>
    <script>
        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {
            width: chartZone.clientWidth,
            height: chartZone.clientHeight,
            layout: { background: { color: '#080a0f' }, textColor: '#787b86' },
            grid: { vertLines: { color: '#111622' }, horzLines: { color: '#111622' } },
            rightPriceScale: { borderColor: '#192130' },
            timeScale: { borderColor: '#192130', timeVisible: true }
        });
        const series = chart.addCandlestickSeries({
            upColor: '#00E676', downColor: '#FF3B30',
            borderUpColor: '#00E676', borderDownColor: '#FF3B30',
            wickUpColor: '#00E676', wickDownColor: '#FF3B30',
        });

        let candles = [];
        fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=100')
            .then(res => res.json())
            .then(data => {
                candles = data.map(d => ({
                    time: Math.floor(d[0] / 1000),
                    open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                }));
                series.setData(candles);
            });

        const ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
        ws.onmessage = (e) => {
            const k = JSON.parse(e.data).k;
            const c = { time: Math.floor(k.t / 1000), open: parseFloat(k.o), high: parseFloat(k.h), low: parseFloat(k.l), close: parseFloat(k.c) };
            document.getElementById('price').innerText = "$" + c.close.toFixed(1);
            series.update(c);
        };

        window.addEventListener('resize', () => {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        });
    </script>
</body>
</html>
"""

components.html(terminal_html, height=850, scrolling=False)
