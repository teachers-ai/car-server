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
pip install flask python-socketio requests
```

---

## WebSocket Events

All car control goes over a Socket.IO WebSocket connection.

### Events you SEND to the server

| Event | Payload | Description |
|---|---|---|
| `take_control` | _(none)_ | Request exclusive control of the car. Only works if no one else holds control. |
| `release_control` | _(none)_ | Give up control. Car stops automatically. |
| `command` | `{"dir": "<direction>"}` | Send a drive command. Only executes if you hold control. |
| `drop_client` | `{"sid": "<sid>"}` | Disconnect another client by their session ID. |
| `set_speed` | `{"move_speed": 0.0–1.0, "turn_speed": 0.0–1.0}` | Update move and/or turn speed. Broadcast to all clients immediately. |
| `approve_control` | _(none)_ | Approve the pending control request. Only works if you hold control. |
| `deny_control` | _(none)_ | Deny the pending control request. Only works if you hold control. |

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
| `control_request` | `{"requester_sid": "...", "requester_ip": "..."}` | Sent to the current controller when someone requests control. Respond with `approve_control` or `deny_control`. |
| `control_pending` | _(empty)_ | Sent to the requester — your request is waiting for approval. |
| `control_response` | `{"approved": true\|false}` | Sent to the requester with the outcome of their request. |

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

## Minimal Python Client

A bare-minimum script to take control and drive the car:

```python
import socketio
import time

SERVER = 'http://192.168.12.147:5000'

sio = socketio.Client()

@sio.on('connect')
def on_connect():
    print('Connected, taking control...')
    sio.emit('take_control')

@sio.on('connection_list')
def on_list(data):
    ctrl = data['active_controller']
    print(f'Controller: {ctrl}')
    print(f'Total clients: {len(data["connections"])}')

@sio.on('control_request')
def on_control_request(data):
    print(f'{data["requester_ip"]} wants control — approving...')
    sio.emit('approve_control')   # or sio.emit('deny_control')

@sio.on('control_pending')
def on_pending():
    print('Waiting for controller to approve...')

@sio.on('control_response')
def on_response(data):
    if data['approved']:
        print('Control granted!')
    else:
        print('Request denied.')

sio.connect(SERVER)

time.sleep(1)
sio.emit('set_speed', {'move_speed': 0.5, 'turn_speed': 0.6})  # adjust speeds
sio.emit('command', {'dir': 'F'})   # go forward
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

sio.connect(SERVER)

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

### No one holds control
```
Client B                    Server
    |--- take_control --------> |
    |<-- connection_list -------| (you are now controller)
```

### Someone already holds control (approval flow)
```
Client B                    Server                    Client A (controller)
    |--- take_control --------> |                            |
    |<-- control_pending -------| (waiting...)               |
    |                           |--- control_request ------> |
    |                           |                            | (shows approve/deny)
    |                           |<-- approve_control --------|
    |<-- control_response ------| {approved: true}           |
    |<-- connection_list -------| (B is now controller)  --->|

    (if denied)
    |<-- control_response ------| {approved: false}
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

- Only **one client** can hold control at a time. If another client already has control, `take_control` is silently ignored — check `active_controller` in `connection_list` to confirm.
- The car **stops automatically** if the controlling client disconnects.
- The camera stream at `/video_feed` supports **multiple simultaneous viewers** — no need to take control to watch the feed.
- `S` (stop) can be sent any time without holding control (the server will ignore it if you're not the controller, but it's safe to call).
