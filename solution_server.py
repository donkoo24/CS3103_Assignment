#!/usr/bin/env python3
"""
CS3103 Assignment 4 - LiveRecall naive working baseline.

This starter is intentionally useful but incomplete. It provides the required
CLI and a basic WebSocket broadcaster so that caption_source.py -> server ->
browser/load clients works on day one.

It DOES NOT implement the graded networking mechanisms:
  - revision-state management or deduplication
  - recent-history recovery or late-join recovery
  - bounded per-client application queues
  - slow-client isolation
  - semantic coalescing / backpressure
  - constrained-bandwidth overload handling

Required evaluator command:
    python solution_server.py --port 8765

Teams should replace or substantially extend the implementation while keeping
this command-line interface and the protocol in the assignment specification.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any
from liverecall.protocol import parse, caption_from
from liverecall.state import CaptionState
from liverecall.history import FinalHistory
from liverecall.hub import Hub

import websockets

from liverecall.policy import apply_startup_limits

STATE = CaptionState()
HISTORY = FinalHistory()
HUB = Hub()

active_source_ws = None

async def handle_source(ws, hello: dict[str, Any]) -> None:
    global active_source_ws

    # Safely disconnect any ghost source connection
    if active_source_ws is not None and active_source_ws != ws:
        try:
            await active_source_ws.close(code=1000, reason="Replaced by new source")
        except Exception:
            pass
            
    active_source_ws = ws
    print(f"Source connected: session={hello.get('session')}", flush=True)

    try:
        async for raw in ws:
            msg = parse(raw)
            cap = caption_from(msg) if msg else None
            
            # Drop malformed inputs silently
            if not cap:
                continue
                
            # The Core Pipeline
            if STATE.apply(cap):
                if cap.final:
                    HISTORY.add(cap)
                    if HISTORY.oldest_segment is not None:
                        STATE.prune(HISTORY.oldest_segment)
                HUB.publish(cap)
    finally:
        if active_source_ws == ws:
            active_source_ws = None
        print("Source disconnected", flush=True)


async def handle_client(ws, hello: dict[str, Any]) -> None:
    client_id = hello.get("client_id")
    try:
        last_seg = int(hello.get("last_segment", 0))
        last_rev = int(hello.get("last_revision", 0))
        history_sec = float(hello.get("history_seconds", 30))
    except (TypeError, ValueError, OverflowError):
        await ws.close(code=1008, reason="Invalid CLIENT_HELLO fields")
        return

    # Atomic Handshake: Generate history and register synchronously to prevent client from missing caption
    hist_msg = HISTORY.cached_history(last_seg, last_rev, history_sec)
    session = HUB.register(ws, client_id, first_messages=[hist_msg])
    
    print(f"Client connected: id={client_id}", flush=True)
    
    try:
        # Keep connection alive while the Hub handles outbound writes
        async for _ in ws:
            pass
    finally:
        HUB.unregister(session)
        print(f"Client disconnected: id={client_id}", flush=True)

async def handler(ws) -> None:
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        hello = parse(raw)
        if not isinstance(hello, dict):
            raise ValueError
    except (asyncio.TimeoutError, ValueError, TypeError):
        await ws.close(code=1008, reason="Expected a valid hello message")
        return

    msg_type = hello.get("type")
    if msg_type == "SOURCE_HELLO":
        await handle_source(ws, hello)
    elif msg_type == "CLIENT_HELLO":
        await handle_client(ws, hello)
    else:
        await ws.close(code=1008, reason="Expected SOURCE_HELLO or CLIENT_HELLO")


async def main_async(port: int) -> None:
    async with websockets.serve(
        handler,
        "0.0.0.0",
        port,
        **apply_startup_limits(),
        max_size=2**20,
        ping_interval=20,
        ping_timeout=20,
    ):
        print(f"LiveRecall baseline listening on ws://0.0.0.0:{port}", flush=True)
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
