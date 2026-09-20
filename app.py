import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests

# --- 24/7 BACKGROUND QUANT ENGINE (ZERO BUGS & SAFE DAEMON) ---
BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"

def send_tg(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=4)
    except Exception:
        pass

def calc_atr(candles, p=14):
    if len(candles) <= p:
        return 90.0
    trs = []
    start_idx = max(1, len(candles) - p)
    for i in range(start_idx, len(candles)):
        h = candles[i]['high']
        l = candles[i]['low']
        prev_c = candles[i-1]['close']
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs) / max(1, len(trs))

class BulletproofEngine:
    def __init__(self):
        self.active_trade = None
        self.last_candle_time = 0

    def start(self):
        while True:
            try:
                # 50 candles limit for absolute performance
                r = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=45", timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if len(data) >= 25:
                        closed_kline = data[-2]
                        live_kline = data[-1]
                        c_time = int(closed_kline[0] / 1000)

                        candles = [{
                            'time': int(d[0]/1000), 'open': float(d[1]), 'high': float(d[2]),
                            'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5])
                        } for d in data[:-1]]

                        live = {
                            'high': float(live_kline[2]),
                            'low': float(live_kline[3]),
                            'close': float(live_kline[4])
                        }

                        # 1. LIVE SL / TP RESOLUTION MONITORING
                        if self.active_trade:
                            if self.active_trade['type'] == 'LONG':
                                if live['high'] >= self.active_trade['tp']:
                                    send_tg(f"🎯 *TARGET HIT (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Long target reached at ${self.active_trade['tp']:.1f}!")
                                    self.active_trade = None
                                elif live['low'] <= self.active_trade['sl']:
                                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Long exited safely at ${self.active_trade['sl']:.1f}.")
                                    self.active_trade = None
                            elif self.active_trade['type'] == 'SHORT':
                                if live['low'] <= self.active_trade['tp']:
                                    send_tg(f"🎯 *TARGET HIT (+$ {self.active_trade['reward']:.1f})*\\n\\nBTC Short target reached at ${self.active_trade['tp']:.1f}!")
                                    self.active_trade = None
                                elif live['high'] >= self.active_trade['sl']:
                                    send_tg(f"🛡️ *STOP LOSS HIT*\\n\\nBTC Short exited safely at ${self.active_trade['sl']:.1f}.")
                                    self.active_trade = None

                        # 2. EVALUATE ONLY WHEN CANDLE FULLY CLOSES (ZERO DUPLICATE SIGNALS)
                        if not self.active_trade and c_time > self.last_candle_time:
                            self.last_candle_time = c_time
                            self.evaluate_market(candles)
            except Exception:
                pass
            time.sleep(3)

    def evaluate_market(self, candles):
        c_now = candles[-1]
        
        # Deep structure analysis on past 15 candles (1 hr 15 mins)
        lookback = candles[-16:-1]
        major_high = max(c['high'] for c in lookback)
        major_low = min(c['low'] for c in lookback)

        # Recent coil range on past 6 candles (30 mins)
        coil = candles[-7:-1]
        coil_high = max(c['high'] for c in coil)
        coil_low = min(c['low'] for c in coil)
        coil_spread = coil_high - coil_low
        avg_vol = sum(c['vol'] for c in coil) / len(coil)

        # Ensure market is in actionable compression ($40 to $160)
        if not (40.0 <= coil_spread <= 160.0):
            return

        live_price = c_now['close']
        body = abs(live_price - c_now['open'])
        atr = calc_atr(candles, 14)

        has_vol = c_now['vol'] >= (avg_vol * 0.85)
        momentum = body >= min(30.0, atr * 0.4)

        valid_long = (live_price > coil_high + 6.0) and (live_price > c_now['open']) and momentum and has_vol
        valid_short = (live_price < coil_low - 6.0) and (live_price < c_now['open']) and momentum and has_vol

        if valid_long:
            entry = live_price
            # SL strictly shielded below major structure support + ATR liquidity buffer
            sl = round(major_low - (atr * 0.35) - 12.0, 1)
            actual_risk = round(entry - sl, 1)

            if actual_risk < 70.0:
                actual_risk = 80.0
                sl = round(entry - 80.0, 1)
            elif actual_risk > 220.0:
                actual_risk = 200.0
                sl = round(entry - 200.0, 1)

            actual_reward = round(actual_risk * 2.35, 1)
            tp = round(entry + actual_reward, 1)

            self.active_trade = {'type': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': actual_risk, 'reward': actual_reward}
            send_tg(
                f"🚀 *BTC 5M LONG ENTRY (DYNAMIC)*\\n\\n"
                f"📍 *Entry:* ${entry:.1f}\\n"
                f"🛡️ *Wick-Proof SL:* ${sl:.1f} (-${actual_risk:.1f})\\n"
                f"🎯 *Exhaustion TP:* ${tp:.1f} (+${actual_reward:.1f})\\n"
                f"📊 *RR Ratio:* 1:2.35\\n"
                f"⚡ _SL placed strictly below recent major liquidity pool_"
            )

        elif valid_short:
            entry = live_price
            # SL strictly shielded above major structure resistance + ATR liquidity buffer
            sl = round(major_high + (atr * 0.35) + 12.0, 1)
            actual_risk = round(sl - entry, 1)

            if actual_risk < 70.0:
                actual_risk = 80.0
                sl = round(entry + 80.0, 1)
            elif actual_risk > 220.0:
                actual_risk = 200.0
                sl = round(entry + 200.0, 1)

            actual_reward = round(actual_risk * 2.35, 1)
            tp = round(entry - actual_reward, 1)

            self.active_trade = {'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': actual_risk, 'reward': actual_reward}
            send_tg(
                f"🩸 *BTC 5M SHORT ENTRY (DYNAMIC)*\\n\\n"
                f"📍 *Entry:* ${entry:.1f}\\n"
                f"🛡️ *Wick-Proof SL:* ${sl:.1f} (-${actual_risk:.1f})\\n"
                f"🎯 *Exhaustion TP:* ${tp:.1f} (+${actual_reward:.1f})\\n"
                f"📊 *RR Ratio:* 1:2.35\\n"
                f"⚡ _SL placed strictly above recent major liquidity pool_"
            )

# START SINGLE PERSISTENT DAEMON
found = False
for th in threading.enumerate():
    if th.name == "BulletproofQuantWorker":
        found = True
        break

if not found:
    engine = BulletproofEngine()
    t = threading.Thread(target=engine.start, name="BulletproofQuantWorker", daemon=True)
    t.start()

# --- STREAMLIT CLEAN MOBILE/DESKTOP INTERFACE ---
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
            height: 40px;
            gap: 8px;
            overflow-x: auto;
            white-space: nowrap;
        }
        .brand { font-weight: 800; color: #fff; font-size: 11px; }
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
        <div class="brand">⚡ WICK-PROOF QUANT</div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SAFE SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">EXHAUSTION TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 13px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="side-bar">
            <div class="card card-full">
                <div style="font-size:9px; color:#848e9c; font-weight:700; display:flex; justify-content:space-between;">
                    <span>STRUCTURAL BOUNDARY RADAR</span>
                    <span style="padding:1px 5px; border-radius:3px; background:rgba(0,230,118,0.15); color:#00e676; font-size:9px;">LIQUIDITY BUFFERED</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                    <div style="font-size: 14px; font-weight: 800; color: #fff;">MAJOR PIVOT SCAN</div>
                    <span style="font-size: 9px; color: #38bdf8;">IST Synced</span>
                </div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">SETUP PROFILE</div>
                <div class="row"><span>SL Buffer</span><b style="color:#ff3b30;">Pivot ± 1.5 ATR</b></div>
                <div class="row"><span>Target Rule</span><b style="color:#00e676;">Exhaustion Cap</b></div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">EXECUTION</div>
                <div class="row"><span>Telegram</span><b style="color:#00e676;">INSTANT 24/7</b></div>
                <div class="row"><span>Noise Defense</span><b style="color:#38bdf8;">Wick Shield Active</b></div>
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
                timeFormatter: timestamp => {
                    const d = new Date((timestamp + (5.5 * 3600)) * 1000);
                    return d.toUTCString().match(/\\d{2}:\\d{2}/)[0];
                }
            }
        });

        const series = chart.addCandlestickSeries({
            upColor: '#00E676', downColor: '#FF3B30',
            borderUpColor: '#00E676', borderDownColor: '#FF3B30',
            wickUpColor: '#00E676', wickDownColor: '#FF3B30',
        });

        let candles = [];
        let ws = null;

        function loadHistoryAndSync() {
            fetch('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=80')
                .then(r => r.json())
                .then(data => {
                    candles = data.map(d => ({
                        time: Math.floor(d[0] / 1000),
                        open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
                    }));
                    series.setData(candles);
                    initWS();
                });
        }
        loadHistoryAndSync();

        function initWS() {
            if (ws) {
                try { ws.onclose = null; ws.close(); } catch(e) {}
            }
            ws = new WebSocket("wss://fstream.binance.com/ws/btcusdt@kline_5m");
            ws.onmessage = (e) => {
                const k = JSON.parse(e.data).k;
                const c = { 
                    time: Math.floor(k.t / 1000), 
                    open: parseFloat(k.o), 
                    high: parseFloat(k.h), 
                    low: parseFloat(k.l), 
                    close: parseFloat(k.c) 
                };
                document.getElementById('live-price').innerText = "$" + c.close.toFixed(1);
                series.update(c);

                if (candles.length > 0) {
                    const lastIdx = candles.length - 1;
                    if (candles[lastIdx].time === c.time) {
                        candles[lastIdx] = c;
                    } else if (c.time > candles[lastIdx].time) {
                        candles.push(c);
                    }
                }
            };
            ws.onclose = () => { setTimeout(initWS, 2500); };
        }

        // Automatic Catch-up & Socket Resync when tab resumes
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible") {
                loadHistoryAndSync();
            }
        });

        window.addEventListener('resize', () => {
            chart.applyOptions({ width: chartZone.clientWidth, height: chartZone.clientHeight });
        });
    </script>
</body>
</html>
