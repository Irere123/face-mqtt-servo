# backend/ws_relay.py
"""
WebSocket Relay Service — VPS Backend

Subscribes to MQTT topic  vision/{TEAM_ID}/movement
and pushes every message to all connected WebSocket clients on port 9002.

Architecture rule:
    ✅ MQTT subscriber + WebSocket server (relay only)
    ❌ No business logic — pure relay

Usage (on VPS):
    python3 ws_relay.py
"""

import asyncio
import json
import threading

import paho.mqtt.client as mqtt
import websockets

# ─── Configuration ──────────────────────────────────────────────────
MQTT_BROKER   = "127.0.0.1"          # localhost — Mosquitto runs on this PC
MQTT_PORT     = 1883
TEAM_ID       = "dragonfly"
MQTT_TOPIC    = f"vision/{TEAM_ID}/movement"

WS_HOST       = "0.0.0.0"            # listen on all interfaces
WS_PORT       = 9002

# ─── State ──────────────────────────────────────────────────────────
connected_clients = set()
latest_message = None                  # cache last message for new clients


# ─── WebSocket Server ──────────────────────────────────────────────

async def ws_handler(websocket, path=None):
    """Handle a new WebSocket client connection."""
    connected_clients.add(websocket)
    client_ip = websocket.remote_address[0] if websocket.remote_address else "?"
    print(f"[WS] Client connected: {client_ip}  (total: {len(connected_clients)})")

    # Send cached latest message so new clients see current state immediately
    if latest_message is not None:
        try:
            await websocket.send(latest_message)
        except Exception:
            pass

    try:
        # Keep connection alive — we only push, never expect input
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"[WS] Client disconnected: {client_ip}  (total: {len(connected_clients)})")


async def broadcast(message: str):
    """Send a message to all connected WebSocket clients."""
    if not connected_clients:
        return
    # Send to all clients concurrently; remove any that fail
    tasks = []
    for ws in connected_clients.copy():
        tasks.append(asyncio.ensure_future(_safe_send(ws, message)))
    await asyncio.gather(*tasks)


async def _safe_send(ws, message: str):
    try:
        await ws.send(message)
    except Exception:
        connected_clients.discard(ws)


# ─── MQTT → WebSocket Bridge ──────────────────────────────────────

loop = None  # will be set to the asyncio event loop


def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    if rc == 0 or rc == mqtt.CONNACK_ACCEPTED:
        client.subscribe(MQTT_TOPIC)
        print(f"[MQTT] Connected and subscribed to: {MQTT_TOPIC}")
    else:
        print(f"[MQTT] Connection failed (rc={rc})")


def on_mqtt_message(client, userdata, msg):
    """Called by paho-mqtt when a message arrives — relay to WebSocket."""
    global latest_message
    payload = msg.payload.decode("utf-8", errors="replace")
    latest_message = payload

    # Schedule broadcast on the asyncio loop (thread-safe)
    if loop is not None:
        asyncio.run_coroutine_threadsafe(broadcast(payload), loop)


def mqtt_thread():
    """Run MQTT client in a background thread."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"ws_relay_{TEAM_ID}",
    )
    client.on_connect = on_mqtt_connect
    client.on_message = on_mqtt_message
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_forever()


# ─── Main ──────────────────────────────────────────────────────────

async def main():
    global loop
    loop = asyncio.get_event_loop()

    # Start MQTT in background thread
    t = threading.Thread(target=mqtt_thread, daemon=True)
    t.start()
    print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT} ...")

    # Start WebSocket server
    print(f"[WS]   Listening on ws://{WS_HOST}:{WS_PORT}")
    print(f"[Relay] Ready — MQTT → WebSocket relay active\n")

    async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    print("=" * 60)
    print("MQTT → WebSocket Relay")
    print(f"Team: {TEAM_ID}")
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}  topic={MQTT_TOPIC}")
    print(f"WS:   0.0.0.0:{WS_PORT}")
    print("=" * 60 + "\n")
    asyncio.run(main())
