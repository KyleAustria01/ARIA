import asyncio
import edge_tts

async def test():
    communicate = edge_tts.Communicate("Hello, this is a test.", "en-US-JennyNeural")
    buf = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf += chunk["data"]
    print(f"Got {len(buf)} bytes of audio")
    # Check first bytes
    if buf:
        header = buf[:3]
        print(f"First 3 bytes: {list(header)}")
        if header[0] == 0xFF or (header[0] == 0x49 and header[1] == 0x44):
            print("Format: MP3")
        else:
            print(f"Format: unknown (header: {header.hex()})")

asyncio.run(test())
