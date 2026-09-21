import streamlit as st
import streamlit.components.v1 as components

# ==============================================================================
# BTC SNIPER 5M - 100% CLIENT-SIDE AUTO RUNNER & TELEGRAM DISPATCHER
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
        .badge-scan {{ background: #00e676; color: #000; font-size: 8px; padding: 2px 5px; border-radius: 3px; font-weight: 900; animation: pulse 1.5s infinite; }}
        @keyframes pulse {{ 0% {{ opacity: 0.6; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0.6; }} }}
        
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
            height: 59vh; 
            background: #080a0f; 
        }}

        .bottom-bar {{
            width: 100vw;
            height: calc(41vh - 38px);
            max-height: 52px;
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
        .history-list {{ overflow-y: auto; max-height: 250px; font-size: 10px; }}
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
            <b id="live-price" style="color: #f0b90b; font-size: 12px;">Connecting...</b>
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
                <button onclick="toggleModal(false)" style="background:transparent; border:none; color:#888; font-size:16px; cursor:pointer;">✕</button>
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
        let lastSignalTime = 0;

        // UI Refresh
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

        function toggleModal(show) {{
            document.getElementById('modal-bg').style.display = show ? 'flex' : 'none';
        }}
        function handleBgClick(e) {{
            if (e.target.id === 'modal-bg') toggleModal(false);
        }}

        // Telegram Direct Send Function
        function sendTelegram(msg) {{
            const url = `https://api.telegram.org/bot${{BOT_TOKEN}}/sendMessage?chat_id=${{CHAT_ID}}&text=${{encodeURIComponent(msg)}}`;
            fetch(url).catch(e => console.error("TG Send Error:", e));
        }}

        // Audio Alert Sound
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

        // Chart Initialization
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

        // Core Signal Scanner (Client-Side Fast Trigger)
        function evaluateSignals(live) {{
            if (candles.length < 5) return;

            const c_prev = candles[candles.length - 2];
            const c_prev2 = candles[candles.length - 3];
            const now = Date.now();

            // Active Position Manager
            if (activeTrade) {{
                if (activeTrade.type === "LONG") {{
                    if (!activeTrade.tp1_hit && live.high >= activeTrade.tp1) {{
                        activeTrade.tp1_hit = true;
                        activeTrade.sl = activeTrade.entry + 15;
                        localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));
                        sendTelegram(`🎯 BTC LONG TP1 HIT (+90 pts) at $${{activeTrade.tp1}}\\nSL moved to BreakEven: $${{activeTrade.sl}}`);
                        updateStatsUI();
                    }}
                    if (live.high >= activeTrade.tp2) {{
                        sendTelegram(`🚀 BTC LONG TARGET 2 REACHED (+${{activeTrade.reward}} pts)!`);
                        recordHistory("LONG", activeTrade.entry, "TP 2 HIT", `+${{activeTrade.reward}}`);
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
                        activeTrade.sl = activeTrade.entry - 15;
                        localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));
                        sendTelegram(`🎯 BTC SHORT TP1 HIT (+90 pts) at $${{activeTrade.tp1}}\\nSL moved to BreakEven: $${{activeTrade.sl}}`);
                        updateStatsUI();
                    }}
                    if (live.low <= activeTrade.tp2) {{
                        sendTelegram(`🩸 BTC SHORT TARGET 2 REACHED (+${{activeTrade.reward}} pts)!`);
                        recordHistory("SHORT", activeTrade.entry, "TP 2 HIT", `+${{activeTrade.reward}}`);
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

            // Dynamic Breakout Criteria (Fast Reaction)
            if (now - lastSignalTime < 60000) return; // 1 min cooldown

            let highBench = Math.max(c_prev.high, c_prev2.high);
            let lowBench = Math.min(c_prev.low, c_prev2.low);
            let candleMove = live.close - live.open;

            // Long Trigger: Price breaks above previous high with green momentum
            if (live.close > highBench && candleMove > 15.0) {{
                lastSignalTime = now;
                let entry = live.close;
                let sl = Math.max(live.low - 15, entry - 95.0);
                let risk = +(entry - sl).toFixed(1);
                let tp1 = +(entry + 90.0).toFixed(1);
                let reward = +(risk * 2.0).toFixed(1);
                let tp2 = +(entry + reward).toFixed(1);

                activeTrade = {{ type: "LONG", entry: entry, sl: sl, tp1: tp1, tp2: tp2, risk: risk, reward: reward, tp1_hit: false }};
                localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));
                playBeep();
                updateStatsUI();

                sendTelegram(`⚡ BTC LONG SIGNAL (5M BREAKOUT)\\n\\n📍 Entry: $${{entry.toFixed(1)}}\\n🛡️ SL: $${{sl.toFixed(1)}} (-$${{risk}})\\n🎯 TP 1: $${{tp1}} (+90 pts BE)\\n🚀 TP 2: $${{tp2}} (+${{reward}} pts)\\n\\nStatus: Momentum Confirmed`);
            }}
            // Short Trigger: Price breaks below previous low with red momentum
            else if (live.close < lowBench && candleMove < -15.0) {{
                lastSignalTime = now;
                let entry = live.close;
                let sl = Math.min(live.high + 15, entry + 95.0);
                let risk = +(sl - entry).toFixed(1);
                let tp1 = +(entry - 90.0).toFixed(1);
                let reward = +(risk * 2.0).toFixed(1);
                let tp2 = +(entry - reward).toFixed(1);

                activeTrade = {{ type: "SHORT", entry: entry, sl: sl, tp1: tp1, tp2: tp2, risk: risk, reward: reward, tp1_hit: false }};
                localStorage.setItem('sniper_active_trade', JSON.stringify(activeTrade));
                playBeep();
                updateStatsUI();

                sendTelegram(`⚡ BTC SHORT SIGNAL (5M BREAKOUT)\\n\\n📍 Entry: $${{entry.toFixed(1)}}\\n🛡️ SL: $${{sl.toFixed(1)}} (-$${{risk}})\\n🎯 TP 1: $${{tp1}} (+90 pts BE)\\n🩸 TP 2: $${{tp2}} (+${{reward}} pts)\\n\\nStatus: Breakdown Confirmed`);
            }}
        }}

        function recordHistory(type, entry, res, pts) {{
            const timeStr = new Date().toLocaleTimeString('en-US', {{ hour12: false, hour: '2-digit', minute: '2-digit' }});
            tradeHistory.unshift({{ time: timeStr, type: type, entry: entry.toFixed(1), result: res, pts: pts }});
            if (tradeHistory.length > 50) tradeHistory.pop();
            localStorage.setItem('sniper_history', JSON.stringify(tradeHistory));
            activeTrade = null;
            localStorage.removeItem('sniper_active_trade');
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

        // Fetch Live Klines
        function syncCandles() {{
            fetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=80')
                .then(r => r.json())
                .then(data => {{
                    candles = data.map(d => ({{
                        time: Math.floor(d[0] / 1000) + IST_OFFSET,
                        open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                    }}));
                    series.setData(candles);
                    chart.timeScale().fitContent();
                    updateMetricsUI();
                    connectLiveStream();
                }}).catch(e => setTimeout(syncCandles, 2000));
        }}
        syncCandles();

        // WebSocket Stream (Unbreakable Live Feed)
        function connectLiveStream() {{
            const ws = new WebSocket("wss://fstream.binance.com/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {{
                const k = JSON.parse(e.data).k;
                const c = {{ 
                    time: Math.floor(k.t / 1000) + IST_OFFSET, 
                    open: parseFloat(k.o), high: parseFloat(k.h), low: parseFloat(k.l), close: parseFloat(k.c) 
                }};
                document.getElementById('live-price').innerText = "$" + c.close.toFixed(1);
                series.update(c);
                if (candles.length > 0) {{
                    const last = candles[candles.length - 1];
                    if (last.time === c.time) candles[candles.length - 1] = c;
                    else if (c.time > last.time) candles.push(c);
                }}
                evaluateSignals(c);
                updateMetricsUI();
            }};
            ws.onclose = () => setTimeout(connectLiveStream, 1500);
        }}

        // Background Fast 1.5s Poller
        setInterval(() => {{
            fetch('https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT')
                .then(r => r.json())
                .then(p => {{
                    const pr = parseFloat(p.price);
                    document.getElementById('live-price').innerText = "$" + pr.toFixed(1);
                    if (candles.length > 0) {{
                        const last = candles[candles.length - 1];
                        last.close = pr;
                        last.high = Math.max(last.high, pr);
                        last.low = Math.min(last.low, pr);
                        series.update(last);
                        evaluateSignals(last);
                    }}
                }}).catch(err => {{}});
        }}, 1500);

        updateStatsUI();
        window.onresize = () => chart.applyOptions({{ width: chartZone.clientWidth, height: chartZone.clientHeight }});
    </script>
</body>
</html>
"""

components.html(terminal_html, height=720, scrolling=False)
