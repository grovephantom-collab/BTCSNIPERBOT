import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests

# ==============================================================================
# VERSION 2.1 PRO (DIRECT MOBILE ALERTS FIXED)
# ==============================================================================

BOT_TOKEN = "8941403990:AAGEFNyFrEG-piIEpSri18QdcJHWLkU4J_4"
CHAT_ID = "7886716805"

def send_tg(text):
    """Reliable multi-attempt Telegram dispatcher for instant mobile alerts."""
    def _dispatch():
        for _ in range(3):
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": CHAT_ID,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                res = requests.post(url, json=payload, timeout=5)
                if res.status_code == 200:
                    break
            except Exception:
                time.sleep(1)
    threading.Thread(target=_dispatch, daemon=True).start()

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

class InstitutionalEngineV21:
    def __init__(self):
        self.active_trade = None
        self.last_candle_time = 0
        # Startup ping - Jaise hi run hoga phone me turant alert aayega
        send_tg("🟢 <b>VERSION 2.1 PRO CONNECTED</b>\n\nBot successfully running on Laptop!\nLive BTC 5M scanner active. Alerts will ring here 24/7.")

    def get_recent_liquidations(self):
        long_liq, short_liq = 0.0, 0.0
        try:
            r = requests.get("https://fapi.binance.com/fapi/v1/allForceOrders?symbol=BTCUSDT&limit=25", timeout=3)
            if r.status_code == 200:
                orders = r.json()
                if isinstance(orders, list):
                    now_ms = time.time() * 1000
                    for o in orders:
                        if now_ms - o.get('time', 0) <= 300000:
                            vol = float(o.get('executedQty', 0)) * float(o.get('avgPrice', 0))
                            if o.get('side') == 'BUY':
                                short_liq += vol
                            elif o.get('side') == 'SELL':
                                long_liq += vol
        except Exception:
            pass
        return long_liq, short_liq

    def start(self):
        while True:
            try:
                r_5m_res = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=45", timeout=5)
                r_1h_res = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=50", timeout=5)

                if r_5m_res.status_code == 200 and r_1h_res.status_code == 200:
                    r_5m = r_5m_res.json()
                    r_1h = r_1h_res.json()

                    if isinstance(r_5m, list) and isinstance(r_1h, list) and len(r_5m) >= 25 and len(r_1h) >= 20:
                        closed_kline = r_5m[-2]
                        live_kline = r_5m[-1]
                        c_time = int(closed_kline[0] / 1000)

                        candles = [{
                            'time': int(d[0]/1000), 'open': float(d[1]), 'high': float(d[2]),
                            'low': float(d[3]), 'close': float(d[4]), 'vol': float(d[5]),
                            'taker_vol': float(d[9])
                        } for d in r_5m[:-1]]

                        live = {
                            'high': float(live_kline[2]),
                            'low': float(live_kline[3]),
                            'close': float(live_kline[4])
                        }

                        closes_1h = [float(d[4]) for d in r_1h[:-1]]
                        ema50_1h = sum(closes_1h[-30:]) / len(closes_1h[-30:])
                        htf_trend_bull = closes_1h[-1] >= ema50_1h

                        long_liq, short_liq = self.get_recent_liquidations()

                        if self.active_trade:
                            self.manage_ladder_trade(live)

                        if not self.active_trade and c_time > self.last_candle_time:
                            self.last_candle_time = c_time
                            self.evaluate_v21_setup(candles, htf_trend_bull, long_liq, short_liq)
            except Exception:
                pass
            time.sleep(3)

    def manage_ladder_trade(self, live):
        t = self.active_trade
        t['duration'] += 1

        if t['type'] == 'LONG':
            # Target 1 (+90 pts): Auto Breakeven Lock
            if not t['tp1_hit'] and live['high'] >= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = t['entry'] + 10.0
                send_tg(f"🎯 <b>TARGET 1 SECURED (+90 pts)</b>\n\nBTC reached ${t['tp1']:.1f}!\nSL moved to Entry (${t['sl']:.1f}). Trade is now 100% RISK-FREE.")

            # Target 2 (Full Runner)
            if live['high'] >= t['tp2']:
                send_tg(f"🚀 <b>FINAL RUNNER TARGET HIT (+${t['reward']:.1f})</b>\n\nBTC Long target reached at ${t['tp2']:.1f}! Full profit booked.")
                self.active_trade = None
                return
            elif live['low'] <= t['sl']:
                status = "BREAKEVEN SECURED" if t['tp1_hit'] else "STOP LOSS HIT"
                send_tg(f"🛡️ <b>{status}</b>\n\nBTC Long closed safely at ${t['sl']:.1f}.")
                self.active_trade = None
                return

            if t['duration'] >= 6 and not t['tp1_hit'] and live['close'] < (t['entry'] + 20.0):
                send_tg(f"⚠️ <b>TIME MOMENTUM STALL</b>\n\nBTC Long stalled for 30m. Exited at ${live['close']:.1f} to protect capital.")
                self.active_trade = None

        elif t['type'] == 'SHORT':
            if not t['tp1_hit'] and live['low'] <= t['tp1']:
                t['tp1_hit'] = True
                t['sl'] = t['entry'] - 10.0
                send_tg(f"🎯 <b>TARGET 1 SECURED (+90 pts)</b>\n\nBTC reached ${t['tp1']:.1f}!\nSL moved to Entry (${t['sl']:.1f}). Trade is now 100% RISK-FREE.")

            if live['low'] <= t['tp2']:
                send_tg(f"🩸 <b>FINAL RUNNER TARGET HIT (+${t['reward']:.1f})</b>\n\nBTC Short target reached at ${t['tp2']:.1f}! Full profit booked.")
                self.active_trade = None
                return
            elif live['high'] >= t['sl']:
                status = "BREAKEVEN SECURED" if t['tp1_hit'] else "STOP LOSS HIT"
                send_tg(f"🛡️ <b>{status}</b>\n\nBTC Short closed safely at ${t['sl']:.1f}.")
                self.active_trade = None
                return

            if t['duration'] >= 6 and not t['tp1_hit'] and live['close'] > (t['entry'] - 20.0):
                send_tg(f"⚠️ <b>TIME MOMENTUM STALL</b>\n\nBTC Short stalled for 30m. Exited at ${live['close']:.1f} to protect capital.")
                self.active_trade = None

    def evaluate_v21_setup(self, candles, htf_bull, long_liq, short_liq):
        c0 = candles[-1]
        c1 = candles[-2]
        c2 = candles[-3]

        atr = calc_atr(candles, 14)
        live_price = c0['close']

        # 1. FVG Imbalance
        bullish_fvg = c0['low'] > c2['high'] + 6.0
        bearish_fvg = c0['high'] < c2['low'] - 6.0

        # 2. Volume & Delta Momentum
        delta = c0['taker_vol'] - (c0['vol'] - c0['taker_vol'])
        has_volume = c0['vol'] >= (sum(c['vol'] for c in candles[-6:-1]) / 5) * 0.90
        body = abs(c0['close'] - c0['open'])
        valid_body = body >= min(28.0, atr * 0.40)

        # 3. Setup Triggers
        valid_long = bullish_fvg and htf_bull and (delta > 0) and has_volume and valid_body and (c0['close'] > c0['open'])
        valid_short = bearish_fvg and (not htf_bull) and (delta < 0) and has_volume and valid_body and (c0['close'] < c0['open'])

        if valid_long:
            entry = live_price
            sl = round(c2['high'] - 12.0, 1)
            actual_risk = round(entry - sl, 1)
            if actual_risk < 70.0: actual_risk = 80.0; sl = round(entry - 80.0, 1)
            if actual_risk > 175.0: actual_risk = 160.0; sl = round(entry - 160.0, 1)

            tp1 = round(entry + 90.0, 1)
            actual_reward = round(actual_risk * 2.4, 1)
            tp2 = round(entry + actual_reward, 1)

            self.active_trade = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': actual_risk, 'reward': actual_reward, 'tp1_hit': False, 'duration': 0
            }
            send_tg(
                f"⚡ <b>VERSION 2.1 BTC LONG (FVG + ORDERFLOW)</b>\n\n"
                f"📍 <b>Entry:</b> ${entry:.1f}\n"
                f"🛡️ <b>Shielded SL:</b> ${sl:.1f} (-${actual_risk:.1f})\n"
                f"🎯 <b>TP 1 (Auto BE):</b> ${tp1:.1f} (+90 pts)\n"
                f"🎯 <b>TP 2 (Runner):</b> ${tp2:.1f} (+${actual_reward:.1f})\n"
                f"🌊 <b>Recent Short Liq:</b> ${short_liq/1000:.0f}K Flush\n"
                f"📊 <b>RR Ratio:</b> 1:2.4 | 1H Bull Regime Active"
            )

        elif valid_short:
            entry = live_price
            sl = round(c2['low'] + 12.0, 1)
            actual_risk = round(sl - entry, 1)
            if actual_risk < 70.0: actual_risk = 80.0; sl = round(entry + 80.0, 1)
            if actual_risk > 175.0: actual_risk = 160.0; sl = round(entry + 160.0, 1)

            tp1 = round(entry - 90.0, 1)
            actual_reward = round(actual_risk * 2.4, 1)
            tp2 = round(entry - actual_reward, 1)

            self.active_trade = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2,
                'risk': actual_risk, 'reward': actual_reward, 'tp1_hit': False, 'duration': 0
            }
            send_tg(
                f"⚡ <b>VERSION 2.1 BTC SHORT (FVG + ORDERFLOW)</b>\n\n"
                f"📍 <b>Entry:</b> ${entry:.1f}\n"
                f"🛡️ <b>Shielded SL:</b> ${sl:.1f} (-${actual_risk:.1f})\n"
                f"🎯 <b>TP 1 (Auto BE):</b> ${tp1:.1f} (+90 pts)\n"
                f"🎯 <b>TP 2 (Runner):</b> ${tp2:.1f} (+${actual_reward:.1f})\n"
                f"🌊 <b>Recent Long Liq:</b> ${long_liq/1000:.0f}K Flush\n"
                f"📊 <b>RR Ratio:</b> 1:2.4 | 1H Bear Regime Active"
            )

# STRICT SINGLETON RUNNER LOCK
if "engine_worker" not in st.session_state:
    st.session_state["engine_worker"] = True
    found = False
    for th in threading.enumerate():
        if th.name == "QuantDaemonV21":
            found = True
            break
    if not found:
        eng = InstitutionalEngineV21()
        t = threading.Thread(target=eng.start, name="QuantDaemonV21", daemon=True)
        t.start()

# --- STREAMLIT UI ---
st.set_page_config(page_title="BTC SNIPER 5M", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    header, footer, #MainMenu { display: none !important; }
    .block-container { padding: 0 !important; margin: 0 !important; max-width: 100vw !important; }
    iframe { width: 100vw !important; height: 100vh !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

terminal_html = """<!DOCTYPE html>
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
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            touch-action: pan-x pan-y;
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
        <div class="brand">⚡ VERSION 2.1 QUANT</div>
        <div class="stat-card"><div class="stat-label">ENTRY</div><div id="disp-entry" class="stat-val" style="color:#38bdf8;">--</div></div>
        <div class="stat-card"><div class="stat-label">SHIELD SL</div><div id="disp-sl" class="stat-val" style="color:#ff3b30;">--</div></div>
        <div class="stat-card"><div class="stat-label">RUNNER TP</div><div id="disp-tp" class="stat-val" style="color:#00e676;">--</div></div>
        <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
            <b id="live-price" style="color: #f0b90b; font-size: 13px;">...</b>
        </div>
    </div>

    <div class="workspace">
        <div id="chart-zone"></div>

        <div class="side-bar">
            <div class="card card-full">
                <div style="font-size:9px; color:#848e9c; font-weight:700; display:flex; justify-content:space-between;">
                    <span>CASCADE & FVG RADAR ACTIVE</span>
                    <span style="padding:1px 5px; border-radius:3px; background:rgba(0,230,118,0.15); color:#00e676; font-size:9px;">VERSION 2.1 ONLINE</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                    <div style="font-size: 14px; font-weight: 800; color: #fff;">LIQUIDATION FLUSH SCAN</div>
                    <span style="font-size: 9px; color: #38bdf8;">Ladder Lock Active</span>
                </div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">MULTI-STAGE TP</div>
                <div class="row"><span>TP 1</span><b style="color:#00e676;">+90 pts (Auto BE)</b></div>
                <div class="row"><span>TP 2</span><b style="color:#38bdf8;">2.4x Full Runner</b></div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">CONFIRMATION</div>
                <div class="row"><span>Regime</span><b style="color:#00e676;">1H EMA + FVG</b></div>
                <div class="row"><span>Telegram</span><b style="color:#38bdf8;">INSTANT 24/7</b></div>
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
                    chart.timeScale().fitContent();
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
                        if (candles.length > 100) candles.shift();
                    }
                }
            };
            ws.onclose = () => { setTimeout(initWS, 2500); };
        }

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
</html>"""

components.html(terminal_html, height=850, scrolling=False)
