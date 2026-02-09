import asyncio
import json
import websockets

async def test_stream(name, url, timeout=10):
    print(f"=== Testing {name} ===")
    print(f"    URL: {url}")
    try:
        async with websockets.connect(url) as ws:
            for i in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(msg)
                print(f"  Raw #{i+1}: {json.dumps(data)[:200]}")
            print(f"  {name}: WORKING\n")
    except asyncio.TimeoutError:
        print(f"  {name}: TIMEOUT (connected but no data)\n")
    except Exception as e:
        print(f"  {name}: FAILED - {e}\n")

async def test_coinbase():
    print("=== Testing Coinbase WebSocket ===")
    url = "wss://ws-feed.exchange.coinbase.com"
    try:
        async with websockets.connect(url) as ws:
            sub = {
                "type": "subscribe",
                "product_ids": ["BTC-USD"],
                "channels": ["matches"]
            }
            await ws.send(json.dumps(sub))
            for i in range(5):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if data.get("type") == "match" or data.get("type") == "last_match":
                    price = float(data['price'])
                    size = float(data['size'])
                    val = price * size
                    side = data['side'].upper()
                    print(f"  Trade #{i+1}: BTC-USD | {side} | Price: ${price:,.2f} | Size: {size} | Value: ${val:,.2f}")
            print("  Coinbase: WORKING\n")
    except asyncio.TimeoutError:
        print("  Coinbase: TIMEOUT\n")
    except Exception as e:
        print(f"  Coinbase: FAILED - {e}\n")

async def main():
    # Test Binance US - single stream format
    await test_stream("Binance US (single)", "wss://stream.binance.us:9443/ws/btcusdt@aggTrade")
    
    # Test Binance US - combined stream format  
    await test_stream("Binance US (combined)", "wss://stream.binance.us:9443/stream?streams=btcusdt@aggTrade")
    
    # Test Coinbase (US-friendly, no restrictions)
    await test_coinbase()

asyncio.run(main())
