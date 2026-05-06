# Car FPV — Client Machine Setup

This document explains how to build a client app (Flask or plain Python) that connects to the RasCar server to control the car and receive the camera feed.

---

## Server Details

| Item | Value |
|---|---|
| Server IP | `192.168.12.147` |
| Port | `5000` |
| Dashboard URL | `http://192.168.12.147:5000/` |
| Camera stream URL | `http://192.168.12.147:5000/video_feed` |
| Protocol | HTTP + WebSocket (Socket.IO) |

Both machines must be on the **same network**.

---

## Install Dependencies (client machine)

```bash
pip install python-socketio requests flask
```

> **Important:** Always connect with `transports=['polling']` — the server runs on Werkzeug which does not support WebSocket upgrades.
> ```python
> sio.connect(SERVER, transports=['polling'])
> ```

---

## WebSocket Events

All car control goes over a Socket.IO WebSocket connection.

### Events you SEND to the server

| Event | Payload | Description |
|---|---|---|
| `take_control` | _(none)_ | Take exclusive control — force-takes from whoever currently holds it. |
| `release_control` | _(none)_ | Give up control. Car stops automatically. |
| `command` | `{"dir": "<direction>"}` | Send a drive command. Only executes if you hold control. |
| `drop_client` | `{"sid": "<sid>"}` | Disconnect another client by their session ID. |
| `set_speed` | `{"move_speed": 0.0–1.0, "turn_speed": 0.0–1.0}` | Update move and/or turn speed. Broadcast to all clients immediately. |

### Direction values for `command`

| Value | Action |
|---|---|
| `F` | Forward |
| `B` | Backward (reverse) |
| `L` | Left |
| `R` | Right |
| `S` | Stop |

### Events you RECEIVE from the server

| Event | Payload | Description |
|---|---|---|
| `connection_list` | See below | Sent to all clients whenever someone connects, disconnects, or sends a command. |
| `speed_update` | `{"move_speed": 0.3, "turn_speed": 0.4}` | Sent to all clients when speed changes; also sent to your client on connect. |

#### `connection_list` payload structure

```json
{
  "active_controller": "<sid or null>",
  "connections": [
    {
      "sid": "abc123",
      "ip": "192.168.12.50",
      "connected_at": "14:32:01",
      "last_cmd": "F",
      "is_controller": true
    }
  ]
}
```

---

## Keyboard Client (ready to use)

`client.py` in this repo is a ready-to-run keyboard client:

```bash
pip install python-socketio
python client.py
```

Controls: `↑ ↓ ← →` to drive, `S` to stop, `T` to take control, `Q` to quit.

---

## Minimal Python Client

The smallest working snippet — paste this into another Claude session to build on:

```python
import socketio
import time

SERVER = 'http://192.168.12.147:5000'

sio = socketio.Client()

@sio.on('connect')
def on_connect():
    print('Connected:', sio.sid)
    sio.emit('take_control')

@sio.on('connection_list')
def on_list(data):
    am_controller = data['active_controller'] == sio.sid
    print(f"Controller: {'ME' if am_controller else data['active_controller']} | Clients: {len(data['connections'])}")

@sio.on('speed_update')
def on_speed(data):
    print(f"Speed — move: {data['move_speed']}  turn: {data['turn_speed']}")

sio.connect(SERVER, transports=['polling'])
time.sleep(1)

sio.emit('set_speed', {'move_speed': 0.5, 'turn_speed': 0.6})
sio.emit('command', {'dir': 'F'})   # forward
time.sleep(2)
sio.emit('command', {'dir': 'S'})   # stop
sio.emit('release_control')
sio.disconnect()
```

---

## Flask Client App (with proxied camera feed)

A full Flask app that shows the camera and exposes control routes:

```python
# client_app.py

import socketio
import requests
from flask import Flask, Response, jsonify, request

SERVER = 'http://192.168.12.147:5000'

app = Flask(__name__)
sio = socketio.Client()
connection_data = {}

# ── Socket.IO ──────────────────────────────────────────────────────────────────

@sio.on('connect')
def on_connect():
    print('Connected to car server')

@sio.on('disconnect')
def on_disconnect():
    print('Disconnected from car server')

@sio.on('connection_list')
def on_list(data):
    global connection_data
    connection_data = data

sio.connect(SERVER, transports=['polling'])

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/camera')
def camera():
    """Proxy the MJPEG camera stream from the car server."""
    stream = requests.get(f'{SERVER}/video_feed', stream=True)
    return Response(
        stream.iter_content(chunk_size=1024),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/take_control', methods=['POST'])
def take_control():
    sio.emit('take_control')
    return jsonify({'status': 'requested'})

@app.route('/release_control', methods=['POST'])
def release_control():
    sio.emit('release_control')
    return jsonify({'status': 'released'})

@app.route('/command', methods=['POST'])
def command():
    """
    Send a drive command.
    Body: {"dir": "F"} — values: F, B, L, R, S
    """
    data = request.get_json()
    direction = data.get('dir', 'S')
    sio.emit('command', {'dir': direction})
    return jsonify({'status': 'sent', 'dir': direction})

@app.route('/drop/<sid>', methods=['POST'])
def drop(sid):
    sio.emit('drop_client', {'sid': sid})
    return jsonify({'status': 'dropped', 'sid': sid})

@app.route('/speed', methods=['POST'])
def set_speed():
    """
    Update move and/or turn speed.
    Body: {"move_speed": 0.5, "turn_speed": 0.6}
    Values are clamped to 0.0 – 1.0 on the server.
    """
    data = request.get_json()
    sio.emit('set_speed', data)
    return jsonify({'status': 'sent', **data})

@app.route('/connections')
def connections():
    """Return live connection list from the car server."""
    return jsonify(connection_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6000)
```

Run it:
```bash
python client_app.py
```

### Client app endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/camera` | Proxied MJPEG stream |
| POST | `/take_control` | Take control of the car |
| POST | `/release_control` | Release control |
| POST | `/command` | Send drive command — body: `{"dir": "F"}` |
| POST | `/drop/<sid>` | Drop a connection by SID |
| POST | `/speed` | Set speeds — body: `{"move_speed": 0.5, "turn_speed": 0.6}` |
| GET | `/connections` | Current connection list |

---

## Control Flow

### Taking control (force takeover — always granted)
```
Client B                    Server
    |--- take_control --------> |
    |<-- connection_list -------| (you are now controller, previous holder loses it)
```

### Driving
```
Client B (controller)       Server
    |--- command {dir:'F'} ---> |
    |                car moves--|-> Robo.forward()
    |<-- connection_list -------| (last_cmd: F)
    |--- release_control -----> |
    |                car stops--|-> Robo.stop()
```

---

## Notes

- `take_control` is a **force takeover** — it always succeeds, kicking whoever currently holds control. The car stops momentarily on transfer.
- The car **stops automatically** if the controlling client disconnects.
- The camera stream at `/video_feed` supports **multiple simultaneous viewers** — no need to take control to watch the feed.
- `S` (stop) can be sent any time without holding control (the server will ignore it if you're not the controller, but it's safe to call).
