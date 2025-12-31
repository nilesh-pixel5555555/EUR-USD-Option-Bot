import os
import time
import schedule
import logging
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import asyncio
from telegram import Bot
from dotenv import load_dotenv

# --- SETUP ---
load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Logging for professional monitoring
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
SYMBOL = "EURUSD=X"  # Yahoo Finance symbol for EUR/USD
TIMEFRAME = "5m"     # 5 Minute candles
RSI_PERIOD = 14
EMA_PERIOD = 50

async def send_telegram_message(message):
    """Sends the formatted signal to the Telegram Channel."""
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='Markdown')
        logger.info(f"Message sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

def get_market_data():
    """Fetches the last day of 5-minute data."""
    try:
        # Fetching slightly more data to ensure MA calculation is accurate
        df = yf.download(tickers=SYMBOL, period="1d", interval=TIMEFRAME, progress=False)
        if df.empty:
            logger.warning("Empty dataframe received.")
            return None
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None

def analyze_market():
    """Applies the strategy and returns a signal if found."""
    df = get_market_data()
    
    if df is None or len(df) < EMA_PERIOD:
        return None

    # Calculate Indicators
    # Using pandas_ta for professional calculation
    df['RSI'] = ta.rsi(df['Close'], length=RSI_PERIOD)
    df['EMA'] = ta.ema(df['Close'], length=EMA_PERIOD)

    # Get the last completed candle (index -2) because index -1 is the current forming candle
    last_candle = df.iloc[-2]
    prev_candle = df.iloc[-3]
    
    current_price = last_candle['Close']
    current_rsi = last_candle['RSI']
    prev_rsi = prev_candle['RSI']
    ema_value = last_candle['EMA']

    signal = None

    # --- STRATEGY LOGIC ---
    
    # CALL SCENARIO: Uptrend (Price > EMA) + RSI crossing upward
    if current_price > ema_value:
        if prev_rsi < 30 and current_rsi >= 30:
            signal = "CALL 🟢"

    # PUT SCENARIO: Downtrend (Price < EMA) + RSI crossing downward
    elif current_price < ema_value:
        if prev_rsi > 70 and current_rsi <= 70:
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
    """The main job running every 5 minutes."""
    logger.info("Analyzing market...")
    result = analyze_market()

    if result:
        message = (
            f"⚡ **BINARY SIGNAL** ⚡\n\n"
            f"Pair: **EUR/USD**\n"
            f"Action: **{result['signal']}**\n"
            f"Time: {result['time']}\n"
            f"Price: {result['price']}\n\n"
            f"⚠️ _Expiry: 5 Minutes_"
        )
        # Using asyncio to run the async telegram function
        asyncio.run(send_telegram_message(message))
    else:
        logger.info("No signal found this cycle.")

# --- EXECUTION ---
if __name__ == "__main__":
    logger.info("Bot started. Waiting for next 5 min interval...")
    
    # Schedule the job every 5 minutes
    # Note: To sync with candle close, in production you might use a more precise timer
    schedule.every(5).minutes.do(job)

    # Run immediately once for testing
    job()

    while True:
        schedule.run_pending()
        time.sleep(1)
