import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="PRO QUANT SNIPER | BTC 5M",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

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
            gap: 8px;
            overflow-x: auto;
            white-space: nowrap;
            height: 38px;
        }
        .top-nav::-webkit-scrollbar { display: none; }
        .brand { font-weight: 800; color: #fff; font-size: 11px; }
        .badge {
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 9px;
        }
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
            height: calc(100vh - 38px);
        }
        #chart-zone {
            width: 100vw;
            height: 48vh;
            background: #080a0f;
            position: relative;
        }
        .side-bar {
            width: 100vw;
            height: calc(52vh - 38px);
            background: #0b0f17;
            border-top: 1px solid #161d2b;
            padding: 8px 10px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
            overflow-y: auto;
        }

        @media (min-width: 850px) {
            .workspace { flex-direction: row; height: calc(100vh - 38px); }
            #chart-zone { flex: 1; height: 100%; width: auto; }
            .side-bar { width: 320px; height: 100%; border-top: none; border-left: 1px solid #161d2b; display: flex; flex-direction: column; }
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
            margin-bottom: 3px;
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
        <div class="brand">⚡ BTC SNIPER</div>
        <div id="status-badge" class="badge badge-idle">SCANNING...</div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <div style="margin-left: auto; display: flex; align-items: center;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="side-bar">
            <div class="card card-full" style="border: 1px solid #293854;">
                <div class="card-header">
                    <span>BREAKOUT QUALITY</span>
                    <span id="bias-pill" style="padding:1px 4px; border-radius:3px; background:#1c2436; color:#848e9c; font-size:9px;">WAITING EXPANSION</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-size: 16px; font-weight: 800; color: #fff;" id="score-text">0 / 100</div>
                    <span style="font-size: 9px; color: #62697a;">Min: $120+ Range Expansion</span>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><span>METRICS</span><span id="conn-state" style="color:#00e676;">LIVE ✅</span></div>
                <div class="row"><span>Trend</span><b id="trend-val" style="color:#fff;">--</b></div>
                <div class="row"><span>RSI</span><b id="rsi-val" style="color:#fff;">--</b></div>
                <div class="row"><span>ATR</span><b id="atr-val" style="color:#f0b90b;">--</b></div>
            </div>

            <div class="card">
                <div class="card-header"><span>ACTIVE TRADE</span><span id="tg-status" style="color:#00e676;">BOT ON</span></div>
                <div class="row"><span>Target</span><b id="gain-pts" style="color:#00e676;">--</b></div>
                <div class="row"><span>Risk</span><b id="loss-pts" style="color:#ff3b30;">--</b></div>
                <div class="row"><span>State</span><b id="exec-state" style="color:#848e9c;">IDLE</b></div>
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
        let ws = null;

        try {
            const savedTrade = localStorage.getItem('btc_sniper_active_trade');
            if (savedTrade) activeTrade = JSON.parse(savedTrade);
        } catch(e) {}

        function sendDirectTelegram(text) {
            fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ chat_id: CHAT_ID, text: text, parse_mode: "Markdown" })
            }).then(() => {
                document.getElementById('tg-status').innerText = "SENT 📲";
                setTimeout(() => { document.getElementById('tg-status').innerText = "BOT ON"; }, 4000);
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
            localStorage.removeItem('btc_sniper_active_trade');
        }

        function drawActiveTrade(trade) {
            if (entryLine) series.removePriceLine(entryLine);
            if (slLine) series.removePriceLine(slLine);
            if (tpLine) series.removePriceLine(tpLine);

            entryLine = series.createPriceLine({ price: trade.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' });
            tpLine = series.createPriceLine({ price: trade.tp, color: '#00e676', lineWidth: 2, title: 'TP' });
            slLine = series.createPriceLine({ price: trade.sl, color: '#ff3b30', lineWidth: 2, title: 'SL' });

            document.getElementById('disp-entry').innerText = "$" + trade.entry.toFixed(1);
            document.getElementById('disp-sl').innerText = "$" + trade.sl.toFixed(1);
            document.getElementById('disp-tp').innerText = "$" + trade.tp.toFixed(1);
            document.getElementById('gain-pts').innerText = "+$" + trade.reward.toFixed(1);
            document.getElementById('loss-pts').innerText = "-$" + trade.risk.toFixed(1);
            document.getElementById('exec-state').innerText = trade.type;
            document.getElementById('exec-state').style.color = trade.type === "LONG" ? "#00e676" : "#ff3b30";

            localStorage.setItem('btc_sniper_active_trade', JSON.stringify(trade));
        }

        function loadHistoricalData() {
            fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=150')
                .then(res => res.json())
                .then(data => {
                    candles = data.map(d => ({
                        time: Math.floor(d[0] / 1000),
                        open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]), volume: parseFloat(d[5])
                    }));
                    series.setData(candles);
                    if (activeTrade) drawActiveTrade(activeTrade);
                    connectWebSocket();
                });
        }
        loadHistoricalData();

        function calcEMA(p, arr) {
            const k = 2 / (p + 1);
            let v = arr[0];
            for (let i = 1; i < arr.length; i++) v = (arr[i] * k) + (v * (1 - k));
            return v;
        }

        function calcATR(c, p = 14) {
            if (c.length < p + 1) return 150;
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
            const ema20 = calcEMA(20, closes);
            const ema50 = calcEMA(50, closes);
            const rsi = calcRSI(closes, 14);
            const atr = calcATR(candles, 14);

            document.getElementById('atr-val').innerText = "$" + atr.toFixed(1);
            document.getElementById('rsi-val').innerText = rsi.toFixed(1);

            const isBullishTrend = ema20 > ema50;
            document.getElementById('trend-val').innerText = isBullishTrend ? "BULL" : "BEAR";
            document.getElementById('trend-val').style.color = isBullishTrend ? "#00e676" : "#ff3b30";

            if (activeTrade) {
                if (activeTrade.type === "LONG") {
                    if (candle.high >= activeTrade.tp) {
                        sendDirectTelegram(`🎯 *TARGET HIT (+$${activeTrade.reward.toFixed(1)})*\\nExit: $${activeTrade.tp.toFixed(1)}`);
                        activeTrade = null; clearAllTradeLines();
                    } else if (candle.low <= activeTrade.sl) {
                        sendDirectTelegram(`🛡️ *STOP LOSS HIT*\\nExit: $${candle.low.toFixed(1)}`);
                        activeTrade = null; clearAllTradeLines();
                    }
                } else if (activeTrade.type === "SHORT") {
                    if (candle.low <= activeTrade.tp) {
                        sendDirectTelegram(`🎯 *TARGET HIT (+$${activeTrade.reward.toFixed(1)})*\\nExit: $${activeTrade.tp.toFixed(1)}`);
                        activeTrade = null; clearAllTradeLines();
                    } else if (candle.high >= activeTrade.sl) {
                        sendDirectTelegram(`🛡️ *STOP LOSS HIT*\\nExit: $${candle.high.toFixed(1)}`);
                        activeTrade = null; clearAllTradeLines();
                    }
                }
                return;
            }

            const c0 = candles[candles.length - 1];
            const prevCandles = candles.slice(-7, -1);
            const rangeHigh = Math.max(...prevCandles.map(c => c.high));
            const rangeLow = Math.min(...prevCandles.map(c => c.low));
            const bodySize = Math.abs(c0.close - c0.open);

            let score = 0;
            let bias = "NEUTRAL";

            if (c0.close > rangeHigh && c0.close > ema20 && isBullishTrend) {
                bias = "LONG"; score += 45;
            } else if (c0.close < rangeLow && c0.close < ema20 && !isBullishTrend) {
                bias = "SHORT"; score += 45;
            }

            if (bodySize >= (atr * 0.70)) score += 35;
            if (bias === "LONG" && rsi >= 54) score += 20;
            if (bias === "SHORT" && rsi <= 46) score += 20;

            document.getElementById('score-text').innerText = score + " / 100";
            const now = Math.floor(Date.now() / 1000);

            if (score >= 80 && (now - lastTriggerTime > 300)) {
                const p = c0.close;
                const risk = Math.max(120, Math.min(180, atr * 1.2));
                const reward = risk * 2.2;

                if (bias === "LONG") {
                    const sl = p - risk;
                    const tp = p + reward;
                    lastTriggerTime = now;
                    activeTrade = { type: "LONG", entry: p, sl: sl, tp: tp, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'belowBar', color: '#00e676', shape: 'arrowUp', text: 'BUY' });
                    series.setMarkers(markers.slice(-4));
                    drawActiveTrade(activeTrade);

                    document.getElementById('status-badge').innerText = "🟢 LONG ACTIVE";
                    document.getElementById('status-badge').className = "badge badge-long";
                    document.getElementById('bias-pill').innerText = "LONG TRIGGER";
                    document.getElementById('bias-pill').style.background = "#00e676";
                    document.getElementById('bias-pill').style.color = "#000";

                    sendDirectTelegram(`🔥 *ACCURATE BTC 5M BUY*\\n\\n💰 *Entry:* $${p.toFixed(1)}\\n🛡️ *SL:* $${sl.toFixed(1)} (-$${risk.toFixed(1)})\\n🎯 *TP:* $${tp.toFixed(1)} (+$${reward.toFixed(1)})\\n📊 *RR:* 1:2.2`);
                } else if (bias === "SHORT") {
                    const sl = p + risk;
                    const tp = p - reward;
                    lastTriggerTime = now;
                    activeTrade = { type: "SHORT", entry: p, sl: sl, tp: tp, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'aboveBar', color: '#ff3b30', shape: 'arrowDown', text: 'SELL' });
                    series.setMarkers(markers.slice(-4));
                    drawActiveTrade(activeTrade);

                    document.getElementById('status-badge').innerText = "🔴 SHORT ACTIVE";
                    document.getElementById('status-badge').className = "badge badge-short";
                    document.getElementById('bias-pill').innerText = "SHORT TRIGGER";
                    document.getElementById('bias-pill').style.background = "#ff3b30";
                    document.getElementById('bias-pill').style.color = "#fff";

                    sendDirectTelegram(`🔥 *ACCURATE BTC 5M SELL*\\n\\n💰 *Entry:* $${p.toFixed(1)}\\n🛡️ *SL:* $${sl.toFixed(1)} (-$${risk.toFixed(1)})\\n🎯 *TP:* $${tp.toFixed(1)} (+$${reward.toFixed(1)})\\n📊 *RR:* 1:2.2`);
                }
            }
        }

        function connectWebSocket() {
            if (ws) { try { ws.close(); } catch(e) {} }
            ws = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@kline_5m");
            ws.onopen = () => { document.getElementById('conn-state').innerText = "LIVE ✅"; document.getElementById('conn-state').style.color = "#00e676"; };
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                const k = data.k;
                const candle = { time: Math.floor(k.t / 1000), open: parseFloat(k.o), high: parseFloat(k.h), low: parseFloat(k.l), close: parseFloat(k.c), volume: parseFloat(k.v) };
                document.getElementById('live-price').innerText = "$" + candle.close.toFixed(1);
                series.update(candle);
                const lastIdx = candles.length - 1;
                if (candles[lastIdx].time === candle.time) candles[lastIdx] = candle;
                else candles.push(candle);
                evaluateTradeEngine(candle);
            };
            ws.onerror = () => { document.getElementById('conn-state').innerText = "RECONNECT"; document.getElementById('conn-state').style.color = "#ff3b30"; };
            ws.onclose = () => { setTimeout(connectWebSocket, 1500); };
        }

        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible") loadHistoricalData();
        });

        function autoResize() {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        }
        window.addEventListener('resize', autoResize);
        setTimeout(autoResize, 400);
    </script>
</body>
</html>
"""

components.html(terminal_html, height=850, scrolling=False)
