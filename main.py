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

# --- WEB SERVER (To Keep Render Alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running and healthy!"

def run_web_server():
    # Render provides the PORT variable
    port = int(os.environ.get("PORT", 10000))
    # We use a production-ready server (Waitress or Gunicorn is ideal, 
    # but for this simple bot, direct Flask run is fine behind Render's proxy)
    app.run(host='0.0.0.0', port=port)

# --- TRADING BOT LOGIC ---
async def send_telegram_message(message):
    if not BOT_TOKEN or not CHANNEL_ID:
        logger.error("Credentials missing! Check .env")
        return
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='Markdown')
        logger.info(f"Signal sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

def analyze_market():
    try:
        # Fetch Data
        df = yf.download(tickers=SYMBOL, period="1d", interval=TIMEFRAME, progress=False)
        
        if df is None or len(df) < EMA_PERIOD:
            logger.warning("Not enough data yet.")
            return

        # Calculate Indicators
        df['RSI'] = ta.rsi(df['Close'], length=RSI_PERIOD)
        df['EMA'] = ta.ema(df['Close'], length=EMA_PERIOD)

        # Get last closed candle (index -2)
        last_candle = df.iloc[-2]
        
        current_price = last_candle['Close']
        current_rsi = last_candle['RSI']
        ema_value = last_candle['EMA']

        # Determine Signal
        signal = None
        
        # CALL Strategy: Price > EMA and RSI crosses UP past 30
        if current_price > ema_value:
             if 30 <= current_rsi < 40: # Catching it as it comes up
                 signal = "CALL 🟢"

        # PUT Strategy: Price < EMA and RSI crosses DOWN past 70
        elif current_price < ema_value:
            if 60 < current_rsi <= 70: # Catching it as it goes down
                signal = "PUT 🔴"

        if signal:
            message = (
                f"⚡ **BINARY SIGNAL** ⚡\n\n"
                f"Pair: **EUR/USD**\n"
                f"Action: **{signal}**\n"
                f"Price: {round(current_price, 5)}\n"
                f"RSI: {round(current_rsi, 2)}\n"
                f"⏳ Expiry: 5 Minutes"
            )
            asyncio.run(send_telegram_message(message))
            
    except Exception as e:
        logger.error(f"Error in analysis: {e}")

def run_scheduler():
    logger.info("Scheduler started...")
    # Schedule the job
    schedule.every(5).minutes.do(analyze_market)
    
    # Infinite loop
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- EXECUTION ---
if __name__ == "__main__":
    # 1. Start the Web Server in a separate thread
    t = Thread(target=run_web_server)
    t.start()
    
    # 2. Start the Bot Scheduler in the main thread
    run_scheduler()
