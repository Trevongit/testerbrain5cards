#!/usr/bin/env python3
import asyncio
import websockets
import json
import sys
import base64
import os

async def take_screenshot(ws_url, output_path):
    """Direct CDP screenshot via WebSocket (Phase 23 Lite)."""
    try:
        # Connect without wait_for wrapping the context manager
        async with websockets.connect(ws_url, open_timeout=5.0) as ws:
            await ws.send(json.dumps({
                "id": 1,
                "method": "Page.captureScreenshot",
                "params": {"format": "png"}
            }))
            
            # Wait for response with a timeout
            while True:
                try:
                    res = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(res)
                    if data.get("id") == 1:
                        if "result" in data and "data" in data["result"]:
                            with open(output_path, "wb") as f:
                                f.write(base64.b64decode(data["result"]["data"]))
                            print(f"SUCCESS:{output_path}")
                            return True
                        else:
                            print(f"ERROR: No data in result: {data}")
                            return False
                except asyncio.TimeoutError:
                    print("ERROR: Timeout waiting for screenshot response")
                    return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: screenshot_helper.py <ws_url> <output_path>")
        sys.exit(1)
    
    success = asyncio.run(take_screenshot(sys.argv[1], sys.argv[2]))
    sys.exit(0 if success else 1)
