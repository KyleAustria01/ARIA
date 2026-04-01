"""Quick diagnostic: connect to the Render WS endpoint, send start, listen for audio."""
import asyncio
import json
import websockets

WS_URL = "wss://aria-backend-7hbb.onrender.com/ws/interview/e1f004f1b19442aa80720fdd50c1d74a"

async def test():
    print(f"Connecting to {WS_URL}...")
    try:
        async with websockets.connect(WS_URL, open_timeout=30) as ws:
            print("Connected! Sending start...")
            await ws.send(json.dumps({"type": "start"}))
            
            for i in range(20):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15)
                    if isinstance(msg, bytes):
                        print(f"[{i}] BINARY: {len(msg)} bytes, first 3: {list(msg[:3])}")
                    else:
                        data = json.loads(msg)
                        print(f"[{i}] JSON: type={data.get('type')}, text={str(data.get('text',''))[:80]}")
                        if data.get("type") == "error":
                            print(f"    ERROR: {data.get('message')}")
                            break
                        if data.get("type") == "verdict":
                            break
                except asyncio.TimeoutError:
                    print(f"[{i}] Timeout waiting for message")
                    break
    except Exception as e:
        print(f"Connection failed: {type(e).__name__}: {e}")

asyncio.run(test())
