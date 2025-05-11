import requests
import sqlite3
import time
import telegram
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration Layer ---
class Config:
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
    COINGECKO_API = "https://api.coingecko.com/api/v3"
    ARKHAM_API = "https://api.arkhamintelligence.com"  # Placeholder
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7883907705:AAE1hGbuRbbqWZdSDwKxYaH7j6GGzNKpKKc")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "917780480")
    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "YOUR_COINGECKO_API_KEY")
    DATABASE_PATH = "tokens.db"
    POLL_INTERVAL = 60  # Seconds
    VOLUME_THRESHOLD = 1_000_000  # $1M
    AGE_THRESHOLD = 3  # Days
    HOLDERS_THRESHOLD = 5_000
    # Placeholder API endpoints
    PUMPFUN_API = "https://api.pump.fun/tokens"
    RUGCHECK_API = "https://api.rugcheck.xyz/check"
    BUBBLEMAPS_API = "https://api.bubblemaps.io/analyze"
    TWITTERSCORE_API = "https://api.twitterscore.io/score"
    GMGN_API = "https://api.gmgn.ai/insider"

# --- Persistence Layer ---
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tokens (
                    token_address TEXT PRIMARY KEY,
                    name TEXT,
                    volume_24h REAL,
                    age_days REAL,
                    holders INTEGER,
                    social_links TEXT,
                    twitter_score REAL,
                    rugcheck_status TEXT,
                    bubblemap_anomaly TEXT,
                    trend_signal TEXT,
                    insider_activity TEXT,
                    pumpfun_tracked BOOLEAN,
                    exchange_listed BOOLEAN,
                    last_whale_activity TEXT,
                    last_updated TIMESTAMP
                )
            ''')
            conn.commit()

    def save_token(self, token: Dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO tokens (
                    token_address, name, volume_24h, age_days, holders,
                    social_links, twitter_score, rugcheck_status,
                    bubblemap_anomaly, trend_signal, insider_activity,
                    pumpfun_tracked, exchange_listed, last_whale_activity,
                    last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                token.get('token_address'),
                token.get('name'),
                token.get('volume_24h'),
                token.get('age_days'),
                token.get('holders'),
                token.get('social_links'),
                token.get('twitter_score'),
                token.get('rugcheck_status'),
                token.get('bubblemap_anomaly'),
                token.get('trend_signal'),
                token.get('insider_activity'),
                token.get('pumpfun_tracked', False),
                token.get('exchange_listed', False),
                token.get('last_whale_activity'),
                datetime.now()
            ))
            conn.commit()

    def get_tracked_tokens(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tokens WHERE pumpfun_tracked = 1')
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

# --- Fetcher Layer ---
class DataFetcher:
    @staticmethod
    def fetch_dexscreener() -> List[Dict[str, Any]]:
        try:
            response = requests.get(Config.DEXSCREENER_API)
            response.raise_for_status()
            data = response.json()
            tokens = []
            for token in data.get('tokens', []):
                creation_time = datetime.fromtimestamp(token.get('created_at', 0) / 1000)
                age_days = (datetime.now() - creation_time).days
                tokens.append({
                    'token_address': token.get('address'),
                    'name': token.get('name'),
                    'volume_24h': token.get('volume', {}).get('h24', 0),
                    'age_days': age_days,
                    'holders': token.get('holders', 0),
                    'social_links': token.get('socials', ''),
                    'price': token.get('price', {}).get('usd', 0)
                })
            return tokens
        except Exception as e:
            logger.error(f"Dexscreener fetch error: {e}")
            return []

    @staticmethod
    def fetch_pumpfun() -> List[Dict[str, Any]]:
        try:
            response = requests.get(Config.PUMPFUN_API)
            response.raise_for_status()
            data = response.json()
            return [{
                'token_address': token.get('address'),
                'name': token.get('name'),
                'pumpfun_tracked': True
            } for token in data.get('tokens', [])]
        except Exception as e:
            logger.error(f"PumpFun fetch error: {e}")
            return []

    @staticmethod
    def fetch_rugcheck(token_address: str) -> str:
        try:
            response = requests.get(f"{Config.RUGCHECK_API}/{token_address}")
            response.raise_for_status()
            return response.json().get('status', 'UNKNOWN')
        except Exception as e:
            logger.error(f"Rugcheck fetch error: {e}")
            return 'UNKNOWN'

    @staticmethod
    def fetch_bubblemaps(token_address: str) -> str:
        try:
            response = requests.get(f"{Config.BUBBLEMAPS_API}/{token_address}")
            response.raise_for_status()
            return response.json().get('anomaly', 'NONE')
        except Exception as e:
            logger.error(f"Bubblemaps fetch error: {e}")
            return 'NONE'

    @staticmethod
    def fetch_twitterscore(token_address: str) -> float:
        try:
            response = requests.get(f"{Config.TWITTERSCORE_API}/{token_address}")
            response.raise_for_status()
            return response.json().get('score', 0.0)
        except Exception as e:
            logger.error(f"TwitterScore fetch error: {e}")
            return 0.0

    @staticmethod
    def fetch_gmgn(token_address: str) -> str:
        try:
            response = requests.get(f"{Config.GMGN_API}/{token_address}")
            response.raise_for_status()
            return response.json().get('activity', 'NONE')
        except Exception as e:
            logger.error(f"GMGN fetch error: {e}")
            return 'NONE'

    @staticmethod
    def fetch_coingecko_exchanges(token_address: str) -> bool:
        try:
            headers = {'x-cg-demo-api-key': Config.COINGECKO_API_KEY}
            response = requests.get(
                f"{Config.COINGECKO_API}/coins/{token_address}/tickers",
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            return len(data.get('tickers', [])) > 0
        except Exception as e:
            logger.error(f"CoinGecko fetch error: {e}")
            return False

    @staticmethod
    def fetch_arkham_whales(token_address: str) -> str:
        try:
            headers = {'Authorization': 'Bearer YOUR_ARKHAM_API_KEY'}
            response = requests.get(
                f"{Config.ARKHAM_API}/transactions/{token_address}",
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            large_tx = any(tx.get('value', 0) > 1_000_000 for tx in data.get('transactions', []))
            return 'WHALE_ACTIVITY' if large_tx else 'NONE'
        except Exception as e:
            logger.error(f"Arkham fetch error: {e}")
            return 'NONE'

# --- Filter Module ---
class TokenFilter:
    @staticmethod
    def filter_tokens(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            token for token in tokens
            if token.get('volume_24h', 0) < Config.VOLUME_THRESHOLD
            and token.get('age_days', float('inf')) < Config.AGE_THRESHOLD
            and token.get('holders', 0) > Config.HOLDERS_THRESHOLD
        ]

# --- Social Presence Checker ---
class SocialChecker:
    @staticmethod
    def verify_socials(token: Dict[str, Any]) -> str:
        socials = token.get('social_links', '')
        return 'ACTIVE' if socials and isinstance(socials, str) and len(socials) > 0 else 'INACTIVE'

# --- Trend Analyzer ---
class TrendAnalyzer:
    @staticmethod
    def compute_trend(token: Dict[str, Any], historical_prices: List[float]) -> str:
        if not historical_prices or len(historical_prices) < 10:
            return 'NEUTRAL'
        df = pd.DataFrame({'price': historical_prices})
        df['ema'] = df['price'].ewm(span=5).mean()
        df['rsi'] = TrendAnalyzer._compute_rsi(df['price'])
        ema_slope = (df['ema'].iloc[-1] - df['ema'].iloc[-2]) / df['ema'].iloc[-2]
        rsi = df['rsi'].iloc[-1]
        if ema_slope > 0.01 and 30 < rsi < 70:
            return 'BULLISH'
        elif ema_slope < -0.01 or rsi > 70:
            return 'BEARISH'
        return 'NEUTRAL'

    @staticmethod
    def _compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

# --- Telegram Integration ---
class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.bot = telegram.Bot(token=token)
        self.chat_id = chat_id

    async def send_signal(self, token: Dict[str, Any], signal: str):
        message = (
            f"{signal} Signal for {token.get('name')} (Contract: {token.get('token_address')})\n"
            f"Price: ${token.get('price', 0):.4f}\n"
            f"Trend: {token.get('trend_signal')}\n"
            f"Twitter Score: {token.get('twitter_score', 0)}\n"
            f"Rugcheck: {token.get('rugcheck_status')}\n"
            f"Socials: {token.get('social_links')}\n"
            f"Exchange Listed: {'YES' if token.get('exchange_listed') else 'NO'}\n"
            f"Whale Activity: {token.get('last_whale_activity')}\n"
            f"Insider Activity: {token.get('insider_activity')}"
        )
        await self.bot.send_message(chat_id=self.chat_id, text=message)

    async def send_exchange_notification(self, token: Dict[str, Any]):
        message = (
            f"Exchange Listing Alert for {token.get('name')} (Contract: {token.get('token_address')})\n"
            f"Listed on Global Exchanges!\n"
            f"Price: ${token.get('price', 0):.4f}\n"
            f"Trend: {token.get('trend_signal')}\n"
            f"Twitter Score: {token.get('twitter_score', 0)}\n"
            f"Socials: {token.get('social_links')}\n"
            f"Whale Activity: {token.get('last_whale_activity')}\n"
            f"Insider Activity: {token.get('insider_activity')}"
        )
        await self.bot.send_message(chat_id=self.chat_id, text=message)

    async def send_whale_notification(self, token: Dict[str, Any]):
        message = (
            f"Whale Movement Alert for {token.get('name')} (Contract: {token.get('token_address')})\n"
            f"Large Transaction Detected!\n"
            f"Price: ${token.get('price', 0):.4f}\n"
            f"Trend: {token.get('trend_signal')}\n"
            f"Twitter Score: {token.get('twitter_score', 0)}\n"
            f"Socials: {token.get('social_links')}\n"
            f"Exchange Listed: {'YES' if token.get('exchange_listed') else 'NO'}\n"
            f"Insider Activity: {token.get('insider_activity')}"
        )
        await self.bot.send_message(chat_id=self.chat_id, text=message)

    async def execute_order(self, token: Dict[str, Any], action: str):
        message = (
            f"Executing {action} order for {token.get('name')} (Contract: {token.get('token_address')})\n"
            f"Price: ${token.get('price', 0):.4f}\n"
            f"Trend: {token.get('trend_signal')}\n"
            f"Twitter Score: {token.get('twitter_score', 0)}\n"
            f"Insider Activity: {token.get('insider_activity')}"
        )
        await self.bot.send_message(chat_id=self.chat_id, text=message)

# --- Main Bot ---
class TradingBot:
    def __init__(self):
        self.db = Database(Config.DATABASE_PATH)
        self.fetcher = DataFetcher()
        self.filter = TokenFilter()
        self.social_checker = SocialChecker()
        self.trend_analyzer = TrendAnalyzer()
        self.notifier = TelegramNotifier(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID)
        self.price_history = {}

    async def run(self):
        while True:
            logger.info("Starting new cycle")
            # Fetch and process Dexscreener data
            tokens = self.fetcher.fetch_dexscreener()
            filtered_tokens = self.filter.filter_tokens(tokens)

            for token in filtered_tokens:
                # Enhance token data
                token['social_links'] = self.social_checker.verify_socials(token)
                token['rugcheck_status'] = self.fetcher.fetch_rugcheck(token['token_address'])
                token['bubblemap_anomaly'] = self.fetcher.fetch_bubblemaps(token['token_address'])
                token['twitter_score'] = self.fetcher.fetch_twitterscore(token['token_address'])
                token['insider_activity'] = self.fetcher.fetch_gmgn(token['token_address'])
                token['exchange_listed'] = self.fetcher.fetch_coingecko_exchanges(token['token_address'])
                token['last_whale_activity'] = self.fetcher.fetch_arkham_whales(token['token_address'])

                # Trend analysis
                self.price_history.setdefault(token['token_address'], []).append(token.get('price', 0))
                if len(self.price_history[token['token_address']]) > 100:
                    self.price_history[token['token_address']] = self.price_history[token['token_address']][-100:]
                token['trend_signal'] = self.trend_analyzer.compute_trend(
                    token, self.price_history[token['token_address']]
                )

                # Save to database
                if token['rugcheck_status'] == 'GOOD':
                    self.db.save_token(token)

                # Send notifications
                if token['trend_signal'] == 'BULLISH' and token['bubblemap_anomaly'] == 'NONE':
                    await self.notifier.send_signal	token, 'BUY')
                    await self.notifier.execute_order(token, 'BUY')
                elif token['trend_signal'] == 'BEARISH':
                    await self.notifier.send_signal(token, 'SELL')
                    await self.notifier.execute_order(token, 'SELL')

                if token['exchange_listed']:
                    await self.notifier.send_exchange_notification(token)

                if token['last_whale_activity'] == 'WHALE_ACTIVITY':
                    await self.notifier.send_whale_notification(token)

            # Fetch and process PumpFun data
            pumpfun_tokens = self.fetcher.fetch_pumpfun()
            for token in pumpfun_tokens:
                token['pumpfun_tracked'] = True
                token['exchange_listed'] = self.fetcher.fetch_coingecko_exchanges(token['token_address'])
                token['last_whale_activity'] = self.fetcher.fetch_arkham_whales(token['token_address'])
                self.db.save_token(token)

            logger.info("Cycle complete, sleeping...")
            await asyncio.sleep(Config.POLL_INTERVAL)

# --- Entry Point ---
if __name__ == "__main__":
    bot = TradingBot()
    asyncio.run(bot.run())
