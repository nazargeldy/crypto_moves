import asyncio
import json
import logging
import websockets
import requests
from datetime import datetime
import os

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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

# Telegram Sender
def send_telegram_alert(message):
    if not config:
        return
    
    bot_token = config['telegram']['bot_token']
    chat_id = config['telegram']['chat_id']
    
    if bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.warning("Telegram Bot Token not set in config.json. Printing alert to console instead.")
        print(f"\n[TELEGRAM SIMULATION] >>> \n{message}\n")
        return

    send_text = f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={message}'
    try:
        response = requests.get(send_text)
        if response.status_code != 200:
            logger.error(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

# Formatting the Alert
def format_alert(symbol, side, price, quantity, usd_value, is_buyer_maker):
    # is_buyer_maker = True means Sell order (taker sold into maker buy)
    # is_buyer_maker = False means Buy order (taker bought from maker sell)
    
    direction = "🔴 SELL" if is_buyer_maker else "🟢 BUY"
    emoji = "🐻" if is_buyer_maker else "jq" # Bull emoji
    
    # Calculate some quick stats or links (Simulated for this MVP)
    # real links would be dynamically generated
    chart_link = f"https://www.binance.com/en/trade/{symbol.replace('USDT', '_USDT')}"
    
    msg = (
        f"*{emoji} WHALE ALERT: {symbol}*\n"
        f"----------------------------\n"
        f"**Direction:** {direction}\n"
        f"**Price:** ${price:,.4f}\n"
        f"**Amount:** {quantity:,.2f} {symbol.replace('USDT', '')}\n"
        f"**Value:** ${usd_value:,.2f}\n"
        f"----------------------------\n"
        f"[View Chart]({chart_link})"
    )
    return msg

# Main WebSocket Listener
async def binance_listener():
    if not config:
        return

    # Extract symbols from watchlist
    watchlist = config.get('watchlist', [])
    if not watchlist:
        logger.error("No coins in watchlist!")
        return

    # Prepare stream streams name
    # Binance format: <symbol>@aggTrade
    # Symbols must be lowercase for stream url
    streams = []
    thresholds = {}
    
    for item in watchlist:
        # We assume pairs are like 'BTC/USDT', we need 'btcusdt'
        clean_symbol = item['symbol'].replace('/', '').lower()
        streams.append(f"{clean_symbol}@aggTrade")
        
        # Store threshold for easy lookup using the stream symbol ticker logic
        # Note: The stream returns symbol as uppercase 'BTCUSDT' in the data payload usually
        thresholds[item['symbol'].replace('/', '')] = item['alert_threshold']

    # exact match on region
    region = config.get('region', 'com').lower()
    base_domain = "binance.us" if region == 'us' else "binance.com"
    stream_url = f"wss://stream.{base_domain}:9443/ws/{'/'.join(streams)}"
    
    logger.info(f"Connecting to Binance ({region.upper()}) Stream for: {[x['symbol'] for x in watchlist]}...")
    
    async with websockets.connect(stream_url) as websocket:
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                
                # Event type 'aggTrade'
                if data['e'] == 'aggTrade':
                    symbol = data['s'] # e.g., 'BTCUSDT'
                    price = float(data['p'])
                    quantity = float(data['q'])
                    is_buyer_maker = data['m']
                    
                    usd_value = price * quantity
                    
                    # Check our specific threshold for this coin
                    limit = thresholds.get(symbol, 50000) # Default 50k if not found
                    
                    if usd_value >= limit:
                        logger.info(f"Whale spotted on {symbol}: ${usd_value:,.2f}")
                        alert_msg = format_alert(symbol, is_buyer_maker, price, quantity, usd_value, is_buyer_maker)
                        send_telegram_alert(alert_msg)
                        
            except websockets.ConnectionClosed:
                logger.error("Connection closed. Reconnecting...")
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")

if __name__ == "__main__":
    if not os.path.exists(CONFIG_PATH):
        print("Creating default config...")
        # (Logic to create default config if missing could go here, but we already created it)
        
    print("Starting Whale Watchtower...")
    print("Press Ctrl+C to stop.")
    
    try:
        asyncio.run(binance_listener())
    except KeyboardInterrupt:
        print("Watchtower stopped.")
