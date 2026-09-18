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
    header, footer, #MainMenu { visibility: hidden !important; height: 0px !important; }
    .stApp { background-color: #080a0f; color: #d1d4dc; }
    .block-container { padding: 0rem !important; max-width: 100% !important; }
    iframe { border: none !important; width: 100vw !important; height: 100vh !important; }
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
        body {
            background: #080a0f;
            color: #d1d4dc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            overflow: hidden;
            width: 100vw;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .top-nav {
            display: flex;
            align-items: center;
            background: #0d111a;
            border-bottom: 1px solid #1a2336;
            padding: 0 16px;
            font-size: 11px;
            height: 48px;
            gap: 16px;
            overflow-x: auto;
            white-space: nowrap;
        }
        .brand { font-weight: 800; color: #fff; font-size: 13px; display: flex; align-items: center; gap: 6px; }
        .badge {
            padding: 4px 10px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 10px;
            letter-spacing: 0.4px;
        }
        .badge-idle { background: #151c2a; color: #848e9c; border: 1px solid #232d42; }
        .badge-long { background: rgba(0, 230, 118, 0.2); color: #00e676; border: 1px solid #00e676; }
        .badge-short { background: rgba(255, 59, 48, 0.2); color: #ff3b30; border: 1px solid #ff3b30; }

        .stat-card { display: flex; flex-direction: column; min-width: 85px; }
        .stat-label { font-size: 8px; color: #62697a; text-transform: uppercase; font-weight: 600; }
        .stat-val { font-size: 12px; font-weight: 700; color: #fff; margin-top: 2px; }

        .workspace {
            display: flex;
            width: 100vw;
            height: calc(100vh - 48px);
        }
        #chart-zone {
            flex: 1;
            height: 100%;
            background: #080a0f;
            position: relative;
        }
        .side-bar {
            width: 325px;
            background: #0b0f17;
            border-left: 1px solid #161d2b;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            font-size: 12px;
            overflow-y: auto;
        }
        .card {
            background: #101520;
            border: 1px solid #1a2233;
            border-radius: 6px;
            padding: 10px 12px;
        }
        .card-header {
            font-size: 10px;
            font-weight: 700;
            color: #848e9c;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
        }
        .row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #151c2a;
        }
        .row:last-child { border-bottom: none; }
        
        .score-box {
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }
        .progress-bar-bg {
            width: 100%;
            height: 6px;
            background: #151c2a;
            border-radius: 3px;
            margin: 6px 0;
            overflow: hidden;
        }
        .progress-bar-fill {
            height: 100%;
            width: 0%;
            transition: width 0.4s ease, background 0.4s ease;
        }
    </style>
</head>
<body>

    <div class="top-nav">
        <div class="brand">⚡ PRE-MOVE EXPANSION RADAR</div>
        <div id="status-badge" class="badge badge-idle">TRACKING VOLUME EXPANSION...</div>

        <div class="stat-card">
            <div class="stat-label">ENTRY</div>
            <div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div>
        </div>

        <div class="stat-card">
            <div class="stat-label">SMART SL</div>
            <div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div>
        </div>

        <div class="stat-card">
            <div class="stat-label">EXPANSION TP</div>
            <div id="disp-tp" class="stat-val" style="color:#00e676;">--</div>
        </div>

        <div class="stat-card">
            <div class="stat-label">EXPLOSION SCORE</div>
            <div id="disp-score" class="stat-val" style="color:#f0b90b;">--/100</div>
        </div>

        <div style="margin-left: auto; display: flex; align-items: center; gap: 8px;">
            <span class="stat-label">LIVE:</span>
            <b id="live-price" style="color: #f0b90b; font-size: 13px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="side-bar">
            <!-- ENGINE HUD -->
            <div class="card" style="border: 1px solid #293854;">
                <div class="card-header">
                    <span>EXPLOSION INTENSITY</span>
                    <span id="engine-status" style="color:#848e9c;">SEARCHING</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div class="score-box" id="score-text" style="color:#848e9c;">0 / 100</div>
                    <span id="bias-pill" style="font-size:10px; font-weight:700; padding:2px 6px; border-radius:3px; background:#1c2436; color:#848e9c;">WAITING</span>
                </div>
                <div class="progress-bar-bg">
                    <div id="score-bar" class="progress-bar-fill" style="background:#848e9c;"></div>
                </div>
                <div style="font-size: 9px; color: #62697a;">Trigger: Volume Breakout + Bollinger Expansion</div>
            </div>

            <!-- FLOW MATRIX -->
            <div class="card">
                <div class="card-header">
                    <span>MOMENTUM & VOLATILITY</span>
                    <span style="color:#00e676;">LIVE FEED</span>
                </div>
                <div class="row"><span style="color:#787b86;">Volume Surge Multiplier</span><b id="vol-surge" style="color:#fff;">1.0x</b></div>
                <div class="row"><span style="color:#787b86;">Bollinger Squeeze</span><b id="bb-squeeze" style="color:#fff;">SCANNING</b></div>
                <div class="row"><span style="color:#787b86;">RSI (14)</span><b id="rsi-val" style="color:#fff;">--</b></div>
                <div class="row"><span style="color:#787b86;">Market ATR</span><b id="atr-val" style="color:#f0b90b;">--</b></div>
            </div>

            <!-- TRADE STATUS -->
            <div class="card">
                <div class="card-header"><span>ACTIVE TRADE MONITOR</span></div>
                <div class="row"><span style="color:#787b86;">Projected Profit</span><b id="gain-pts" style="color:#00e676;">--</b></div>
                <div class="row"><span style="color:#787b86;">Defined Risk</span><b id="loss-pts" style="color:#ff3b30;">--</b></div>
                <div class="row"><span style="color:#787b86;">Telegram Bot</span><b id="tg-status" style="color:#00e676;">ONLINE DIRECT ✅</b></div>
                <div class="row"><span style="color:#787b86;">Execution State</span><b id="exec-state" style="color:#848e9c;">IDLE</b></div>
            </div>

            <div class="card" style="font-size: 11px; color: #848e9c; line-height: 1.5;">
                <b style="color:#fff;">Early Move Detection Specs:</b><br>
                1. <b>Volume Surge Filter:</b> Volume expand hote hi move ke start me entry.<br>
                2. <b>Dynamic Smart Stop:</b> $45-$75 tight buffer to protect capital.<br>
                3. <b>Target/SL Auto-Wipe:</b> Hit hote hi screen clean aur ready for next setup.
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
            layout: { background: { color: '#080a0f' }, textColor: '#787b86', fontFamily: 'Segoe UI, sans-serif' },
            grid: { vertLines: { color: '#111622' }, horzLines: { color: '#111622' } },
            rightPriceScale: { borderColor: '#192130', scaleMargins: { top: 0.18, bottom: 0.18 } },
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
            const url = `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`;
            fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ chat_id: CHAT_ID, text: text, parse_mode: "Markdown" })
            }).then(() => {
                document.getElementById('tg-status').innerText = "SENT TO PHONE 📲";
                setTimeout(() => { document.getElementById('tg-status').innerText = "ONLINE DIRECT ✅"; }, 5000);
            }).catch(e => console.error("TG error:", e));
        }

        setTimeout(() => {
            sendDirectTelegram("⚡ *Pre-Move Engine Online* - Monitoring volume expansion & compression breaks!");
        }, 2000);

        function clearAllTradeLines() {
            if (entryLine) { series.removePriceLine(entryLine); entryLine = null; }
            if (slLine) { series.removePriceLine(slLine); slLine = null; }
            if (tpLine) { series.removePriceLine(tpLine); tpLine = null; }
            
            document.getElementById('disp-entry').innerText = "--";
            document.getElementById('disp-sl').innerText = "--";
            document.getElementById('disp-tp').innerText = "--";
            document.getElementById('gain-pts').innerText = "--";
            document.getElementById('loss-pts').innerText = "--";
            document.getElementById('exec-state').innerText = "WAITING MOVE";
            document.getElementById('exec-state').style.color = "#848e9c";
        }

        function drawActiveTrade(trade) {
            clearAllTradeLines();
            entryLine = series.createPriceLine({ price: trade.entry, color: '#38bdf8', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, title: 'ENTRY' });
            tpLine = series.createPriceLine({ price: trade.tp, color: '#00e676', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, title: 'TARGET' });
            slLine = series.createPriceLine({ price: trade.sl, color: '#ff3b30', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, title: 'SL' });

            document.getElementById('disp-entry').innerText = "$" + trade.entry.toFixed(1);
            document.getElementById('disp-sl').innerText = "$" + trade.sl.toFixed(1);
            document.getElementById('disp-tp').innerText = "$" + trade.tp.toFixed(1);
            document.getElementById('gain-pts').innerText = "+$" + trade.reward.toFixed(1);
            document.getElementById('loss-pts').innerText = "-$" + trade.risk.toFixed(1);
            document.getElementById('exec-state').innerText = trade.type + " ACTIVE";
            document.getElementById('exec-state').style.color = trade.type === "LONG" ? "#00e676" : "#ff3b30";
        }

        // LOAD 5M CANDLES
        fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=150')
            .then(res => res.json())
            .then(data => {
                candles = data.map(d => ({
                    time: Math.floor(d[0] / 1000),
                    open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]), volume: parseFloat(d[5])
                }));
                series.setData(candles);
                initKlineWebSocket();
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
                const diff = closes[i] - closes[i - 1];
                if (diff >= 0) g += diff; else l -= diff;
            }
            if (l === 0) return 100;
            return 100 - (100 / (1 + ((g / p) / (l / p))));
        }

        function calcBollinger(closes, p = 20) {
            if (closes.length < p) return { mid: closes[closes.length-1], upper: closes[closes.length-1]+100, lower: closes[closes.length-1]-100, width: 200 };
            const slice = closes.slice(-p);
            const mean = slice.reduce((a, b) => a + b, 0) / p;
            const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / p;
            const std = Math.sqrt(variance);
            return { mid: mean, upper: mean + (std * 2), lower: mean - (std * 2), width: std * 4 };
        }

        function evaluatePreMoveBreakout(candle) {
            const closes = candles.map(c => c.close);
            const volumes = candles.map(c => c.volume);
            const ema9 = calcEMA(9, closes);
            const ema21 = calcEMA(21, closes);
            const rsi = calcRSI(closes, 14);
            const atr = calcATR(candles, 14);
            const bb = calcBollinger(closes, 20);

            document.getElementById('atr-val').innerText = "$" + atr.toFixed(1);
            document.getElementById('rsi-val').innerText = rsi.toFixed(1);

            // Volume Surge Detection (vs 12-period volume average)
            const recentVols = volumes.slice(-13, -1);
            const avgVol = recentVols.reduce((a, b) => a + b, 0) / recentVols.length;
            const volMultiplier = avgVol > 0 ? (candle.volume / avgVol) : 1.0;
            document.getElementById('vol-surge').innerText = volMultiplier.toFixed(1) + "x";
            document.getElementById('vol-surge').style.color = volMultiplier >= 1.3 ? "#00e676" : "#848e9c";

            // Squeeze & Expansion State
            const isCompressed = bb.width < (atr * 2.2);
            document.getElementById('bb-squeeze').innerText = isCompressed ? "COMPRESSED (READY)" : "EXPANDING";
            document.getElementById('bb-squeeze').style.color = isCompressed ? "#f0b90b" : "#00e676";

            // Active Trade Exit
            if (activeTrade) {
                if (activeTrade.type === "LONG") {
                    if (candle.high >= activeTrade.tp) {
                        document.getElementById('status-badge').innerText = "TARGET ACHIEVED 🎯 (+1:2)";
                        document.getElementById('status-badge').className = "badge badge-long";
                        sendDirectTelegram(`🎯 *TARGET HIT (LONG)*\n\nProfit Level: $${activeTrade.tp.toFixed(1)}\nLines cleared. Watching next move.`);
                        activeTrade = null;
                        clearAllTradeLines();
                    } else if (candle.low <= activeTrade.sl) {
                        document.getElementById('status-badge').innerText = "SL HIT 🛡️";
                        document.getElementById('status-badge').className = "badge badge-short";
                        sendDirectTelegram(`🛡️ *STOP LOSS HIT (LONG)*\n\nExit: $${candle.low.toFixed(1)}\nCapital protected.`);
                        activeTrade = null;
                        clearAllTradeLines();
                    }
                } else if (activeTrade.type === "SHORT") {
                    if (candle.low <= activeTrade.tp) {
                        document.getElementById('status-badge').innerText = "TARGET ACHIEVED 🎯 (+1:2)";
                        document.getElementById('status-badge').className = "badge badge-long";
                        sendDirectTelegram(`🎯 *TARGET HIT (SHORT)*\n\nProfit Level: $${activeTrade.tp.toFixed(1)}\nLines cleared. Watching next move.`);
                        activeTrade = null;
                        clearAllTradeLines();
                    } else if (candle.high >= activeTrade.sl) {
                        document.getElementById('status-badge').innerText = "SL HIT 🛡️";
                        document.getElementById('status-badge').className = "badge badge-short";
                        sendDirectTelegram(`🛡️ *STOP LOSS HIT (SHORT)*\n\nExit: $${candle.high.toFixed(1)}\nCapital protected.`);
                        activeTrade = null;
                        clearAllTradeLines();
                    }
                }
                return;
            }

            // Early Price Action Range (Last 4 candles)
            const c0 = candles[candles.length - 1];
            const c1 = candles[candles.length - 2];
            const c2 = candles[candles.length - 3];
            const c3 = candles[candles.length - 4];

            const recentHigh = Math.max(c1.high, c2.high, c3.high);
            const recentLow = Math.min(c1.low, c2.low, c3.low);

            // SCORING
            let score = 0;
            let bias = "NEUTRAL";

            // Price vs Breakout
            if (c0.close > recentHigh) { score += 35; bias = "LONG"; }
            else if (c0.close < recentLow) { score += 35; bias = "SHORT"; }

            // Volume Surge (Early move entry)
            if (volMultiplier >= 1.25) score += 25;
            else if (volMultiplier >= 1.05) score += 15;

            // Momentum & EMA
            if (bias === "LONG" && c0.close > ema9 && rsi > 48) score += 25;
            else if (bias === "SHORT" && c0.close < ema9 && rsi < 52) score += 25;

            if (isCompressed || bb.width < atr * 2.8) score += 15;

            // HUD
            document.getElementById('score-text').innerText = score + " / 100";
            document.getElementById('disp-score').innerText = score + "/100";
            document.getElementById('score-bar').style.width = Math.min(100, score) + "%";

            const now = Math.floor(Date.now() / 1000);
            const badge = document.getElementById('status-badge');
            const biasPill = document.getElementById('bias-pill');
            const engineStatus = document.getElementById('engine-status');

            // EARLY EXPLOSION TRIGGER (Score >= 65 and 3 min cooldown)
            if (score >= 65 && (now - lastTriggerTime > 180)) {
                const p = c0.close;

                // --- EARLY LONG EXPANSION BREAKOUT ---
                if (bias === "LONG" && p > recentHigh && rsi > 48) {
                    const risk = Math.max(45, Math.min(80, (p - Math.min(c0.low, c1.low)) + 10));
                    const reward = risk * 1.8;
                    const sl = p - risk;
                    const tp = p + reward;

                    lastTriggerTime = now;
                    activeTrade = { type: "LONG", entry: p, sl: sl, tp: tp, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'belowBar', color: '#00e676', shape: 'arrowUp', text: 'LONG EXPANSION' });
                    series.setMarkers(markers.slice(-4));
                    drawActiveTrade(activeTrade);

                    badge.innerText = "🟢 LONG EXPANSION (" + score + "/100)";
                    badge.className = "badge badge-long";
                    biasPill.innerText = "LONG BREAKOUT";
                    biasPill.style.background = "#00e676";
                    biasPill.style.color = "#000";

                    const msg = `🟢 *BTC/USDT PRE-MOVE LONG BREAKOUT*\n\n💰 *Entry:* $${p.toFixed(1)}\n🛡️ *Smart SL:* $${sl.toFixed(1)} (-$${risk.toFixed(1)})\n🎯 *Target:* $${tp.toFixed(1)} (+$${reward.toFixed(1)})\n📊 *RR:* 1:1.8\n\n⚡ _Confluence: Volume Surge (${volMultiplier.toFixed(1)}x) + Range High Break ($${recentHigh.toFixed(1)})_`;
                    sendDirectTelegram(msg);
                }
                // --- EARLY SHORT EXPANSION BREAKDOWN ---
                else if (bias === "SHORT" && p < recentLow && rsi < 52) {
                    const risk = Math.max(45, Math.min(80, (Math.max(c0.high, c1.high) - p) + 10));
                    const reward = risk * 1.8;
                    const sl = p + risk;
                    const tp = p - reward;

                    lastTriggerTime = now;
                    activeTrade = { type: "SHORT", entry: p, sl: sl, tp: tp, risk: risk, reward: reward };
                    markers.push({ time: candle.time, position: 'aboveBar', color: '#ff3b30', shape: 'arrowDown', text: 'SHORT EXPANSION' });
                    series.setMarkers(markers.slice(-4));
                    drawActiveTrade(activeTrade);

                    badge.innerText = "🔴 SHORT EXPANSION (" + score + "/100)";
                    badge.className = "badge badge-short";
                    biasPill.innerText = "SHORT BREAKDOWN";
                    biasPill.style.background = "#ff3b30";
                    biasPill.style.color = "#fff";

                    const msg = `🔴 *BTC/USDT PRE-MOVE SHORT BREAKDOWN*\n\n💰 *Entry:* $${p.toFixed(1)}\n🛡️ *Smart SL:* $${sl.toFixed(1)} (-$${risk.toFixed(1)})\n🎯 *Target:* $${tp.toFixed(1)} (+$${reward.toFixed(1)})\n📊 *RR:* 1:1.8\n\n⚡ _Confluence: Volume Surge (${volMultiplier.toFixed(1)}x) + Range Low Breakdown ($${recentLow.toFixed(1)})_`;
                    sendDirectTelegram(msg);
                }
            } else if (score >= 45) {
                badge.innerText = "🟡 " + bias + " EXPANSION FORMING (" + score + "/100)";
                badge.className = "badge badge-idle";
                biasPill.innerText = bias + " FORMING";
                biasPill.style.background = "#f0b90b";
                biasPill.style.color = "#000";
            } else {
                badge.innerText = "TRACKING VOLUME EXPANSION...";
                badge.className = "badge badge-idle";
                biasPill.innerText = "WAITING";
                biasPill.style.background = "#1c2436";
                biasPill.style.color = "#848e9c";
            }
        }

        // WEBSOCKET
        function initKlineWebSocket() {
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

                evaluatePreMoveBreakout(candle);
            };
        }

        window.addEventListener('resize', () => {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        });
    </script>
</body>
</html>
"""

components.html(terminal_html, height=760, scrolling=False)