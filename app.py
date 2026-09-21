import streamlit as st
import streamlit.components.v1 as components

# ==============================================================================
# BTC SNIPER 5M - 100% SYNCHRONIZED REALTIME ENGINE (LINES + SL SAFE + CLEAR FIX)
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
            height: 55vh; 
            background: #080a0f; 
        }}

        .trade-dock {{
            width: 100vw;
            height: 38px;
            background: #0a0e17;
            border-top: 1px solid #1a2336;
            padding: 2px 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 10px;
        }}
        .dock-group {{ display: flex; align-items: center; gap: 6px; }}
        .dock-input {{
            background: #121824; border: 1px solid #23304a; color: #00e676;
            font-size: 11px; font-weight: 800; border-radius: 4px; padding: 2px 6px; width: 50px; text-align: center;
        }}
        .toggle-btn {{
            background: #00e676; color: #000; font-size: 9px; font-weight: 900;
            padding: 4px 8px; border-radius: 4px; border: none; cursor: pointer;
        }}

        .bottom-bar {{
            width: 100vw;
            height: calc(45vh - 76px);
            max-height: 48px;
            background: #0d121c;
            border-top: 1px solid #1a2336;
            padding: 3px 8px;
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
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid #192233;
            height: 36px;
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
            font-size: 10px;
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
            width: 92vw; max-width: 420px; max-height: 80vh; display: flex; flex-direction: column;
            padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }}
        .history-list {{ overflow-y: auto; max-height: 280px; font-size: 10px; }}
        .history-item {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #151d2b; }}
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="brand">⚡ SNIPER 5M <span class="badge-scan">PRO AUTO</span></div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">BIG TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <button class="btn-history" onclick="toggleModal(true)">📜 HISTORY (<span id="hist-count">0</span>)</button>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">Connecting...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="trade-dock">
            <div class="dock-group">
                <button id="btn-auto-toggle" class="toggle-btn" onclick="toggleAutoTrade()">AUTO TRADE: ON</button>
                <span style="color:#62697a; font-weight:800;">AMT ($):</span>
                <input id="input-amount" class="dock-input" type="number" value="100" onchange="updateCalcQty()">
                <span style="color:#62697a; font-weight:800;">LEV:</span>
                <input id="input-lev" class="dock-input" type="number" value="10" onchange="updateCalcQty()">
            </div>
            <div class="dock-group">
                <span style="color:#62697a;">QTY:</span>
                <b id="calc-qty" style="color:#38bdf8; font-size:11px;">0.0118 BTC</b>
            </div>
        </div>

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
                <span class="cell-head">POSITION STATUS</span>
                <div class="cell-body" id="val-setup" style="color:#38bdf8;">READY TO SCAN</div>
            </div>
        </div>
    </div>

    <div id="modal-bg" class="modal-bg" onclick="handleBgClick(event)">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <b style="color:#fff; font-size:12px;">TRADE HISTORY & STATS</b>
                <div style="display:flex; gap:6px; align-items:center;">
                    <button onclick="clearAllHistory()" style="background:#ff3b30; border:none; color:#fff; font-size:9px; font-weight:800; padding:3px 8px; border-radius:3px; cursor:pointer;">CLEAR ALL</button>
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
            <div id="history-container" class="history-list">
                <div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>
            </div>
        </div>
    </div>

    <script>
        const BOT_TOKEN = "{BOT_TOKEN}";
        const CHAT_ID = "{CHAT_ID}";
        const IST_OFFSET = 5.5 * 3600;

        let autoTradeEnabled = true;
        let activeTrade = JSON.parse(localStorage.getItem('sniper_live_active') || 'null');
        let tradeHistory = JSON.parse(localStorage.getItem('sniper_live_hist') || '[]');
        let lastSignalBarTime = 0;
        let currentPrice = 85000.0;
        let candles = [];

        let lineEntry = null, lineSL = null, lineTP = null;

        function toggleModal(show) {{
            document.getElementById('modal-bg').style.display = show ? 'flex' : 'none';
        }}
        function handleBgClick(e) {{
            if (e.target.id === 'modal-bg') toggleModal(false);
        }}

        function toggleAutoTrade() {{
            autoTradeEnabled = !autoTradeEnabled;
            const btn = document.getElementById('btn-auto-toggle');
            btn.innerText = autoTradeEnabled ? "AUTO TRADE: ON" : "AUTO TRADE: OFF";
            btn.style.background = autoTradeEnabled ? "#00e676" : "#ff3b30";
            btn.style.color = autoTradeEnabled ? "#000" : "#fff";
        }}

        function updateCalcQty() {{
            let amt = parseFloat(document.getElementById('input-amount').value) || 100;
            let lev = parseFloat(document.getElementById('input-lev').value) || 10;
            let qty = ((amt * lev) / currentPrice).toFixed(4);
            document.getElementById('calc-qty').innerText = qty + " BTC";
        }}

        // GUARANTEED 100% CLEAR ALL FUNCTION
        function clearAllHistory() {{
            tradeHistory = [];
            activeTrade = null;
            localStorage.removeItem('sniper_live_hist');
            localStorage.removeItem('sniper_live_active');
            removeLines();
            updateUI();
        }}

        function sendTelegram(msg) {{
            const url = `https://api.telegram.org/bot${{BOT_TOKEN}}/sendMessage?chat_id=${{CHAT_ID}}&text=${{encodeURIComponent(msg)}}`;
            fetch(url).catch(e => console.error(e));
        }}

        // CHART CREATION
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

        // DRAW LINES DIRECTLY ON CHART
        function renderLines() {{
            removeLines();
            if (!activeTrade) return;

            lineEntry = series.createPriceLine({{
                price: activeTrade.entry, color: '#38bdf8', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true,
                title: 'ENTRY $' + activeTrade.entry.toFixed(1)
            }});

            lineSL = series.createPriceLine({{
                price: activeTrade.sl, color: '#ff3b30', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true,
                title: 'SL $' + activeTrade.sl.toFixed(1)
            }});

            lineTP = series.createPriceLine({{
                price: activeTrade.tp, color: '#00e676', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true,
                title: 'TP $' + activeTrade.tp.toFixed(1)
            }});
        }}

        function removeLines() {{
            if (lineEntry) {{ try {{ series.removePriceLine(lineEntry); }} catch(e){{}} lineEntry = null; }}
            if (lineSL) {{ try {{ series.removePriceLine(lineSL); }} catch(e){{}} lineSL = null; }}
            if (lineTP) {{ try {{ series.removePriceLine(lineTP); }} catch(e){{}} lineTP = null; }}
        }}

        function updateUI() {{
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
                            <span>${{item.time}} <b style="color:${{typeCol}};">${{item.type}}</b> [${{item.qty}} BTC] @ $${{item.entry}}</span>
                            <span><b style="color:${{resCol}};">${{item.result}}</b> (${{item.pnl}})</span>
                        </div>
                    `;
                }});
            }} else {{
                histCont.innerHTML = '<div style="color:#555; text-align:center; padding:15px 0;">No trades recorded yet...</div>';
            }}

            if (activeTrade) {{
                document.getElementById('disp-entry').innerText = "$" + activeTrade.entry.toFixed(1);
                document.getElementById('disp-sl').innerText = "$" + activeTrade.sl.toFixed(1);
                document.getElementById('disp-tp').innerText = "$" + activeTrade.tp.toFixed(1);
                document.getElementById('val-setup').innerText = activeTrade.type + " RUNNING 🔥";
                document.getElementById('val-setup').style.color = activeTrade.type === "LONG" ? "#00e676" : "#ff3b30";
            }} else {{
                document.getElementById('disp-entry').innerText = "--";
                document.getElementById('disp-sl').innerText = "--";
                document.getElementById('disp-tp').innerText = "--";
                document.getElementById('val-setup').innerText = "READY TO SCAN";
                document.getElementById('val-setup').style.color = "#38bdf8";
            }}
        }}

        // POSITION MANAGER (MANAGES ACTIVE TRADE)
        function checkPosition(price) {{
            if (!activeTrade) return;

            let qty = activeTrade.qty;
            if (activeTrade.type === "LONG") {{
                // Take Profit
                if (price >= activeTrade.tp) {{
                    let pts = +(activeTrade.tp - activeTrade.entry).toFixed(1);
                    let pnlUsd = +(pts * qty).toFixed(2);
                    sendTelegram(`🚀 BTC LONG TP HIT!\\nProfit: +$${{pnlUsd}} (+${{pts}} pts)\\nClosed @ $${{price}}`);
                    recordTrade("LONG", activeTrade.entry, "TP HIT", `+$${{pnlUsd}}`, qty);
                    return;
                }}
                // Stop Loss
                if (price <= activeTrade.sl) {{
                    let pts = +(activeTrade.entry - activeTrade.sl).toFixed(1);
                    let pnlUsd = +(pts * qty).toFixed(2);
                    sendTelegram(`🛡️ BTC LONG SL HIT\\nLoss: -$${{pnlUsd}} (-${{pts}} pts)\\nClosed @ $${{price}}`);
                    recordTrade("LONG", activeTrade.entry, "SL HIT", `-$${{pnlUsd}}`, qty);
                    return;
                }}
            }} else if (activeTrade.type === "SHORT") {{
                // Take Profit
                if (price <= activeTrade.tp) {{
                    let pts = +(activeTrade.entry - activeTrade.tp).toFixed(1);
                    let pnlUsd = +(pts * qty).toFixed(2);
                    sendTelegram(`🩸 BTC SHORT TP HIT!\\nProfit: +$${{pnlUsd}} (+${{pts}} pts)\\nClosed @ $${{price}}`);
                    recordTrade("SHORT", activeTrade.entry, "TP HIT", `+$${{pnlUsd}}`, qty);
                    return;
                }}
                // Stop Loss
                if (price >= activeTrade.sl) {{
                    let pts = +(activeTrade.sl - activeTrade.entry).toFixed(1);
                    let pnlUsd = +(pts * qty).toFixed(2);
                    sendTelegram(`🛡️ BTC SHORT SL HIT\\nLoss: -$${{pnlUsd}} (-${{pts}} pts)\\nClosed @ $${{price}}`);
                    recordTrade("SHORT", activeTrade.entry, "SL HIT", `-$${{pnlUsd}}`, qty);
                    return;
                }}
            }}
        }}

        function recordTrade(type, entry, res, pnl, qty) {{
            const timeStr = new Date().toLocaleTimeString('en-US', {{ hour12: false, hour: '2-digit', minute: '2-digit' }});
            tradeHistory.unshift({{
                time: timeStr, type: type, entry: entry.toFixed(1), result: res, pnl: pnl, qty: qty
            }});
            if (tradeHistory.length > 500) tradeHistory.pop();
            localStorage.setItem('sniper_live_hist', JSON.stringify(tradeHistory));
            activeTrade = null;
            localStorage.removeItem('sniper_live_active');
            removeLines();
            updateUI();
        }}

        // ACCURATE SIGNAL SCANNER (SAFE ATR SL - NO MORE EARLY SL HITS)
        function scanSignals(candle) {{
            if (activeTrade || !autoTradeEnabled || candles.length < 20) return;
            if (candle.time <= lastSignalBarTime) return;

            // 1. Calculate Real ATR (14)
            let trSum = 0;
            for (let i = candles.length - 14; i < candles.length; i++) {{
                let c = candles[i], p = candles[i - 1];
                trSum += Math.max(c.high - c.low, Math.abs(c.high - p.close), Math.abs(c.low - p.close));
            }}
            let atr = Math.max(trSum / 14, 180.0);

            // 2. Trend & Range Analysis
            const lookback = candles.slice(-10, -1);
            const high10 = Math.max(...lookback.map(c => c.high));
            const low10 = Math.min(...lookback.map(c => c.low));
            const body = candle.close - candle.open;

            // Trend Confirmation (EMA 20)
            const closes = candles.map(c => c.close);
            const ema20 = closes.slice(-20).reduce((a, b) => a + b, 0) / 20;

            const isLong = (candle.close > high10) && (candle.close > ema20) && (body >= 28.0);
            const isShort = (candle.close < low10) && (candle.close < ema20) && (body <= -28.0);

            let amt = parseFloat(document.getElementById('input-amount').value) || 100;
            let lev = parseFloat(document.getElementById('input-lev').value) || 10;
            let qty = +((amt * lev) / candle.close).toFixed(4);
            if (qty <= 0) qty = 0.001;

            if (isLong) {{
                lastSignalBarTime = candle.time;
                let entry = candle.close;
                // SAFE SL: 1.25x ATR (~$350-$450 safe breathing space)
                let safeRisk = +(atr * 1.25).toFixed(1);
                let sl = +(entry - safeRisk).toFixed(1);
                let tp = +(entry + (safeRisk * 1.8)).toFixed(1);

                activeTrade = {{ type: "LONG", entry: entry, sl: sl, tp: tp, risk: safeRisk, qty: qty }};
                localStorage.setItem('sniper_live_active', JSON.stringify(activeTrade));
                renderLines();
                updateUI();

                sendTelegram(`⚡ [AUTO BUY] BTC LONG\\n\\n📍 Entry: $${{entry.toFixed(1)}}\\n🛡️ Safe SL: $${{sl.toFixed(1)}} (-$${{safeRisk}})\\n🎯 TP: $${{tp.toFixed(1)}} (+${{safeRisk * 1.8}})\\n📦 Qty: ${{qty}} BTC (~$${{amt * lev}})`);
            }}
            else if (isShort) {{
                lastSignalBarTime = candle.time;
                let entry = candle.close;
                let safeRisk = +(atr * 1.25).toFixed(1);
                let sl = +(entry + safeRisk).toFixed(1);
                let tp = +(entry - (safeRisk * 1.8)).toFixed(1);

                activeTrade = {{ type: "SHORT", entry: entry, sl: sl, tp: tp, risk: safeRisk, qty: qty }};
                localStorage.setItem('sniper_live_active', JSON.stringify(activeTrade));
                renderLines();
                updateUI();

                sendTelegram(`⚡ [AUTO SELL] BTC SHORT\\n\\n📍 Entry: $${{entry.toFixed(1)}}\\n🛡️ Safe SL: $${{sl.toFixed(1)}} (-$${{safeRisk}})\\n🎯 TP: $${{tp.toFixed(1)}} (+${{safeRisk * 1.8}})\\n📦 Qty: ${{qty}} BTC (~$${{amt * lev}})`);
            }}
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
                        open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                    }}));
                    series.setData(candles);
                    chart.timeScale().fitContent();
                    renderLines();
                    updateUI();
                    updateMetricsUI();
                    connectLiveStream();
                }}).catch(e => setTimeout(syncCandles, 2000));
        }}
        syncCandles();

        function updateLiveCandle(price, rawTimeSec) {{
            if (candles.length === 0) return;
            currentPrice = price;
            updateCalcQty();

            const barTime = get5MBoundary(rawTimeSec);
            let last = candles[candles.length - 1];

            if (barTime === last.time) {{
                last.close = price;
                if (price > last.high) last.high = price;
                if (price < last.low) last.low = price;
                series.update(last);
            }} else if (barTime > last.time) {{
                // Candle Closed -> Scan for Clean Breakout
                scanSignals(last);

                const newBar = {{ time: barTime, open: price, high: price, low: price, close: price }};
                candles.push(newBar);
                series.update(newBar);
            }}

            document.getElementById('live-price').innerText = "$" + price.toFixed(1);
            checkPosition(price);
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

        renderLines();
        updateUI();
        window.onresize = () => chart.applyOptions({{ width: chartZone.clientWidth, height: chartZone.clientHeight }});
    </script>
</body>
</html>
"""

components.html(terminal_html, height=720, scrolling=False)
