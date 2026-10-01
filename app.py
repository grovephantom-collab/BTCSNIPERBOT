import os
import time
import hmac
import hashlib
import json
import threading
import requests
import pandas as pd
import pandas_ta as ta
from flask import Flask, jsonify

app = Flask(__name__)

# --- CONFIGURATIONS ---
BASE_URL = os.environ.get("DELTA_BASE_URL", "https://cdn.india.delta.exchange")
API_KEY = os.environ.get("DELTA_API_KEY", "YOUR_API_KEY")
API_SECRET = os.environ.get("DELTA_API_SECRET", "YOUR_API_SECRET")
SYMBOL = os.environ.get("SYMBOL", "BTCUSD")
SIZE = int(os.environ.get("CONTRACT_SIZE", 1))

# Live state tracker
bot_status = {
    "status": "Initializing Engine...",
    "last_price": 0,
    "last_trade": "None",
    "active_position": False,
    "last_error": "None",
    "total_trades": 0
}

last_trade_time = None  # Ek candle me double trade na ho uske liye

def generate_signature(secret, method, path, query="", payload=""):
    timestamp = str(int(time.time()))
    message = method + timestamp + path + query + payload
    signature = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature, timestamp

def get_headers(method, path, query="", payload=""):
    sig, ts = generate_signature(API_SECRET, method, path, query, payload)
    return {"api-key": API_KEY, "timestamp": ts, "signature": sig, "Content-Type": "application/json"}

def get_product_id():
    try:
        res = requests.get(f"{BASE_URL}/v2/products", timeout=10).json()
        if res.get("success"):
            for p in res.get("result", []):
                if p["symbol"] == SYMBOL:
                    return p["id"]
    except Exception as e:
        bot_status["last_error"] = f"Product ID fetch error: {e}"
    return None

def has_open_position(product_id):
    try:
        headers = get_headers("GET", "/v2/positions")
        res = requests.get(f"{BASE_URL}/v2/positions", headers=headers, timeout=10).json()
        if res.get("success"):
            for pos in res.get("result", []):
                if pos.get("product_id") == product_id and abs(float(pos.get("size", 0))) > 0:
                    return True
    except Exception as e:
        bot_status["last_error"] = f"Position check error: {e}"
    return False

def get_market_data(symbol, resolution="5m", limit=300):
    try:
        end_time = int(time.time())
        start_time = end_time - (limit * 300)
        url = f"{BASE_URL}/v2/chart/history?symbol={symbol}&resolution={resolution}&from={start_time}&to={end_time}"
        res = requests.get(url, timeout=10).json()
        
        if not res.get("success") or not res.get("result"):
            return None

        df = pd.DataFrame(res["result"])
        df['close'] = pd.to_numeric(df['close'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        
        # --- TECHNICAL INDICATORS (TRIPLE FILTER) ---
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['ema_200'] = ta.ema(df['close'], length=200)
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        
        return df
    except Exception as e:
        bot_status["last_error"] = f"Candle data error: {e}"
        return None

def place_bracket_order(product_id, side, entry_price, atr_value):
    # Dynamic SL & TP based on volatility (1.5x ATR for SL, 3.0x ATR for TP)
    sl_points = atr_value * 1.5
    tp_points = atr_value * 3.0

    if side == "buy":
        sl_price = round(entry_price - sl_points, 1)
        tp_price = round(entry_price + tp_points, 1)
    else:
        sl_price = round(entry_price + sl_points, 1)
        tp_price = round(entry_price - tp_points, 1)

    payload = {
        "product_id": product_id,
        "size": SIZE,
        "side": side,
        "order_type": "market_order",
        "bracket_stop_loss_price": str(sl_price),
        "bracket_take_profit_price": str(tp_price)
    }

    try:
        payload_str = json.dumps(payload)
        headers = get_headers("POST", "/v2/orders", payload=payload_str)
        res = requests.post(f"{BASE_URL}/v2/orders", headers=headers, data=payload_str, timeout=10).json()
        
        if res.get("success"):
            bot_status["last_trade"] = f"{side.upper()} @ {entry_price} | SL: {sl_price} | TP: {tp_price}"
            bot_status["total_trades"] += 1
            return True
        else:
            bot_status["last_error"] = f"Order failed: {res.get('error', 'Unknown Error')}"
            return False
    except Exception as e:
        bot_status["last_error"] = f"Execution error: {e}"
        return False

# --- MAIN TRADING ENGINE ---
def run_trading_bot():
    global bot_status, last_trade_time
    
    prod_id = get_product_id()
    while not prod_id:
        time.sleep(10)
        prod_id = get_product_id()

    bot_status["status"] = "ACTIVE & SCANNING"
    
    while True:
        try:
            in_position = has_open_position(prod_id)
            bot_status["active_position"] = in_position
            
            # Agar trade chal raha hai toh wait karo
            if in_position:
                time.sleep(15)
                continue

            df = get_market_data(SYMBOL)
            
            # Data enough nahi hai 200 EMA ke liye toh wait karo
            if df is None or len(df) < 201:
                time.sleep(10)
                continue

            last = df.iloc[-1]
            prev = df.iloc[-2]
            current_time = last.name  # Assuming index is time or row number
            
            current_price = float(last['close'])
            bot_status["last_price"] = current_price
            
            # Agar is candle par trade le chuke hain toh skip
            if last_trade_time == current_time:
                time.sleep(5)
                continue

            # --- STRATEGY CONDITIONS ---
            bullish_cross = prev['ema_9'] <= prev['ema_21'] and last['ema_9'] > last['ema_21']
            bearish_cross = prev['ema_9'] >= prev['ema_21'] and last['ema_9'] < last['ema_21']
            
            up_trend = current_price > last['ema_200']
            down_trend = current_price < last['ema_200']
            
            good_momentum_buy = last['rsi'] > 50
            good_momentum_sell = last['rsi'] < 50
            
            current_atr = float(last['atr'])

            # EXECUTE BUY
            if bullish_cross and up_trend and good_momentum_buy:
                success = place_bracket_order(prod_id, "buy", current_price, current_atr)
                if success:
                    last_trade_time = current_time
                    time.sleep(300) # Wait 5 mins

            # EXECUTE SELL
            elif bearish_cross and down_trend and good_momentum_sell:
                success = place_bracket_order(prod_id, "sell", current_price, current_atr)
                if success:
                    last_trade_time = current_time
                    time.sleep(300)

            time.sleep(10) # 10 second delay for CPU efficiency

        except Exception as e:
            bot_status["last_error"] = f"Main Loop Crash Prevented: {e}"
            time.sleep(10) # Crash hone par 10 sec wait karke restart

# Start background thread
bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
bot_thread.start()

# --- WEB DASHBOARD ---
@app.route('/')
def index():
    color = "green" if bot_status['active_position'] else "gray"
    html = f"""
    <html>
    <head>
        <title>Delta Pro Bot V2</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; }}
            .card {{ background: #1e293b; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            .status {{ color: {color}; font-weight: bold; }}
            .err {{ color: #ef4444; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🤖 Trade Bot Analytics</h2>
            <p><b>Engine Status:</b> {bot_status['status']}</p>
            <p><b>Live BTC Price:</b> ${bot_status['last_price']}</p>
            <p><b>Active Trade Running:</b> <span class="status">{'YES' if bot_status['active_position'] else 'NO'}</span></p>
            <p><b>Total Trades Taken:</b> {bot_status['total_trades']}</p>
            <hr>
            <p><b>Last Action:</b> {bot_status['last_trade']}</p>
            <p class="err"><b>System Logs:</b> {bot_status['last_error']}</p>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/ping')
def ping():
    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
