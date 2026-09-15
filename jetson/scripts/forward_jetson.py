import asyncio

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8000
REMOTE_HOST = "100.104.251.40"
REMOTE_PORT = 8000

async def handle_client(local_reader, local_writer):
    try:
        remote_reader, remote_writer = await asyncio.open_connection(REMOTE_HOST, REMOTE_PORT)
    except Exception:
        local_writer.close()
        return

    async def forward(reader, writer):
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    await asyncio.gather(
        forward(local_reader, remote_writer),
        forward(remote_reader, local_writer),
        return_exceptions=True
    )

async def main():
    server = await asyncio.start_server(handle_client, LOCAL_HOST, LOCAL_PORT)
    print(f"Proxying {LOCAL_HOST}:{LOCAL_PORT} -> {REMOTE_HOST}:{REMOTE_PORT}", flush=True)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
