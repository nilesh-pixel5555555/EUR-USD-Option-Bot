import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
import yfinance as yf
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BinaryOptionsBot:
    def __init__(self, telegram_token, channel_id, symbol="EURUSD=X", min_confidence=60):
        """
        Initialize the Binary Options Trading Bot
        
        Args:
            telegram_token (str): Telegram bot token
            channel_id (str): Telegram channel ID (e.g., @yourchannel or -1001234567890)
            symbol (str): Trading symbol (default: EURUSD=X)
            min_confidence (int): Minimum confidence percentage (default: 60)
        """
        self.bot = Bot(token=telegram_token)
        self.channel_id = channel_id
        self.symbol = symbol
        self.interval = "1m"  # 1-minute data for precise analysis
        self.min_confidence = min_confidence
        
    def fetch_market_data(self, period="1d"):
        """Fetch real-time market data for EUR/USD"""
        try:
            data = yf.download(
                self.symbol,
                period=period,
                interval=self.interval,
                progress=False
            )
            if data.empty:
                logger.error("No data fetched from yfinance")
                return None
            return data
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return None
    
    def calculate_indicators(self, df):
        """Calculate technical indicators for signal generation"""
        try:
            # RSI (Relative Strength Index)
            rsi = RSIIndicator(close=df['Close'], window=14)
            df['RSI'] = rsi.rsi()
            
            # MACD (Moving Average Convergence Divergence)
            macd = MACD(close=df['Close'])
            df['MACD'] = macd.macd()
            df['MACD_Signal'] = macd.macd_signal()
            df['MACD_Diff'] = macd.macd_diff()
            
            # EMA (Exponential Moving Average)
            ema_9 = EMAIndicator(close=df['Close'], window=9)
            ema_21 = EMAIndicator(close=df['Close'], window=21)
            df['EMA_9'] = ema_9.ema_indicator()
            df['EMA_21'] = ema_21.ema_indicator()
            
            # Bollinger Bands
            bollinger = BollingerBands(close=df['Close'], window=20, window_dev=2)
            df['BB_High'] = bollinger.bollinger_hband()
            df['BB_Low'] = bollinger.bollinger_lband()
            df['BB_Mid'] = bollinger.bollinger_mavg()
            
            # Stochastic Oscillator
            stoch = StochasticOscillator(
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                window=14,
                smooth_window=3
            )
            df['Stoch_K'] = stoch.stoch()
            df['Stoch_D'] = stoch.stoch_signal()
            
            return df
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return None
    
    def generate_signal(self, df):
        """
        Generate trading signal based on multiple indicator confluence
        
        Returns:
            dict: Signal information with direction, confidence, and reasoning
        """
        if df is None or len(df) < 30:
            return None
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        call_score = 0
        put_score = 0
        reasons = []
        
        # RSI Analysis (30% weight)
        if latest['RSI'] < 30:
            call_score += 3
            reasons.append("RSI Oversold (<30)")
        elif latest['RSI'] > 70:
            put_score += 3
            reasons.append("RSI Overbought (>70)")
        elif latest['RSI'] < 40 and prev['RSI'] < latest['RSI']:
            call_score += 1
            reasons.append("RSI Bullish Momentum")
        elif latest['RSI'] > 60 and prev['RSI'] > latest['RSI']:
            put_score += 1
            reasons.append("RSI Bearish Momentum")
        
        # MACD Analysis (25% weight)
        if latest['MACD_Diff'] > 0 and prev['MACD_Diff'] <= 0:
            call_score += 2.5
            reasons.append("MACD Bullish Crossover")
        elif latest['MACD_Diff'] < 0 and prev['MACD_Diff'] >= 0:
            put_score += 2.5
            reasons.append("MACD Bearish Crossover")
        elif latest['MACD_Diff'] > 0:
            call_score += 0.5
        elif latest['MACD_Diff'] < 0:
            put_score += 0.5
        
        # EMA Trend Analysis (20% weight)
        if latest['EMA_9'] > latest['EMA_21'] and latest['Close'] > latest['EMA_9']:
            call_score += 2
            reasons.append("Strong Bullish Trend (EMA)")
        elif latest['EMA_9'] < latest['EMA_21'] and latest['Close'] < latest['EMA_9']:
            put_score += 2
            reasons.append("Strong Bearish Trend (EMA)")
        
        # Bollinger Bands Analysis (15% weight)
        if latest['Close'] < latest['BB_Low']:
            call_score += 1.5
            reasons.append("Price Below Lower BB")
        elif latest['Close'] > latest['BB_High']:
            put_score += 1.5
            reasons.append("Price Above Upper BB")
        
        # Stochastic Analysis (10% weight)
        if latest['Stoch_K'] < 20 and latest['Stoch_K'] > prev['Stoch_K']:
            call_score += 1
            reasons.append("Stochastic Oversold Reversal")
        elif latest['Stoch_K'] > 80 and latest['Stoch_K'] < prev['Stoch_K']:
            put_score += 1
            reasons.append("Stochastic Overbought Reversal")
        
        # Determine signal
        total_score = call_score + put_score
        if total_score < 3:
            return None  # Not enough confluence
        
        if call_score > put_score:
            signal_type = "CALL"
            confidence = min(95, int((call_score / 10) * 100))
        else:
            signal_type = "PUT"
            confidence = min(95, int((put_score / 10) * 100))
        
        # Require minimum confidence
        if confidence < self.min_confidence:
            return None
        
        return {
            'type': signal_type,
            'confidence': confidence,
            'reasons': reasons[:3],  # Top 3 reasons
            'price': latest['Close'],
            'time': datetime.now()
        }
    
    def format_signal_message(self, signal):
        """Format the trading signal for Telegram"""
        emoji = "🟢" if signal['type'] == "CALL" else "🔴"
        
        message = f"""
{emoji} **BINARY OPTIONS SIGNAL** {emoji}

📊 **Pair:** EUR/USD
⏱ **Expiry:** 5 Minutes
📈 **Signal:** {signal['type']}
💰 **Entry Price:** {signal['price']:.5f}
🎯 **Confidence:** {signal['confidence']}%

**Analysis:**
"""
        for reason in signal['reasons']:
            message += f"✓ {reason}\n"
        
        message += f"\n⏰ **Time:** {signal['time'].strftime('%H:%M:%S UTC')}"
        message += "\n\n⚠️ *Trade at your own risk. This is not financial advice.*"
        
        return message
    
    async def send_signal(self, signal):
        """Send signal to Telegram channel"""
        try:
            message = self.format_signal_message(signal)
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"Signal sent: {signal['type']} at {signal['price']:.5f}")
            return True
        except TelegramError as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def run(self):
        """Main bot loop - sends signals every 5 minutes"""
        logger.info("Binary Options Bot Started!")
        logger.info(f"Monitoring: {self.symbol}")
        logger.info(f"Signal Interval: 5 minutes")
        
        # Send startup message
        try:
            await self.bot.send_message(
                chat_id=self.channel_id,
                text="🤖 **Binary Options Signal Bot Started**\n\n"
                     "📊 Pair: EUR/USD\n"
                     "⏱ Timeframe: 5 Minutes\n"
                     "🎯 Strategy: Multi-Indicator Confluence\n\n"
                     "Signals will be sent every 5 minutes.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending startup message: {e}")
        
        while True:
            try:
                # Wait until next 5-minute mark
                now = datetime.now()
                next_signal = now + timedelta(minutes=5 - now.minute % 5, 
                                              seconds=-now.second,
                                              microseconds=-now.microsecond)
                wait_seconds = (next_signal - now).total_seconds()
                
                if wait_seconds > 0:
                    logger.info(f"Next signal in {int(wait_seconds)} seconds...")
                    await asyncio.sleep(wait_seconds)
                
                # Fetch data and generate signal
                logger.info("Analyzing market data...")
                df = self.fetch_market_data(period="1d")
                
                if df is not None:
                    df = self.calculate_indicators(df)
                    if df is not None:
                        signal = self.generate_signal(df)
                        
                        if signal:
                            await self.send_signal(signal)
                        else:
                            logger.info("No high-confidence signal at this time")
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error

async def main():
    # Load configuration from environment variables
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
    SYMBOL = os.getenv('SYMBOL', 'EURUSD=X')
    MIN_CONFIDENCE = int(os.getenv('MIN_CONFIDENCE', '60'))
    
    # Validate configuration
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment variables!")
        logger.info("Create a .env file and add: TELEGRAM_BOT_TOKEN=your_token")
        logger.info("Get token from @BotFather on Telegram")
        return
    
    if not CHANNEL_ID:
        logger.error("TELEGRAM_CHANNEL_ID not set in environment variables!")
        logger.info("Create a .env file and add: TELEGRAM_CHANNEL_ID=@your_channel")
        logger.info("Add your bot as admin to the channel first")
        return
    
    # Initialize and run bot
    bot = BinaryOptionsBot(TELEGRAM_TOKEN, CHANNEL_ID, SYMBOL, MIN_CONFIDENCE)
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
