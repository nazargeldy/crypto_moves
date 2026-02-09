import asyncio
import json
import logging
import websockets
import requests
import aiohttp
from datetime import datetime, timezone
import os

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found at {CONFIG_PATH}")
        return None

config = load_config()

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram_alert(message):
    if not config:
        return
    
    bot_token = config['telegram']['bot_token']
    chat_id = config['telegram']['chat_id']
    
    if bot_token == "YOUR_BOT_TOKEN_HERE":
        print(f"\n{'='*50}")
        print(message)
        print(f"{'='*50}\n")
        return

    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Telegram API error: {response.text}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")

# ============================================================
# ALERT FORMATTING
# ============================================================
def format_coinbase_alert(symbol, side, price, size, usd_value):
    direction = "🔴 SELL" if side == "sell" else "🟢 BUY"
    emoji = "🐻" if side == "sell" else "🐋"
    coin = symbol.split("-")[0]
    chart_link = f"https://www.coinbase.com/advanced-trade/spot/{symbol}"
    
    msg = (
        f"{emoji} *WHALE ALERT: {symbol}* (Coinbase)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Direction: {direction}\n"
        f"Price: ${price:,.4f}\n"
        f"Amount: {size:,.6f} {coin}\n"
        f"Value: *${usd_value:,.2f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"[View Chart]({chart_link})"
    )
    return msg

def format_dex_alert(symbol, price_change_5m, price_usd, volume_5m, pair_address):
    emoji = "🟢" if price_change_5m >= 0 else "🔴"
    chart_link = f"https://dexscreener.com/base/{pair_address}"
    
    msg = (
        f"🐋 *DEX ALERT: {symbol}* (Base Chain)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Price: ${price_usd:,.8f}\n"
        f"5min Change: {emoji} {price_change_5m:+.2f}%\n"
        f"5min Volume: *${volume_5m:,.2f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"[View on DexScreener]({chart_link})"
    )
    return msg

# ============================================================
# ENGINE 1: COINBASE WEBSOCKET (BTC, ETH, SOL, DOGE, PEPE)
# ============================================================
async def coinbase_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    coinbase_coins = [x for x in watchlist if x.get('exchange') == 'coinbase']
    
    if not coinbase_coins:
        logger.info("No Coinbase coins in watchlist.")
        return

    product_ids = [x['symbol'] for x in coinbase_coins]
    thresholds = {x['symbol']: x['alert_threshold'] for x in coinbase_coins}
    
    url = "wss://ws-feed.exchange.coinbase.com"
    
    while True:
        try:
            logger.info(f"Connecting to Coinbase for: {product_ids}...")
            
            async with websockets.connect(url) as ws:
                # Subscribe to the "matches" channel (confirmed trades)
                subscribe_msg = {
                    "type": "subscribe",
                    "product_ids": product_ids,
                    "channels": ["matches"]
                }
                await ws.send(json.dumps(subscribe_msg))
                
                msg_count = 0
                
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    # Only process confirmed trade matches
                    if data.get("type") in ("match", "last_match"):
                        symbol = data['product_id']       # e.g. "BTC-USD"
                        price = float(data['price'])
                        size = float(data['size'])
                        side = data['side']                # "buy" or "sell"
                        usd_value = price * size
                        
                        # Debug: first 5 trades
                        msg_count += 1
                        if msg_count <= 5:
                            logger.info(f"[Coinbase] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                        
                        # Check threshold
                        limit = thresholds.get(symbol, 500)
                        if usd_value >= limit:
                            logger.info(f"🐋 WHALE on {symbol}: {side.upper()} ${usd_value:,.2f}")
                            alert_msg = format_coinbase_alert(symbol, side, price, size, usd_value)
                            send_telegram_alert(alert_msg)
                            
        except websockets.ConnectionClosed:
            logger.warning("Coinbase connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Coinbase error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 2: DEXSCREENER POLLER (BRETT, TOSHI on Base)
# ============================================================
async def dex_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    dex_coins = [x for x in watchlist if 'dex' in x.get('exchange', '')]

    if not dex_coins:
        logger.info("No DEX coins in watchlist.")
        return

    logger.info(f"Starting DEX Poller for: {[x['symbol'] for x in dex_coins]}...")
    
    # Store previous volume snapshots to detect spikes
    prev_volumes = {}
    
    token_addresses = ",".join([x['token_address'] for x in dex_coins])
    api_url = f"https://api.dexscreener.com/latest/dex/tokens/{token_addresses}"

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])
                        
                        for coin in dex_coins:
                            addr = coin['token_address'].lower()
                            threshold = coin['alert_threshold']
                            symbol = coin['symbol']
                            
                            # Find matching pairs for this token
                            coin_pairs = [p for p in pairs if p['baseToken']['address'].lower() == addr]
                            
                            if not coin_pairs:
                                continue
                            
                            # Take the most liquid pair
                            top_pair = sorted(
                                coin_pairs, 
                                key=lambda x: float(x.get('liquidity', {}).get('usd', 0)), 
                                reverse=True
                            )[0]
                            
                            price_usd = float(top_pair.get('priceUsd', 0))
                            price_change_5m = float(top_pair.get('priceChange', {}).get('m5', 0) or 0)
                            volume_5m = float(top_pair.get('volume', {}).get('m5', 0) or 0)
                            pair_address = top_pair.get('pairAddress', addr)
                            
                            # Track volume spikes
                            prev_vol = prev_volumes.get(symbol, 0)
                            prev_volumes[symbol] = volume_5m
                            
                            # Alert if 5-min volume exceeds threshold OR price moved > 3% in 5 min
                            if volume_5m >= threshold or abs(price_change_5m) >= 3.0:
                                # Don't spam the same alert if volume hasn't changed
                                if volume_5m != prev_vol or abs(price_change_5m) >= 3.0:
                                    logger.info(f"🐋 DEX Activity on {symbol}: Vol=${volume_5m:,.0f} | Change={price_change_5m:+.2f}%")
                                    alert_msg = format_dex_alert(symbol, price_change_5m, price_usd, volume_5m, pair_address)
                                    send_telegram_alert(alert_msg)
                    else:
                        logger.warning(f"DexScreener API returned {response.status}")
                        
            except Exception as e:
                logger.error(f"DEX Poller error: {e}")
            
            # Poll every 10 seconds
            await asyncio.sleep(10)

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  WHALE WATCHTOWER v2 (Coinbase + DEX)")
    print("=" * 50)
    print("Press Ctrl+C to stop.\n")
    
    try:
        async def main():
            await asyncio.gather(
                coinbase_listener(),
                dex_listener()
            )
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWatchtower stopped.")
