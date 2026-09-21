import streamlit as st
import streamlit.components.v1 as components

# ==============================================================================
# BTC SNIPER 5M - EXTENDED 500 HISTORY CAPACITY + CLEAR ALL FUNCTIONALITY
# ==============================================================================

BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"

st.set_page_config(page_title="BTC SNIPER 5M", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    header, footer, #MainMenu { display: none !important; }
    .stDeployButton, [data-testid="stStatusWidget"], footer, .viewerBadge_container__1QSob { display: none !important; }
    .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
    iframe { width: 100vw !important; height: 100vh !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

terminal_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html, body {{ background: #080a0f; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100vw; height: 100vh; overflow: hidden; }}
        
        .top-nav {{ 
            display: flex; align-items: center; background: #0d111a; 
            border-bottom: 1px solid #1a2336; padding: 4px 8px; 
            font-size: 11px; height: 38px; gap: 8px; overflow-x: auto; white-space: nowrap; 
        }}
        .brand {{ font-weight: 800; color: #fff; font-size: 10px; display: flex; align-items: center; gap: 4px; }}
        .badge-scan {{ background: #00e676; color: #000; font-size: 8px; padding: 2px 5px; border-radius: 3px; font-weight: 900; }}
        
        .stat-card {{ display: flex; flex-direction: column; min-width: 50px; }}
        .stat-label {{ font-size: 7px; color: #62697a; text-transform: uppercase; font-weight: 800; }}
        .stat-val {{ font-size: 10px; font-weight: 800; color: #fff; }}
        
        .btn-history {{
            background: #141c2c; color: #38bdf8; border: 1px solid #1f2a40;
            border-radius: 4px; padding: 3px 8px; font-size: 9px; font-weight: 800; cursor: pointer;
        }}

        .workspace {{ 
            display: flex; 
            flex-direction: column; 
            width: 100vw; 
            height: calc(100vh - 38px); 
        }}
        
        #chart-zone {{ 
            width: 100vw; 
            height: 60vh; 
            background: #080a0f; 
        }}

        .bottom-bar {{
            width: 100vw;
            height: calc(40vh - 38px);
            max-height: 50px;
            background: #0d121c;
            border-top: 1px solid #1a2336;
            padding: 4px 8px;
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1.5fr;
            gap: 6px;
            align-items: center;
        }}
        .metric-cell {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            background: #101624;
            padding: 3px 6px;
            border-radius: 4px;
            border: 1px solid #192233;
            height: 38px;
        }}
        .cell-head {{
            font-size: 7px;
            color: #62697a;
            font-weight: 800;
            text-transform: uppercase;
            line-height: 1;
            margin-bottom: 2px;
        }}
        .cell-body {{
            font-size: 10.5px;
            font-weight: 800;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .modal-bg {{
            display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 999;
            align-items: center; justify-content: center;
        }}
        .modal-box {{
            background: #0d121c; border: 1px solid #1f2a40; border-radius: 8px;
            width: 90vw; max-width: 400px; max-height: 80vh; display: flex; flex-direction: column;
            padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }}
        .history-list {{ overflow-y: auto; max-height: 280px; font-size: 10px; }}
        .history-item {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }}
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ SNIPER 5M <span class="badge-scan">AUTO-SCAN</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">BIG TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 HISTORY (<span id="hist-count">0</span>)</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="bottom-bar">
            <div class="metric-cell">
                <span class="cell-head">TREND</span>
                <div class="cell-body" id="val-trend" style="color:#00e676;">ANALYZING...</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">RSI (14)</span>
                <div class="cell-body" id="val-rsi">--</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">ATR VOL</span>
                <div class="cell-body" id="val-atr" style="color:#f0b90b;">--</div>
            </div>
            <div class="metric-cell">
                <span class="cell-head">ACTIVE SETUP</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">SCANNING MOMENTUM</div>
            </div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:12px;">TRADE HISTORY & STATS</b>
                <div style="display:flex; gap:6px; align-items:center;">
                    <button onclick="clearHistoryData()" style="background:#ff3b30; border:none; color:#fff; font-size:9px; font-weight:800; padding:3px 8px; border-radius:3px; cursor:pointer;">CLEAR ALL</button>
                    <button onclick="toggleModal(false)" style="background:transparent; border:none; color:#888; font-size:16px; cursor:pointer; margin-left:4px;">✕</button>
                </div>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin-bottom:10px;">
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>Total Signals</span><b id="stat-total" style="color:#fff;">0</b>
                </div>
                <div style="background:#131a26; padding:5px 8px; border-radius:4px; font-size:10px; display:flex; justify-content:space-between;">
                    <span>Win Rate</span><b id="stat-rate" style="color:#00e676;">0.0%</b>
                </div>
            </div>
            <div id="history-container" class="history-list">
                <div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>
            </div>
        </div>
    </div>

    <script>
        const BOT_TOKEN = "{BOT_TOKEN}";
        const CHAT_ID = "{CHAT_ID}";
        const IST_OFFSET = 5.5 * 3600;

        let candles = [];
        let activeTrade = JSON.parse(localStorage.getItem('sniper_active_trade') || 'null');
        let tradeHistory = JSON.parse(localStorage.getItem('sniper_history') || '[]');
        let lastSignalBarTime = 0;

        let lineEntry = null;
        let lineSL = null;
        let lineTP = null;
        let markersList = [];

        function toggleModal(show) {{
            document.getElementById('modal-bg').style.display = show ? 'flex' : 'none';
        }}
        function handleBgClick(e) {{
            if (e.target.id === 'modal-bg') toggleModal(false);
        }}

        function sendTelegram(msg) {{
            const url = `https://api.telegram.org/bot${{BOT_TOKEN}}/sendMessage?chat_id=${{CHAT_ID}}&text=${{encodeURIComponent(msg)}}`;
            fetch(url).catch(e => console.error("TG Send Error:", e));
        }}

        function playBeep() {{
            try {{
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                osc.type = "sine";
                osc.frequency.setValueAtTime(880, ctx.currentTime);
                osc.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.3);
            }} catch(e) {{}}
        }}

        const chartZone = document.getElementById('chart-zone');
        const chart = LightweightCharts.createChart(chartZone, {{
            width: chartZone.clientWidth, height: chartZone.clientHeight,
            layout: {{ background: {{ color: '#080a0f' }}, textColor: '#787b86' }},
            grid: {{ vertLines: {{ color: '#111622' }}, horzLines: {{ color: '#111622' }} }},
            rightPriceScale: {{ borderColor: '#192130' }},
            timeScale: {{ borderColor: '#192130', timeVisible: true, secondsVisible: false }},
            localization: {{
                timeFormatter: t => {{
                    const d = new Date((t + IST_OFFSET) * 1000);
                    return d.toUTCString().match(/\\d{{2}}:\\d{{2}}/)[0];
                }}
            }}
        }});

        const series = chart.addCandlestickSeries({{
            upColor: '#00E676', downColor: '#FF3B30',
            borderUpColor: '#00E676', borderDownColor: '#FF3B30',
            wickUpColor: '#00E676', wickDownColor: '#FF3B30'
        }});

        function drawTradeLinesOnChart() {{
            removeTradeLines();
            if (!activeTrade) return;

            lineEntry = series.createPriceLine({{
                price: activeTrade.entry,
                color: '#38bdf8',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'ENTRY $' + activeTrade.entry.toFixed(1)
            }});

            lineSL = series.createPriceLine({{
                price: activeTrade.sl,
                color: '#ff3b30',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'SL $' + activeTrade.sl.toFixed(1)
            }});

            lineTP = series.createPriceLine({{
                price: activeTrade.tp2,
                color: '#00e676',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'TP $' + activeTrade.tp2.toFixed(1)
            }});
        }}

        function removeTradeLines() {{
            if (lineEntry) {{ try {{ series.removePriceLine(lineEntry); }} catch(e){{}} lineEntry = null; }}
            if (lineSL) {{ try {{ series.removePriceLine(lineSL); }} catch(e){{}} lineSL = null; }}
            if (lineTP) {{ try {{ series.removePriceLine(lineTP); }} catch(e){{}} lineTP = null; }}
        }}

        function updateStatsUI() {{
            document.getElementById('hist-count').innerText = tradeHistory.length;
            document.getElementById('stat-total').innerText = tradeHistory.length;
            let wins = tradeHistory.filter(x => x.result.includes('TP')).length;
            let rate = tradeHistory.length > 0 ? ((wins / tradeHistory.length) * 100).toFixed(1) : 0;
            document.getElementById('stat-rate').innerText = rate + "%";

            const histCont = document.getElementById('history-container');
            if (tradeHistory.length > 0) {{
                histCont.innerHTML = "";
                tradeHistory.forEach(item => {{
                    let resCol = item.result.includes("TP") ? "#00e676" : "#ff3b30";
                    let typeCol = item.type === "LONG" ? "#00e676" : "#ff3b30";
                    histCont.innerHTML += `
                        <div class="history-item">
                            <span>${{item.time}} <b style="color:${{typeCol}};">${{item.type}}</b> @ $${{item.entry}}</span>
                            <span><b style="color:${{resCol}};">${{item.result}}</b> (${{item.pts}} pts)</span>
                        </div>
                    `;
                }});
            }} else {{
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>';
            }}

            if (activeTrade) {{
                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
                document.getElementById('disp-tp').innerText = "$" + activeTrade.tp2.toFixed(1);
                document.getElementById('val-setup').innerText = activeTrade.type + " RUNNING 🔥";
                document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
            }} else {{
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = "SCANNING MOMENTUM";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }}
        }}

        // CLEAR ALL HISTORY & ACTIVE STATE
        function clearHistoryData() {{
            tradeHistory = [];
            localStorage.removeItem('sniper_history');
            activeTrade = null;
            localStorage.removeItem('sniper_active_trade');
            removeTradeLines();
            markersList = [];
            series.setMarkers([]);
            updateStatsUI();
        }}

        function evaluateSignals(live) {{
            if (candles.length < 10) return;

            if (activeTrade) {{
                if (activeTrade.type === "LONG") {{
                    if (!activeTrade.tp1_hit && live.high >= activeTrade.tp1) {{
                        activeTrade.tp1_hit = true;
                        activeTrade.sl = +(activeTrade.entry + 15).toFixed(1);
                        localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));
                        drawTradeLinesOnChart();
                        sendTelegram(`🎯 BTC LONG TP1 HIT (+90 pts) at $${{activeTrade.tp1}}\\nSL locked at Breakeven: $${{activeTrade.sl}}`);
                        updateStatsUI();
                    }}
                    if (live.high >= activeTrade.tp2) {{
                        sendTelegram(`🚀 BTC LONG RUNNER REACHED (+${{activeTrade.reward}} pts)!`);
                        recordHistory("LONG", activeTrade.entry, "TP RUNNER", `+${{activeTrade.reward}}`);
                        return;
                    }} else if (live.low <= activeTrade.sl) {{
                        let res = activeTrade.tp1_hit ? "BE LOCKED" : "SL HIT";
                        let pts = activeTrade.tp1_hit ? "+15" : `-${{activeTrade.risk}}`;
                        sendTelegram(`🛡️ BTC LONG ${{res}} at $${{activeTrade.sl}}`);
                        recordHistory("LONG", activeTrade.entry, res, pts);
                        return;
                    }}
                }} else if (activeTrade.type === "SHORT") {{
                    if (!activeTrade.tp1_hit && live.low <= activeTrade.tp1) {{
                        activeTrade.tp1_hit = true;
                        activeTrade.sl = +(activeTrade.entry - 15).toFixed(1);
                        localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));
                        drawTradeLinesOnChart();
                        sendTelegram(`🎯 BTC SHORT TP1 HIT (+90 pts) at $${{activeTrade.tp1}}\\nSL locked at Breakeven: $${{activeTrade.sl}}`);
                        updateStatsUI();
                    }}
                    if (live.low <= activeTrade.tp2) {{
                        sendTelegram(`🩸 BTC SHORT RUNNER REACHED (+${{activeTrade.reward}} pts)!`);
                        recordHistory("SHORT", activeTrade.entry, "TP RUNNER", `+${{activeTrade.reward}}`);
                        return;
                    }} else if (live.high >= activeTrade.sl) {{
                        let res = activeTrade.tp1_hit ? "BE LOCKED" : "SL HIT";
                        let pts = activeTrade.tp1_hit ? "+15" : `-${{activeTrade.risk}}`;
                        sendTelegram(`🛡️ BTC SHORT ${{res}} at $${{activeTrade.sl}}`);
                        recordHistory("SHORT", activeTrade.entry, res, pts);
                        return;
                    }}
                }}
                return;
            }}

            const currentBarTime = live.time;
            if (currentBarTime <= lastSignalBarTime) return;

            const prevCandles = candles.slice(-6, -1);
            const highRange = Math.max(...prevCandles.map(c => c.high));
            const lowRange = Math.min(...prevCandles.map(c => c.low));
            const candleBody = Math.abs(live.close - live.open);

            const validLong = (live.close > highRange) && (live.close > live.open) && (candleBody >= 22.0);
            const validShort = (live.close < lowRange) && (live.close < live.open) && (candleBody >= 22.0);

            if (validLong) {{
                lastSignalBarTime = currentBarTime;
                let entry = live.close;
                let sl = +(Math.min(live.low, lowRange + 10) - 20.0).toFixed(1);
                let risk = +(entry - sl).toFixed(1);
                if (risk < 65) risk = 75; sl = +(entry - risk).toFixed(1);
                if (risk > 140) risk = 125; sl = +(entry - risk).toFixed(1);

                let tp1 = +(entry + 90.0).toFixed(1);
                let reward = +(risk * 2.2).toFixed(1);
                let tp2 = +(entry + reward).toFixed(1);

                activeTrade = {{ type: "LONG", entry: entry, sl: sl, tp1: tp1, tp2: tp2, risk: risk, reward: reward, tp1_hit: false }};
                localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));
                
                drawTradeLinesOnChart();
                markersList.push({{
                    time: live.time,
                    position: 'belowBar',
                    color: '#00e676',
                    shape: 'arrowUp',
                    text: 'BUY LONG @ $' + entry.toFixed(1)
                }});
                series.setMarkers(markersList);

                playBeep();
                updateStatsUI();
                sendTelegram(`⚡ BTC CONFIRMED LONG (5M BREAKOUT)\\n\\n📍 Entry: $${{entry.toFixed(1)}}\\n🛡️ SL: $${{sl.toFixed(1)}} (-$${{risk}})\\n🎯 TP 1: $${{tp1}} (+90 pts BE)\\n🚀 TP 2: $${{tp2}} (+${{reward}} pts)`);
            }}
            else if (validShort) {{
                lastSignalBarTime = currentBarTime;
                let entry = live.close;
                let sl = +(Math.max(live.high, highRange - 10) + 20.0).toFixed(1);
                let risk = +(sl - entry).toFixed(1);
                if (risk < 65) risk = 75; sl = +(entry + risk).toFixed(1);
                if (risk > 140) risk = 125; sl = +(entry - risk).toFixed(1);

                let tp1 = +(entry - 90.0).toFixed(1);
                let reward = +(risk * 2.2).toFixed(1);
                let tp2 = +(entry - reward).toFixed(1);

                activeTrade = {{ type: "SHORT", entry: entry, sl: sl, tp1: tp1, tp2: tp2, risk: risk, reward: reward, tp1_hit: false }};
                localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));

                drawTradeLinesOnChart();
                markersList.push({{
                    time: live.time,
                    position: 'aboveBar',
                    color: '#ff3b30',
                    shape: 'arrowDown',
                    text: 'SELL SHORT @ $' + entry.toFixed(1)
                }});
                series.setMarkers(markersList);

                playBeep();
                updateStatsUI();
                sendTelegram(`⚡ BTC CONFIRMED SHORT (5M BREAKOUT)\\n\\n📍 Entry: $${{entry.toFixed(1)}}\\n🛡️ SL: $${{sl.toFixed(1)}} (-$${{risk}})\\n🎯 TP 1: $${{tp1}} (+90 pts BE)\\n🩸 TP 2: $${{tp2}} (+${{reward}} pts)`);
            }}
        }}

        // EXTENDED LIMIT TO 500 SIGNALS
        function recordHistory(type, entry, res, pts) {{
            const timeStr = new Date().toLocaleTimeString('en-US', {{ hour12: false, hour: '2-digit', minute: '2-digit' }});
            tradeHistory.unshift({{ time: timeStr, type: type, entry: entry.toFixed(1), result: res, pts: pts }});
            if (tradeHistory.length > 500) tradeHistory.pop();
            localStorage.setItem('sniper_history', JSON.stringify(tradeHistory));
            activeTrade = null;
            localStorage.removeItem('sniper_active_trade');
            removeTradeLines();
            updateStatsUI();
        }}

        function updateMetricsUI() {{
            if (candles.length < 15) return;
            const closes = candles.map(c => c.close);
            let gains = 0, losses = 0;
            for (let i = closes.length - 14; i < closes.length; i++) {{
                let diff = closes[i] - closes[i - 1];
                if (diff >= 0) gains += diff; else losses -= diff;
            }}
            let rsi = (100 - (100 / (1 + (losses === 0 ? 100 : gains / losses)))).toFixed(1);
            document.getElementById('val-rsi').innerText = rsi;

            let trSum = 0;
            for (let i = candles.length - 14; i < candles.length; i++) {{
                let c = candles[i], p = candles[i - 1];
                trSum += Math.max(c.high - c.low, Math.abs(c.high - p.close), Math.abs(c.low - p.close));
            }}
            let atr = (trSum / 14).toFixed(1);
            document.getElementById('val-atr').innerText = "$" + atr;

            let isBull = candles[candles.length - 1].close >= candles[candles.length - 8].close;
            document.getElementById('val-trend').innerText = isBull ? "BULLISH ▲" : "BEARISH ▼";
            document.getElementById('val-trend').style.color = isBull ? "#00e676" : "#ff3b30";
        }}

        function get5MBoundary(unixSec) {{
            return unixSec - (unixSec % 300);
        }}

        function syncCandles() {{
            fetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=80')
                .then(r => r.json())
                .then(data => {{
                    candles = data.map(d => ({{
                        time: get5MBoundary(Math.floor(d[0] / 1000)),
                        open: parseFloat(d[1]), 
                        high: parseFloat(d[2]), 
                        low: parseFloat(d[3]), 
                        close: parseFloat(d[4])
                    }}));
                    series.setData(candles);
                    chart.timeScale().fitContent();
                    drawTradeLinesOnChart();
                    updateMetricsUI();
                    connectLiveStream();
                }}).catch(e => setTimeout(syncCandles, 2000));
        }}
        syncCandles();

        function updateLiveCandle(price, rawTimeSec) {{
            if (candles.length === 0) return;
            
            const barTime = get5MBoundary(rawTimeSec);
            let last = candles[candles.length - 1];

            if (barTime === last.time) {{
                last.close = price;
                if (price > last.high) last.high = price;
                if (price < last.low) last.low = price;
                series.update(last);
            }} else if (barTime > last.time) {{
                const newBar = {{
                    time: barTime,
                    open: price,
                    high: price,
                    low: price,
                    close: price
                }};
                candles.push(newBar);
                series.update(newBar);
            }}
            document.getElementById('live-price').innerText = "$" + price.toFixed(1);
            evaluateSignals(candles[candles.length - 1]);
            updateMetricsUI();
        }}

        function connectLiveStream() {{
            const ws = new WebSocket("wss://fstream.binance.com/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {{
                const k = JSON.parse(e.data).k;
                const candleTimeSec = Math.floor(k.t / 1000);
                const closePrice = parseFloat(k.c);
                updateLiveCandle(closePrice, candleTimeSec);
            }};
            ws.onclose = () => setTimeout(connectLiveStream, 1500);
        }}

        setInterval(() => {{
            fetch('https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT')
                .then(r => r.json())
                .then(p => {{
                    const pr = parseFloat(p.price);
                    const nowSec = Math.floor(Date.now() / 1000);
                    updateLiveCandle(pr, nowSec);
                }}).catch(err => {{}});
        }}, 1500);

        updateStatsUI();
        window.onresize = () => chart.applyOptions({{ width: chartZone.clientWidth, height: chartZone.clientHeight }});
    </script>
</body>
</html>
"""

components.html(terminal_html, height=720, scrolling=False)
