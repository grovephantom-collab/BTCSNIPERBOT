import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="PRO QUANT SNIPER | BTC 5M",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Streamlit container padding aur iframe ko pure mobile width par stretch karna
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
        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        html, body {
            background: #080a0f;
            color: #d1d4dc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            width: 100%;
            overflow-x: hidden;
        }

        .top-nav {
            display: flex;
            align-items: center;
            background: #0d111a;
            border-bottom: 1px solid #1a2336;
            padding: 8px 10px;
            font-size: 11px;
            gap: 10px;
            overflow-x: auto;
            white-space: nowrap;
            width: 100%;
        }
        .brand { font-weight: 800; color: #fff; font-size: 12px; }
        .badge {
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 10px;
        }
        .badge-idle { background: #151c2a; color: #848e9c; border: 1px solid #232d42; }
        .badge-long { background: rgba(0, 230, 118, 0.2); color: #00e676; border: 1px solid #00e676; }
        .badge-short { background: rgba(255, 59, 48, 0.2); color: #ff3b30; border: 1px solid #ff3b30; }

        .stat-card { display: flex; flex-direction: column; min-width: 60px; }
        .stat-label { font-size: 8px; color: #62697a; text-transform: uppercase; font-weight: 600; }
        .stat-val { font-size: 11px; font-weight: 700; color: #fff; }

        /* FLEX CONTAINER */
        .workspace {
            display: flex;
            flex-direction: column; /* Mobile by default: Chart UP, Cards DOWN */
            width: 100%;
        }
        #chart-zone {
            width: 100vw;
            height: 56vh; /* Mobile standard height */
            min-height: 350px;
            background: #080a0f;
        }
        .side-bar {
            width: 100vw;
            background: #0b0f17;
            border-top: 1px solid #161d2b;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding-bottom: 60px;
        }

        /* LAPTOP DESKTOP OVERRIDE (Screen > 850px) */
        @media (min-width: 851px) {
            .workspace {
                flex-direction: row;
                height: calc(100vh - 48px);
            }
            #chart-zone {
                flex: 1;
                height: 100%;
                min-height: unset;
                width: auto;
            }
            .side-bar {
                width: 330px;
                border-top: none;
                border-left: 1px solid #161d2b;
                overflow-y: auto;
                padding-bottom: 20px;
            }
        }

        .card {
            background: #101520;
            border: 1px solid #1a2233;
            border-radius: 6px;
            padding: 10px 12px;
            font-size: 12px;
        }
        .card-header {
            font-size: 10px;
            font-weight: 700;
            color: #848e9c;
            text-transform: uppercase;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
        }
        .row {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid #151c2a;
        }
        .row:last-child { border-bottom: none; }
    </style>
</head>
<body>

    <div class="top-nav">
        <div class="brand">⚡ SNIPER RADAR</div>
        <div id="status-badge" class="badge badge-idle">MONITORING BTC 5M</div>
        <div class="stat-card">
            <div class="stat-label">ENTRY</div>
            <div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">STOP LOSS</div>
            <div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">TARGET</div>
            <div id="disp-tp" class="stat-val" style="color:#00e676;">--</div>
        </div>
        <div style="margin-left: auto; display: flex; align-items: center;">
            <b id="live-price" style="color: #f0b90b; font-size: 13px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="side-bar">
            <div class="card" style="border: 1px solid #293854;">
                <div class="card-header">
                    <span>EXPLOSION INTENSITY</span>
                    <span id="bias-pill" style="padding:2px 6px; border-radius:3px; background:#1c2436; color:#848e9c;">WAITING</span>
                </div>
                <div style="font-size: 22px; font-weight: 800; color: #fff;" id="score-text">0 / 100</div>
                <div style="font-size: 10px; color: #62697a; margin-top: 4px;">Dynamic Breakout & Range Expansion Engine</div>
            </div>

            <div class="card">
                <div class="card-header"><span>MARKET METRICS</span><span style="color:#00e676;">LIVE</span></div>
                <div class="row"><span style="color:#787b86;">RSI (14)</span><b id="rsi-val" style="color:#fff;">--</b></div>
                <div class="row"><span style="color:#787b86;">Market ATR</span><b id="atr-val" style="color:#f0b90b;">--</b></div>
                <div class="row"><span style="color:#787b86;">Candle Pace</span><b id="candle-pace" style="color:#00e676;">SCANNING</b></div>
            </div>

            <div class="card">
                <div class="card-header"><span>ACTIVE TRADE MONITOR</span></div>
                <div class="row"><span style="color:#787b86;">Projected Profit</span><b id="gain-pts" style="color:#00e676;">--</b></div>
                <div class="row"><span style="color:#787b86;">Defined Risk</span><b id="loss-pts" style="color:#ff3b30;">--</b></div>
                <div class="row"><span style="color:#787b86;">Telegram Bot</span><b id="tg-status" style="color:#00e676;">ONLINE DIRECT ✅</b></div>
                <div class="row"><span style="color:#787b86;">Status</span><b id="exec-state" style="color:#848e9c;">IDLE</b></div>
            </div>
        </div>
    </div>

    <script>
        const BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4";
        const CHAT_ID = "7886716805";

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
        let lastTriggerTime = 0;

        function sendDirectTelegram(text) {
            fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ chat_id: CHAT_ID, text: text, parse_mode: "Markdown" })
            }).then(() => {
                document.getElementById('tg-status').innerText = "SENT 📲";
                setTimeout(() => { document.getElementById('tg-status').innerText = "ONLINE DIRECT ✅"; }, 4000);
            }).catch(e => console.error(e));
        }

        function clearAllTradeLines() {
            if (entryLine) { series.removePriceLine(entryLine); entryLine = null; }
            if (slLine) { series.removePriceLine(slLine); slLine = null; }
            if (tpLine) { series.removePriceLine(tpLine); tpLine = null; }
            document.getElementById('disp-entry').innerText = "--";
            document.getElementById('disp-sl').innerText = "--";
            document.getElementById('disp-tp').innerText = "--";
            document.getElementById('gain-pts').innerText = "--";
            document.getElementById('loss-pts').innerText = "--";
            document.getElementById('exec-state').innerText = "IDLE";
            document.getElementById('exec-state').style.color = "#848e9c";
        }

        function drawActiveTrade(trade) {
            clearAllTradeLines();
            entryLine = series.createPriceLine({ price: trade.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' });
            tpLine = series.createPriceLine({ price: trade.tp, color: '#00e676', lineWidth: 2, title: 'TARGET' });
            slLine = series.createPriceLine({ price: trade.sl, color: '#ff3b30', lineWidth: 2, title: 'SL' });

            document.getElementById('disp-entry').innerText = "$" + trade.entry.toFixed(1);
            document.getElementById('disp-sl').innerText = "$" + trade.sl.toFixed(1);
            document.getElementById('disp-tp').innerText = "$" + trade.tp.toFixed(1);
            document.getElementById('gain-pts').innerText = "+$" + trade.reward.toFixed(1);
            document.getElementById('loss-pts').innerText = "-$" + trade.risk.toFixed(1);
            document.getElementById('exec-state').innerText = trade.type + " ACTIVE";
            document.getElementById('exec-state').style.color = trade.type === "LONG" ? "#00e676" : "#ff3b30";
        }

        fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=150')
            .then(res => res.json())
            .then(data => {
                candles = data.map(d => ({
                    time: Math.floor(d[0] / 1000),
                    open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]), volume: parseFloat(d[5])
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
            if (c.length < p + 1) return 100;
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

        function evaluateTradeEngine(candle) {
            const closes = candles.map(c => c.close);
            const ema9 = calcEMA(9, closes);
            const ema21 = calcEMA(21, closes);
            const rsi = calcRSI(closes, 14);
            const atr = calcATR(candles, 14);

            document.getElementById('atr-val').innerText = "$" + atr.toFixed(1);
            document.getElementById('rsi-val').innerText = rsi.toFixed(1);

            if (activeTrade) {
                if (activeTrade.type === "LONG") {
                    if (candle.high >= activeTrade.tp) {
                        document.getElementById('status-badge').innerText = "TARGET REACHED 🎯";
                        document.getElementById('status-badge').className = "badge badge-long";
                        sendDirectTelegram(`🎯 *TARGET ACHIEVED (LONG)*\\n\\nExit Level: $${activeTrade.tp.toFixed(1)}\\nProfit Locked!`);
                        activeTrade = null; clearAllTradeLines();
                    } else if (candle.low <= activeTrade.sl) {
                        document.getElementById('status-badge').innerText = "SL EXIT 🛡️";
                        document.getElementById('status-badge').className = "badge badge-short";
                        sendDirectTelegram(`🛡️ *STOP LOSS (LONG)*\\n\\nExit: $${candle.low.toFixed(1)}`);
                        activeTrade = null; clearAllTradeLines();
                    }
                } else if (activeTrade.type === "SHORT") {
                    if (candle.low <= activeTrade.tp) {
                        document.getElementById('status-badge').innerText = "TARGET REACHED 🎯";
                        document.getElementById('status-badge').className = "badge badge-long";
                        sendDirectTelegram(`🎯 *TARGET ACHIEVED (SHORT)*\\n\\nExit Level: $${activeTrade.tp.toFixed(1)}\\nProfit Locked!`);
                        activeTrade = null; clearAllTradeLines();
                    } else if (candle.high >= activeTrade.sl) {
                        document.getElementById('status-badge').innerText = "SL EXIT 🛡️";
                        document.getElementById('status-badge').className = "badge badge-short";
                        sendDirectTelegram(`🛡️ *STOP LOSS (SHORT)*\\n\\nExit: $${candle.high.toFixed(1)}`);
                        activeTrade = null; clearAllTradeLines();
                    }
                }
                return;
            }

            const c0 = candles[candles.length - 1];
            const c1 = candles[candles.length - 2];
            const c2 = candles[candles.length - 3];
            const recentHigh = Math.max(c1.high, c2.high);
            const recentLow = Math.min(c1.low, c2.low);
            const bodySize = Math.abs(c0.close - c0.open);

            let score = 0;
            let bias = "NEUTRAL";

            if (c0.close < recentLow) { score += 40; bias = "SHORT"; }
            else if (c0.close > recentHigh) { score += 40; bias = "LONG"; }

            if (bodySize > (atr * 0.35)) {
                score += 30;
                document.getElementById('candle-pace').innerText = "FAST MOVE ⚡";
                document.getElementById('candle-pace').style.color = "#00e676";
            } else {
                document.getElementById('candle-pace').innerText = "NORMAL";
                document.getElementById('candle-pace').style.color = "#848e9c";
            }

            if (bias === "SHORT" && c0.close < ema9 && ema9 < ema21) score += 30;
            else if (bias === "LONG" && c0.close > ema9 && ema9 > ema21) score += 30;

            document.getElementById('score-text').innerText = score + " / 100";
            const now = Math.floor(Date.now() / 1000);

            if (score >= 70 && (now - lastTriggerTime > 120)) {
                const p = c0.close;

                if (bias === "SHORT") {
                    const risk = Math.max(45, Math.min(80, (c0.high - p) + 10));
                    const reward = risk * 1.8;
                    const sl = p + risk;
                    const tp = p - reward;

                    lastTriggerTime = now;
                    activeTrade = { type: "SHORT", entry: p, sl: sl, tp: tp, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'aboveBar', color: '#ff3b30', shape: 'arrowDown', text: 'SELL' });
                    series.setMarkers(markers.slice(-4));
                    drawActiveTrade(activeTrade);

                    document.getElementById('status-badge').innerText = "🔴 SHORT RUNNING";
                    document.getElementById('status-badge').className = "badge badge-short";
                    document.getElementById('bias-pill').innerText = "SHORT TRIGGER";
                    document.getElementById('bias-pill').style.background = "#ff3b30";
                    document.getElementById('bias-pill').style.color = "#fff";

                    sendDirectTelegram(`🔴 *BTC/USDT 5M SHORT BREAKDOWN*\\n\\n💰 Entry: $${p.toFixed(1)}\\n🛡️ Stop Loss: $${sl.toFixed(1)} (-$${risk.toFixed(1)})\\n🎯 Target: $${tp.toFixed(1)} (+$${reward.toFixed(1)})\\n⚡ _Velocity Break below $${recentLow.toFixed(1)}_`);
                } else if (bias === "LONG") {
                    const risk = Math.max(45, Math.min(80, (p - c0.low) + 10));
                    const reward = risk * 1.8;
                    const sl = p - risk;
                    const tp = p + reward;

                    lastTriggerTime = now;
                    activeTrade = { type: "LONG", entry: p, sl: sl, tp: tp, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'belowBar', color: '#00e676', shape: 'arrowUp', text: 'BUY' });
                    series.setMarkers(markers.slice(-4));
                    drawActiveTrade(activeTrade);

                    document.getElementById('status-badge').innerText = "🟢 LONG RUNNING";
                    document.getElementById('status-badge').className = "badge badge-long";
                    document.getElementById('bias-pill').innerText = "LONG TRIGGER";
                    document.getElementById('bias-pill').style.background = "#00e676";
                    document.getElementById('bias-pill').style.color = "#000";

                    sendDirectTelegram(`🟢 *BTC/USDT 5M LONG BREAKOUT*\\n\\n💰 Entry: $${p.toFixed(1)}\\n🛡️ Stop Loss: $${sl.toFixed(1)} (-$${risk.toFixed(1)})\\n🎯 Target: $${tp.toFixed(1)} (+$${reward.toFixed(1)})\\n⚡ _Velocity Break above $${recentHigh.toFixed(1)}_`);
                }
            }
        }

        function initWebSocket() {
            const ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                const k = data.k;
                const candle = {
                    time: Math.floor(k.t / 1000), open: parseFloat(k.o), high: parseFloat(k.h), low: parseFloat(k.l), close: parseFloat(k.c), volume: parseFloat(k.v)
                };
                document.getElementById('live-price').innerText = "$" + candle.close.toFixed(1);
                series.update(candle);

                const lastIdx = candles.length - 1;
                if (candles[lastIdx].time === candle.time) {
                    candles[lastIdx] = candle;
                } else {
                    candles.push(candle);
                }

                evaluateTradeEngine(candle);
            };
        }

        function autoResize() {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        }
        window.addEventListener('resize', autoResize);
        setTimeout(autoResize, 500);
    </script>
</body>
</html>
"""

components.html(terminal_html, height=1350, scrolling=False)
