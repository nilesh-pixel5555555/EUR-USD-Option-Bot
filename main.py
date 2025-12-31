import os
import time
import schedule
import logging
import yfinance as yf
import pandas_ta as ta
import asyncio
from telegram import Bot
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- SETUP ---
load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
SYMBOL = "EURUSD=X"
TIMEFRAME = "5m"
RSI_PERIOD = 14
EMA_PERIOD = 50

# --- FLASK SERVER (To Keep Render Alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    # Render assigns a port in the PORT env var, default to 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT LOGIC ---
async def send_telegram_message(message):
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='Markdown')
        logger.info(f"Message sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

def get_market_data():
    try:
        df = yf.download(tickers=SYMBOL, period="1d", interval=TIMEFRAME, progress=False)
        if df.empty: return None
        return df
    except Exception:
        return None

def analyze_market():
    df = get_market_data()
    if df is None or len(df) < EMA_PERIOD: return None

    df['RSI'] = ta.rsi(df['Close'], length=RSI_PERIOD)
    df['EMA'] = ta.ema(df['Close'], length=EMA_PERIOD)

    last_candle = df.iloc[-2]
    prev_candle = df.iloc[-3]
    
    current_price = last_candle['Close']
    current_rsi = last_candle['RSI']
    prev_rsi = prev_candle['RSI']
    ema_value = last_candle['EMA']

    signal = None

    if current_price > ema_value and prev_rsi < 30 and current_rsi >= 30:
        signal = "CALL 🟢"
    elif current_price < ema_value and prev_rsi > 70 and current_rsi <= 70:
        signal = "PUT 🔴"

    if signal:
        return {
            'signal': signal,
            'price': round(current_price, 5),
            'rsi': round(current_rsi, 2),
            'time': last_candle.name.strftime('%H:%M UTC')
        }
    return None

def job():
    logger.info("Analyzing market...")
    result = analyze_market()
    if result:
        message = (
            f"⚡ **BINARY SIGNAL** ⚡\n"
            f"Pair: **EUR/USD**\n"
            f"Action: **{result['signal']}**\n"
            f"Time: {result['time']}\n"
            f"Price: {result['price']}"
        )
        asyncio.run(send_telegram_message(message))

def run_scheduler():
    schedule.every(5).minutes.do(job)
    # Run once on start
    job() 
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- EXECUTION ---
if __name__ == "__main__":
    # Start Flask in a separate thread
    t = Thread(target=run_flask)
    t.start()
    
    # Start the Bot
    run_scheduler()
