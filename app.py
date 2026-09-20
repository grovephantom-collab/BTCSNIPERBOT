import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests

# --- 24/7 CLOUD SERVER ENGINE (TELEGRAM DIRECT ON 5M CLOSED CANDLES) ---
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
        return 140.0
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

class InstitutionalEngine:
    def __init__(self):
        self.active_trade = None
        self.last_processed_candle_time = 0

    def run(self):
        while True:
            try:
                # Sirf complete closed candles uthayenge
                r = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=150", timeout=8)
                data = r.json()
                if len(data) >= 80:
                    # data[-1] abhi live ban rahi hai, data[-2] confirm closed candle hai
                    closed_kline = data[-2]
                    candle_time = int(closed_kline[0] / 1000)

                    # Har closed candle par sirf 1 baar calculation hogi
                    if candle_time > self.last_processed_candle_time:
                        self.last_processed_candle_time = candle_time
                        candles = [{
                            'time': int(d[0]/1000),
                            'open': float(d[1]), 'high': float(d[2]),
                            'low': float(d[3]), 'close': float(d[4]),
                            'volume': float(d[5])
                        } for d in data[:-1]]

                        current_live = {
                            'high': float(data[-1][2]),
                            'low': float(data[-1][3]),
                            'close': float(data[-1][4])
                        }
                        self.evaluate(candles, current_live)
            except Exception:
                pass
            time.sleep(10)

    def evaluate(self, candles, live_candle):
        c_last = candles[-1]
        closes = [c['close'] for c in candles]
        atr = calc_atr(candles, 14)
        ema20 = calc_ema(20, closes)
        ema50 = calc_ema(50, closes)
        rsi = calc_rsi(closes, 14)

        # 1. RUNNING POSITION SL/TP TRACKING
        if self.active_trade:
            if self.active_trade['type'] == 'LONG':
                if live_candle['high'] >= self.active_trade['tp']:
                    send_tg(f"🎯 *TARGET HIT (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Long target reached at ${self.active_trade['tp']:.1f}! Book Profit.")
                    self.active_trade = None
                elif live_candle['low'] <= self.active_trade['sl']:
                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Long safe exit at ${self.active_trade['sl']:.1f}.")
                    self.active_trade = None
            elif self.active_trade['type'] == 'SHORT':
                if live_candle['low'] <= self.active_trade['tp']:
                    send_tg(f"🎯 *TARGET HIT (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Short target reached at ${self.active_trade['tp']:.1f}! Book Profit.")
                    self.active_trade = None
                elif live_candle['high'] >= self.active_trade['sl']:
                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Short safe exit at ${self.active_trade['sl']:.1f}.")
                    self.active_trade = None
            return

        # 2. ACCURATE BIG MOVE SETUP (Consolidation Squeeze Breakout)
        # Pichhli 12 candles (1 hour) ka high/low consolidation zone
        lookback = candles[-13:-1]
        consolidation_high = max(c['high'] for c in lookback)
        consolidation_low = min(c['low'] for c in lookback)
        box_range = consolidation_high - consolidation_low

        # Filter: Range compress honi chahiye ($100 se $350 ke beech consolidation)
        is_squeezed = 100 <= box_range <= 350
        body = abs(c_last['close'] - c_last['open'])

        # Long Trigger: Closed candle box ke upar nikle, Trend Bullish ho, RSI 54-68 (Overbought na ho)
        long_condition = (
            c_last['close'] > consolidation_high and
            c_last['close'] > ema20 and
            ema20 > ema50 and
            body >= (atr * 0.75) and
            54 <= rsi <= 68
        )

        # Short Trigger: Closed candle box ke niche close ho, Trend Bearish ho, RSI 32-46
        short_condition = (
            c_last['close'] < consolidation_low and
            c_last['close'] < ema20 and
            ema20 < ema50 and
            body >= (atr * 0.75) and
            32 <= rsi <= 46
        )

        if is_squeezed and long_condition:
            entry = c_last['close']
            sl = consolidation_low - (atr * 0.3)
            risk = entry - sl
            if risk < 120: risk = 140
            if risk > 220: risk = 200
            sl = entry - risk
            reward = risk * 2.5
            tp = entry + reward

            self.active_trade = {'type': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk, 'reward': reward}
            send_tg(f"🚀 *INSTITUTIONAL BTC 5M BUY SIGNAL*\\n\\n💰 *Entry:* ${entry:.1f}\\n🛡️ *Safe SL:* ${sl:.1f} (-${risk:.1f})\\n🎯 *Big Target:* ${tp:.1f} (+${reward:.1f})\\n📊 *Risk/Reward:* 1:2.5\\n⚡ _Consolidation Breakout Confirmed_")

        elif is_squeezed and short_condition:
            entry = c_last['close']
            sl = consolidation_high + (atr * 0.3)
            risk = sl - entry
            if risk < 120: risk = 140
            if risk > 220: risk = 200
            sl = entry + risk
            reward = risk * 2.5
            tp = entry - reward

            self.active_trade = {'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk, 'reward': reward}
            send_tg(f"🩸 *INSTITUTIONAL BTC 5M SELL SIGNAL*\\n\\n💰 *Entry:* ${entry:.1f}\\n🛡️ *Safe SL:* ${sl:.1f} (-${risk:.1f})\\n🎯 *Big Target:* ${tp:.1f} (+${reward:.1f})\\n📊 *Risk/Reward:* 1:2.5\\n⚡ _Consolidation Breakdown Confirmed_")

# BACKGROUND DAEMON THREAD
if "quant_engine_started" not in st.session_state:
    st.session_state["quant_engine_started"] = True
    for th in threading.enumerate():
        if th.name == "QuantEngineThread":
            break
    else:
        inst_engine = InstitutionalEngine()
        t = threading.Thread(target=inst_engine.run, name="QuantEngineThread", daemon=True)
        t.start()

# --- STREAMLIT UI (SMOOTH NON-FLICKERING CHART & IST TIME) ---
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
            height: 40px;
            gap: 8px;
            overflow-x: auto;
            white-space: nowrap;
        }
        .top-nav::-webkit-scrollbar { display: none; }
        .brand { font-weight: 800; color: #fff; font-size: 11px; }
        .badge { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 9px; }
        .stat-card { display: flex; flex-direction: column; min-width: 58px; }
        .stat-label { font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 700; }
        .stat-val { font-size: 10px; font-weight: 700; color: #fff; }

        .workspace {
            display: flex;
            flex-direction: column;
            width: 100vw;
            height: calc(100vh - 40px);
        }
        #chart-zone {
            width: 100vw;
            height: 52vh;
            background: #080a0f;
        }
        .side-bar {
            width: 100vw;
            height: calc(48vh - 40px);
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
        <div class="brand">⚡ SNIPER 5M</div>
        <div id="status-badge" class="badge" style="background:#151c2a; color:#848e9c; border:1px solid #232d42;">SCANNING</div>
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
                <div style="font-size:9px; color:#848e9c; font-weight:700; display:flex; justify-content:space-between;">
                    <span>INSTITUTIONAL SETUP</span>
                    <span id="bias-pill" style="padding:1px 5px; border-radius:3px; background:#1c2436; color:#848e9c; font-size:9px;">MONITORING SQUEEZE</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:3px;">
                    <div style="font-size: 15px; font-weight: 800; color: #fff;" id="score-text">0 / 100</div>
                    <span style="font-size: 9px; color: #62697a;">Only Closed 5M Candles</span>
                </div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">METRICS</div>
                <div class="row"><span>Trend</span><b id="trend-val" style="color:#fff;">--</b></div>
                <div class="row"><span>RSI</span><b id="rsi-val" style="color:#fff;">--</b></div>
                <div class="row"><span>ATR</span><b id="atr-val" style="color:#f0b90b;">--</b></div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">TRADE INFO</div>
                <div class="row"><span>Reward</span><b id="gain-pts" style="color:#00e676;">--</b></div>
                <div class="row"><span>Risk</span><b id="loss-pts" style="color:#ff3b30;">--</b></div>
                <div class="row"><span>Alerts</span><b style="color:#00e676;">TG Active ✅</b></div>
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
            timeScale: { 
                borderColor: '#192130', 
                timeVisible: true,
                secondsVisible: false
            },
            localization: {
                // Indian Standard Time (+5:30) offset
                timeFormatter: timestamp => {
                    const date = new Date((timestamp + (5.5 * 3600)) * 1000);
                    return date.toISOString().substr(11, 5);
                }
            }
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
        let lastTriggeredCandle = 0;

        function drawTradeLines(trade) {
            if (entryLine) series.removePriceLine(entryLine);
            if (slLine) series.removePriceLine(slLine);
            if (tpLine) series.removePriceLine(tpLine);

            entryLine = series.createPriceLine({ price: trade.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' });
            tpLine = series.createPriceLine({ price: trade.tp, color: '#00e676', lineWidth: 2, title: 'BIG TP' });
            slLine = series.createPriceLine({ price: trade.sl, color: '#ff3b30', lineWidth: 2, title: 'SAFE SL' });

            document.getElementById('disp-entry').innerText = "$" + trade.entry.toFixed(1);
            document.getElementById('disp-sl').innerText = "$" + trade.sl.toFixed(1);
            document.getElementById('disp-tp').innerText = "$" + trade.tp.toFixed(1);
            document.getElementById('gain-pts').innerText = "+$" + trade.reward.toFixed(1);
            document.getElementById('loss-pts').innerText = "-$" + trade.risk.toFixed(1);
            
            const badge = document.getElementById('status-badge');
            badge.innerText = trade.type + " ACTIVE";
            badge.style.background = trade.type === "LONG" ? "rgba(0, 230, 118, 0.2)" : "rgba(255, 59, 48, 0.2)";
            badge.style.color = trade.type === "LONG" ? "#00e676" : "#ff3b30";
            badge.style.border = "1px solid " + (trade.type === "LONG" ? "#00e676" : "#ff3b30");
        }

        function clearTradeLines() {
            if (entryLine) { series.removePriceLine(entryLine); entryLine = null; }
            if (slLine) { series.removePriceLine(slLine); slLine = null; }
            if (tpLine) { series.removePriceLine(tpLine); tpLine = null; }
            document.getElementById('disp-entry').innerText = "--";
            document.getElementById('disp-sl').innerText = "--";
            document.getElementById('disp-tp').innerText = "--";
            document.getElementById('gain-pts').innerText = "--";
            document.getElementById('loss-pts').innerText = "--";
            const badge = document.getElementById('status-badge');
            badge.innerText = "SCANNING";
            badge.style.background = "#151c2a";
            badge.style.color = "#848e9c";
            badge.style.border = "1px solid #232d42";
        }

        fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=100')
            .then(res => res.json())
            .then(data => {
                candles = data.map(d => ({
                    time: Math.floor(d[0] / 1000),
                    open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                }));
                series.setData(candles);
                initWebSocket();
            });

        function calcEMA(p, arr) {
            const k = 2 / (p + 1);
            let v = arr[0];
            for (let i = 1; i < arr.length; i++) v = (arr[i] * k) + (v * (1 - k));
            return v;
        }

        function calcATR(c, p = 14) {
            if (c.length < p + 1) return 140;
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
                const diff = closes[i] - closes[i - 1];
                if (diff >= 0) g += diff; else l -= diff;
            }
            return l === 0 ? 100 : 100 - (100 / (1 + ((g / p) / (l / p))));
        }

        // ONLY TRIGGER ON CLOSED CANDLE EVENT (ZERO DUPLICATE SIGNALS)
        function processClosedCandle(c_last) {
            if (c_last.time <= lastTriggeredCandle) return;

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

            if (activeTrade) return;

            const lookback = candles.slice(-13, -1);
            const boxHigh = Math.max(...lookback.map(c => c.high));
            const boxLow = Math.min(...lookback.map(c => c.low));
            const boxRange = boxHigh - boxLow;
            const body = Math.abs(c_last.close - c_last.open);

            let score = 0;
            if (boxRange >= 100 && boxRange <= 350) score += 30; // Compression confirmed

            let bias = "NONE";
            if (c_last.close > boxHigh && c_last.close > ema20 && isBull && rsi >= 54 && rsi <= 68) {
                bias = "LONG"; score += 50;
            } else if (c_last.close < boxLow && c_last.close < ema20 && !isBull && rsi <= 46 && rsi >= 32) {
                bias = "SHORT"; score += 50;
            }

            if (body >= (atr * 0.75)) score += 20;
            document.getElementById('score-text').innerText = score + " / 100";

            if (score >= 80) {
                lastTriggeredCandle = c_last.time;
                const p = c_last.close;
                let risk = bias === "LONG" ? (p - boxLow) : (boxHigh - p);
                if (risk < 120) risk = 140;
                if (risk > 220) risk = 200;
                const reward = risk * 2.5;

                if (bias === "LONG") {
                    activeTrade = { type: "LONG", entry: p, sl: p - risk, tp: p + reward, risk: risk, reward: reward };
                    markers.push({ time: c_last.time, position: 'belowBar', color: '#00e676', shape: 'arrowUp', text: 'BUY' });
                } else {
                    activeTrade = { type: "SHORT", entry: p, sl: p + risk, tp: p - reward, risk: risk, reward: reward };
                    markers.push({ time: c_last.time, position: 'aboveBar', color: '#ff3b30', shape: 'arrowDown', text: 'SELL' });
                }
                series.setMarkers(markers.slice(-3));
                drawTradeLines(activeTrade);
            }
        }

        function initWebSocket() {
            const ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {
                const k = JSON.parse(e.data).k;
                const candle = { 
                    time: Math.floor(k.t / 1000), 
                    open: parseFloat(k.o), 
                    high: parseFloat(k.h), 
                    low: parseFloat(k.l), 
                    close: parseFloat(k.c) 
                };

                document.getElementById('live-price').innerText = "$" + candle.close.toFixed(1);
                series.update(candle);

                const last = candles.length - 1;
                if (candles[last].time === candle.time) {
                    candles[last] = candle;
                } else {
                    candles.push(candle);
                }

                // Active Trade TP / SL Live Exit Monitoring
                if (activeTrade) {
                    if (activeTrade.type === "LONG") {
                        if (candle.high >= activeTrade.tp || candle.low <= activeTrade.sl) {
                            activeTrade = null;
                            clearTradeLines();
                        }
                    } else if (activeTrade.type === "SHORT") {
                        if (candle.low <= activeTrade.tp || candle.high >= activeTrade.sl) {
                            activeTrade = null;
                            clearTradeLines();
                        }
                    }
                }

                // Candle Closed Event (k.x === true)
                if (k.x === true) {
                    processClosedCandle(candle);
                }
            };
            ws.onclose = () => { setTimeout(initWebSocket, 2000); };
        }

        window.addEventListener('resize', () => {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        });
    </script>
</body>
</html>
"""

components.html(terminal_html, height=850, scrolling=False)
