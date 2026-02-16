import asyncio
import json
import websockets
import aiohttp

async def test_coinbase():
    print("=== Testing Coinbase ===")
    url = "wss://ws-feed.exchange.coinbase.com"
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["matches"]}))
            count = 0
            for _ in range(10):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if data.get("type") in ("match", "last_match"):
                    p, s = float(data['price']), float(data['size'])
                    count += 1
                    print(f"  #{count} BTC-USD | {data['side'].upper()} | ${p*s:,.2f}")
                    if count >= 2: break
            print("  Coinbase: WORKING\n")
    except Exception as e:
        print(f"  Coinbase: FAILED - {e}\n")

async def test_kraken():
    print("=== Testing Kraken ===")
    url = "wss://ws.kraken.com/v2"
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "trade", "symbol": ["BTC/USD"]}}))
            count = 0
            for _ in range(20):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if data.get("channel") == "trade" and "data" in data:
                    for t in data["data"]:
                        p, q = float(t["price"]), float(t["qty"])
                        count += 1
                        print(f"  #{count} BTC/USD | {t['side'].upper()} | ${p*q:,.2f}")
                        if count >= 2: break
                if count >= 2: break
            print("  Kraken: WORKING\n")
    except Exception as e:
        print(f"  Kraken: FAILED - {e}\n")

async def test_gemini():
    print("=== Testing Gemini ===")
    url = "wss://api.gemini.com/v1/marketdata/btcusd?trades=true&bids=false&offers=false"
    try:
        async with websockets.connect(url) as ws:
            count = 0
            for _ in range(10):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                for ev in data.get("events", []):
                    if ev.get("type") == "trade":
                        p, a = float(ev["price"]), float(ev["amount"])
                        side = "SELL" if ev.get("makerSide") == "bid" else "BUY"
                        count += 1
                        print(f"  #{count} BTCUSD | {side} | ${p*a:,.2f}")
                        if count >= 2: break
                if count >= 2: break
            print("  Gemini: WORKING\n")
    except Exception as e:
        print(f"  Gemini: FAILED - {e}\n")

async def test_binance():
    print("=== Testing Binance (Global) ===")
    url = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    try:
        async with websockets.connect(url) as ws:
            count = 0
            for _ in range(5):
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                if data.get("e") == "aggTrade":
                    p, q = float(data["p"]), float(data["q"])
                    side = "SELL" if data["m"] else "BUY"
                    count += 1
                    print(f"  #{count} BTCUSDT | {side} | ${p*q:,.2f}")
                    if count >= 2: break
            print("  Binance: WORKING\n")
    except Exception as e:
        print(f"  Binance: FAILED - {e}\n")

async def test_okx():
    print("=== Testing OKX ===")
    url = "wss://ws.okx.com:8443/ws/v5/public"
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "trades", "instId": "BTC-USDT"}]}))
            count = 0
            for _ in range(15):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if "data" in data and data.get("arg", {}).get("channel") == "trades":
                    for t in data["data"]:
                        p, s = float(t["px"]), float(t["sz"])
                        side = t["side"].upper()
                        count += 1
                        print(f"  #{count} BTC-USDT | {side} | ${p*s:,.2f}")
                        if count >= 2: break
                if count >= 2: break
            print("  OKX: WORKING\n")
    except Exception as e:
        print(f"  OKX: FAILED - {e}\n")

async def test_bybit():
    print("=== Testing Bybit ===")
    url = "wss://stream.bybit.com/v5/public/spot"
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": ["publicTrade.BTCUSDT"]}))
            count = 0
            for _ in range(15):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if data.get("topic") == "publicTrade.BTCUSDT" and "data" in data:
                    for t in data["data"]:
                        p, s = float(t["p"]), float(t["v"])
                        side = t["S"].upper() if "S" in t else "?"
                        # Bybit: S = "Buy" or "Sell"
                        count += 1
                        print(f"  #{count} BTCUSDT | {side} | ${p*s:,.2f}")
                        if count >= 2: break
                if count >= 2: break
            print("  Bybit: WORKING\n")
    except Exception as e:
        print(f"  Bybit: FAILED - {e}\n")

async def test_bitget():
    print("=== Testing Bitget ===")
    url = "wss://ws.bitget.com/v2/ws/public"
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [{"instType": "SPOT", "channel": "trade", "instId": "BTCUSDT"}]}))
            count = 0
            for _ in range(15):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if "data" in data and data.get("action") == "snapshot" or "data" in data:
                    for t in data.get("data", []):
                        if "price" in t or "px" in t:
                            p = float(t.get("price", t.get("px", 0)))
                            s = float(t.get("size", t.get("sz", 0)))
                            side = t.get("side", "?").upper()
                            count += 1
                            print(f"  #{count} BTCUSDT | {side} | ${p*s:,.2f}")
                            if count >= 2: break
                if count >= 2: break
            print("  Bitget: WORKING\n")
    except Exception as e:
        print(f"  Bitget: FAILED - {e}\n")

async def test_kucoin():
    print("=== Testing KuCoin ===")
    # KuCoin requires getting a WS token first via REST
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.kucoin.com/api/v1/bullet-public") as resp:
                data = await resp.json()
                token = data["data"]["token"]
                endpoint = data["data"]["instanceServers"][0]["endpoint"]
                ws_url = f"{endpoint}?token={token}"
        
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            sub = {"id": 1, "type": "subscribe", "topic": "/market/match:BTC-USDT", "privateChannel": False, "response": True}
            await ws.send(json.dumps(sub))
            count = 0
            for _ in range(20):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if data.get("topic") == "/market/match:BTC-USDT" and "data" in data:
                    t = data["data"]
                    p, s = float(t["price"]), float(t["size"])
                    side = t.get("side", "?").upper() if "side" in t else "?"
                    count += 1
                    print(f"  #{count} BTC-USDT | {side} | ${p*s:,.2f}")
                    if count >= 2: break
            print("  KuCoin: WORKING\n")
    except Exception as e:
        print(f"  KuCoin: FAILED - {e}\n")

async def test_gateio():
    print("=== Testing Gate.io ===")
    url = "wss://api.gateio.ws/ws/v4/"
    try:
        async with websockets.connect(url) as ws:
            import time
            await ws.send(json.dumps({"time": int(time.time()), "channel": "spot.trades", "event": "subscribe", "payload": ["BTC_USDT"]}))
            count = 0
            for _ in range(15):
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if data.get("channel") == "spot.trades" and data.get("event") == "update":
                    result = data.get("result", {})
                    if isinstance(result, dict):
                        result = [result]
                    for t in result:
                        p = float(t.get("price", 0))
                        a = float(t.get("amount", 0))
                        side = t.get("side", "?").upper()
                        count += 1
                        print(f"  #{count} BTC_USDT | {side} | ${p*a:,.2f}")
                        if count >= 2: break
                if count >= 2: break
            print("  Gate.io: WORKING\n")
    except Exception as e:
        print(f"  Gate.io: FAILED - {e}\n")

async def main():
    await test_coinbase()
    await test_kraken()
    await test_gemini()
    await test_binance()
    await test_okx()
    await test_bybit()
    await test_bitget()
    await test_kucoin()
    await test_gateio()

asyncio.run(main())
