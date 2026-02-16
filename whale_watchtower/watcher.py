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
def format_exchange_alert(symbol, side, price, size, usd_value, exchange_name):
    direction = "🔴 SELL" if side == "sell" else "🟢 BUY"
    emoji = "🐻" if side == "sell" else "🐋"
    coin = symbol.split("-")[0].split("/")[0]
    
    msg = (
        f"{emoji} *WHALE ALERT: {symbol}* ({exchange_name})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Direction: {direction}\n"
        f"Price: ${price:,.4f}\n"
        f"Amount: {size:,.6f} {coin}\n"
        f"Value: *${usd_value:,.2f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
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
                            alert_msg = format_exchange_alert(symbol, side, price, size, usd_value, "Coinbase")
                            send_telegram_alert(alert_msg)
                            
        except websockets.ConnectionClosed:
            logger.warning("Coinbase connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Coinbase error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 2: KRAKEN WEBSOCKET
# ============================================================
async def kraken_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    kraken_coins = [x for x in watchlist if x.get('exchange') == 'kraken']
    
    if not kraken_coins:
        logger.info("No Kraken coins in watchlist.")
        return

    # Kraken uses symbols like "BTC/USD"
    symbols = [x['symbol'] for x in kraken_coins]
    thresholds = {x['symbol']: x['alert_threshold'] for x in kraken_coins}
    
    url = "wss://ws.kraken.com/v2"
    
    while True:
        try:
            logger.info(f"Connecting to Kraken for: {symbols}...")
            
            async with websockets.connect(url) as ws:
                subscribe_msg = {
                    "method": "subscribe",
                    "params": {
                        "channel": "trade",
                        "symbol": symbols
                    }
                }
                await ws.send(json.dumps(subscribe_msg))
                
                msg_count = 0
                
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    if data.get("channel") == "trade" and "data" in data:
                        for trade in data["data"]:
                            symbol = trade.get("symbol", "?")
                            price = float(trade["price"])
                            qty = float(trade["qty"])
                            side = trade.get("side", "buy")
                            usd_value = price * qty
                            
                            msg_count += 1
                            if msg_count <= 5:
                                logger.info(f"[Kraken] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                            
                            limit = thresholds.get(symbol, 500)
                            if usd_value >= limit:
                                logger.info(f"🐋 WHALE on Kraken {symbol}: {side.upper()} ${usd_value:,.2f}")
                                alert_msg = format_exchange_alert(symbol, side, price, qty, usd_value, "Kraken")
                                send_telegram_alert(alert_msg)
                                
        except websockets.ConnectionClosed:
            logger.warning("Kraken connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Kraken error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 3: GEMINI WEBSOCKET
# ============================================================
async def gemini_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    gemini_coins = [x for x in watchlist if x.get('exchange') == 'gemini']
    
    if not gemini_coins:
        logger.info("No Gemini coins in watchlist.")
        return

    logger.info(f"Connecting to Gemini for: {[x['symbol'] for x in gemini_coins]}...")
    
    # Gemini requires one WebSocket per symbol
    async def watch_gemini_symbol(coin):
        symbol = coin['symbol']       # e.g. "btcusd"
        threshold = coin['alert_threshold']
        display = symbol.upper()
        url = f"wss://api.gemini.com/v1/marketdata/{symbol}?trades=true&bids=false&offers=false"
        
        while True:
            try:
                async with websockets.connect(url) as ws:
                    msg_count = 0
                    while True:
                        message = await ws.recv()
                        data = json.loads(message)
                        events = data.get("events", [])
                        
                        for ev in events:
                            if ev.get("type") == "trade":
                                price = float(ev["price"])
                                amount = float(ev["amount"])
                                usd_value = price * amount
                                maker_side = ev.get("makerSide", "ask")
                                # makerSide "bid" = taker sold, "ask" = taker bought
                                side = "sell" if maker_side == "bid" else "buy"
                                
                                msg_count += 1
                                if msg_count <= 3:
                                    logger.info(f"[Gemini] #{msg_count} {display} {side.upper()} ${usd_value:,.2f}")
                                
                                if usd_value >= threshold:
                                    logger.info(f"🐋 WHALE on Gemini {display}: {side.upper()} ${usd_value:,.2f}")
                                    alert_msg = format_exchange_alert(display, side, price, amount, usd_value, "Gemini")
                                    send_telegram_alert(alert_msg)
                                    
            except websockets.ConnectionClosed:
                logger.warning(f"Gemini {display} connection closed. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Gemini {display} error: {e}. Reconnecting in 10s...")
                await asyncio.sleep(10)
    
    # Launch all Gemini symbol watchers concurrently
    await asyncio.gather(*[watch_gemini_symbol(c) for c in gemini_coins])

# ============================================================
# ENGINE 4: BINANCE WEBSOCKET
# ============================================================
async def binance_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    binance_coins = [x for x in watchlist if x.get('exchange') == 'binance']
    
    if not binance_coins:
        logger.info("No Binance coins in watchlist.")
        return

    streams = []
    thresholds = {}
    for item in binance_coins:
        clean = item['symbol'].replace('/', '').lower()
        streams.append(f"{clean}@aggTrade")
        thresholds[item['symbol'].replace('/', '').upper()] = item['alert_threshold']
    
    url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
    
    while True:
        try:
            logger.info(f"Connecting to Binance for: {[x['symbol'] for x in binance_coins]}...")
            async with websockets.connect(url) as ws:
                msg_count = 0
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    if data.get('data'):
                        data = data['data']
                    if data.get("e") == "aggTrade":
                        symbol = data['s']
                        price = float(data['p'])
                        qty = float(data['q'])
                        is_buyer_maker = data['m']
                        side = "sell" if is_buyer_maker else "buy"
                        usd_value = price * qty
                        
                        msg_count += 1
                        if msg_count <= 5:
                            logger.info(f"[Binance] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                        
                        limit = thresholds.get(symbol, 500000)
                        if usd_value >= limit:
                            logger.info(f"🐋 WHALE on Binance {symbol}: {side.upper()} ${usd_value:,.2f}")
                            alert_msg = format_exchange_alert(symbol, side, price, qty, usd_value, "Binance")
                            send_telegram_alert(alert_msg)
                            
        except websockets.ConnectionClosed:
            logger.warning("Binance connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Binance error: {e}. Reconnecting in 30s...")
            await asyncio.sleep(30)

# ============================================================
# ENGINE 5: OKX WEBSOCKET
# ============================================================
async def okx_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    okx_coins = [x for x in watchlist if x.get('exchange') == 'okx']
    
    if not okx_coins:
        logger.info("No OKX coins in watchlist.")
        return

    thresholds = {x['symbol']: x['alert_threshold'] for x in okx_coins}
    sub_args = [{"channel": "trades", "instId": x['symbol']} for x in okx_coins]
    
    url = "wss://ws.okx.com:8443/ws/v5/public"
    
    while True:
        try:
            logger.info(f"Connecting to OKX for: {[x['symbol'] for x in okx_coins]}...")
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": sub_args}))
                msg_count = 0
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    if "data" in data and data.get("arg", {}).get("channel") == "trades":
                        for t in data["data"]:
                            symbol = t.get("instId", "?")
                            price = float(t["px"])
                            size = float(t["sz"])
                            side = t["side"]
                            usd_value = price * size
                            
                            msg_count += 1
                            if msg_count <= 5:
                                logger.info(f"[OKX] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                            
                            limit = thresholds.get(symbol, 500000)
                            if usd_value >= limit:
                                logger.info(f"🐋 WHALE on OKX {symbol}: {side.upper()} ${usd_value:,.2f}")
                                alert_msg = format_exchange_alert(symbol, side, price, size, usd_value, "OKX")
                                send_telegram_alert(alert_msg)
                                
        except websockets.ConnectionClosed:
            logger.warning("OKX connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"OKX error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 6: BYBIT WEBSOCKET
# ============================================================
async def bybit_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    bybit_coins = [x for x in watchlist if x.get('exchange') == 'bybit']
    
    if not bybit_coins:
        logger.info("No Bybit coins in watchlist.")
        return

    thresholds = {x['symbol']: x['alert_threshold'] for x in bybit_coins}
    sub_args = [f"publicTrade.{x['symbol']}" for x in bybit_coins]
    
    url = "wss://stream.bybit.com/v5/public/spot"
    
    while True:
        try:
            logger.info(f"Connecting to Bybit for: {[x['symbol'] for x in bybit_coins]}...")
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": sub_args}))
                msg_count = 0
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    topic = data.get("topic", "")
                    if topic.startswith("publicTrade.") and "data" in data:
                        for t in data["data"]:
                            symbol = t.get("s", topic.replace("publicTrade.", ""))
                            price = float(t["p"])
                            size = float(t["v"])
                            side = t.get("S", "Buy").lower()
                            usd_value = price * size
                            
                            msg_count += 1
                            if msg_count <= 5:
                                logger.info(f"[Bybit] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                            
                            limit = thresholds.get(symbol, 500000)
                            if usd_value >= limit:
                                logger.info(f"🐋 WHALE on Bybit {symbol}: {side.upper()} ${usd_value:,.2f}")
                                alert_msg = format_exchange_alert(symbol, side, price, size, usd_value, "Bybit")
                                send_telegram_alert(alert_msg)
                                
        except websockets.ConnectionClosed:
            logger.warning("Bybit connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Bybit error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 7: BITGET WEBSOCKET
# ============================================================
async def bitget_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    bitget_coins = [x for x in watchlist if x.get('exchange') == 'bitget']
    
    if not bitget_coins:
        logger.info("No Bitget coins in watchlist.")
        return

    thresholds = {x['symbol']: x['alert_threshold'] for x in bitget_coins}
    sub_args = [{"instType": "SPOT", "channel": "trade", "instId": x['symbol']} for x in bitget_coins]
    
    url = "wss://ws.bitget.com/v2/ws/public"
    
    while True:
        try:
            logger.info(f"Connecting to Bitget for: {[x['symbol'] for x in bitget_coins]}...")
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": sub_args}))
                msg_count = 0
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    if "data" in data:
                        for t in data.get("data", []):
                            if "price" in t or "px" in t:
                                symbol = data.get("arg", {}).get("instId", "?")
                                price = float(t.get("price", t.get("px", 0)))
                                size = float(t.get("size", t.get("sz", 0)))
                                side = t.get("side", "buy").lower()
                                usd_value = price * size
                                
                                msg_count += 1
                                if msg_count <= 5:
                                    logger.info(f"[Bitget] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                                
                                limit = thresholds.get(symbol, 500000)
                                if usd_value >= limit:
                                    logger.info(f"🐋 WHALE on Bitget {symbol}: {side.upper()} ${usd_value:,.2f}")
                                    alert_msg = format_exchange_alert(symbol, side, price, size, usd_value, "Bitget")
                                    send_telegram_alert(alert_msg)
                                    
        except websockets.ConnectionClosed:
            logger.warning("Bitget connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Bitget error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 8: KUCOIN WEBSOCKET
# ============================================================
async def kucoin_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    kucoin_coins = [x for x in watchlist if x.get('exchange') == 'kucoin']
    
    if not kucoin_coins:
        logger.info("No KuCoin coins in watchlist.")
        return

    thresholds = {x['symbol']: x['alert_threshold'] for x in kucoin_coins}
    topics = [f"/market/match:{x['symbol']}" for x in kucoin_coins]
    
    while True:
        try:
            logger.info(f"Connecting to KuCoin for: {[x['symbol'] for x in kucoin_coins]}...")
            # KuCoin requires getting a WS token first
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.kucoin.com/api/v1/bullet-public") as resp:
                    bullet = await resp.json()
                    token = bullet["data"]["token"]
                    endpoint = bullet["data"]["instanceServers"][0]["endpoint"]
                    ws_url = f"{endpoint}?token={token}"
            
            async with websockets.connect(ws_url, ping_interval=20) as ws:
                for topic in topics:
                    await ws.send(json.dumps({"id": 1, "type": "subscribe", "topic": topic, "privateChannel": False, "response": True}))
                
                msg_count = 0
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    topic = data.get("topic", "")
                    if topic.startswith("/market/match:") and "data" in data:
                        t = data["data"]
                        symbol = t.get("symbol", topic.replace("/market/match:", ""))
                        price = float(t["price"])
                        size = float(t["size"])
                        side = t.get("side", "buy").lower()
                        usd_value = price * size
                        
                        msg_count += 1
                        if msg_count <= 5:
                            logger.info(f"[KuCoin] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                        
                        limit = thresholds.get(symbol, 500000)
                        if usd_value >= limit:
                            logger.info(f"🐋 WHALE on KuCoin {symbol}: {side.upper()} ${usd_value:,.2f}")
                            alert_msg = format_exchange_alert(symbol, side, price, size, usd_value, "KuCoin")
                            send_telegram_alert(alert_msg)
                            
        except websockets.ConnectionClosed:
            logger.warning("KuCoin connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"KuCoin error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 9: GATE.IO WEBSOCKET
# ============================================================
async def gateio_listener():
    if not config:
        return

    watchlist = config.get('watchlist', [])
    gateio_coins = [x for x in watchlist if x.get('exchange') == 'gateio']
    
    if not gateio_coins:
        logger.info("No Gate.io coins in watchlist.")
        return

    thresholds = {x['symbol']: x['alert_threshold'] for x in gateio_coins}
    import time
    
    url = "wss://api.gateio.ws/ws/v4/"
    
    while True:
        try:
            logger.info(f"Connecting to Gate.io for: {[x['symbol'] for x in gateio_coins]}...")
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({
                    "time": int(time.time()),
                    "channel": "spot.trades",
                    "event": "subscribe",
                    "payload": [x['symbol'] for x in gateio_coins]
                }))
                msg_count = 0
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    if data.get("channel") == "spot.trades" and data.get("event") == "update":
                        result = data.get("result", {})
                        if isinstance(result, dict):
                            result = [result]
                        for t in result:
                            symbol = t.get("currency_pair", "?")
                            price = float(t.get("price", 0))
                            amount = float(t.get("amount", 0))
                            side = t.get("side", "buy").lower()
                            usd_value = price * amount
                            
                            msg_count += 1
                            if msg_count <= 5:
                                logger.info(f"[Gate.io] #{msg_count} {symbol} {side.upper()} ${usd_value:,.2f}")
                            
                            limit = thresholds.get(symbol, 500000)
                            if usd_value >= limit:
                                logger.info(f"🐋 WHALE on Gate.io {symbol}: {side.upper()} ${usd_value:,.2f}")
                                alert_msg = format_exchange_alert(symbol, side, price, amount, usd_value, "Gate.io")
                                send_telegram_alert(alert_msg)
                                
        except websockets.ConnectionClosed:
            logger.warning("Gate.io connection closed. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Gate.io error: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)

# ============================================================
# ENGINE 10: DEXSCREENER POLLER (BRETT, TOSHI on Base)
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
    print("  WHALE WATCHTOWER v4")
    print("  Coinbase | Kraken | Gemini | Binance")
    print("  OKX | Bybit | Bitget | KuCoin | Gate.io")
    print("  + DexScreener (Base chain)")
    print("=" * 50)
    print("Press Ctrl+C to stop.\n")
    
    try:
        async def main():
            await asyncio.gather(
                coinbase_listener(),
                kraken_listener(),
                gemini_listener(),
                binance_listener(),
                okx_listener(),
                bybit_listener(),
                bitget_listener(),
                kucoin_listener(),
                gateio_listener(),
                dex_listener()
            )
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWatchtower stopped.")
