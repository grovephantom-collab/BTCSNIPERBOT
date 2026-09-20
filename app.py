import streamlit as st
import streamlit.components.v1 as components
import threading
import time
import requests

# --- FULL PRO INSTITUTIONAL QUANT ENGINE ---
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

class InstitutionalEngine:
    def __init__(self):
        self.active_trade = None
        self.last_candle_time = 0
        self.prev_oi = 0.0

    def start(self):
        while True:
            try:
                # 1. Fetch 5M execution candles & 1H regime candles
                r_5m = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=45", timeout=5).json()
                r_1h = requests.get("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=50", timeout=5).json()
                
                # Fetch Open Interest
                r_oi = requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT", timeout=4).json()
                curr_oi = float(r_oi.get('openInterest', 0))

                if len(r_5m) >= 25 and len(r_1h) >= 20:
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

                    oi_change_pct = 0.0
                    if self.prev_oi > 0:
                        oi_change_pct = ((curr_oi - self.prev_oi) / self.prev_oi) * 100
                    self.prev_oi = curr_oi

                    # 2. ACTIVE POSITION MANAGEMENT (TRAILING SL + STALL INVALIDATION)
                    if self.active_trade:
                        self.manage_position(live, c_time)

                    # 3. EVALUATE ENTRY ON 5M CLOSED CANDLE
                    if not self.active_trade and c_time > self.last_candle_time:
                        self.last_candle_time = c_time
                        self.evaluate_market(candles, htf_trend_bull, oi_change_pct)
            except Exception:
                pass
            time.sleep(3)

    def manage_position(self, live, current_time):
        t = self.active_trade
        t['duration_candles'] += 1

        if t['type'] == 'LONG':
            # Target Hit
            if live['high'] >= t['tp']:
                send_tg(f"🎯 *TARGET HIT (+$ {t['reward']:.1f})*\n\nBTC Long target reached at ${t['tp']:.1f}! Full profit secured.")
                self.active_trade = None
                return
            # Stop Loss Hit
            elif live['low'] <= t['sl']:
                status = "BREAKEVEN EXIT" if t['is_breakeven'] else "STOP LOSS HIT"
                send_tg(f"🛡️ *{status}*\n\nBTC Long closed at ${t['sl']:.1f}.")
                self.active_trade = None
                return
            # Breakeven Trail (+110 points profit triggers risk-free lock)
            if not t['is_breakeven'] and (live['high'] >= t['entry'] + 110.0):
                t['sl'] = t['entry'] + 10.0
                t['is_breakeven'] = True
                send_tg(f"🔒 *RISK-FREE SL LOCK*\n\nBTC reached +$110 profit! SL automatically moved to Breakeven (${t['sl']:.1f}).")

            # Momentum Stall Invalidation (6 candles without progress)
            if t['duration_candles'] >= 6 and live['close'] < (t['entry'] + 30.0):
                send_tg(f"⚠️ *TIME STALL INVALIDATION*\n\nBTC Long momentum slowed down over 30 mins. Exiting trade at ${live['close']:.1f} to protect capital.")
                self.active_trade = None

        elif t['type'] == 'SHORT':
            # Target Hit
            if live['low'] <= t['tp']:
                send_tg(f"🎯 *TARGET HIT (+$ {t['reward']:.1f})*\n\nBTC Short target reached at ${t['tp']:.1f}! Full profit secured.")
                self.active_trade = None
                return
            # Stop Loss Hit
            elif live['high'] >= t['sl']:
                status = "BREAKEVEN EXIT" if t['is_breakeven'] else "STOP LOSS HIT"
                send_tg(f"🛡️ *{status}*\n\nBTC Short closed at ${t['sl']:.1f}.")
                self.active_trade = None
                return
            # Breakeven Trail
            if not t['is_breakeven'] and (live['low'] <= t['entry'] - 110.0):
                t['sl'] = t['entry'] - 10.0
                t['is_breakeven'] = True
                send_tg(f"🔒 *RISK-FREE SL LOCK*\n\nBTC dropped -$110 profit! SL automatically moved to Breakeven (${t['sl']:.1f}).")

            # Momentum Stall Invalidation
            if t['duration_candles'] >= 6 and live['close'] > (t['entry'] - 30.0):
                send_tg(f"⚠️ *TIME STALL INVALIDATION*\n\nBTC Short momentum slowed down over 30 mins. Exiting trade at ${live['close']:.1f} to protect capital.")
                self.active_trade = None

    def evaluate_market(self, candles, htf_bull, oi_change):
        c_now = candles[-1]
        lookback = candles[-16:-1]
        major_high = max(c['high'] for c in lookback)
        major_low = min(c['low'] for c in lookback)

        coil = candles[-7:-1]
        coil_high = max(c['high'] for c in coil)
        coil_low = min(c['low'] for c in coil)
        coil_spread = coil_high - coil_low
        
        total_vol = sum(c['vol'] for c in coil)
        avg_vol = total_vol / max(1, len(coil))
        atr = calc_atr(candles, 14)

        # Dynamic Volatility Squeeze: Range relative to current ATR regime
        is_coiled = coil_spread <= (atr * 1.85)

        live_price = c_now['close']
        body = abs(live_price - c_now['open'])
        delta = c_now['taker_vol'] - (c_now['vol'] - c_now['taker_vol'])

        has_volume = (c_now['vol'] >= avg_vol * 0.9) and (delta > 0 if live_price > c_now['open'] else delta < 0)
        strong_break = body >= min(32.0, atr * 0.45)

        # Long: Coiled + Breakout + HTF Bull + Buyer Delta
        valid_long = is_coiled and (live_price > coil_high + 6.0) and htf_bull and strong_break and has_volume
        # Short: Coiled + Breakdown + HTF Bear + Seller Delta
        valid_short = is_coiled and (live_price < coil_low - 6.0) and (not htf_bull) and strong_break and has_volume

        if valid_long:
            entry = live_price
            sl = round(major_low - (atr * 0.35) - 12.0, 1)
            actual_risk = round(entry - sl, 1)

            if actual_risk < 75.0: actual_risk = 85.0; sl = round(entry - 85.0, 1)
            elif actual_risk > 210.0: actual_risk = 195.0; sl = round(entry - 195.0, 1)

            actual_reward = round(actual_risk * 2.35, 1)
            tp = round(entry + actual_reward, 1)

            self.active_trade = {
                'type': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp,
                'risk': actual_risk, 'reward': actual_reward,
                'is_breakeven': False, 'duration_candles': 0
            }
            send_tg(
                f"🚀 *BTC 5M LONG (HTF CONFIRMED)*\n\n"
                f"📍 *Entry:* ${entry:.1f}\n"
                f"🛡️ *Wick-Proof SL:* ${sl:.1f} (-${actual_risk:.1f})\n"
                f"🎯 *Exhaustion TP:* ${tp:.1f} (+${actual_reward:.1f})\n"
                f"📊 *RR Ratio:* 1:2.35 | *OI Shift:* {oi_change:+.2f}%\n"
                f"⚡ _1H Bull Regime + Taker Volume Delta Active_"
            )

        elif valid_short:
            entry = live_price
            sl = round(major_high + (atr * 0.35) + 12.0, 1)
            actual_risk = round(sl - entry, 1)

            if actual_risk < 75.0: actual_risk = 85.0; sl = round(entry + 85.0, 1)
            elif actual_risk > 210.0: actual_risk = 195.0; sl = round(entry + 195.0, 1)

            actual_reward = round(actual_risk * 2.35, 1)
            tp = round(entry - actual_reward, 1)

            self.active_trade = {
                'type': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp,
                'risk': actual_risk, 'reward': actual_reward,
                'is_breakeven': False, 'duration_candles': 0
            }
            send_tg(
                f"🩸 *BTC 5M SHORT (HTF CONFIRMED)*\n\n"
                f"📍 *Entry:* ${entry:.1f}\n"
                f"🛡️ *Wick-Proof SL:* ${sl:.1f} (-${actual_risk:.1f})\n"
                f"🎯 *Exhaustion TP:* ${tp:.1f} (+${actual_reward:.1f})\n"
                f"📊 *RR Ratio:* 1:2.35 | *OI Shift:* {oi_change:+.2f}%\n"
                f"⚡ _1H Bear Regime + Taker Volume Delta Active_"
            )

# START INDEPENDENT THREAD
found = False
for th in threading.enumerate():
    if th.name == "InstitutionalQuantDaemon":
        found = True
        break

if not found:
    engine = InstitutionalEngine()
    t = threading.Thread(target=engine.start, name="InstitutionalQuantDaemon", daemon=True)
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
        <div class="brand">⚡ INSTITUTIONAL QUANT</div>
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
                    <span>DERIVATIVES ORDER FLOW RADAR</span>
                    <span style="padding:1px 5px; border-radius:3px; background:rgba(0,230,118,0.15); color:#00e676; font-size:9px;">LIVE QUANT DAEMON</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                    <div style="font-size: 14px; font-weight: 800; color: #fff;">1H REGIME + DELTA ACTIVE</div>
                    <span style="font-size: 9px; color: #38bdf8;">IST Synced</span>
                </div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">DEFENSE & TRAIL</div>
                <div class="row"><span>Trail Rule</span><b style="color:#00e676;">Auto BE @ +110 pts</b></div>
                <div class="row"><span>Time Invalidation</span><b style="color:#f0b90b;">30m Momentum Cap</b></div>
            </div>

            <div class="card">
                <div style="font-size:9px; color:#848e9c; font-weight:700; margin-bottom:2px;">CONFIRMATION</div>
                <div class="row"><span>HTF Trend</span><b style="color:#38bdf8;">1H EMA Filtered</b></div>
                <div class="row"><span>Telegram</span><b style="color:#00e676;">INSTANT 24/7</b></div>
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
</html>
