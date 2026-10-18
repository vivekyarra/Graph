"""Real MCP stdio client for bounded graph tools; failure stops investigation.

One `python -m maelin.mcp_server` subprocess is started lazily and kept alive
on a background event loop, so every agent tool call is a genuine MCP
`tools/call` round trip without paying process start-up per call. If the
session dies it is restarted once; a second failure propagates.
"""
import asyncio
import json
import os
import sys
import threading


class _Session:
    def __init__(self):
        self._loop = None
        self._session = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._error = None
        self._stop = None

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable, args=["-m", "maelin.mcp_server"],
                                       env=dict(os.environ))
        self._stop = asyncio.Event()
        try:
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._stop.wait()
        except Exception as exc:  # surfaced to the caller waiting on _ready
            self._error = exc
        finally:
            self._session = None
            self._ready.set()

    def ensure(self):
        with self._lock:
            if self._session is not None:
                return
            self._ready.clear()
            self._error = None
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._run, name="maelin-mcp", daemon=True).start()
        if not self._ready.wait(timeout=30) or self._session is None:
            raise RuntimeError(f"MCP graph server failed to start: {self._error!r}")

    def reset(self):
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._session = None

    def call(self, name, arguments, timeout=60):
        self.ensure()
        future = asyncio.run_coroutine_threadsafe(self._session.call_tool(name, arguments), self._loop)
        return future.result(timeout=timeout)


_SESSION = _Session()


def _decode(name, reply):
    if reply.isError:
        raise RuntimeError("MCP graph tool failed: " + name)
    data = getattr(reply, "structuredContent", None)
    if data is None:
        texts = [block.text for block in reply.content if hasattr(block, "text")]
        if len(texts) != 1:
            raise RuntimeError("MCP tool returned an unexpected result")
        data = json.loads(texts[0])
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    if not isinstance(data, dict):
        raise RuntimeError("MCP tool must return a structured object")
    return data


def call_tool(name, arguments):
    try:
        reply = _SESSION.call(name, arguments)
    except RuntimeError:
        raise
    except Exception:
        # Transport hiccup (e.g. server process exited): restart once.
        _SESSION.reset()
        reply = _SESSION.call(name, arguments)
    return _decode(name, reply)
