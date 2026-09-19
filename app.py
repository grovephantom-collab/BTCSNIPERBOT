import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests

# --- 24/7 CLOUD SERVER TRADING ENGINE (TELEGRAM DIRECT) ---
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
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
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

class CloudTrader:
    def __init__(self):
        self.active_trade = None
        self.last_alert_candle = 0

    def run(self):
        while True:
            try:
                r = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=80", timeout=8)
                data = r.json()
                candles = [{
                    'time': int(d[0]/1000),
                    'open': float(d[1]), 'high': float(d[2]),
                    'low': float(d[3]), 'close': float(d[4])
                } for d in data]

                if len(candles) >= 50:
                    self.evaluate(candles)
            except Exception:
                pass
            time.sleep(3)

    def evaluate(self, candles):
        current = candles[-1]
        closes = [c['close'] for c in candles]
        atr = calc_atr(candles, 14)
        ema20 = calc_ema(20, closes)
        ema50 = calc_ema(50, closes)
        rsi = calc_rsi(closes, 14)
        is_bull = ema20 > ema50

        if self.active_trade:
            if self.active_trade['type'] == 'LONG':
                if current['high'] >= self.active_trade['tp']:
                    send_tg(f"🎯 *TARGET ACHIEVED (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Long target hit at ${self.active_trade['tp']:.1f}!")
                    self.active_trade = None
                elif current['low'] <= self.active_trade['sl']:
                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Long exited at ${current['low']:.1f}.")
                    self.active_trade = None
            elif self.active_trade['type'] == 'SHORT':
                if current['low'] <= self.active_trade['tp']:
                    send_tg(f"🎯 *TARGET ACHIEVED (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Short target hit at ${self.active_trade['tp']:.1f}!")
                    self.active_trade = None
                elif current['high'] >= self.active_trade['sl']:
                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Short exited at ${current['high']:.1f}.")
                    self.active_trade = None
            return

        if current['time'] <= self.last_alert_candle:
            return

        prev_candles = candles[-8:-1]
        high_lvl = max(c['high'] for c in prev_candles)
        low_lvl = min(c['low'] for c in prev_candles)
        body = abs(current['close'] - current['open'])

        score = 0
        bias = "NONE"

        if current['close'] > high_lvl and current['close'] > ema20 and is_bull:
            bias = "LONG"
            score += 45
        elif current['close'] < low_lvl and current['close'] < ema20 and not is_bull:
            bias = "SHORT"
            score += 45

        if body >= (atr * 0.70):
            score += 35
        if bias == "LONG" and rsi >= 54:
            score += 20
        if bias == "SHORT" and rsi <= 46:
            score += 20

        if score >= 80:
            p = current['close']
            risk = max(120.0, min(180.0, atr * 1.2))
            reward = risk * 2.2

            if bias == "LONG":
                sl = p - risk
                tp = p + reward
                self.active_trade = {'type': 'LONG', 'entry': p, 'sl': sl, 'tp': tp, 'risk': risk, 'reward': reward}
                self.last_alert_candle = current['time']
                send_tg(f"🔥 *INSTITUTIONAL BTC 5M BUY*\\n\\n💰 *Entry:* ${p:.1f}\\n🛡️ *Safe SL:* ${sl:.1f} (-${risk:.1f})\\n🎯 *Big Target:* ${tp:.1f} (+${reward:.1f})\\n📊 *RR:* 1:2.2\\n⚡ _Expansion Confirmed_")
            elif bias == "SHORT":
                sl = p + risk
                tp = p - reward
                self.active_trade = {'type': 'SHORT', 'entry': p, 'sl': sl, 'tp': tp, 'risk': risk, 'reward': reward}
                self.last_alert_candle = current['time']
                send_tg(f"🔥 *INSTITUTIONAL BTC 5M SELL*\\n\\n💰 *Entry:* ${p:.1f}\\n🛡️ *Safe SL:* ${sl:.1f} (-${risk:.1f})\\n🎯 *Big Target:* ${tp:.1f} (+${reward:.1f})\\n📊 *RR:* 1:2.2\\n⚡ _Expansion Confirmed_")

if "bg_trader_started" not in st.session_state:
    st.session_state["bg_trader_started"] = True
    found = False
    for t in threading.enumerate():
        if t.name == "CloudTraderThread":
            found = True
            break
    if not found:
        ct = CloudTrader()
        t = threading.Thread(target=ct.run, name="CloudTraderThread", daemon=True)
        t.start()

# --- STREAMLIT CLEAN MOBILE UI ---
st.set_page_config(page_title="PRO QUANT SNIPER", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

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
            height: 42px;
            gap: 8px;
            overflow-x: auto;
            white-space: nowrap;
        }
        .top-nav::-webkit-scrollbar { display: none; }
        .brand { font-weight: 800; color: #fff; font-size: 11px; }
        .badge { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 9px; }
        .badge-idle { background: #151c2a; color: #848e9c; border: 1px solid #232d42; }
        .badge-long { background: rgba(0, 230, 118, 0.2); color: #00e676; border: 1px solid #00e676; }
        .badge-short { background: rgba(255, 59, 48, 0.2); color: #ff3b30; border: 1px solid #ff3b30; }

        .stat-card { display: flex; flex-direction: column; min-width: 55px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 700; }
        .stat-val { font-size: 10px; font-weight: 700; color: #fff; }

        .workspace {
            display: flex;
            flex-direction: column;
            width: 100vw;
            height: calc(100vh - 42px);
        }
        #chart-zone {
            width: 100vw;
            height: 48vh;
            background: #080a0f;
        }
        .side-bar {
            width: 100vw;
            height: calc(52vh - 42px);
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
        .card-header {
            font-size: 9px;
            font-weight: 700;
            color: #848e9c;
            text-transform: uppercase;
            margin-bottom: 2px;
            display: flex;
            justify-content: space-between;
        }
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
        <div class="brand">⚡ SNIPER 5M</div>
        <div id="status-badge" class="badge badge-idle">SCANNING</div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">BIG TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <div style="margin-left: auto; display: flex; align-items: center;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="side-bar">
            <div class="card card-full">
                <div class="card-header">
                    <span>BREAKOUT QUALITY</span>
                    <span id="bias-pill" style="padding:1px 4px; border-radius:3px; background:#1c2436; color:#848e9c; font-size:9px;">WAITING</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-size: 16px; font-weight: 800; color: #fff;" id="score-text">0 / 100</div>
                    <span style="font-size: 9px; color: #62697a;">Min: $120+ Expansion Required</span>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><span>METRICS</span><span style="color:#00e676;">LIVE ✅</span></div>
                <div class="row"><span>Trend</span><b id="trend-val" style="color:#fff;">--</b></div>
                <div class="row"><span>RSI (14)</span><b id="rsi-val" style="color:#fff;">--</b></div>
                <div class="row"><span>ATR Vol</span><b id="atr-val" style="color:#f0b90b;">--</b></div>
            </div>

            <div class="card">
                <div class="card-header"><span>ACTIVE TRADE</span><span id="trade-badge" style="color:#848e9c;">NONE</span></div>
                <div class="row"><span>Target Gain</span><b id="gain-pts" style="color:#00e676;">--</b></div>
                <div class="row"><span>Risk Buffer</span><b id="loss-pts" style="color:#ff3b30;">--</b></div>
                <div class="row"><span>Server Status</span><b style="color:#00e676;">24/7 ONLINE</b></div>
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
        let markers = [];
        let activeTrade = null;
        let entryLine = null, slLine = null, tpLine = null;

        try {
            const saved = localStorage.getItem('btc_sniper_active_trade');
            if (saved) activeTrade = JSON.parse(saved);
        } catch(e) {}

        function drawLines(t) {
            if (entryLine) series.removePriceLine(entryLine);
            if (slLine) series.removePriceLine(slLine);
            if (tpLine) series.removePriceLine(tpLine);

            entryLine = series.createPriceLine({ price: t.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' });
            tpLine = series.createPriceLine({ price: t.tp, color: '#00e676', lineWidth: 2, title: 'TARGET' });
            slLine = series.createPriceLine({ price: t.sl, color: '#ff3b30', lineWidth: 2, title: 'SL' });

            document.getElementById('disp-entry').innerText = "$" + t.entry.toFixed(1);
            document.getElementById('disp-sl').innerText = "$" + t.sl.toFixed(1);
            document.getElementById('disp-tp').innerText = "$" + t.tp.toFixed(1);
            document.getElementById('gain-pts').innerText = "+$" + t.reward.toFixed(1);
            document.getElementById('loss-pts').innerText = "-$" + t.risk.toFixed(1);
            document.getElementById('trade-badge').innerText = t.type;
            document.getElementById('trade-badge').style.color = t.type === 'LONG' ? '#00e676' : '#ff3b30';
            localStorage.setItem('btc_sniper_active_trade', JSON.stringify(t));
        }

        function clearLines() {
            if (entryLine) { series.removePriceLine(entryLine); entryLine = null; }
            if (slLine) { series.removePriceLine(slLine); slLine = null; }
            if (tpLine) { series.removePriceLine(tpLine); tpLine = null; }
            document.getElementById('disp-entry').innerText = "--";
            document.getElementById('disp-sl').innerText = "--";
            document.getElementById('disp-tp').innerText = "--";
            document.getElementById('gain-pts').innerText = "--";
            document.getElementById('loss-pts').innerText = "--";
            document.getElementById('trade-badge').innerText = "NONE";
            document.getElementById('trade-badge').style.color = "#848e9c";
            localStorage.removeItem('btc_sniper_active_trade');
        }

        fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=100')
            .then(res => res.json())
            .then(data => {
                candles = data.map(d => ({
                    time: Math.floor(d[0] / 1000),
                    open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                }));
                series.setData(candles);
                if (activeTrade) drawLines(activeTrade);
                connectLiveSocket();
            });

        function calcEMA(p, arr) {
            const k = 2 / (p + 1);
            let v = arr[0];
            for (let i = 1; i < arr.length; i++) v = (arr[i] * k) + (v * (1 - k));
            return v;
        }

        function calcATR(c, p = 14) {
            if (c.length < p + 1) return 120;
            let sum = 0;
            for (let i = c.length - p; i < c.length; i++) {
                sum += Math.max(c[i].high - c[i].low, Math.abs(c[i].high - c[i-1].close), Math.abs(c[i].low - c[i-1].close));
            }
            return sum / p;
        }

        function calcRSI(closes, p = 14) {
            if (closes.length < p + 1) return 50;
            let g = 0, l = 0;
            for (let i = closes.length - p; i < closes.length; i++) {
                const d = closes[i] - closes[i - 1];
                if (d >= 0) g += d; else l -= d;
            }
            return l === 0 ? 100 : 100 - (100 / (1 + ((g / p) / (l / p))));
        }

        function runLiveAnalysis(candle) {
            const closes = candles.map(c => c.close);
            const ema20 = calcEMA(20, closes);
            const ema50 = calcEMA(50, closes);
            const rsi = calcRSI(closes, 14);
            const atr = calcATR(candles, 14);

            document.getElementById('atr-val').innerText = "$" + atr.toFixed(1);
            document.getElementById('rsi-val').innerText = rsi.toFixed(1);

            const isBull = ema20 > ema50;
            document.getElementById('trend-val').innerText = isBull ? "BULL" : "BEAR";
            document.getElementById('trend-val').style.color = isBull ? "#00e676" : "#ff3b30";

            if (activeTrade) {
                if (activeTrade.type === "LONG") {
                    if (candle.high >= activeTrade.tp) { activeTrade = null; clearLines(); }
                    else if (candle.low <= activeTrade.sl) { activeTrade = null; clearLines(); }
                } else if (activeTrade.type === "SHORT") {
                    if (candle.low <= activeTrade.tp) { activeTrade = null; clearLines(); }
                    else if (candle.high >= activeTrade.sl) { activeTrade = null; clearLines(); }
                }
                return;
            }

            const c0 = candles[candles.length - 1];
            const prev = candles.slice(-8, -1);
            const highLvl = Math.max(...prev.map(c => c.high));
            const lowLvl = Math.min(...prev.map(c => c.low));
            const body = Math.abs(c0.close - c0.open);

            let score = 0;
            let bias = "NEUTRAL";

            if (c0.close > highLvl && c0.close > ema20 && isBull) { bias = "LONG"; score += 45; }
            else if (c0.close < lowLvl && c0.close < ema20 && !isBull) { bias = "SHORT"; score += 45; }

            if (body >= (atr * 0.70)) score += 35;
            if (bias === "LONG" && rsi >= 54) score += 20;
            if (bias === "SHORT" && rsi <= 46) score += 20;

            document.getElementById('score-text').innerText = score + " / 100";

            if (score >= 80) {
                const p = c0.close;
                const risk = Math.max(120, Math.min(180, atr * 1.2));
                const reward = risk * 2.2;

                if (bias === "LONG") {
                    activeTrade = { type: "LONG", entry: p, sl: p - risk, tp: p + reward, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'belowBar', color: '#00e676', shape: 'arrowUp', text: 'BUY' });
                    series.setMarkers(markers.slice(-4));
                    drawLines(activeTrade);
                } else if (bias === "SHORT") {
                    activeTrade = { type: "SHORT", entry: p, sl: p + risk, tp: p - reward, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'aboveBar', color: '#ff3b30', shape: 'arrowDown', text: 'SELL' });
                    series.setMarkers(markers.slice(-4));
                    drawLines(activeTrade);
                }
            }
        }

        function connectLiveSocket() {
            const ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {
                const k = JSON.parse(e.data).k;
                const c = { time: Math.floor(k.t / 1000), open: parseFloat(k.o), high: parseFloat(k.h), low: parseFloat(k.l), close: parseFloat(k.c) };
                document.getElementById('live-price').innerText = "$" + c.close.toFixed(1);
                series.update(c);

                const last = candles.length - 1;
                if (candles[last].time === c.time) candles[last] = c;
                else candles.push(c);

                runLiveAnalysis(c);
            };
            ws.onclose = () => { setTimeout(connectLiveSocket, 2000); };
        }

        window.addEventListener('resize', () => {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        });
    </script>
</body>
</html>
"""

components.html(terminal_html, height=850, scrolling=False)
